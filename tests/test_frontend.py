"""Serve the bundled module through real HA HTTP; reload without duplicate routes."""

from pathlib import Path

from tests.test_integration import setup_entry


async def test_frontend_module_served_and_survives_reload(hass, hass_client):
    entry = await setup_entry(hass, [])
    client = await hass_client()
    url = "/lightweight_status_badge/frontend/lightweight-status-badge.js"
    response = await client.get(url)
    assert response.status == 200
    assert response.content_type in {"text/javascript", "application/javascript"}
    source = await hass.async_add_executor_job(
        Path("frontend/lightweight-status-badge.js").read_text
    )
    assert await response.text() == source
    assert "max-age=31536000" not in response.headers.get("Cache-Control", "")
    assert await hass.config_entries.async_reload(entry.entry_id)
    assert (await client.get(url)).status == 200


async def test_static_registration_failure_closes_monitoring(hass):
    from unittest.mock import patch

    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.lightweight_status_badge.const import DOMAIN

    assert await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    with patch.object(hass.http, "async_register_static_paths", side_effect=OSError("failed")):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data.closed
