# Graphical rule management

Current installation: [INSTALLATION.md](INSTALLATION.md). The device/integration
picker builds on the existing rule editor and reuses the backend evaluators;
SPEC.md and ARCHITECTURE.md remain unchanged.

## Everyday operation / Bedienung

Add **Lightweight Status Badge** under **Settings → Devices & services → Add
integration**. This is an integration, not a Helpers entry. Open **Configure**
on the integration to manage rules. German and English labels follow the HA
frontend language using HA's standard translations and selectors.

1. **Add rule / Regel hinzufügen** offers **Choose device / Gerät auswählen**,
   **Choose integration / Integration auswählen**, or direct selection of a single
   entity. Device/integration selection opens a native **checkbox list** of all
   associated registered entities. There is no domain or diagnostic-category
   filter: `vacuum.*`, `lawn_mower.*`, hidden and disabled entries are included.
   Integration selection distinguishes individual config entries and includes
   entities without a device. Disabled entries are not automatically enabled;
   activate them separately in HA if they should provide live states. Nothing is
   checked automatically. Registry UUIDs and manually entered entity IDs remain
   supported by the optional single-entity path.
2. Select and apply a template. Update entities suggest the update template;
   binary sensors with device class `problem` or `safety` suggest an explicit
   fault indicator. Vacuum/mower operating entities and sources declaring enum
   options suggest **Select fault states / Fehlerzustände auswählen**. Other
   entities suggest a custom rule. Nothing is enrolled automatically. An update template requires an `update.*` entity; a generic
   binary sensor's `on` state is not presumed to be a fault.
3. Review the trigger. Error-state sets, error strings and healthy-state allowlists
   use native checkboxes. Suggestions combine declared entity/registry `options`,
   standardized HA robot activities, and the current entity state. Only checked
   error states trigger the rule; other ordinary states do not. For drive-health
   rules the checked states instead form the healthy allowlist. Add states absent
   from the list through **Additional values / Weitere Werte**; these are individual
   entries, not comma-split text. Availability is handled separately by the
   unknown/unavailable policies. Custom conditions have an operator, a text/numeric value and a set field:
   `in`/`not_in` use the set; other operators use the single value. Numbers must
   be finite. All string comparisons are case-insensitive.
4. In **Title, messages and availability / Titel, Meldungen und Verfügbarkeit**,
   set the title, severity, explanation, recommendation, enabled flag,
   unknown/unavailable policies and attribute whitelist. An empty explanation
   retains the backend's translated, state-specific template explanations.
   GoodWe defaults both availability policies to **Ignore**; all other templates
   default to **Warning**. Updates default to severity 1; other templates to 2.
   UPS LB/FSD always escalate to 3 as specified by the backend.
5. Each form's **Apply / continue** accepts that page into the draft and returns
   to the editor. **Back (discard this page)** leaves that page without applying
   its fields; previously accepted draft pages remain intact. From the editor,
   **Discard draft / back** discards the whole current draft. Template application
   replaces trigger, severity, explanation and availability defaults in the draft;
   review them before saving. Title, recommendation and attribute list survive.
6. **Save rule / Regel speichern** validates the complete rule list and persists
   one complete change. When multiple entities were checked, the next entity's
   draft opens after each save; each source has its own rule and condition. Use
   **Skip this entity / Diese Entität überspringen** to omit a pending source.
   Cancelling discards the current draft and remaining unsaved selections, while
   already saved rules remain saved. After the last source, return to the overview
   without closing the manager. Monitoring reloads immediately, without rebooting
   HA. **Done / Fertig** closes the manager. Closing the dialog discards only the unsaved rule draft; earlier
   explicitly saved rules remain saved.
7. **Select existing rule / Vorhandene Regel auswählen** lists every rule by
   title, source ID and stable rule ID. The overview previews the first ten rules;
   the native searchable dropdown includes all rules. ✓ means enabled, ⏸ disabled.
   Select a rule to edit, enable/disable, or remove it. Removal requires an explicit
   confirmation; backing out does not remove anything.

