"""Exercise the real HA options flow manager, selectors, reloads and drafts."""

import json
from pathlib import Path

import pytest
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.lightweight_status_badge.rules import OPERATORS, TYPES
from tests.test_integration import setup_entry


async def start(hass, rules=()):
    entry = await setup_entry(hass, list(rules))
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return entry, result


async def go(hass, result, data):
    # Validate the schema exactly as HA does; defaults and selectors are exercised.
    if result["type"] == FlowResultType.FORM:
        data = result["data_schema"](data)
    return await hass.config_entries.options.async_configure(result["flow_id"], data)


async def menu(hass, result, step):
    return await go(hass, result, {"next_step_id": step})


async def add(hass, result, preset, entity="sensor.source", config=None):
    result = await menu(hass, result, "add")
    assert result["step_id"] == "source"
    assert result["data_schema"].schema["entity_id"].selector_type == "entity"
    result = await go(hass, result, {"entity_id": entity})
    result = await go(hass, result, {"preset": preset})
    result = await go(hass, result, config or {})
    assert result["step_id"] == "edit"
    return result


@pytest.mark.parametrize("kind", sorted(TYPES) + ["goodwe_code"])
async def test_every_template_add_reopen(hass, kind):
    entry, result = await start(hass)
    result = await add(
        hass, result, kind, "update.source" if kind == "update_available" else "sensor.source"
    )
    result = await menu(hass, result, "save")
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"
    await hass.async_block_till_done()
    rule = entry.options["rules"][0]
    assert rule["kind"] == ("nonzero_code" if kind == "goodwe_code" else kind)
    assert entry.runtime_data.rules[0].id == rule["id"]
    if kind == "goodwe_code":
        assert rule["unknown_policy"] == rule["unavailable_policy"] == "ignore"
    result = await menu(hass, result, "finish")
    assert result["type"] == FlowResultType.CREATE_ENTRY
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await menu(hass, result, "choose")
    result = await go(hass, result, {"rule_id": rule["id"]})
    assert result["step_id"] == "manage"


@pytest.mark.parametrize("operator", sorted(OPERATORS))
async def test_custom_operators_and_acknowledgement_semantics(hass, operator):
    hass.states.async_set("sensor.source", "5")
    entry, result = await start(hass)
    result = await add(
        hass,
        result,
        "custom",
        config={
            "operator": operator,
            "value": "4" if operator in {"gt", "ge", "lt", "le"} else "5",
            "values": ["5", "6"],
        },
    )
    result = await menu(hass, result, "save")
    await hass.async_block_till_done()
    saved = entry.options["rules"][0]
    assert saved["config"]["operator"] == operator
    if operator in {"in", "not_in"}:
        assert saved["config"]["value"] == ["5", "6"]
    result = await menu(hass, result, "choose")
    result = await go(hass, result, {"rule_id": saved["id"]})
    result = await menu(hass, result, "edit")
    result = await menu(hass, result, "details")
    result = await go(
        hass, result, {"label": "New title", "message": "State: {state}", "attributes": ["code"]}
    )
    result = await menu(hass, result, "save")
    await hass.async_block_till_done()
    assert entry.options["rules"][0]["id"] == saved["id"]
    assert entry.options["rules"][0]["label"] == "New title"


