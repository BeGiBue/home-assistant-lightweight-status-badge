"""Reproducible event-path measurements; no hardware-specific timing assertions."""

import json
import platform
import time
import tracemalloc
from unittest.mock import Mock, patch

import pytest
from homeassistant.core import CoreState

from custom_components.lightweight_status_badge.coordinator import Coordinator


@pytest.mark.parametrize("size", [30, 100])
async def test_selected_entity_burst(hass, size, record_property):
    hass.set_state(CoreState.running)
    rules = [
        {"id": f"r{i}", "entity_id": f"sensor.selected_{i}", "kind": "positive_count"}
        for i in range(size)
    ]
    core = Coordinator(hass, f"perf-{size}", rules)
    await core.async_start()
    listener = Mock()
    core.subscribe(listener)
    before = core.evaluations
    # Keep every value in the matching condition, with a changing numeric raw state.
    # The number of evaluations must equal the selected events, not events * rules.
    tracemalloc.start()
    cpu_start = time.process_time()
    wall_start = time.perf_counter()
    with patch.object(core.storage.store, "async_delay_save") as save:
        for round_ in range(1, 101):
            for i in range(size):
                hass.states.async_set(f"sensor.selected_{i}", str(round_))
            hass.states.async_set("sensor.unselected", str(round_))
            await hass.async_block_till_done()
        assert core.evaluations - before == size * 100
        save.assert_not_called()
    wall = time.perf_counter() - wall_start
    cpu = time.process_time() - cpu_start
    retained, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert core.counts == (size, size, 2)
    assert listener.call_count < size * 100
    assert len(core.details()["alerts"]) == size
    result = {
        "entities": size,
        "events": size * 100,
        "cpu_seconds": round(cpu, 4),
        "wall_seconds": round(wall, 4),
        "traced_retained_kib": round(retained / 1024, 1),
        "traced_peak_kib": round(peak / 1024, 1),
        "refreshes": listener.call_count,
        "platform": platform.machine(),
        "python": platform.python_version(),
    }
    print("\nPERFORMANCE " + json.dumps(result))
    record_property("performance", json.dumps(result))
    await core.async_close()
