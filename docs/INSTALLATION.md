# Installation, updates and technical boundaries / Installation und Aktualisierung

## HACS package

This is a custom **integration**, not a separate HACS dashboard/plugin repository.
HACS installs the single directory `custom_components/lightweight_status_badge`,
including `www/lightweight-status-badge.js`, translations and manifest. No Node,
frontend build, manual file copy or integration YAML is required on the HA host.
The checked-in module is verified against source in CI. `hacs.json` supplies the
name, minimum tested HA version and README rendering; the default integration
layout needs no `content_in_root`, ZIP release or separate JavaScript download.
No release is generated. The repository must expose this code on an installable
revision before users can follow the normal default-branch HACS path.

Follow the four GUI steps in [README](../README.md). Rules are configured under
Devices & services, not Helpers. Use the independent alerts card even when all
alerts are acknowledged. Dashboard placement is deliberately user-configured;
the integration does not modify dashboard layouts.

## Automatic resource registration

On HA 2026.10.2 the Lovelace resource collection has a writable storage API.
Setup uses `ResourceStorageCollection.async_get_info`, `async_items`,
`async_create_item` and `async_update_item`. It registers a module URL under
`/lightweight_status_badge/frontend/` with a content hash, upgrades an existing
unversioned entry, and repeats safely on reload/restart. It does not edit HA's
`.storage` files. An `after_dependencies` relationship orders setup after Lovelace
when present. HTTP is a required dependency. Module code is public static data;
alert content/actions still require HA authentication and source permissions.

This is possible, but these Python collection classes are **HA internal APIs**,
not a stable custom-integration registration contract. Compatibility must be
checked on HA upgrades. Storage-mode tests exercise the actual HA collection.
If the registry write fails, setup fails visibly instead of falsely reporting a
completed installation. Backend setup cleans its subscriptions on that path.
If Lovelace is absent or uses YAML resources, setup logs the module URL and
monitoring remains available; no YAML or other resources are overwritten.

In YAML resource mode add to the existing resources configuration:

```yaml
lovelace:
  resources:
    - url: /lightweight_status_badge/frontend/lightweight-status-badge.js
      type: module
```

Merge into your existing block rather than adding a second `lovelace` key. This
exception requires YAML because HA's YAML resource collection is read-only.
In storage mode the minimal fallback is one GUI resource entry with that URL and
module type. Enable Advanced mode if the Resources menu is hidden. Refresh the
browser and check for duplicate entries or stale cache if the picker is missing.

## Updates, rollback, removal

HACS update → restart HA → reload browsers. The installed module hash updates
without manual URL edits. Matching active acknowledgements and rule IDs survive;
resolved/substantively changed rules lose their old acknowledgement. An existing
page must reload to execute a new module version. Repeated imports do not register
custom elements or picker entries twice. No version bump/release was made here.

Back up HA first. Roll back using HACS's version selection if a previous installed
revision is available, or restore the backup. No storage schema change is included
in this review; downgrade compatibility with arbitrary future versions is not
promised. Never edit `.storage` by hand.

Remove dashboard badge/card instances and the single matching Resources entry,
then remove the integration under Devices & services and remove its files through
HACS. The resource entry is deliberately retained on temporary unload/disable;
it is also not deleted automatically on removal, because it may have been added
by the user. Remove it through the GUI to avoid a stale URL after uninstalling.
Integration removal removes its acknowledgement Store via HA's API.

## Deutsche Kurzfassung

HACS installiert Backend, Übersetzungen und fertiges Frontend gemeinsam. Nach dem
Download HA neu starten, Integration hinzufügen, Regeln konfigurieren und Browser
neu laden. Im GUI-Ressourcenmodus wird das JavaScript-Modul automatisch angelegt
bzw. aktualisiert. Badge und zusätzliche Meldungskarte über die Dashboard-Editoren
platzieren. Bei YAML-Ressourcen ist der obige einzelne Ressourceneintrag notwendig;
eine automatische persistente Änderung dieser schreibgeschützten Sammlung ist
nicht möglich. Die automatische Registrierung nutzt interne HA-APIs und muss bei
HA-Upgrades weiter geprüft werden.

Updates: HA sichern, in HACS aktualisieren, HA neu starten, Browser neu laden.
Deinstallation: Dashboardelemente und Ressourceneintrag über die GUI entfernen,
danach Integration und HACS-Download entfernen. Quittierung bleibt global; bei
Stromausfall kann die letzte Sekunde noch nicht gespeicherter Änderungen verloren
gehen. Andere HA-Versionen und physische Raspberry-Pi-Messungen sind noch offen.
