"""Real HA events, real storage, reconnects, startup reconciliation and lifecycle."""

from datetime import timedelta
from unittest.mock import Mock

import pytest
from homeassistant.core import CoreState
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.lightweight_status_badge.coordinator import Coordinator


async def start(hass, data, entry_id="test"):
    hass.set_state(CoreState.running)
    core = Coordinator(hass, entry_id, [data])
    await core.async_start()
    return core


async def state(hass, value):
    hass.states.async_set("sensor.ups", value)
    await hass.async_block_till_done()


async def test_global_ack_resolve_recur_and_stale_action(hass, rule_data):
    await state(hass, "OB")
    core = await start(hass, rule_data)
    occurrence = core.alerts["ups"].occurrence
    core.set_acknowledged("ups", occurrence, True)
    assert core.counts == (0, 1, 0)
    assert core.details()["alerts"][0]["acknowledged"]
    core.set_acknowledged("ups", occurrence, False)
    assert core.counts == (1, 1, 2)
    core.set_acknowledged("ups", occurrence, True)
    await state(hass, "OL")
    assert core.counts == (0, 0, 0)
    assert core.storage.data == {}
    await state(hass, "OB")
    assert core.counts == (1, 1, 2)
    with pytest.raises(ValueError):
        core.set_acknowledged("ups", occurrence, True)
    await core.async_close()


async def test_real_storage_restart_and_condition_change(hass, rule_data):
    await state(hass, "OB")
    core = await start(hass, rule_data)
    core.set_acknowledged("ups", core.alerts["ups"].occurrence, True)
    await core.async_close()
    restored = await start(hass, rule_data)
    assert restored.counts == (0, 1, 0)
    await state(hass, "OB DISCHRG")
    assert restored.counts == (0, 1, 0)
    await state(hass, "OB LB")
    assert restored.counts == (1, 1, 3)
    assert restored.storage.data == {}
    await restored.async_close()


@pytest.mark.parametrize("temporary", ["unknown", " UNKNOWN "])
async def test_startup_unknown_does_not_destroy_restoration(hass, rule_data, temporary):
    await state(hass, "OB")
    core = await start(hass, rule_data)
    core.set_acknowledged("ups", core.alerts["ups"].occurrence, True)
    await core.async_close()
    hass.set_state(CoreState.starting)
    await state(hass, temporary)
    restored = Coordinator(hass, "test", [rule_data])
    await restored.async_start()
    assert restored.pending
    await state(hass, "unavailable")
    await state(hass, "OB")
    hass.bus.async_fire("homeassistant_started")
    await hass.async_block_till_done()
    assert restored.counts == (0, 1, 0)
    assert not restored.pending
    await restored.async_close()


async def test_startup_stale_ack_removed_and_missing_entity(hass, rule_data):
    await state(hass, "OB")
    core = await start(hass, rule_data)
    core.set_acknowledged("ups", core.alerts["ups"].occurrence, True)
    await core.async_close()
    hass.states.async_remove("sensor.ups")
    restored = await start(hass, rule_data)
    assert restored.counts == (1, 1, 2)
    assert restored.alerts["ups"].condition == "unavailable"
    assert restored.storage.data == {}
    await restored.async_close()


async def test_reconnect_new_alert_and_removal(hass, rule_data):
    await state(hass, "OB")
    core = await start(hass, rule_data)
    core.set_acknowledged("ups", core.alerts["ups"].occurrence, True)
    await state(hass, "unavailable")
    assert not core.alerts["ups"].acknowledged
    await state(hass, "OB")
    assert not core.alerts["ups"].acknowledged
    hass.states.async_remove("sensor.ups")
    await hass.async_block_till_done()
    assert core.alerts["ups"].condition == "unavailable"
    await core.async_close()


async def test_latest_snapshot_wins_delayed_save(hass, rule_data):
    await state(hass, "OB")
    core = await start(hass, rule_data)
    core.set_acknowledged("ups", core.alerts["ups"].occurrence, True)
    await state(hass, "OL")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done()
    await core.async_close()
    await state(hass, "OB")
    restored = await start(hass, rule_data)
    assert restored.counts == (1, 1, 2)
    await restored.async_close()


async def test_event_index_and_dispatch_coalescing(hass, rule_data):
    core = await start(hass, rule_data)
    listener = Mock()
    unsub = core.subscribe(listener)
    before = core.evaluations
    hass.states.async_set("sensor.unselected", "OB")
    for value in ["OB", "OL", "OB LB", "OB", "OL"]:
        hass.states.async_set("sensor.ups", value)
    await hass.async_block_till_done()
    assert core.evaluations - before == 5
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    listener.assert_called_once()
    unsub()
    await core.async_close()
    before = core.evaluations
    await state(hass, "OB")
    assert core.evaluations == before


@pytest.mark.parametrize(
    "change", [{"enabled": False}, {"kind": "binary_on"}, {"entity_id": "sensor.other"}]
)
async def test_rule_edit_invalidates_ack(hass, rule_data, change):
    await state(hass, "OB")
    core = await start(hass, rule_data)
    core.set_acknowledged("ups", core.alerts["ups"].occurrence, True)
    await core.async_close()
    restored = await start(hass, {**rule_data, **change})
    assert restored.storage.data == {}
    assert not any(a.acknowledged for a in restored.alerts.values())
    await restored.async_close()


