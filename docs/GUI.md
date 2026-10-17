# Graphical rule management (issue #3 / work package B)

Based on `feat/status-badge-backend` from PR #6, commit
`e99d6952377e7634224a401766d18418115fadde`. Product requirements in SPEC.md and
ARCHITECTURE.md are unchanged. This branch implements rule management, not the
work-package-C dashboard badge/dialog or secondary acknowledged-alert view.

## Everyday operation / Bedienung

Add **Lightweight Status Badge** under **Settings → Devices & services → Add
integration**. This is an integration, not a Helpers entry. Open **Configure**
on the integration to manage rules. German and English labels follow the HA
frontend language using HA's standard translations and selectors.

1. **Add rule / Regel hinzufügen** opens HA's native entity picker. Search by
   friendly name or entity ID. Registry UUID selections are resolved to entity
   IDs; explicitly entered IDs also support temporarily missing sources.
2. Select and apply a template. Update entities suggest the update template;
   binary sensors with device class `problem` or `safety` suggest an explicit
   fault indicator. All other entities suggest a custom rule. Nothing is enrolled
   automatically. An update template requires an `update.*` entity; a generic
   binary sensor's `on` state is not presumed to be a fault.
3. Review the trigger. String sets have individual entries, not comma-split text.
   Custom conditions have an operator, a text/numeric value and a set field:
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
   one complete change, returning to the overview without closing the manager.
   Monitoring reloads immediately, without rebooting HA. **Done / Fertig** closes
   the manager. Closing the dialog discards only the unsaved rule draft; earlier
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
remain part of the full suite. Final local validation: **167 tests passed** (51 new GUI tests), **96%** overall
statement coverage and **98%** for `config_flow.py`, Python 3.14.8 on Linux x86_64.
Ruff lint, Ruff formatting and `git diff --check` passed.
Browser rendering on a physical HA installation and other HA versions remain
unverified; HTTP serialization and flow behavior are automated, not a screenshot
or manual browser usability claim.

Run the commands in [BACKEND.md](BACKEND.md) with the pinned test dependencies.
Do not release or merge this branch as part of implementation.
