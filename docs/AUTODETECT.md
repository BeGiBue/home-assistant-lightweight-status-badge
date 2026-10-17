# Automatic rule proposals: catalog → local analysis → manual

Status: implemented on branch `feat/auto-detect-sources` (not released, see AGENTS.md).
Audience: maintainers and coding agents. Read this before changing `autodetect.py`,
`catalog.py`, `catalog.json` or the `autodetect_*` steps of the options flow.

## Purpose

Maintaining a hand-written YAML template for "everything that can go wrong" is more
effort than the problems it reports. The device/integration picker therefore **proposes
the rules itself**. The user picks a device or integration, confirms once, and only has to
work by hand for entities nobody could classify.

This is the only place where the integration interprets entity metadata. Monitoring
itself is unchanged: rules, evaluators, coordinator and acknowledgements know nothing about
where a rule came from.

## User-visible flow

```
Add rule → Choose device / integration
              │
              ▼
      async_step_autodetect          (config_flow.py)
              │  async_detect()      (autodetect.py)
   ┌──────────┼───────────────┐
   ▼          ▼               ▼
 catalog    heuristic        none
 found?     found?       (nothing found)
   │          │               │
   ▼          ▼               ▼
autodetect_  autodetect_   entities            ← the pre-existing manual checkbox list
catalog      heuristic     (all unchecked)
   │          │
   └────┬─────┘
        ▼
 checkbox list, proposals preselected and marked ★
   • checked ★ entities  → saved immediately with the proposed rule (one confirmation)
   • checked, not ★      → pre-existing per-entity editor (preset → trigger → save), one by one
   • unchecked           → nothing happens
```

Order is strict: the heuristic runs only if the catalog produced **no proposal** for this
source; the manual list is shown only if both produced nothing. Catalog and heuristic
results are never merged. Back (`navigation=back`) returns to the device/integration picker.

Every saved rule is an ordinary rule: it can be edited, disabled or removed under
**Select existing rule**. Proposals are never persisted without the user pressing
Apply / continue.

## Components

| File | Responsibility |
| --- | --- |
| `custom_components/lightweight_status_badge/autodetect.py` | `async_detect()` orchestrates the three stages, `Proposal`/`Detection` data classes, the local heuristic, catalog application to registry entries. |
| `custom_components/lightweight_status_badge/catalog.py` | Loading (online, bundled fallback, short cache), validation of untrusted catalog data, matching a source to an entry. |
| `custom_components/lightweight_status_badge/catalog.json` | The catalog. The same file is the offline fallback **and** what `CATALOG_URL` serves from `main`. |
| `custom_components/lightweight_status_badge/discovery.py` | `declared_options()` (new, extracted from `state_choices`) and the existing `source_entities()`. |
| `custom_components/lightweight_status_badge/config_flow.py` | Steps `autodetect`, `autodetect_catalog`, `autodetect_heuristic`; `_label()` helper. |
| `custom_components/lightweight_status_badge/const.py` | `CATALOG_URL`, timeout, size limit, cache TTL. |
| `strings.json`, `translations/{en,de}.json` | Texts of the two new steps (the three files must stay in sync). |
| `tests/test_autodetect.py`, `tests/conftest.py` | Tests; the autouse fixture `offline_catalog` blocks network access. |

## Stage 1: catalog

Format (`catalog.json`, `version` 1):

```json
{
  "integrations": {
    "<integration domain>": {
      "description": "Shown to the user, max 200 characters.",
      "rules": [
        {
          "match": {"domain": "binary_sensor", "device_class": "connectivity",
                    "entity_category": "diagnostic"},
          "kind": "custom",
          "severity": 2,
          "config": {"operator": "eq", "value": "off"},
          "unknown_policy": "warning",
          "unavailable_policy": "warning"
        }
      ]
    }
  },
  "devices": [
    {"manufacturer": "AVM", "model": "FRITZ!Box*", "description": "…", "rules": ["…"]}
  ]
}
```

- `match` keys (all must match, at least one required): `domain`, `device_class`,
  `translation_key`, `entity_category`. Values come from the entity registry; the device
  class falls back to the state attribute.
