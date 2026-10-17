# Dashboard badge and active-alert dialog (issue #4 / work package C)

> Historical work-package report. Current installation: [INSTALLATION.md](INSTALLATION.md); independent review and current evidence: [REVIEW.md](REVIEW.md), [REVIEW_TEST_RESULTS.md](REVIEW_TEST_RESULTS.md).

Based on PR #7, `feat/status-badge-rule-management`, commit
`7fc0a199f3dfeb34d589dde69d27295d96c06672`. SPEC.md and ARCHITECTURE.md are
unchanged. This is development work, not a release or completion of work package D.

## Native component assessment

Source review of HA's [entity badge](https://github.com/home-assistant/frontend/blob/dev/src/panels/lovelace/badges/hui-entity-badge.ts),
[badge host](https://github.com/home-assistant/frontend/blob/dev/src/panels/lovelace/badges/hui-badge.ts)
and [badge factory](https://github.com/home-assistant/frontend/blob/dev/src/panels/lovelace/create-element/create-badge-element.ts)
on 2026-10-17 preceded implementation. Native entity badges can show an aggregate
sensor and have dashboard visibility conditions. Several conditional badges could
represent severity. Their normal actions / entity more-info dialog do not consume
this integration's authenticated, permission-filtered paginated alert API or offer
per-occurrence global acknowledge/revoke controls for every active alert. Putting
records into aggregate entity attributes would conflict with the architecture.
Therefore native badges alone do not satisfy the detail workflow. This conclusion
is a source-level capability assessment, not a claim of a manual native-dashboard
prototype on a physical HA installation.

The companion uses HA's `customBadges` registry and standard `setConfig`, `hass`,
`getConfigElement`, `getStubConfig` contracts. `connectedWhileHidden` and
`badge-visibility-changed` allow the native `hui-badge` wrapper to disappear
without disconnecting its update subscription. A native HTML modal is mounted
outside that wrapper so acknowledging the final unread alert can hide the entire
badge while keeping the dialog usable. The modal is removed on close/navigation.

## Install and configure entirely through the GUI

1. Copy the complete `custom_components/lightweight_status_badge` directory,
   including `www`, into a development HA installation and restart HA. Add the
   integration and configure rules as described in [GUI.md](GUI.md).
2. Enable Advanced mode in your HA profile if the Resources menu is hidden.
   In **Settings → Dashboards → ⋮ → Resources**, add this URL with resource type
   **JavaScript module**:
   `/lightweight_status_badge/frontend/lightweight-status-badge.js`.
   Reload the browser. The integration serves this bundled file; no CDN, separate
   JavaScript installation, YAML or manual `.storage` edits are needed. The module
   is public static code; it contains no alert data or credentials. Alert data
   remains behind the existing authenticated WebSocket API.
3. Edit a dashboard view, choose **Add badge → Lightweight Status Badge** and
   optionally edit its display name in the visual editor. Save. The badge is
   in the native badge area, hidden at zero unacknowledged active alerts. Otherwise
   it shows an icon, unread count and highest unread priority, with theme-based
   info/warning/error icon colors. Acknowledged critical alerts do not raise the
   priority of lower-priority unread alerts. At load/error/disconnection it shows
   status instead of falsely presenting a verified zero.
4. **Also add the `Lightweight Status Alerts` card** to the dashboard using the
   normal visual card picker. This is the deliberate permanent entry point when
   the badge is hidden. Its count includes all active alerts. It opens the same
   dialog, including acknowledged alerts and an empty-state message. Add this
   card to every dashboard where that independent access is wanted.
5. Tap either entry to inspect all currently active alerts. Each includes title,
   severity, understandable description, optional recommendation, original state
   and source entity ID. Quittieren / Acknowledge is global; Rücknehmen / Undo
   revokes it globally. Read-only users see disabled actions. Actions never
   control the monitored entity. Labels and built-in descriptions follow the
   browser's HA locale (German or English, with English fallback); user-written
   titles and explanations remain as configured.

No HA Lovelace resource registry is rewritten automatically. GUI resource setup
and the independent card are explicit installation steps. This does not claim
HACS packaging/discovery validation. After replacing the integration files, reload
the browser to load the new module.

## Data, performance and failure behavior

One in-memory store/subscription per HA connection and locale is shared by every
badge/card on that page. Normal `hass` state-object updates do not request data or
re-render. Invalidation fetches only the backend's bounded pages (100 per page,
maximum 1000 configured rules); simultaneous events coalesce behind an in-flight
read. A complete consistent snapshot is published atomically. Changes of revision
or total between pages restart at offset zero, with at most three retries before
showing a recoverable error. An intervening invalidation discards obsolete reads.
Revision numbers may reset on backend reload.

There are no timers, polling, persisted frontend data, alert history, external
runtime dependencies or copies of HA libraries. Only the current snapshot and
in-flight action identifiers are retained. All snapshots are cleared on disconnect
or final detach. Connection `ready` and HA's subscription reconnection mechanism
restore updates. Once registered, the backend now also accepts subscriptions
during an unload window and emits `loaded:false`, then a loaded invalidation on
setup; this prevents losing the subscription when reconnect coincides with reload.
A failed subscription or read offers a manual retry; it does not start a retry loop.

Actions carry both stable rule ID and occurrence. Duplicate actions on the same
record are blocked while pending; there is no optimistic acknowledgement. The
backend remains authoritative across clients. Permission denials and stale or
resolved occurrences show localized errors and refresh current data. A timed-out
or failed action is never replayed automatically. `can_acknowledge` is an additive
permission hint in detail responses, not an authorization substitute.

Backend-escaped display strings are decoded once using a fixed character map,
then assigned only through `textContent`. No `innerHTML`, HTML parser, templates,
eval, unsafe URLs or sensor-supplied CSS is used. Raw entity IDs are also text.
The dialog uses native modal semantics and Escape, explicit Tab/Shift-Tab
containment, named controls, focus restoration when the origin is still visible,
44px action targets, a scrollable body and long-word wrapping. It inherits HA
color/background/border/shadow variables and copies inherited theme variables
when opening its portal. Transparent backgrounds are retained; a theme-supplied
`--ha-card-backdrop-filter` / `--backdrop-filter` is respected.

## Reproduce validation

Python dependencies and environment: [BACKEND.md](BACKEND.md).
Frontend requires Node 24; Playwright is a development-only locked dependency.

```sh
npm ci
npm test
npm run check
npm run build
npx playwright install --with-deps chromium
npm run test:browser
ruff check .
ruff format --check .
python -m pytest --timeout=30 --cov=custom_components.lightweight_status_badge --cov-report=term-missing
git diff --check
```

`npm run build` checks module syntax and copies the dependency-free source into
the integration's `www` directory. `npm run check` fails if that checked-in artifact
is stale; no bundler is necessary. Both commands run in CI along with Python,
store and browser tests. `CHROMIUM_PATH` optionally selects an installed browser.

### Actual results, 2026-10-17

- **170 Python/HA tests passed in 14.46s**, **97%** total statement coverage
  (**92%** API, **95%** entry lifecycle).
- **17 frontend store/logic tests passed**, including lifecycle, error recovery,
  permission hints, stale actions, paginated revisions, burst invalidations,
  disconnect during reads and asynchronous unsubscribe failure.
- **9 Chromium UI tests passed in 10.64s**: GUI registration/editor events,
  safe text rendering, global acknowledge/revoke and zero-layout disappearance,
  secondary access, no reads/DOM churn for 100 ordinary hass updates, disconnect/
  ready, cleanup, read-only actions, empty/reappearing badge and 105-record
  pagination at 360×640, 768×1024 and 1440×900, long text, transparent/frosted
  theme variables, modal keyboard behavior and focus.
- `npm ci`, build, artifact freshness check, Ruff lint/format and
  `git diff --check` passed. The deployed module is **21,130 bytes**
  (**6,129 bytes with gzip**), with **zero runtime dependencies**.
- Environment: Linux x86_64, HA **2026.10.2**, Python **3.14.8**, Node **24.19.0**,
  npm **11.9.0**, Playwright **1.62.1**, system Chromium **154.0.8037.57**.
  GitHub Actions is configured to install Playwright's matched Chromium build;
  its result is separate from these local results.

Earlier failures were corrected before these results: the new HTTP dependency required initializing
HTTP before a storage-error test patched HA Store globally; browser tests exposed
and verified a fix for Tab escaping at the last dialog action. The first
sandboxed run lacked local socket permissions; the completed HTTP/WS/browser runs
used the environment's approved process and network access.

Limits: browser tests run the real built custom elements against a deterministic
HA connection fixture and a source-based badge-host visibility fixture. Python
tests use real HA 2026.10.2 HTTP, authenticated WebSocket clients and permissions.
These layers test the frontend and backend contracts separately; they are not a
full automated Lovelace session on a running physical installation. Other browsers,
physical touch devices, real third-party theme packages, screen-reader usability,
HACS validation and Raspberry Pi CPU/RAM measurements remain unverified. Viewport
and theme-variable tests do not establish those wider claims.
