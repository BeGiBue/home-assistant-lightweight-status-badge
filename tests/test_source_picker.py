"""Device/integration checkbox discovery, per-source drafts and fault-state choices."""

from unittest.mock import patch

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lightweight_status_badge.discovery import source_entities, state_choices
from tests.test_config_flow import go, manual, menu, start


@pytest.fixture
def robot_sources(hass, entity_registry, device_registry):
    first = MockConfigEntry(domain="test", title="Robot integration")
    second = MockConfigEntry(domain="test", title="Other instance")
    first.add_to_hass(hass)
    second.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=first.entry_id, identifiers={("test", "robot")}, name="Robot"
    )
    other = device_registry.async_get_or_create(
        config_entry_id=second.entry_id, identifiers={("test", "other")}, name="Other"
    )
    result = {}
    for domain, key, owner, device_id, extra in [
        ("vacuum", "vacuum", first, device.id, {}),
        ("lawn_mower", "mower", first, device.id, {}),
        ("sensor", "hidden", first, device.id, {"hidden_by": er.RegistryEntryHider.USER}),
        ("sensor", "disabled", first, device.id, {"disabled_by": er.RegistryEntryDisabler.USER}),
        ("sensor", "no_device", first, None, {}),
        ("vacuum", "other", second, other.id, {}),
    ]:
        result[key] = entity_registry.async_get_or_create(
            domain,
            "test",
            key,
            config_entry=owner,
            device_id=device_id,
            original_name=key,
            **extra,
        )
    hass.states.async_set(result["vacuum"].entity_id, "cleaning")
    hass.states.async_set(result["mower"].entity_id, "mowing")
    return first, second, device, result


def options(form, key):
    return form["data_schema"].schema[key].config["options"]


async def pick(hass, result, source_type, source_id):
    result = await menu(hass, result, "add")
    result = await menu(hass, result, source_type)
    return await go(
        hass, result, {"device_id" if source_type == "device" else "entry_id": source_id}
    )


async def test_device_list_includes_operational_hidden_disabled_without_enabling(
    hass,
    robot_sources,
    entity_registry,
):
    first, second, device, entities = robot_sources
    entry, result = await start(hass)
    result = await pick(hass, result, "device", device.id)
    assert result["step_id"] == "entities"
    config = result["data_schema"].schema["entity_ids"].config
    assert config["mode"] == "list"
    assert config["multiple"] is True
    assert {v["value"] for v in config["options"]} == {
        entities[k].entity_id for k in ("vacuum", "mower", "hidden", "disabled")
    }
    assert result["data_schema"]({})["entity_ids"] == []  # Nothing enrolled automatically.
    result = await go(hass, result, {"entity_ids": [entities["disabled"].entity_id]})
    result = await go(hass, result, {"preset": "custom"})
    result = await go(hass, result, {"operator": "eq", "value": "error"})
    await menu(hass, result, "save")
    assert entity_registry.async_get(entities["disabled"].entity_id).disabled_by
    assert entry.options["rules"][0]["entity_id"] == entities["disabled"].entity_id
    await hass.async_block_till_done()


async def test_integration_instance_includes_entities_without_device(hass, robot_sources):
    first, second, device, entities = robot_sources
    _, result = await start(hass)
    result = await menu(hass, result, "add")
    result = await menu(hass, result, "integration")
    assert {v["value"] for v in options(result, "entry_id")} >= {first.entry_id, second.entry_id}
    result = await go(hass, result, {"entry_id": first.entry_id})
    assert {v["value"] for v in options(result, "entity_ids")} == {
        entity.entity_id for key, entity in entities.items() if key != "other"
    }
    result = await go(hass, result, {"navigation": "back"})
    result = await go(hass, result, {"entry_id": second.entry_id})
    assert {v["value"] for v in options(result, "entity_ids")} == {entities["other"].entity_id}