- `kind`, `severity`, `config`, `unknown_policy`, `unavailable_policy` use the existing rule
  model (`rules.py`). Omitted policies default to `warning`, severity to `2`.
- Per entity the **first** matching rule of the entry wins.
- `devices[]` matches `manufacturer`/`model` with case-insensitive `fnmatch` patterns
  (max 64 characters) and beats an `integrations` entry. For a device source the domains of
  all its config entries are tried against `integrations`.
- `version` must equal `CATALOG_VERSION` (currently 1). An online catalog with another or
  a missing version is ignored and the bundled copy is used, so a future format change on
  `main` cannot be misread by older installations. Raise the constant together with any
  incompatible format change and keep the bundled file readable by the code it ships with.
- `description` is untrusted text that HA renders as markdown. `catalog._text` removes URLs,
  link/image/HTML/emphasis characters and line breaks and cuts it to 200 characters.
- Unknown top-level keys such as `comment` are ignored.

Validation (`catalog._clean_rule`): the catalog is untrusted input. A rule survives only if
`match` uses the four allowed keys with short strings **and** the rule passes
`Rule.from_dict` with a placeholder entity (`<domain>.placeholder`). Anything else is
dropped silently, so a broken entry degrades to "no catalog entry" instead of an error.
Rules are validated again with the real entity ID before they become proposals (for
example `update_available` on a non-update entity is discarded). The catalog cannot execute
code, cannot introduce new rule kinds and cannot reference concrete entity IDs.

Loading (`catalog.async_load_catalog`): HTTPS GET of `CATALOG_URL` with a 5 s timeout and a
256 KiB limit; success is cached for 10 minutes. Any failure (network, HTTP error, bad JSON
including pathologically nested JSON that raises `RecursionError`, non-object, wrong format
version, too large) falls back to the bundled file, which is always consistent with the
installed code. Origin is reported as `online`, `bundled` or `none`.

### Changing the catalog

1. Edit `custom_components/lightweight_status_badge/catalog.json`. Use only standard Home
   Assistant metadata (domain, device class, translation key, entity category) and existing
   rule kinds. Do not guess what an integration's private codes mean (SPEC.md: unknown
   codes stay unknown).
2. Every rule must pass `catalog._clean_rule`; `test_bundled_catalog_is_valid_and_complete`
   enforces this.
3. If you add a behaviour (new `match` key, new field), extend `catalog._clean_rule`,
   `autodetect._matches`, this document and the tests together.
4. Merging to `main` publishes the change to all installations immediately (they fetch
   `main`). Review catalog changes like code.

## Stage 2: local heuristic

Only standard metadata, only conservative rules (`autodetect._heuristic_for`):

| Entity | Proposed rule | Severity |
| --- | --- | --- |
| `binary_sensor`, class `safety`, `smoke`, `gas`, `carbon_monoxide` | `binary_on` | 3 |
| `binary_sensor`, class `problem`, `tamper`, `moisture` | `binary_on` | 2 |
| `binary_sensor`, class `battery` | `binary_on` | 1 |
| `binary_sensor`, class `connectivity` **and** entity category `diagnostic` | `custom` `eq` `off` | 2 |
| `update.*` | `update_available` | 1 |
| `sensor` that **declares** options containing `error`, `warning`, `fault` or `failed` | `diagnostic_state` with exactly those options (original spelling) | 2 |

Deliberate omissions: connectivity entities without the diagnostic category (client or
presence entities would be noise), anything that only *currently* has a fault-like state
(declared options only), vacuum and lawn mower entities (the manual editor already suggests
`diagnostic_state` for them; adding them here would change that flow).

Availability defaults: `unknown_policy = ignore` (common right after start-up),
`unavailable_policy = warning`. Catalog rules choose their own policies.

## Common to both stages

- Disabled entities are never proposed (they would only raise "unavailable" alerts) but stay
  selectable in the list. Hidden entities are treated like visible ones.
- Entities that already have a rule are never proposed again, so re-running the picker on a
  source does not create duplicates; it ends in the manual list when nothing new remains.
- A proposal becomes a rule dict through `Proposal.to_rule()`: fresh UUID, empty `message`
  (the backend then uses its locale-aware explanations), no label.
