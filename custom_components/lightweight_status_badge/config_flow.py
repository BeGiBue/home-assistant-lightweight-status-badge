"""Graphical, draft-based rule maintenance through native HA selectors."""

from copy import deepcopy
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import DOMAIN
from .coordinator import Coordinator
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
        self.values = {}

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
            description_placeholders=placeholders,
            last_step=False,
        )

    async def async_step_init(self, user_input=None):
        rules = self._rules()
        overview = "\n".join(
            f"• {'✓' if r.get('enabled', True) else '⏸'} "
            f"{r.get('label') or r['entity_id']} ({r['entity_id']})"
            for r in rules[:10]
        )
        return self.async_show_menu(
            step_id="init",
            menu_options=["add", "choose", "finish"],
            description_placeholders={"count": str(len(rules)), "rules": overview},
        )

    async def async_step_finish(self, user_input=None):
        return self.async_create_entry(title="", data=dict(self.config_entry.options))

    async def async_step_add(self, user_input=None):
        self.selected = None
        self.draft = {"id": uuid4().hex, "entity_id": "", "kind": "custom"}
        self.values = {}
        return await self.async_step_source()

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
        return self.async_show_menu(
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
        return await self.async_step_init()

    async def async_step_edit(self, user_input=None):
        return self.async_show_menu(
            step_id="edit",
            menu_options=["source", "preset", "trigger", "details", "save", "cancel"],
            description_placeholders={
                "rule": self.draft.get("label") or self.draft["entity_id"],
                "entity": self.draft["entity_id"],
            },
        )

    async def async_step_cancel(self, user_input=None):
        if self.selected:
            self.draft = next(r for r in self._rules() if r["id"] == self.selected)
            self.values = {}
            return await self.async_step_manage()
        return await self.async_step_back()

    async def async_step_source(self, user_input=None):
        errors = {}
        if user_input:
            if user_input.get("navigation") == "back":
                return await (
                    self.async_step_edit() if self.draft["entity_id"] else self.async_step_init()
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
                "diagnostic_state": {"states": ["error", "warning"]},
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
            "diagnostic_state": ("states", ["error", "warning"], multiple),
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
                validator,
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
        return await self.async_step_back()

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