Display-only changes preserve the rule ID and acknowledgement. Trigger, source,
severity or availability changes invalidate acknowledgement as defined by the
backend. Disabling/removing a rule clears its alert and acknowledgement. None of
these operations writes to the source entity.

## Templates and migration

All ten evaluator schemas in [BACKEND.md](BACKEND.md) are represented. The extra
GoodWe template is a `nonzero_code` rule with ignore availability defaults.
Diagnostic and error-string lists remain editable; health allowlists, count
thresholds and all nine custom operators are available without YAML. The UPS
message remains empty by default so the backend can explain OB, LB, FSD and RB
individually in the requested language, rather than replacing all token meanings
with one static message. Unfamiliar UPS tokens are not classified.

Use `{state}` and `{attributes.NAME}` in explanation/recommendation templates;
list `NAME` in the attribute whitelist. The forms show these placeholders including their braces. No Python,
Jinja, arbitrary attribute access or automatic import of legacy Jinja is provided.
Backend bounds (1000 rules, 1000 characters per text, 10 whitelisted attributes)
are checked before saving. An invalid complete draft shows an error and offers a
back action so it can be corrected or discarded.

The literal list of 29 original entity IDs and their old Jinja conditions is not
included in this repository or issue. Tests therefore cover the supplied category
semantics with representative fixtures, not a claim of verified migration of
unavailable original entity IDs. No physical devices or Raspberry Pi measurements
are claimed by this GUI work.

## Security and tests

The flow uses HA's authenticated options-flow endpoints with HA's configuration
edit permission requirement; it adds no alternate mutation endpoint. Tests check
that authenticated read-only users cannot start or continue the options flow,
while an administrator can access the serialized native entity picker.

Automated tests use the actual HA 2026.10.2 flow manager, selector validators,
config entry updates, loaded coordinator and reload listener. They cover all ten
evaluators, GoodWe defaults, nine custom operators, add/reopen/edit/enable/disable/
remove, explicit back/cancel paths, invalid drafts, duplicate IDs, missing and
unknown states, stable IDs, acknowledgement preservation/invalidation and
translation-key parity. Existing backend authentication and acknowledgement tests
remain part of the full suite. Current local validation: **185 tests passed**, **97%**
overall statement coverage, **99%** for `config_flow.py` and **100%** for
`discovery.py`, Python 3.14.8 on Linux x86_64. This includes ten new picker/discovery
tests for device/integration membership, operational/hidden/disabled sources,
per-entity save/skip/cancel, metadata and custom states, native checkbox HTTP
serialization, read-only permission denial and sources removed during selection.
Ruff lint, Ruff formatting and `git diff --check` passed.
Browser rendering on a physical HA installation and other HA versions remain
unverified; HTTP serialization and flow behavior are automated, not a screenshot
or manual browser usability claim.

Run the commands in [BACKEND.md](BACKEND.md) with the pinned test dependencies.
Do not release or merge this branch as part of implementation.

## Discovery limits

Entity discovery runs only when the configuration pages are opened/submitted;
it adds no polling, event history or full registry scan to the monitoring path.
Membership is checked again on submission, so a source moved or removed during
selection cannot silently become a different device's rule. Hidden/disabled
entities are not excluded and their HA configuration is not modified.

Home Assistant does not expose a complete state catalogue for every entity.
`options` lists are used when supplied (including registry capabilities while a
source is unavailable). Robot suggestions come from HA's `VacuumActivity` and
`LawnMowerActivity` enums; these are standard domain states, not a promise that
every device emits every listed state. For other entities only the current state
may be known, or no values may be discoverable. Additional values always remain
available; no unobserved error-code meanings are inferred. Fault selection still
uses the existing `diagnostic_state` evaluator: this is a state rule, not automatic
classification of arbitrary error attributes. Attribute-only faults require an
appropriate source entity; this change does not add attribute evaluators.

Before planning fundamental importer/configuration/storage changes, clarify
backward compatibility with the user. Ask again before release only if that
decision remains open or the scope has changed. The user confirmed that
compatibility is not required for 0.1.5 (see AGENTS.md).