- Saving uses the same `_persist()` path as manual rules (`Coordinator.validate_rules`,
  `MAX_RULES`).

## Privacy and security

- The only network access is the catalog download, **inside the options flow**, never during
  monitoring. It sends no information about the user's setup: the whole file is downloaded
  and matched locally. The remote host sees the usual metadata of an HTTPS request.
- Pointing `CATALOG_URL` elsewhere is the only supported way to use a private catalog.
- Anything from the catalog is data, never code; see "Validation" above.

## Invariants for future changes

1. No polling, no event subscriptions, no network access outside the options flow.
2. Never persist proposals without explicit user confirmation.
3. Never infer the meaning of vendor-specific states or codes; use declared options or an
   explicit catalog entry.
4. All rules, wherever they come from, must pass `Rule.from_dict`.
5. Keep `strings.json`, `translations/en.json` and `translations/de.json` in sync.
6. Behaviour changes need tests in `tests/test_autodetect.py` and an update of this file.

## Tests

`tests/test_autodetect.py` covers catalog validation (including hostile input), matching,
online fetch failures (`aioclient_mock`), caching and offline fallback, detection for
catalog/heuristic/none, device matching, skipping of disabled and already-ruled entities,
and the options flow end to end (checked proposals, extra manual entities, back navigation,
validation errors, re-running a source, device sources). The autouse fixture
`offline_catalog` in `tests/conftest.py` replaces the download with "unavailable", so every
test sees the bundled catalog and no test can reach the network.

Verification state: the authoring environment could not run the Home Assistant based test
suite (PyPI unreachable); locally only `ruff`, a Python 3.14 compile check and a stub script
for the pure logic were possible. The first real execution was GitHub Actions: on commit
`5a1617d` the `Backend and frontend tests` workflow (pytest, `ruff check`,
`ruff format --check`, frontend and browser tests) and the hassfest/HACS validation were
green, and an independent review found no blocker. Changes made after that commit (catalog
version gate, description sanitising, `RecursionError` handling, selection kept after
validation errors) need their own green CI run before merging. Check the Actions result of
the head commit; do not rely on this paragraph for later commits.

## Known limitations and open points

- No setting to disable the online catalog (the bundled one is used only when offline).
  The manifest keeps `iot_class: local_push`: the outbound request happens only while the
  configuration dialog is used and carries no device data.
- Offline failures are not cached, so without internet every source pick may wait up to the
  5 s timeout before the bundled file is used. A short negative cache would fix this.
- Already-ruled entities are hidden from proposals but remain selectable in the list, so a
  second rule for the same entity is still possible by hand (same as the manual list).
- Catalog and heuristic are never combined; a catalog entry matching only part of a source
  hides heuristic proposals for the rest (those entities can still be checked manually).
- Before the branch is merged, `CATALOG_URL` returns 404 on `main`, which correctly falls
  back to the bundled file.
- Proposals cannot be tuned in the list itself; use **Select existing rule** afterwards.
- The seeded catalog entries use generic device-class rules only; integration-specific
  entries (UPS, Synology drive health, GoodWe codes) still need verified metadata.

## Compatibility

No stored data changed: proposals produce ordinary rules in the existing format. The user
also confirmed (AGENTS.md) that backward compatibility is not required for this scope.

## Zusammenfassung (Deutsch)

Nach der Auswahl von Gerät oder Integration prüft die Integration zuerst einen Online-
Katalog (`catalog.json`, offline die mitgelieferte Kopie), dann eine lokale Analyse der
Standard-Metadaten (Geräteklassen, Kategorien, deklarierte Optionen). Gefundene Regeln sind
mit ★ vorausgewählt und werden mit einer Bestätigung gespeichert. Nur wenn beides nichts
findet, erscheint wie bisher die manuelle Auswahlliste; manuell angekreuzte Entitäten ohne
Vorschlag laufen durch den bisherigen Editor. Katalogdaten gelten als nicht vertrauenswürdig
und werden hart validiert. Die Home-Assistant-Tests liefen lokal nicht (PyPI nicht
erreichbar); die CI muss vor dem Merge grün sein.