async def test_batch_has_distinct_rules_and_per_entity_fault_states(hass, robot_sources):
    first, second, device, entities = robot_sources
    entry, result = await start(hass)
    result = await pick(hass, result, "device", device.id)
    chosen = [entities["vacuum"].entity_id, entities["mower"].entity_id]
    result = await go(hass, result, {"entity_ids": chosen})
    for index, entity_id in enumerate(chosen):
        assert result["step_id"] == "preset"
        assert result["description_placeholders"]["entity"] == entity_id
        assert result["data_schema"]({})["preset"] == "diagnostic_state"
        result = await go(hass, result, {})  # Apply the suggested preset.
        config = result["data_schema"].schema["states"].config
        assert config["mode"] == "list" and config["multiple"]
        assert not config["custom_value"]  # HA renders checkboxes only without custom values.
        assert "error" in config["options"]
        assert ("cleaning" if index == 0 else "mowing") in config["options"]
        assert result["data_schema"]({})["states"] == ["error"]
        result = await go(hass, result, {"states": ["error"]})
        assert len(entry.options["rules"]) == index  # Draft not saved yet.
        result = await menu(hass, result, "save")
        await hass.async_block_till_done()
    assert result["step_id"] == "init"
    rules = entry.options["rules"]
    assert len({rule["id"] for rule in rules}) == 2
    assert [rule["entity_id"] for rule in rules] == chosen
    assert not entry.runtime_data.alerts
    for entity_id in chosen:
        hass.states.async_set(entity_id, "error")
    await hass.async_block_till_done()
    assert entry.runtime_data.counts == (2, 2, 2)
    hass.states.async_set(chosen[0], "returning")
    hass.states.async_set(chosen[1], "docked")
    await hass.async_block_till_done()
    assert entry.runtime_data.counts == (0, 0, 0)


async def test_skip_and_cancel_do_not_silently_save_remaining_entities(hass, robot_sources):
    first, second, device, entities = robot_sources
    entry, result = await start(hass)
    result = await pick(hass, result, "device", device.id)
    result = await go(
        hass, result, {"entity_ids": [entities[k].entity_id for k in ("hidden", "vacuum", "mower")]}
    )
    result = await go(hass, result, {"navigation": "back"})
    assert "skip" in result["menu_options"]
    result = await menu(hass, result, "skip")
    assert result["description_placeholders"]["entity"] == entities["vacuum"].entity_id
    result = await go(hass, result, {})
    result = await go(hass, result, {"states": ["error"]})
    result = await menu(hass, result, "save")
    assert result["description_placeholders"]["entity"] == entities["mower"].entity_id
    result = await go(hass, result, {"navigation": "back"})
    result = await menu(hass, result, "cancel")
    assert result["step_id"] == "init"
    assert [r["entity_id"] for r in entry.options["rules"]] == [entities["vacuum"].entity_id]
    await hass.async_block_till_done()


async def test_membership_revalidated_if_entity_moves_during_selection(
    hass,
    robot_sources,
    entity_registry,
    device_registry,
):
    first, second, device, entities = robot_sources
    _, result = await start(hass)
    result = await pick(hass, result, "device", device.id)
    other = device_registry.async_get_or_create(
        config_entry_id=first.entry_id, identifiers={("test", "moved")}
    )
    entity_registry.async_update_entity(entities["vacuum"].entity_id, device_id=other.id)
    result = await go(hass, result, {"entity_ids": [entities["vacuum"].entity_id]})
    assert result["errors"] == {"entity_ids": "source_changed"}
    assert entities["vacuum"].entity_id not in {v["value"] for v in options(result, "entity_ids")}


async def test_empty_groups_selection_validation_and_navigation(hass, robot_sources):
    first, second, device, entities = robot_sources
    _, result = await start(hass)
    result = await pick(hass, result, "device", device.id)
    result = await go(hass, result, {})
    assert result["errors"] == {"entity_ids": "select_entities"}
    with patch("custom_components.lightweight_status_badge.config_flow.MAX_RULES", 1):
        result = await go(
            hass,
            result,
            {
                "entity_ids": [
                    entities["vacuum"].entity_id,
                    entities["mower"].entity_id,
                ]
            },
        )
        assert result["errors"] == {"base": "too_many_rules"}
    result = await go(hass, result, {"navigation": "back"})
    result = await go(hass, result, {"navigation": "back"})
    result = await menu(hass, result, "integration")
    # Use an integration with no registered entities, including no aggregates.
    empty = MockConfigEntry(domain="test", title="Empty")
    empty.add_to_hass(hass)
    result = await go(hass, result, {"navigation": "back"})
    result = await menu(hass, result, "integration")
    result = await go(hass, result, {"entry_id": empty.entry_id})
    assert result["errors"] == {"base": "no_entities"}


