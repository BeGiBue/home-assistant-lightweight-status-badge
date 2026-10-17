"""Graphical, draft-based rule maintenance through native HA selectors."""

from copy import deepcopy
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.frontend.storage import async_user_store
from homeassistant.components.http.const import KEY_HASS_USER
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from homeassistant.helpers.http import current_request
from homeassistant.helpers.translation import async_get_translations

from .const import DOMAIN, MAX_RULES
from .coordinator import Coordinator
from .discovery import source_entities, state_choices
from .rules import OPERATORS, POLICIES, TYPES, Rule

PRESETS = sorted(TYPES) + ["goodwe_code"]


def select(options, key):
    return selector.SelectSelector(
        selector.SelectSelectorConfig(options=list(options), translation_key=key)
    )


def field(schema, name, default, validator):
    schema[vol.Optional(name, default=default)] = validator


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return RuleOptionsFlow()

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Lightweight Status Badge", data={})
        return self.async_show_form(step_id="user")


class RuleOptionsFlow(config_entries.OptionsFlow):
    """Save one complete validated mutation at a time; keep the manager open."""

    def __init__(self):
        self.draft = None
        self.selected = None
        self.original = None
        self.values = {}
        self.source_type = None
        self.source_id = None
        self.chosen_entities = []
        self.pending_entities = []

    def _rules(self):
        return deepcopy(self.config_entry.options.get("rules", []))

    def _persist(self, rules):
        Coordinator.validate_rules(rules)
        self.hass.config_entries.async_update_entry(
            self.config_entry, options={**self.config_entry.options, "rules": rules}
        )

    def _form(self, step, fields, errors=None, placeholders=None):
        field(fields, "navigation", "continue", select(["continue", "back"], "navigation"))
        return self.async_show_form(
            step_id=step,
            data_schema=vol.Schema(fields),
            errors=errors or {},
            description_placeholders={
                "entity": (self.draft or {}).get("entity_id", ""),
                "remaining": str(len(self.pending_entities)),
                **(placeholders or {}),
            },
            last_step=False,
        )

    async def _menu(self, *, step_id, menu_options, description_placeholders=None):
        """Send actual labels: cached frontend translations must not yield blank buttons."""
        language = self.hass.config.language
        request = current_request.get()
        if request is not None and (user := request.get(KEY_HASS_USER)):
            store = await async_user_store(self.hass, user.id)
            preferences = store.data.get("language", {})
            if isinstance(preferences, dict) and isinstance(preferences.get("language"), str):
                language = preferences["language"] or language
        translations = await async_get_translations(self.hass, language, "options", {DOMAIN})
        fallback = await async_get_translations(self.hass, "en", "options", {DOMAIN})
        prefix = f"component.{DOMAIN}.options.step.{step_id}.menu_options."
        return self.async_show_menu(
            step_id=step_id,
            menu_options={
                option: translations.get(prefix + option)
                or fallback.get(prefix + option)
                or option.replace("_", " ").capitalize()
                for option in menu_options
            },
            description_placeholders=description_placeholders,
        )

    async def async_step_init(self, user_input=None):
        rules = self._rules()
        overview = "\n".join(
            f"• {'✓' if r.get('enabled', True) else '⏸'} "
            f"{r.get('label') or r['entity_id']} ({r['entity_id']})"
            for r in rules[:10]
        )
        return await self._menu(
            step_id="init",
            menu_options=["add", "choose", "finish"],
            description_placeholders={"count": str(len(rules)), "rules": overview},
        )

    async def async_step_finish(self, user_input=None):
        return self.async_create_entry(title="", data=dict(self.config_entry.options))

    def _new_draft(self, entity_id=""):
        self.selected = None
        self.original = None
        self.draft = {"id": uuid4().hex, "entity_id": entity_id, "kind": "custom"}
        self.values = {}

    async def async_step_add(self, user_input=None):
        self._new_draft()
        self.source_type = self.source_id = None
        self.chosen_entities = []
        self.pending_entities = []
        return await self.async_step_pick_source()

    async def async_step_pick_source(self, user_input=None):
        return await self._menu(
            step_id="pick_source", menu_options=["device", "integration", "source", "back"]
        )

    async def async_step_device(self, user_input=None):
        if user_input and user_input.get("navigation") == "back":
            return await self.async_step_pick_source()
        errors = {}
        if user_input:
            device_id = user_input.get("device_id")
            if not dr.async_get(self.hass).async_get(device_id):
                errors["device_id"] = "invalid_device"
            else:
                self._set_source("device", device_id)
                return await self.async_step_entities()
        fields = {
            vol.Optional(
                "device_id",
                description={
                    "suggested_value": self.source_id if self.source_type == "device" else None
                },
            ): selector.DeviceSelector()
        }
        return self._form("device", fields, errors)

    async def async_step_integration(self, user_input=None):
        if user_input and user_input.get("navigation") == "back":
            return await self.async_step_pick_source()
        entries = self.hass.config_entries.async_entries()
        choices = [
            {
                "value": entry.entry_id,
                "label": f"{entry.title or entry.domain} ({entry.domain})",
            }
            for entry in sorted(entries, key=lambda entry: (entry.title, entry.entry_id))
        ]
        errors = {}
        if user_input:
            entry_id = user_input.get("entry_id")
            if not self.hass.config_entries.async_get_entry(entry_id):
                errors["entry_id"] = "invalid_integration"
            else:
                self._set_source("integration", entry_id)
                return await self.async_step_entities()
        fields = {
            vol.Optional(
                "entry_id",
                description={
                    "suggested_value": self.source_id if self.source_type == "integration" else None
                },
            ): select(choices, "integrations")
        }
        return self._form("integration", fields, errors)

    def _set_source(self, source_type, source_id):
        if (self.source_type, self.source_id) != (source_type, source_id):
            self.chosen_entities = []
        self.source_type, self.source_id = source_type, source_id

    async def async_step_entities(self, user_input=None):
        if user_input and user_input.get("navigation") == "back":
            return await (
                self.async_step_device()
                if self.source_type == "device"
                else self.async_step_integration()
            )
        entries = source_entities(self.hass, self.source_type, self.source_id)
        valid_ids = {entry.entity_id for entry in entries}
        errors = {} if entries else {"base": "no_entities"}
        if user_input:
            chosen = list(dict.fromkeys(user_input.get("entity_ids", [])))
            if not chosen:
                errors["entity_ids"] = "select_entities"
            elif not set(chosen) <= valid_ids:
                errors["entity_ids"] = "source_changed"
            elif len(self._rules()) + len(chosen) > MAX_RULES:
                errors["base"] = "too_many_rules"
            else:
                self.chosen_entities = chosen
                self.pending_entities = chosen[1:]
                self._new_draft(chosen[0])
                return await self.async_step_preset()
        choices = []
        for entry in entries:
            state = self.hass.states.get(entry.entity_id)
            name = (
                entry.name
                or entry.original_name
                or (state.attributes.get("friendly_name") if state else None)
            )
            label = f"{name} · {entry.entity_id}" if name else entry.entity_id
            choices.append({"value": entry.entity_id, "label": label})
        fields = {
            vol.Optional(
                "entity_ids",
                default=[entity for entity in self.chosen_entities if entity in valid_ids],
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=choices, multiple=True, mode=selector.SelectSelectorMode.LIST
                )
            )
        }
        return self._form("entities", fields, errors)

    async def async_step_skip(self, user_input=None):
        if self.pending_entities:
            self._new_draft(self.pending_entities.pop(0))
            return await self.async_step_preset()
        return await self.async_step_back()

    async def async_step_choose(self, user_input=None):
        if user_input and user_input.get("navigation") == "back":
            return await self.async_step_init()
        rules = self._rules()
        if not rules:
            return await self.async_step_init()
        errors = {}
        if user_input:
            rule = next((r for r in rules if r["id"] == user_input.get("rule_id")), None)
            if rule:
                self.selected = rule["id"]
                self.original = deepcopy(rule)
                self.draft = deepcopy(rule)
                self.values = {}
                return await self.async_step_manage()
            errors["base"] = "missing_rule"
        choices = [
            {
                "value": r["id"],
                "label": (
                    f"{'✓' if r.get('enabled', True) else '⏸'} "
                    f"{r.get('label') or r['entity_id']} · {r['entity_id']} · {r['id']}"
                ),
            }
            for r in rules
        ]
        return self._form("choose", {vol.Optional("rule_id"): select(choices, "rules")}, errors)

    async def async_step_manage(self, user_input=None):
        return await self._menu(
            step_id="manage",
            menu_options=[
                "edit",
                "disable" if self.draft.get("enabled", True) else "enable",
                "remove",
                "back",
            ],
            description_placeholders={
                "rule": self.draft.get("label") or self.draft["entity_id"],
                "enabled": "✓" if self.draft.get("enabled", True) else "⏸",
            },
        )

    async def async_step_back(self, user_input=None):
        self.draft = None
        self.pending_entities = []
        return await self.async_step_init()

    async def async_step_edit(self, user_input=None):
        return await self._menu(
            step_id="edit",
            menu_options=[
                "source",
                "preset",
                "trigger",
                "details",
                "save",
                *(["skip"] if self.pending_entities else []),
                "cancel",
            ],
            description_placeholders={
                "rule": self.draft.get("label") or self.draft["entity_id"],
                "entity": self.draft["entity_id"],
                "remaining": str(len(self.pending_entities)),
            },
        )

    async def async_step_cancel(self, user_input=None):
        if self.selected:
            self.draft = next((r for r in self._rules() if r["id"] == self.selected), None)
            if self.draft is None:
                return await self.async_step_back()
            self.original = deepcopy(self.draft)
            self.values = {}
            return await self.async_step_manage()
        return await self.async_step_back()

    async def async_step_source(self, user_input=None):
        errors = {}
        if user_input:
            if user_input.get("navigation") == "back":
                return await (
                    self.async_step_edit()
                    if self.draft["entity_id"]
                    else self.async_step_pick_source()
                )
            entity_id = er.async_resolve_entity_id(
                er.async_get(self.hass), user_input.get("entity_id", "")
            )
            # HA entity selector is intentionally unrestricted: fault indicators must be explicit.
            try:
                Rule.from_dict({"id": "check", "entity_id": entity_id, "kind": "binary_on"})
            except ValueError:
                errors["entity_id"] = "invalid_entity"
            else:
                self.draft["entity_id"] = entity_id
                if self.selected is None and "config" not in self.draft:
                    return await self.async_step_preset()
                return await self.async_step_edit()
        fields = {}
        fields[
            vol.Optional("entity_id", description={"suggested_value": self.draft["entity_id"]})
        ] = selector.EntitySelector()
        return self._form("source", fields, errors)

    def _suggest_preset(self):
        entity_id = self.draft["entity_id"]
        if entity_id.startswith("update."):
            return "update_available"
        state = self.hass.states.get(entity_id)
        if (
            state
            and entity_id.startswith("binary_sensor.")
            and state.attributes.get("device_class") in {"problem", "safety"}
        ):
            return "binary_on"
        registered = er.async_get(self.hass).async_get(entity_id)
        capabilities = registered.capabilities if registered else None
        if (
            entity_id.startswith(("vacuum.", "lawn_mower."))
            or (
                capabilities
                and isinstance(capabilities.get("options"), (list, tuple))
                and capabilities["options"]
            )
            or (
                state
                and isinstance(state.attributes.get("options"), (list, tuple))
                and state.attributes["options"]
            )
        ):
            return "diagnostic_state"
        return "custom"

    async def async_step_preset(self, user_input=None):
        if user_input:
            if user_input.get("navigation") == "back":
                return await self.async_step_edit()
            preset = user_input.get("preset", self._suggest_preset())
            kind = "nonzero_code" if preset == "goodwe_code" else preset
            self.draft.update(
                kind=kind,
                severity=1 if kind == "update_available" else 2,
                unknown_policy="ignore" if preset == "goodwe_code" else "warning",
                unavailable_policy="ignore" if preset == "goodwe_code" else "warning",
            )
            self.draft["config"] = {
                "disk_health": {"allowlist": ["normal", "healthy", "good", "passed"]},
                "positive_count": {"threshold": 0},
                "diagnostic_state": {
                    "states": [
                        state
                        for state in state_choices(self.hass, self.draft["entity_id"])
                        if state.casefold() in {"error", "warning", "fault", "failed"}
                    ]
                },
                "custom": {"operator": "eq", "value": ""},
            }.get(kind, {})
            # Empty message uses the backend's locale-aware, token-specific explanations.
            self.draft["message"] = ""
            self.values = {}
            return await self.async_step_trigger()
        fields = {}
        field(
            fields,
            "preset",
            self.draft["kind"] if "config" in self.draft else self._suggest_preset(),
            select(PRESETS, "preset"),
        )
        return self._form("preset", fields)

    async def async_step_trigger(self, user_input=None):
        kind = self.draft["kind"]
        config = deepcopy(self.draft.get("config", {}))
        errors = {}
        if user_input:
            if user_input.get("navigation") == "back":
                return await self.async_step_edit()
            candidate = {k: v for k, v in user_input.items() if k != "navigation"}
            additional = candidate.pop("additional_states", [])
            state_field = {
                "diagnostic_state": "states",
                "disk_health": "allowlist",
                "nonzero_code": "error_strings",
            }.get(kind)
            if state_field:
                candidate[state_field] = list(
                    dict.fromkeys(
                        [
                            *candidate.get(state_field, []),
                            *additional,
                        ]
                    )
                )
            if kind == "nonzero_code" and not candidate.get("error_strings"):
                candidate = {}
            if kind == "custom":
                operator = candidate.get("operator", "eq")
                value = (
                    candidate.pop("values", [])
                    if operator in {"in", "not_in"}
                    else candidate.get("value", "")
                )
                candidate = {"operator": operator, "value": value}
            try:
                Rule.from_dict({**self.draft, "config": candidate})
            except ValueError, TypeError:
                errors["base"] = "invalid_trigger"
                self.values["trigger"] = user_input
            else:
                self.draft["config"] = candidate
                self.values.pop("trigger", None)
                return await self.async_step_edit()
        fields = {}
        multiple = selector.TextSelector(selector.TextSelectorConfig(multiple=True))
        text = selector.TextSelector()
        configs = {
            "disk_health": ("allowlist", ["normal", "healthy", "good", "passed"], multiple),
            "positive_count": ("threshold", "0", text),
            "nonzero_code": ("error_strings", [], multiple),
            "diagnostic_state": ("states", [], multiple),
        }
        if kind in configs:
            name, default, validator = configs[kind]
            field(
                fields,
                name,
                (
                    str(self.values.get("trigger", {}).get(name, config.get(name, default)))
                    if name == "threshold"
                    else self.values.get("trigger", {}).get(name, config.get(name, default))
                ),
                (
                    self._state_list(name, config)
                    if name in {"states", "error_strings", "allowlist"}
                    else validator
                ),
            )
        if kind in {"diagnostic_state", "disk_health", "nonzero_code"}:
            field(
                fields,
                "additional_states",
                self.values.get("trigger", {}).get("additional_states", []),
                multiple,
            )
        if kind == "custom":
            previous = self.values.get("trigger", {})
            field(
                fields,
                "operator",
                previous.get("operator", config.get("operator", "eq")),
                select(sorted(OPERATORS), "operator"),
            )
            field(
                fields,
                "value",
                str(
                    previous.get(
                        "value",
                        config.get("value", "")
                        if not isinstance(config.get("value"), list)
                        else "",
                    )
                ),
                text,
            )
            field(
                fields,
                "values",
                previous.get(
                    "values",
                    config.get("value", []) if isinstance(config.get("value"), list) else [],
                ),
                multiple,
            )
        return self._form("trigger", fields, errors, {"kind": kind})

    def _state_list(self, name, config):
        # Existing/user-entered states remain editable even if not advertised by the source.
        values = [
            *state_choices(self.hass, self.draft["entity_id"]),
            *config.get(name, []),
            *self.values.get("trigger", {}).get(name, []),
        ]
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(dict.fromkeys(values)),
                multiple=True,
                mode=selector.SelectSelectorMode.LIST,
                translation_key="entity_state",
            )
        )

    async def async_step_details(self, user_input=None):
        defaults = {
            "label": "",
            "message": "",
            "recommendation": "",
            "severity": 2,
            "enabled": True,
            "unknown_policy": "warning",
            "unavailable_policy": "warning",
            "attributes": [],
        }
        errors = {}
        if user_input:
            if user_input.get("navigation") == "back":
                return await self.async_step_edit()
            changes = {k: v for k, v in user_input.items() if k != "navigation"}
            if "severity" in changes:
                changes["severity"] = int(changes["severity"])
            try:
                Rule.from_dict({**self.draft, **changes})
            except ValueError, TypeError:
                errors["base"] = "invalid_rule"
                self.values["details"] = user_input
            else:
                self.draft.update(changes)
                self.values.pop("details", None)
                return await self.async_step_edit()
        fields = {}
        values = {**defaults, **self.draft, **self.values.get("details", {})}
        for name in defaults:
            validator = selector.TextSelector()
            if name in {"message", "recommendation"}:
                validator = selector.TextSelector(selector.TextSelectorConfig(multiline=True))
            elif name == "enabled":
                validator = selector.BooleanSelector()
            elif name == "severity":
                validator = select(["1", "2", "3"], "severity")
            elif name.endswith("_policy"):
                validator = select(POLICIES, "policy")
            elif name == "attributes":
                validator = selector.TextSelector(selector.TextSelectorConfig(multiple=True))
            field(
                fields, name, str(values[name]) if name == "severity" else values[name], validator
            )
        return self._form(
            "details",
            fields,
            errors,
            {"state_placeholder": "{state}", "attribute_placeholder": "{attributes.NAME}"},
        )

    async def async_step_save(self, user_input=None):
        if user_input and user_input.get("navigation") == "back":
            return await self.async_step_edit()
        rules = self._rules()
        if self.selected and not any(r["id"] == self.selected for r in rules):
            return await self.async_step_back()
        if self.selected and next(r for r in rules if r["id"] == self.selected) != self.original:
            return self.async_show_form(
                step_id="save",
                errors={"base": "rule_changed"},
                data_schema=vol.Schema(
                    {vol.Optional("navigation", default="back"): select(["back"], "navigation")}
                ),
                last_step=False,
            )
        if self.selected:
            rules = [self.draft if r["id"] == self.selected else r for r in rules]
        else:
            rules.append(self.draft)
        try:
            self._persist(rules)
        except ValueError, TypeError:
            return self.async_show_form(
                step_id="save",
                errors={"base": "invalid_rule"},
                data_schema=vol.Schema(
                    {vol.Optional("navigation", default="back"): select(["back"], "navigation")}
                ),
                last_step=False,
            )
        return await self.async_step_skip()

    async def async_step_enable(self, user_input=None):
        return await self._set_enabled(True)

    async def async_step_disable(self, user_input=None):
        return await self._set_enabled(False)

    async def _set_enabled(self, enabled):
        rules = self._rules()
        for rule in rules:
            if rule["id"] == self.selected:
                rule["enabled"] = enabled
        self._persist(rules)
        return await self.async_step_back()

    async def async_step_remove(self, user_input=None):
        if user_input:
            if user_input.get("navigation") != "back" and user_input.get("confirm"):
                self._persist([r for r in self._rules() if r["id"] != self.selected])
                return await self.async_step_back()
            return await self.async_step_manage()
        return self._form(
            "remove", {vol.Optional("confirm", default=False): selector.BooleanSelector()}
        )
