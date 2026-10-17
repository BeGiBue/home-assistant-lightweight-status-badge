# Architecture proposal – v0.1

## Modules
```
custom_components/lightweight_status_badge/
  manifest.json
  const.py
  __init__.py              # config entry lifecycle, domain services
  config_flow.py           # GUI setup / options flows with selectors
  coordinator.py           # event subscriptions, rule evaluation, dispatch
  rules.py                 # pure state evaluators and localized message IDs
  sensor.py                # aggregate sensors: unacknowledged count, active count, severity
  binary_sensor.py         # optional aggregate has_unacknowledged_alerts
  storage.py               # acknowledgement persistence and reconciliation
  strings.json
  translations/de.json
  translations/en.json
frontend/
  lightweight-status-badge.js   # only if needed after native UX prototype
tests/
  test_rules.py
  test_acknowledgements.py
  test_config_flow.py
```

These paths describe proposed files and are not yet implemented.

## Core data flow
HA state_changed event → entity-id filtered subscription → evaluate rules tied to that entity → update active alert map → reconcile acknowledgements → publish aggregate sensor values and frontend detail payload → badge reacts to HA event state. No periodic polling.

Use unique stable rule IDs as alert identity, combined with condition discriminator if needed. State transition to clear removes the active alert and acknowledgement. At startup reevaluate all configured rules from current HA states before restoring only matching acknowledgements. Persist acknowledgements on change using an async queued save mechanism; never write to disk for each underlying sensor event.

## UI / frontend integration
Official HA options flow selects HA entities and rule presets. Options flow capabilities should be validated against HA-supported selectors and navigation in targeted HA version. Detailed alert payload should not be forced into an unbounded state attribute: use small aggregate sensors plus a controlled authenticated backend/frontend data channel (e.g. HA websocket API registration) for alert records. A frontend companion badge should use HA dashboard GUI editor and authorized WebSocket calls, subscribe to updates, display a popup, and show nothing when unread=0. Native badge implementation should be tested first: prefer it if it satisfies compact rendering + dynamic popup + reachable acknowledged details, otherwise implement companion badge.

If badge is hidden when everything is acknowledged, provide a separate, discoverable integration detail view (or dedicated dashboard card) to see still-active acknowledged alerts.

## Automatic rule proposals
Added modules (details in docs/AUTODETECT.md): `autodetect.py` (orchestration, local heuristic, `Proposal`/`Detection`), `catalog.py` (loading, validation and matching of the untrusted rule catalog), `catalog.json` (the catalog; also the offline fallback and the file served from the default branch). The options flow inserts the steps `autodetect` / `autodetect_catalog` / `autodetect_heuristic` between source selection and the manual `entities` step. The feature runs only on demand inside the options flow: no subscriptions, no polling, no network access at runtime, and the coordinator, evaluators and storage are unaware of it.

## Risk checks
1. Integration config flow ergonomics with many rules (paging, back action, entity selector, options save semantics).
2. Home Assistant permission model for globally mutating acknowledgement state, and accessible UI behavior.
3. Native badge capability vs custom dashboard badge registration, lifecycle and HACS distribution.
4. Attribute size and event amplification; test with 100 entities and high-frequency updates.
5. Avoid showing unreviewed UPS/SMART/error-code interpretations as definitive causes.
6. Serialization: race when an acknowledged condition resolves during delayed storage flush.

## Proposed work packages
A. Backend pure evaluator + coordinator + persistence + aggregate entities, tests.
B. GUI options flows, translations and end-to-end rule management, tests.
C. Native-badge feasibility prototype, then minimal companion badge and detail dialog if necessary.
D. Integration testing on current HA, HACS validation, independent review and release notes.

No release until all acceptance criteria pass.