async def test_metadata_states_can_be_checked_and_custom_faults_added(hass):
    hass.states.async_set("sensor.machine", "ready", {"options": ["ready", "working", "jammed"]})
    entry, result = await start(hass)
    result = await manual(hass, result)
    result = await go(hass, result, {"entity_id": "sensor.machine"})
    assert result["data_schema"]({})["preset"] == "diagnostic_state"
    result = await go(hass, result, {})
    assert options(result, "states") == ["jammed", "ready", "working"]
    assert result["data_schema"]({})["states"] == []  # No invented fault interpretation.
    result = await go(hass, result, {})
    assert result["errors"] == {"base": "invalid_trigger"}
    result = await go(hass, result, {"states": ["jammed"], "additional_states": ["blocked"]})
    result = await menu(hass, result, "save")
    await hass.async_block_till_done()
    assert not entry.runtime_data.alerts
    hass.states.async_set("sensor.machine", "jammed")
    await hass.async_block_till_done()
    assert entry.runtime_data.counts == (1, 1, 2)
    hass.states.async_set("sensor.machine", "working")
    await hass.async_block_till_done()
    assert not entry.runtime_data.alerts
    # Disappearing options must not erase an existing configured fault state on edit.
    result = await menu(hass, result, "choose")
    result = await go(hass, result, {"rule_id": entry.options["rules"][0]["id"]})
    result = await menu(hass, result, "edit")
    result = await menu(hass, result, "trigger")
    assert set(options(result, "states")) == {"jammed", "blocked", "working"}
    assert result["data_schema"]({})["states"] == ["jammed", "blocked"]


async def test_capability_options_and_partial_current_state(hass, entity_registry):
    registered = entity_registry.async_get_or_create(
        "sensor",
        "test",
        "enum",
        capabilities={"options": ["OK", "failed", "unknown"]},
    )
    hass.states.async_set(registered.entity_id, "unavailable")
    assert state_choices(hass, registered.entity_id) == ["failed", "OK"]
    hass.states.async_set("sensor.numeric", "42", {"options": "not a list"})
    assert state_choices(hass, "sensor.numeric") == ["42"]
    assert state_choices(hass, "sensor.missing") == []
    assert set(state_choices(hass, "vacuum.missing")) >= {"cleaning", "error", "docked"}
    assert set(state_choices(hass, "lawn_mower.missing")) >= {"mowing", "error", "docked"}
    assert state_choices(hass, "binary_sensor.problem") == ["off", "on"]
    assert source_entities(hass, "integration", "missing") == []


async def test_http_exposes_native_checkboxes_for_entities_and_fault_states(
    hass,
    robot_sources,
    hass_client,
    hass_read_only_access_token,
):
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "config", {})
    _, _, device, entities = robot_sources
    entry, result = await start(hass)
    admin = await hass_client()
    readonly = await hass_client(hass_read_only_access_token)
    url = "/api/config/config_entries/options/flow/" + result["flow_id"]
    for data in ({"next_step_id": "add"}, {"next_step_id": "device"}, {"device_id": device.id}):
        response = await admin.post(url, json=data)
        assert response.status == 200
        result = await response.json()
    entities_field = next(f for f in result["data_schema"] if f["name"] == "entity_ids")
    selection = entities_field["selector"]["select"]
    assert selection["multiple"] and selection["mode"] == "list"
    assert not selection["custom_value"]
    assert entities["vacuum"].entity_id in {option["value"] for option in selection["options"]}
    blocked = await readonly.post(
        url,
        json={"entity_ids": [entities["vacuum"].entity_id]},
        headers={"Authorization": f"Bearer {hass_read_only_access_token}"},
    )
    assert blocked.status == 401
    for data in ({"entity_ids": [entities["vacuum"].entity_id]}, {}):
        response = await admin.post(url, json=data)
        assert response.status == 200
        result = await response.json()
    states_field = next(f for f in result["data_schema"] if f["name"] == "states")
    selection = states_field["selector"]["select"]
    assert selection["mode"] == "list" and selection["multiple"]
    assert not selection["custom_value"]
    assert "error" in selection["options"]
    assert not entry.options["rules"]


async def test_removed_device_and_integration_report_validation_errors(
    hass,
    robot_sources,
    device_registry,
):
    first, second, device, entities = robot_sources
    _, result = await start(hass)
    result = await menu(hass, result, "add")
    result = await menu(hass, result, "device")
    device_registry.async_remove_device(device.id)
    result = await go(hass, result, {"device_id": device.id})
    assert result["errors"] == {"device_id": "invalid_device"}
    result = await go(hass, result, {"navigation": "back"})
    result = await menu(hass, result, "integration")
    result = await go(hass, result, {})
    assert result["errors"] == {"entry_id": "invalid_integration"}
