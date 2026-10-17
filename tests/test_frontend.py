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


async def test_storage_resource_registration_create_update_and_reload(hass):
    from homeassistant.components.lovelace.const import LOVELACE_DATA
    from homeassistant.setup import async_setup_component

    from custom_components.lightweight_status_badge.frontend import (
        RESOURCE_URL,
        async_register_resource,
    )

    assert await async_setup_component(hass, "lovelace", {"lovelace": {}})
    resources = hass.data[LOVELACE_DATA].resources
    foreign = await resources.async_create_item(
        {"url": "https://example.com" + RESOURCE_URL, "res_type": "module"}
    )
    await resources.async_create_item({"url": RESOURCE_URL, "res_type": "js"})
    await async_register_resource(hass)
    assert resources.async_items()[0] == foreign
    items = resources.async_items()[1:]
    assert len(items) == 1
    assert items[0]["type"] == "module"
    assert items[0]["url"].startswith(RESOURCE_URL + "?v=")
    before = list(resources.async_items())
    await async_register_resource(hass)
    assert resources.async_items() == before
    await resources.async_delete_item(items[0]["id"])
    await async_register_resource(hass)
    assert len(resources.async_items()) == 2


async def test_yaml_resources_are_not_mutated(hass, caplog):
    from types import SimpleNamespace

    from homeassistant.components.lovelace.const import LOVELACE_DATA
    from homeassistant.components.lovelace.resources import ResourceYAMLCollection

    from custom_components.lightweight_status_badge.frontend import async_register_resource

    collection = ResourceYAMLCollection([])
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=collection)
    await async_register_resource(hass)
    assert collection.async_items() == []
    assert "JavaScript module" in caplog.text