async def test_payload_escaping_whitelist_and_pagination(hass, rule_data):
    hass.states.async_set("sensor.ups", "OB", {"public": "<b>", "secret": "HIDDEN"})
    core = await start(
        hass,
        {
            **rule_data,
            "label": "<script>",
            "attributes": ["public"],
            "message": "{state} {attributes.public} {attributes.secret}",
        },
    )
    record = core.details("de")["alerts"][0]
    assert record["title"] == "&lt;script&gt;"
    assert record["description"] == "OB &lt;b&gt; "
    assert "HIDDEN" not in str(record)
    assert core.details(can_read=lambda _: False)["total"] == 0
    await core.async_close()


def test_duplicate_ids_rejected(rule_data):
    with pytest.raises(ValueError):
        Coordinator.validate_rules([rule_data, rule_data])


async def test_graceful_stop_freezes_ack_before_teardown(hass, rule_data):
    await state(hass, "OB")
    core = await start(hass, rule_data)
    core.set_acknowledged("ups", core.alerts["ups"].occurrence, True)
    hass.bus.async_fire("homeassistant_stop")
    await hass.async_block_till_done()
    assert core.closed
    await state(hass, "unavailable")
    assert core.alerts["ups"].acknowledged
    assert core.storage.data == {"ups": core.alerts["ups"].identity}
    await state(hass, "OB")
    restored = await start(hass, rule_data)
    assert restored.counts == (0, 1, 0)
    await restored.async_close()


async def test_transient_unknown_after_initial_restore(hass, rule_data):
    await state(hass, "OB")
    core = await start(hass, rule_data)
    core.set_acknowledged("ups", core.alerts["ups"].occurrence, True)
    await core.async_close()
    hass.set_state(CoreState.starting)
    restored = Coordinator(hass, "test", [rule_data])
    await restored.async_start()
    assert restored.alerts["ups"].acknowledged
    await state(hass, "unknown")
    await state(hass, "OB")
    hass.bus.async_fire("homeassistant_started")
    await hass.async_block_till_done()
    assert restored.alerts["ups"].acknowledged
    await restored.async_close()


async def test_availability_ack_restored_after_startup(hass, rule_data):
    await state(hass, "unavailable")
    core = await start(hass, rule_data)
    core.set_acknowledged("ups", core.alerts["ups"].occurrence, True)
    await core.async_close()
    hass.set_state(CoreState.starting)
    restored = Coordinator(hass, "test", [rule_data])
    await restored.async_start()
    hass.bus.async_fire("homeassistant_started")
    await hass.async_block_till_done()
    assert restored.counts == (0, 1, 0)
    await restored.async_close()


async def test_code_change_is_new_condition(hass):
    data = {
        "id": "code",
        "entity_id": "sensor.ups",
        "kind": "nonzero_code",
        "unknown_policy": "ignore",
        "unavailable_policy": "ignore",
    }
    await state(hass, "42")
    core = await start(hass, data)
    core.set_acknowledged("code", core.alerts["code"].occurrence, True)
    await state(hass, "43")
    assert core.counts == (1, 1, 2)
    assert "43" == core.details()["alerts"][0]["raw_state"]
    assert "43" not in core.details()["alerts"][0]["description"]
    await core.async_close()


async def test_display_edit_preserves_ack_but_threshold_edit_does_not(hass):
    data = {
        "id": "count",
        "entity_id": "sensor.ups",
        "kind": "positive_count",
        "config": {"threshold": 0},
    }
    await state(hass, "10")
    core = await start(hass, data)
    core.set_acknowledged("count", core.alerts["count"].occurrence, True)
    await core.async_close()
    display_edit = await start(hass, {**data, "label": "New label", "message": "New text"})
    assert display_edit.counts == (0, 1, 0)
    await display_edit.async_close()
    trigger_edit = await start(hass, {**data, "config": {"threshold": 5}})
    assert trigger_edit.counts == (1, 1, 2)
    await trigger_edit.async_close()


async def test_multiple_rules_same_entity_and_paged_details(hass):
    hass.set_state(CoreState.running)
    await state(hass, "OB")
    rules = [{"id": f"r{i}", "entity_id": "sensor.ups", "kind": "ups_status"} for i in range(101)]
    core = Coordinator(hass, "pages", rules)
    await core.async_start()
    assert core.counts == (101, 101, 2)
    first = core.details()
    assert len(first["alerts"]) == 100
    assert first["next_offset"] == 100
    second = core.details(offset=100)
    assert len(second["alerts"]) == 1
    assert second["next_offset"] is None
    before = core.evaluations
    await state(hass, "OL")
    assert core.evaluations - before == 101
    assert core.counts == (0, 0, 0)
    await core.async_close()


async def test_stopping_state_flushes_on_ha_final_write(hass, hass_storage, rule_data):
    await state(hass, "OB")
    core = await start(hass, rule_data)
    core.set_acknowledged("ups", core.alerts["ups"].occurrence, True)
    expected = {"ups": core.alerts["ups"].identity}
    hass.set_state(CoreState.stopping)
    hass.bus.async_fire("homeassistant_stop")
    await hass.async_block_till_done()
    await state(hass, "unavailable")
    hass.bus.async_fire("homeassistant_final_write")
    await hass.async_block_till_done()
    assert hass_storage[core.storage.store.key]["data"]["acknowledgements"] == expected
    hass.set_state(CoreState.running)


async def test_consumed_startup_and_stop_listeners_do_not_log_errors(hass, rule_data, caplog):
    hass.set_state(CoreState.starting)
    core = Coordinator(hass, "listeners", [rule_data])
    await core.async_start()
    hass.bus.async_fire("homeassistant_started")
    await hass.async_block_till_done()
    hass.bus.async_fire("homeassistant_stop")
    await hass.async_block_till_done()
    assert core.closed
    assert not core.unsubs
    assert "Unable to remove unknown job listener" not in caplog.text
