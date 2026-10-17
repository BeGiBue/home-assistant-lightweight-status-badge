# Backend development (work package A / issue #2)

> Historical work-package report. Current installation: [INSTALLATION.md](INSTALLATION.md); independent review and current evidence: [REVIEW.md](REVIEW.md), [REVIEW_TEST_RESULTS.md](REVIEW_TEST_RESULTS.md).

The Python backend implements the rule engine, event subscriptions, active alerts,
acknowledgements, storage, aggregate entities and authenticated detail/action API
from SPEC.md and ARCHITECTURE.md. Those product documents are unchanged.

This is **not the complete usable badge product**. This branch adds work package
B (the options-flow rule editor and GUI template picker); see [GUI.md](GUI.md).
The dashboard badge/dialog and secondary detail UI remain work package C. HACS
validation, live-device integration testing and Raspberry Pi measurements remain
work package D. The HA setup flow creates the single integration config entry;
its Configure action opens rule management. No release is created by this change.

## Development and validation

Tested with Home Assistant **2026.10.2**, Python **3.14.8**, on Linux x86_64.
Python >=3.14.2 is required by this HA version. From the checkout:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements_test.txt
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m pytest --timeout=30 --cov=custom_components.lightweight_status_badge --cov-report=term-missing
.venv/bin/python -m pytest -q -s tests/test_performance.py
```

CI runs the same lint, format and HA-harness suite. Tests use actual HA state
changes, config entries, sensor platforms, permissions, and authenticated
WebSocket clients. Most storage tests use the HA harness's JSON-roundtripping
in-memory file adapter; `test_storage.py` additionally exercises HA Store against
actual temporary files with atomic writes enabled.

To run in an existing development HA installation, copy or symlink
`custom_components/lightweight_status_badge` into its `custom_components`
directory, restart HA, then add **Lightweight Status Badge** in Devices & services.
Do not install this development branch into a production instance expecting a
dashboard badge. No credentials or network services are needed by this local integration.

## Config-entry contract for the options flow

Rules live in `entry.options["rules"]`, a list validated before backend startup.
The options flow calls `Coordinator.validate_rules` before saving through
`hass.config_entries.async_update_entry`. The registered update listener reloads
the integration without restarting HA. There is no recurring YAML workflow and
users should not edit HA's `.storage` files by hand.

Example rule data for a development fixture or the options flow:

```json
[
  {"id": "dsm_update", "entity_id": "update.dsm", "kind": "update_available"},
  {"id": "ups", "entity_id": "sensor.ups_status", "kind": "ups_status"},
  {"id": "temperature", "entity_id": "sensor.temperature", "kind": "custom",
   "config": {"operator": "gt", "value": 40}, "severity": 3,
   "label": "Temperature", "message": "Temperature is {state}. Check cooling."},
  {"id": "goodwe_code", "entity_id": "sensor.goodwe_fault_code", "kind": "nonzero_code",
   "unknown_policy": "ignore", "unavailable_policy": "ignore"}
]
```

All rules accept `enabled` (default true), `severity` (1/2/3, default 2),
`label`, `message`, `recommendation`, `unknown_policy`, `unavailable_policy`
(`ignore`/`notice`/`warning`/`critical`; default warning), and `attributes`
(an explicit placeholder whitelist). Stable IDs are supplied by the rule editor,
not regenerated on an edit. GoodWe fault-code templates must explicitly prefill
both availability policies to `ignore`, as shown above.

| Kind | Evaluator configuration |
| --- | --- |
| `binary_on` | Matches `on`; choose a suitable fault indicator explicitly |
| `update_available` | Matches `on`; requires an `update.*` entity |
| `disk_health` | Optional `allowlist`; defaults to normal/healthy/good/passed |
| `positive_count` | Optional finite `threshold`, default 0; strictly greater |
| `unifi_state` | disconnected/offline/isolated/failed/adopting_failed |
| `ups_status` | Whitespace tokens OB/LB/FSD/RB; LB/FSD severity 3 |
| `nonzero_code` | Nonzero finite number, or optional `error_strings` list |
| `diagnostic_state` | Required `states` list |
| `grid_fault` | grid fault/grid_fault/grid failure/fault |
| `custom` | Required `operator` and `value` |

Custom operators: `eq`, `ne`, `in`, `not_in`, `contains`, `gt`, `ge`, `lt`,
`le`. String matching is case-insensitive. Numeric thresholds must be finite;
malformed inputs, booleans, NaN and infinity are not numbers. `unknown`,
`unavailable`, and missing entities are handled before ordinary matching.

Messages support only `{state}` and `{attributes.NAME}`; missing, complex,
or non-whitelisted attributes expand to an empty string. No Python, Jinja,
arbitrary attribute lookup or HTML execution is supported. Display text and raw
state are HTML-escaped by the backend; clients should decode/display as text,
never interpolate into HTML. Attribute values are limited to scalar values and
255 characters; templates/titles to 1000 characters; detail pages to 100 records;
there are at most 1000 configured rules and 10 whitelisted attributes per rule.
These bounds prevent unbounded payloads on the HA state machine/API.

## Authenticated API

Use HA's standard `/api/websocket` authentication. Every message needs a unique,
increasing integer `id`, as required by HA.

- `lightweight_status_badge/alerts`: optional `offset` (default 0) and `language`
  (`de`/`en`, default HA installation language with English fallback). Returns
  `revision`, `alerts`, permission-filtered `total`, `next_offset`. Records contain
  `rule_id`, `occurrence`, `entity_id`, `title`, `severity`, `acknowledged`,
  `description`, `recommendation`, escaped `raw_state`, `started`, `message_ids`, and `can_acknowledge` (current control permission;
  the mutation endpoint still rechecks authorization).
  Acknowledged active alerts are included. Cleared alerts are absent.
- `lightweight_status_badge/subscribe`: returns normal HA subscription success,
  then an initial invalidation event and coalesced subsequent invalidations.
  Once the integration has registered its API, subscribing while it is unloaded
  is supported: the initial event is `loaded: false`, and a later setup sends a
  loaded invalidation. This avoids a lost subscription on reconnect during reload.
  Event payload is `{ "loaded": true, "revision": N }` or `{ "loaded": false }`.
  Fetch the desired detail page on invalidation. No polling. Subscriptions survive
  config-entry reloads; unsubscribe with HA's `unsubscribe_events`. Revisions are
  local to one loaded coordinator and may restart after reload; always refetch
  on a loaded invalidation. Paginated consumers should restart at offset 0 if
  the revision changes between pages.
- `lightweight_status_badge/acknowledge`: required `rule_id` and `occurrence`,
  optional `acknowledged` (default true). Set false to revoke globally.
  Requires current HA read **and control** permission for the monitored entity.
  Missing, disabled or stale occurrences are rejected instead of acknowledging
  a later recurrence accidentally.

There is also the `lightweight_status_badge.acknowledge` HA action with the same
three fields. It resolves the caller from `ServiceCall.context.user_id` and uses
the same permission checks. Anonymous/system calls without a user context are
rejected; client-supplied user IDs are not accepted as action data. Read-only
users can inspect permitted details but cannot acknowledge. All users and
dashboards see the same underlying acknowledgement state. Mutation does not
change the monitored entity. Subscription messages carry no alert content;
detail reads are filtered using the current user's source-entity permissions.

The aggregate sensors expose unread count, active count, and highest **unread**
severity (0 when none), plus a binary sensor for any unread alerts. They contain
no alert arrays or dynamic source attributes and do not poll. HA controls access
to these aggregate entities through its own entity permissions.

## Persistence, startup and races

Only rule-ID → condition-fingerprint mappings for acknowledged active alerts are
stored in `.storage/lightweight_status_badge.ENTRY_ID.acknowledgements`.
No alert records, original state values, timestamps, event history or retention
configuration are stored by this integration. `started` and occurrence IDs are
live metadata only and reset on reload/restart.

Condition fingerprints include entity, evaluator type/config, priority and
availability policies. Display-label/message/recommendation changes preserve
acknowledgement; substantive rule changes, disable/removal, resolution, or a
changed fault discriminator invalidate it. UPS discriminator considers only
recognized fault tokens: adding LB invalidates an OB acknowledgement, changing
CHRG/DISCHRG does not. Error-code, diagnostic, drive-health and UniFi fault-state
changes create distinct conditions; numeric count changes inside the same
threshold condition do not.

All alert mutations are synchronous on HA's event loop. Acknowledge/revoke reads
the current occurrence and mutates without an await. Stale frontend requests
cannot acknowledge another occurrence. Storage saves are queued/coalesced in a one-second window measured from the
first change; repeated actions do not extend that window. A callback reads the
latest snapshot at write time; resolving
a fault during the delay removes the pending identity. HA Store serializes in
the event loop and writes atomically in its executor. There is no disk write
on ordinary sensor-state changes. Graceful shutdown stops monitoring before
teardown-generated unavailable states and flushes through HA's final-write
phase; unload flushes before the next coordinator loads.

While HA is starting, restoration candidates survive temporary unknown and
unavailable states. Known states are evaluated as they arrive. At
`homeassistant_started`, every configured source is reevaluated and only matching
acknowledgements survive; missing/remaining-unavailable states follow their
configured policy. A fault cleared while HA was offline cannot retain its old
acknowledgement if the live condition no longer matches. Faults that resolved and
recurred entirely while HA was offline cannot be distinguished without history,
which the specification excludes.

A hard process kill or power loss before the delayed save can lose the latest
second of acknowledgement changes. Normal HA restart/final-write is covered;
this is not an fsync journal or a guarantee across storage failure. HA logs write
errors; corrupt/unreadable acknowledgement structures fail setup/retry instead
of being silently overwritten. Any first-version UI must keep still-active
acknowledged details reachable even when a badge hides itself; backend API access
alone is not the product's required secondary UI.

## Performance results

See [TEST_RESULTS.md](TEST_RESULTS.md) for measured results, methodology and limits.
