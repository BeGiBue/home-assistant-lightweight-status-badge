"""Run real HA in a disposable config directory; invoke once, then with matching, then without.

Usage: python scripts/ha_smoke.py work/ha-smoke [matching]
Never point this script at a production configuration. Port 18123 must be free.
"""

import asyncio
import shutil
import sys
from pathlib import Path

from homeassistant import bootstrap
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.config_entries import ConfigEntryState
from homeassistant.runner import RuntimeConfig

DOMAIN = "lightweight_status_badge"


def prepare_config():
    config_dir = Path(sys.argv[1]).resolve()
    if config_dir.exists() and not (config_dir / ".review-smoke-config").exists():
        raise RuntimeError("Refusing an existing directory without smoke marker")
    if not config_dir.exists():
        config_dir.mkdir(parents=True)
        shutil.copytree(
            Path(__file__).resolve().parents[1] / "custom_components/lightweight_status_badge",
            config_dir / "custom_components/lightweight_status_badge",
        )
        (config_dir / "configuration.yaml").write_text(
            "homeassistant:\n  name: Installation review\n  latitude: 52\n"
            "  longitude: 13\n  elevation: 0\n  time_zone: Europe/Berlin\n"
            "  unit_system: metric\nhttp:\n  server_host: 127.0.0.1\n"
            "  server_port: 18123\nfrontend:\nconfig:\nlovelace:\n"
            "logger:\n  default: warning\n"
        )
    if not (config_dir / ".review-smoke-config").exists():
        if (config_dir / ".storage").exists():
            raise RuntimeError("Refusing an existing HA installation")
        (config_dir / ".review-smoke-config").touch()
    return config_dir


async def main(config_dir):
    hass = await bootstrap.async_setup_hass(RuntimeConfig(config_dir=str(config_dir)))
    assert hass is not None
    if len(sys.argv) > 2 and sys.argv[2] == "matching":
        hass.states.async_set("sensor.review_ups", "OB")
    await hass.async_start()
    await hass.async_block_till_done()
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        entry = result["result"]
        await hass.async_block_till_done()
        hass.config_entries.async_update_entry(
            entry,
            options={
                "rules": [{"id": "ups", "entity_id": "sensor.review_ups", "kind": "ups_status"}]
            },
        )
        await hass.async_block_till_done()
        hass.states.async_set("sensor.review_ups", "OB")
        await hass.async_block_till_done()
        core = entry.runtime_data
        core.set_acknowledged("ups", core.alerts["ups"].occurrence, True)
        assert core.counts == (0, 1, 0)
        print(
            "INSTALL: flow, options reload, state evaluation and acknowledgement passed", flush=True
        )
    else:
        entry = entries[0]
        hass.states.async_set("sensor.review_ups", "OB")
        await hass.async_block_till_done()
        # Source was missing on startup: its availability condition correctly invalidated old ack.
        assert entry.runtime_data.counts == ((0, 1, 0) if len(sys.argv) > 2 else (1, 1, 2))
        print("RESTART: persisted rules and acknowledgement reconciliation passed", flush=True)
    assert entry.state is ConfigEntryState.LOADED
    resources = hass.data[LOVELACE_DATA].resources.async_items()
    assert len([r for r in resources if "/lightweight_status_badge/" in r["url"]]) == 1
    print("RESOURCE: exactly one registered module", flush=True)
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get("http://127.0.0.1:18123" + resources[0]["url"]) as response:
            assert response.status == 200
            assert "class AlertStore" in await response.text()
    print("HTTP: installed frontend module served", flush=True)
    await hass.async_stop()


if __name__ == "__main__":
    asyncio.run(main(prepare_config()))