async def test_edit_toggle_remove_reload_and_acknowledgement(hass):
    hass.states.async_set("sensor.source", "OB")
    entry, result = await start(
        hass, [{"id": "ups", "entity_id": "sensor.source", "kind": "ups_status"}]
    )
    core = entry.runtime_data
    core.set_acknowledged("ups", core.alerts["ups"].occurrence, True)
    result = await menu(hass, result, "choose")
    result = await go(hass, result, {"rule_id": "ups"})
    result = await menu(hass, result, "edit")
    result = await menu(hass, result, "details")
    result = await go(hass, result, {"label": "UPS", "recommendation": "Check power"})
    result = await menu(hass, result, "save")
    await hass.async_block_till_done()
    assert entry.runtime_data.alerts["ups"].acknowledged
    # Substantive condition changes invalidate the acknowledgement.
    result = await menu(hass, result, "choose")
    result = await go(hass, result, {"rule_id": "ups"})
    result = await menu(hass, result, "edit")
    result = await menu(hass, result, "details")
    result = await go(hass, result, {"severity": "3"})
    result = await menu(hass, result, "save")
    await hass.async_block_till_done()
    assert not entry.runtime_data.alerts["ups"].acknowledged
    for expected in (False, True):
        result = await menu(hass, result, "choose")
        result = await go(hass, result, {"rule_id": "ups"})
        result = await menu(hass, result, "enable" if expected else "disable")
        await hass.async_block_till_done()
        assert entry.options["rules"][0]["enabled"] is expected
        assert bool(entry.runtime_data.alerts) is expected
    result = await menu(hass, result, "choose")
    result = await go(hass, result, {"rule_id": "ups"})
    result = await menu(hass, result, "remove")
    result = await go(hass, result, {"navigation": "back"})
    assert result["step_id"] == "manage"
    assert len(entry.options["rules"]) == 1
    result = await menu(hass, result, "remove")
    result = await go(hass, result, {"confirm": True})
    await hass.async_block_till_done()
    assert not entry.options["rules"]
    assert not entry.runtime_data.alerts


async def test_draft_navigation_and_invalid_inputs(hass):
    entry, result = await start(hass)
    result = await menu(hass, result, "choose")
    assert result["step_id"] == "init"
    result = await menu(hass, result, "add")
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(result["flow_id"], {"entity_id": "bad"})
    result = await go(hass, result, {"entity_id": "00000000000000000000000000000000"})
    assert result["errors"] == {"entity_id": "invalid_entity"}
    result = await go(hass, result, {"entity_id": "sensor.source"})
    result = await go(hass, result, {"preset": "custom"})
    result = await go(hass, result, {"operator": "gt", "value": "nan"})
    assert result["errors"] == {"base": "invalid_trigger"}
    result = await go(hass, result, {"navigation": "back"})
    result = await menu(hass, result, "details")
    result = await go(hass, result, {"label": "Draft", "attributes": ["bad.name"]})
    assert result["errors"] == {"base": "invalid_rule"}
    result = await go(hass, result, {"label": "Draft", "attributes": ["code"]})
    result = await menu(hass, result, "source")
    result = await go(hass, result, {"navigation": "back"})
    result = await menu(hass, result, "details")
    assert result["data_schema"]({})["label"] == "Draft"
    result = await go(hass, result, {"navigation": "back"})
    result = await menu(hass, result, "trigger")
    result = await go(hass, result, {"operator": "gt", "value": "3"})
    result = await menu(hass, result, "save")
    assert entry.options["rules"][0]["label"] == "Draft"
    result = await menu(hass, result, "choose")
    result = await go(hass, result, {"rule_id": entry.options["rules"][0]["id"]})
    result = await menu(hass, result, "edit")
    result = await menu(hass, result, "details")
    result = await go(hass, result, {"label": "Discarded"})
    result = await menu(hass, result, "cancel")
    assert result["step_id"] == "manage"
    assert entry.options["rules"][0]["label"] == "Draft"


@pytest.mark.parametrize(
    "entity,device_class,expected",
    [
        ("update.firmware", None, "update_available"),
        ("binary_sensor.problem", "problem", "binary_on"),
        ("binary_sensor.motion", "motion", "custom"),
        ("binary_sensor.on", None, "custom"),
    ],
)
async def test_conservative_suggestions(hass, entity, device_class, expected):
    hass.states.async_set(entity, "on", {"device_class": device_class})
    entry, result = await start(hass)
    result = await menu(hass, result, "add")
    result = await go(hass, result, {"entity_id": entity})
    assert result["data_schema"]({})["preset"] == expected
    assert not entry.options["rules"] if "rules" in entry.options else True


