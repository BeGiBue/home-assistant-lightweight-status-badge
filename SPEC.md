# Statuswächter – Product and functional specification (v0.1 draft)

## Purpose
A lightweight Home Assistant custom integration with full graphical configuration and an optional purpose-built dashboard badge. Users select entities in HA, choose predefined or custom rules, and get comprehensible live fault information. No recurring YAML edits.

## Confirmed decisions
- Entity selection, editing and removal in Home Assistant configuration UI.
- Built-in rule templates **and** custom rules; rules individually disableable.
- Severity: 1 notice, 2 warning, 3 critical.
- Event-driven, low-overhead monitoring suitable for Raspberry Pi 4.
- Badge placed in dashboard header: hidden when there are no **unacknowledged** active alerts.
- Tapping opens details with **all currently active** alerts, including acknowledged alerts, with severity, readable cause, original state and source entity.
- Global acknowledgements across all users and dashboards. Acknowledgement does not modify the monitored entity.
- Persist global acknowledgement across HA restart while the underlying condition remains true.
- Closing an alert clears its acknowledgement; a subsequent recurrence creates a new unacknowledged alert.
- No separate alert history, event log, metrics database or retention configuration.
- German and English interface following HA locale.
- Target HACS installation; backend and frontend may be distributed together if compliant.

## Scope / terminology
An **entity rule** has a stable ID, entity ID, enabled flag, label, evaluator configuration, severity, readable message and unknown/unavailable policy.
An **active alert** exists only while its evaluator matches the current entity state. Its acknowledgement flag is a separate persistent state.
The badge count equals the number of active alerts NOT acknowledged, not the total number of active alerts. The highest displayed severity is computed from those unacknowledged alerts. Multiple matching rules for one entity may each yield their own alert.
Rule creation/editing must not create an alert history.
Removing/disabling a rule immediately removes its alert. Changing a rule invalidates its prior acknowledgement if the triggering condition has substantively changed.

## Rule types
- `binary_on`: matches `on` (template must be used only for suitable entities; not every on is a fault).
- `update_available`: for HA update entities, matches `on`.
- `disk_health`: alert unless state is in a configured case-insensitive allowlist (default normal, healthy, good, passed).
- `positive_count`: numeric count greater than 0; threshold configurable.
- `unifi_state`: disconnected, offline, isolated, failed, adopting_failed.
- `ups_status`: parse whitespace-separated status tokens; OB, LB, FSD, RB with severity override for LB/FSD. Preserve raw state and provide readable translations. Do not classify unfamiliar tokens without a rule.
- `nonzero_code`: nonzero numeric error or a configured set of error strings.
- `diagnostic_state`: configured error/warning states.
- `grid_fault`: grid fault, grid_fault, grid failure, fault.
- `custom`: editable equality / inequality, set inclusion, numeric comparison with threshold, or case-insensitive substring match. No unrestricted user-supplied Python execution.
Templates can be customized or saved as a distinct rule. A template selector should prefill appropriate severity and explanation.

## Unknown / unavailable
Each rule specifies `unknown_policy` and `unavailable_policy`: ignore, notice, warning or critical. These conditions produce a specific human-readable alert when configured; they must not be interpreted as numeric or ordinary state transitions. Preserve the original input state. For GoodWe fault-code templates, default to ignore unknown/unavailable consistent with the supplied example; other types can default to warning, but should be reviewable on rule creation. A missing entity ID is treated as unavailable.

## Message content
Each active alert provides:
- A concise title/name, severity and acknowledgement state.
- Full understandable description, such as "Die USV läuft im Batteriebetrieb. Prüfe die Netzversorgung." for OB, not just "OB".
- Original entity state and entity ID; show technical information separately.
- Optional recommendation and optional dynamic placeholders for current entity state and whitelisted attributes; escape displayed HTML.
- Time since current alert began may be displayed as live UI metadata, but is not retained as history.
Unknown fault codes remain recognizable and are not assigned unsupported meaning.

## UI workflows
1. Configure integration in Settings > Devices & services.
2. Open an options menu with list of rules; add via HA entity selector and template picker; configure trigger, priority, title, description and availability handling.
3. Edit, disable, enable, remove existing rules. Use page navigation/back controls where relevant.
4. Add a badge in a dashboard editor (prefer native badge conditional visibility if details are comfortably supported; otherwise custom badge with GUI editor).
5. Badge disappears entirely at zero unacknowledged active alerts. On tap, show a scrollable accessible detail dialog with one acknowledgement action per active unacknowledged alert.
6. Acknowledged active alerts remain visible from the detail UI by a deliberate secondary entry point when badge is hidden (e.g. integration configuration/detail view or dedicated dashboard view).

## Example migration from current manually maintained template
Existing monitored categories: Synology security, DSM updates, drive health/SMART, volume; RPi power and firmware; TouchKio errors/updates; SMLIGHT firmware; UPS status; UniFi device health/updates; GoodWe battery codes, diagnosis, grid state. Import automatically from arbitrary Jinja templates is NOT promised; these should be directly reproducible by adding rules through the GUI. Preserve flexible display names and severity.

## Persistence and security
- Persist rules through HA config entry options or supported storage.
- Persist only active acknowledgement identities; reconcile with live states at start and remove stale entries after state evaluation.
- No separate event/history storage.
- Normal Home Assistant authentication and permission checks for acknowledgement services/actions; do not expose unauthenticated operations.
- Handle malformed values, entity removal, startup unknown/unavailable, reconnect storms and HA stop gracefully.

## Performance acceptance
- Listen to relevant `state_changed` events rather than polling all entities or performing full registry scans on every event.
- Filter by selected entity IDs; evaluate only their associated rules on changes.
- Debounce UI refresh/coalesce dispatch on large state bursts if needed.
- No synchronous disk I/O on every sensor state change; acknowledgement writes should be coalesced and restart-safe.
- Avoid frontend polling, unnecessary DOM rendering and unbounded state attributes.
- Benchmark with ~30 and ~100 selected entities on modest HA hardware; report measured CPU/memory rather than inventing estimates.

## Acceptance criteria for first usable version
- Configure sample update, UPS, unavailable and custom numeric rule via UI only.
- Trigger/resolve each condition and verify counts, priority, descriptions and badge visibility.
- Acknowledge globally; verify across two authenticated clients and after restart; resolution resets acknowledgement.
- With all alerts acknowledged, badge is gone but details remain reachable in the integration.
- Rule add/edit/delete works without restart, and localization works in German/English.
- Basic automated tests cover evaluator and acknowledgement state transitions.
- HACS validation/docs and installation instructions before any public release.

## Explicit exclusions (first version)
No push notifications, automatic issue discovery, historical timeline, charting, automatic repairs or device control.
