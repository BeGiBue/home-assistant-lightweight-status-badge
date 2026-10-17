"""Exercise HA atomic storage against actual temporary files (not the fixture store)."""

import json
from unittest.mock import patch

from homeassistant.helpers.storage import Store

from custom_components.lightweight_status_badge.storage import AcknowledgementStore

# Capture before HA's hass_storage fixture patches the class methods.
REAL_LOAD = Store._async_load
REAL_WRITE = Store._async_write_data


async def test_file_roundtrip_and_latest_delayed_snapshot(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    with (
        patch.object(Store, "_async_load", REAL_LOAD),
        patch.object(Store, "_async_write_data", REAL_WRITE),
    ):
        store = AcknowledgementStore(hass, "disk-test")
        assert store.store._atomic_writes
        assert await store.load() == {}
        store.update({"fault": "condition"})
        # Execute the actual pending save callback; verify the on-disk JSON.
        await store.store._async_callback_delayed_write()
        path = tmp_path / ".storage" / store.store.key
        document = await hass.async_add_executor_job(lambda: json.loads(path.read_text()))
        assert document["data"] == {"acknowledgements": {"fault": "condition"}}
        fresh = AcknowledgementStore(hass, "disk-test")
        assert await fresh.load() == {"fault": "condition"}
        fresh.update({"fault": "condition", "other": "second"})
        fresh.update({})  # Fault resolution wins over an already queued acknowledgement.
        await fresh.store._async_callback_delayed_write()
        again = AcknowledgementStore(hass, "disk-test")
        assert await again.load() == {}
        document = await hass.async_add_executor_job(lambda: json.loads(path.read_text()))
        assert document["data"] == {"acknowledgements": {}}
        assert set(document["data"]) == {"acknowledgements"}


async def test_ack_burst_does_not_postpone_first_save(hass):
    store = AcknowledgementStore(hass, "burst")
    with patch.object(store.store, "async_delay_save") as schedule:
        store.update({"first": "one"})
        store.update({"first": "one", "second": "two"})
        store.update({"second": "two"})
        schedule.assert_called_once()
        callback, delay = schedule.call_args.args
        assert delay == 1
        assert callback() == {"acknowledgements": {"second": "two"}}
        store.update({"third": "three"})
        assert schedule.call_count == 2
        assert schedule.call_args.args[0]() == {"acknowledgements": {"third": "three"}}
