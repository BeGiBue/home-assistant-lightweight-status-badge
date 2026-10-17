# Lightweight Status Badge

Event-driven Home Assistant monitoring with graphical rule management, German and
English explanations, a dashboard badge and global acknowledgements. No polling,
alert history, runtime JavaScript dependencies or recurring YAML configuration.

**Development / release candidate preparation.** No release has been created.
Requires Home Assistant **2026.10.2 or newer** (tested: 2026.10.2). Physical Raspberry
Pi 4 measurements and a complete real-Lovelace browser acceptance run remain open.

## Installation / Einrichtung

1. In HACS, open **Custom repositories**, add
   `https://github.com/BeGiBue/home-assistant-lightweight-status-badge`, category
   **Integration**, and download **Lightweight Status Badge**. Until this work is
   merged into the repository's distribution branch, the default HACS download
   does **not** contain it. A maintainer/tester must select a revision containing
   this PR; this is not a published release or a HACS default-list submission.
2. Restart Home Assistant. Add **Lightweight Status Badge** in **Settings →
   Devices & services → Add integration**. Choose **Configure** to add rules using
   the entity and template pickers. Review severity and availability policies.
3. In normal GUI/storage resource mode the integration automatically registers
   its bundled JavaScript module and updates its content version on HA reload or
   restart. Reload the browser after installation/update.
4. Edit the dashboard view: **Add badge → Lightweight Status Badge**. Also add
   the **Lightweight Status Alerts** card using the visual card picker. This card
   keeps acknowledged active alerts reachable when the badge disappears.

Deutsch: In HACS als benutzerdefiniertes Repository der Kategorie **Integration**
aufnehmen und herunterladen, HA neu starten, unter **Einstellungen → Geräte &
Dienste** hinzufügen und über **Konfigurieren** Regeln anlegen. Die Ressource wird
im GUI-Modus automatisch registriert. Browser neu laden; Badge **und** die Karte
**Lightweight Status Alerts** im Dashboard hinzufügen. Keine manuellen Dateikopien
oder YAML-Einträge im normalen GUI-Betrieb. Vor Integration dieses PRs enthält der
Standarddownload diese Änderungen noch nicht.

**YAML resource mode / Sonderfall:** HA treats YAML resources as configuration,
not a writable registry. Add the module URL
`/lightweight_status_badge/frontend/lightweight-status-badge.js` once to your
existing Lovelace YAML resources, type `module`, and reload resources/browser.
If Lovelace was unavailable at setup, use **Settings → Dashboards → ⋮ → Resources**
to add that URL as **JavaScript module** (Advanced mode may be required).
Do not add a second entry when the automatic one already exists.

## Operation, update and removal

Tap the badge/card for all active alerts. Acknowledgement is global and requires
HA read/control permission for the source entity. It never changes that entity.
The badge hides at zero **unacknowledged** alerts; the card remains available.
Missing entities follow the rule's unavailable policy. GoodWe defaults to ignore.

Update through HACS, restart HA and reload each browser. Rules and matching
acknowledgements persist; a hash in the registered module URL prevents stale
module caches. A hard power loss may lose the last second of acknowledgement
changes. Before updating, take a normal HA backup. See [installation details](docs/INSTALLATION.md)
for rollback, removal, version boundaries and troubleshooting.

## Development and evidence

- [Independent review, fixes, risks and release assessment](docs/REVIEW.md)
- [Review validation results and exact test boundaries](docs/REVIEW_TEST_RESULTS.md)
- [GUI rule workflows](docs/GUI.md), [backend/API](docs/BACKEND.md),
  [frontend architecture and original validation](docs/FRONTEND.md)
- [Product specification](SPEC.md), [architecture](ARCHITECTURE.md)

Earlier package-specific reports describe their original commits. The review
report supersedes installation instructions and readiness claims for this branch.