def test_translation_parity():
    root = Path("custom_components/lightweight_status_badge")
    en = json.loads((root / "strings.json").read_text())
    assert en == json.loads((root / "translations/en.json").read_text())
    de = json.loads((root / "translations/de.json").read_text())

    def paths(data, prefix=""):
        return {
            p
            for k, v in data.items()
            for p in (paths(v, prefix + "." + k) if isinstance(v, dict) else {prefix + "." + k})
        }

    assert paths(en) == paths(de)


async def test_initial_back_and_registry_uuid(hass, entity_registry):
    entry, result = await start(hass)
    result = await menu(hass, result, "add")
    result = await go(hass, result, {"navigation": "back"})
    assert result["step_id"] == "init"
    registered = entity_registry.async_get_or_create("sensor", "test", "source")
    result = await menu(hass, result, "add")
    result = await go(hass, result, {"entity_id": registered.id})
    result = await go(hass, result, {"preset": "ups_status"})
    result = await go(hass, result, {})
    result = await menu(hass, result, "save")
    assert entry.options["rules"][0]["entity_id"] == registered.entity_id


async def test_options_http_permissions_and_serialized_entity_selector(
    hass, hass_client, hass_read_only_access_token
):
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "config", {})
    entry, result = await start(hass)
    assert hass.auth.async_validate_access_token(hass_read_only_access_token) is not None
    readonly = await hass_client(hass_read_only_access_token)
    response = await readonly.post(
        "/api/config/config_entries/options/flow",
        json={"handler": entry.entry_id},
        headers={"Authorization": f"Bearer {hass_read_only_access_token}"},
    )
    assert response.status == 401  # HA maps its Unauthorized permission error to HTTP 401.
    admin = await hass_client()
    # Use the flow already started above via the real authenticated HTTP endpoint.
    url = "/api/config/config_entries/options/flow/" + result["flow_id"]
    response = await admin.post(url, json={"next_step_id": "add"})
    assert response.status == 200
    result = await response.json()
    assert result["step_id"] == "source"
    entity = next(f for f in result["data_schema"] if f["name"] == "entity_id")
    assert "entity" in entity["selector"]
    assert entity["selector"]["entity"]["multiple"] is False
    assert "filter" not in entity["selector"]["entity"]
    response = await readonly.post(
        url,
        json={"entity_id": "sensor.forbidden"},
        headers={"Authorization": f"Bearer {hass_read_only_access_token}"},
    )
    assert response.status == 401  # HA maps its Unauthorized permission error to HTTP 401.
    response = await admin.post(url, json={"entity_id": "sensor.allowed"})
    assert response.status == 200
    assert (await response.json())["step_id"] == "preset"
    assert not entry.options["rules"]


@pytest.mark.parametrize(
    "policy,severity", [("ignore", 0), ("notice", 1), ("warning", 2), ("critical", 3)]
)
async def test_availability_ui(hass, policy, severity):
    entry, result = await start(hass)
    result = await add(hass, result, "ups_status")
    result = await menu(hass, result, "details")
    result = await go(hass, result, {"unknown_policy": policy, "unavailable_policy": policy})
    result = await menu(hass, result, "save")
    await hass.async_block_till_done()
    # Missing entity is unavailable; unknown is never evaluated as an ordinary UPS state.
    assert entry.runtime_data.counts == (int(bool(severity)), int(bool(severity)), severity)
    hass.states.async_set("sensor.source", "unknown")
    await hass.async_block_till_done()
    assert entry.runtime_data.counts == (int(bool(severity)), int(bool(severity)), severity)


async def test_invalid_update_template_and_save_back(hass):
    entry, result = await start(hass)
    result = await menu(hass, result, "add")
    result = await go(hass, result, {"entity_id": "sensor.source"})
    result = await go(hass, result, {"preset": "update_available"})
    result = await go(hass, result, {})
    assert result["errors"] == {"base": "invalid_trigger"}
    result = await go(hass, result, {"navigation": "back"})
    result = await menu(hass, result, "save")
    assert result["errors"] == {"base": "invalid_rule"}
    result = await go(hass, result, {"navigation": "back"})
    result = await menu(hass, result, "source")
    result = await go(hass, result, {"entity_id": "update.source"})
    result = await menu(hass, result, "save")
    assert result["step_id"] == "init"
    assert len(entry.options["rules"]) == 1


