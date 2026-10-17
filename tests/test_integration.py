"""HA entry setup/unload/reload, actual aggregate entities and bootstrap flow."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import CoreState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.lightweight_status_badge.const import DOMAIN


async def setup_entry(hass, rules):
    hass.set_state(CoreState.running)
    entry = MockConfigEntry(domain=DOMAIN, options={"rules": rules})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def tick(hass):
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()


async def test_sensors_reload_disable_remove(hass, rule_data):
    hass.states.async_set("sensor.ups", "OB")
    entry = await setup_entry(hass, [rule_data])
    states = {
        s.entity_id: s
        for s in hass.states.async_all()
        if s.entity_id.startswith(("sensor.lightweight_", "binary_sensor.lightweight_"))
    }
    assert len(states) == 4

    def by_id(suffix):
        return hass.states.get("sensor.lightweight_status_badge_" + suffix)

    assert by_id("unacknowledged_alerts").state == "1"
    assert by_id("active_alerts").state == "1"
    assert by_id("highest_unacknowledged_severity").state == "2"
    core = entry.runtime_data
    core.set_acknowledged("ups", core.alerts["ups"].occurrence, True)
    await tick(hass)
    assert by_id("unacknowledged_alerts").state == "0"
    assert by_id("active_alerts").state == "1"
    assert not any("alerts" in s.attributes for s in states.values())
    hass.config_entries.async_update_entry(
        entry, options={"rules": [{**rule_data, "enabled": False}]}
    )
    await hass.async_block_till_done()
    await tick(hass)
    assert core.closed
    assert entry.runtime_data.counts == (0, 0, 0)
    assert not entry.runtime_data.storage.data
    hass.config_entries.async_update_entry(entry, options={"rules": []})
    await hass.async_block_till_done()
    assert entry.runtime_data.rules == []
    last_core = entry.runtime_data
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert last_core.closed


async def test_invalid_config_is_setup_error(hass, rule_data):
    entry = MockConfigEntry(domain=DOMAIN, options={"rules": [rule_data, rule_data]})
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state == ConfigEntryState.SETUP_ERROR


async def test_storage_error_does_not_overwrite_acknowledgements(hass):
    # This test patches HA Store, so initialize HTTP's own storage first.
    assert await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.lightweight_status_badge.storage.Store.async_load",
            side_effect=ValueError("invalid data"),
        ),
        patch(
            "custom_components.lightweight_status_badge.storage.Store.async_save",
            new_callable=AsyncMock,
        ) as save,
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        save.assert_not_called()
    assert entry.state == ConfigEntryState.SETUP_RETRY


async def test_bootstrap_and_single_instance(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    second = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert second["type"] == FlowResultType.ABORT
    assert second["reason"] == "single_instance_allowed"
