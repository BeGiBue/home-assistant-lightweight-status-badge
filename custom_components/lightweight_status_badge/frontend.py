"""Register the bundled module in HA's storage-managed Lovelace resources."""

import logging
from hashlib import sha256
from pathlib import Path

from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
RESOURCE_URL = "/lightweight_status_badge/frontend/lightweight-status-badge.js"


async def async_register_resource(hass: HomeAssistant) -> None:
    """Use the collection API; never write .storage or YAML directly."""
    lovelace = hass.data.get(LOVELACE_DATA)
    if lovelace is None or not isinstance(lovelace.resources, ResourceStorageCollection):
        _LOGGER.warning("Add %s as a JavaScript module in Lovelace resources", RESOURCE_URL)
        return
    collection = lovelace.resources
    await collection.async_get_info()  # Ensure persisted items are loaded before deduplication.
    digest = await hass.async_add_executor_job(
        lambda: sha256(
            (Path(__file__).parent / "www/lightweight-status-badge.js").read_bytes()
        ).hexdigest()[:12]
    )
    url = f"{RESOURCE_URL}?v={digest}"
    matching = [
        item for item in collection.async_items() if item["url"].split("?", 1)[0] == RESOURCE_URL
    ]
    if not matching:
        await collection.async_create_item({"url": url, "res_type": "module"})
        return
    for item in matching:
        if item["url"] != url or item["type"] != "module":
            await collection.async_update_item(item["id"], {"url": url, "res_type": "module"})