async def test_duplicate_ids_rejected_without_overwrite(hass):
    from unittest.mock import patch

    entry, result = await start(
        hass, [{"id": "same", "entity_id": "sensor.old", "kind": "ups_status"}]
    )
    with patch("custom_components.lightweight_status_badge.config_flow.uuid4") as uuid:
        uuid.return_value.hex = "same"
        result = await add(hass, result, "ups_status")
    result = await menu(hass, result, "save")
    assert result["errors"] == {"base": "invalid_rule"}
    assert len(entry.options["rules"]) == 1
    assert entry.options["rules"][0]["entity_id"] == "sensor.old"


@pytest.mark.parametrize(
    "preset,config,active,clear",
    [
        ("binary_on", {}, "on", "off"),
        ("update_available", {}, "on", "off"),
        ("disk_health", {"allowlist": ["ok", "passed"]}, "failing", "OK"),
        ("positive_count", {"threshold": "2"}, "3", "2"),
        ("unifi_state", {}, "adopting_failed", "connected"),
        ("ups_status", {}, "OB LB DISCHRG", "OL CHRG"),
        ("nonzero_code", {"error_strings": ["ERR_X"]}, "err_x", "0"),
        ("diagnostic_state", {"states": ["warning", "error"]}, "WARNING", "normal"),
        ("grid_fault", {}, "grid failure", "normal"),
        ("goodwe_code", {}, "4096", "0"),
    ],
)
async def test_gui_configured_templates_monitor_live_states(hass, preset, config, active, clear):
    entity = "update.source" if preset == "update_available" else "sensor.source"
    hass.states.async_set(entity, active)
    entry, result = await start(hass)
    result = await add(hass, result, preset, entity, config)
    result = await menu(hass, result, "save")
    await hass.async_block_till_done()
    rule_id = entry.options["rules"][0]["id"]
    alert = entry.runtime_data.alerts[rule_id]
    assert alert.raw_state == active
    if preset == "ups_status":
        assert alert.severity == 3
    hass.states.async_set(entity, clear)
    await hass.async_block_till_done()
    assert not entry.runtime_data.alerts


@pytest.mark.parametrize(
    "preset,config",
    [
        ("positive_count", {"threshold": "inf"}),
        ("diagnostic_state", {"states": []}),
        ("disk_health", {"allowlist": []}),
        ("custom", {"operator": "in", "values": []}),
    ],
)
async def test_invalid_trigger_preserves_form_and_can_cancel(hass, preset, config):
    entry, result = await start(hass)
    result = await menu(hass, result, "add")
    result = await go(hass, result, {"entity_id": "sensor.source"})
    result = await go(hass, result, {"preset": preset})
    result = await go(hass, result, config)
    assert result["errors"] == {"base": "invalid_trigger"}
    result = await go(hass, result, {"navigation": "back"})
    result = await menu(hass, result, "cancel")
    assert result["step_id"] == "init"
    assert not entry.options["rules"]


@pytest.mark.parametrize(
    "language,title,enable",
    [("de", "Regelverwaltung", "Aktivieren"), ("en", "Rule management", "Enable")],
)
async def test_ha_loads_translations(hass, language, title, enable):
    from homeassistant.helpers.translation import async_get_translations

    from custom_components.lightweight_status_badge.const import DOMAIN

    await start(hass)
    translations = await async_get_translations(hass, language, "options", {DOMAIN})
    assert translations[f"component.{DOMAIN}.options.step.init.title"] == title
    assert translations[f"component.{DOMAIN}.options.step.manage.menu_options.enable"] == enable
    selectors = await async_get_translations(hass, language, "selector", {DOMAIN})
    assert selectors[f"component.{DOMAIN}.selector.policy.options.ignore"] == (
        "Ignorieren" if language == "de" else "Ignore"
    )
