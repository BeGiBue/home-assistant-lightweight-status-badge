"""Home Assistant entry lifecycle for Lightweight Status Badge."""

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady

from .api import async_register
from .const import DOMAIN, PLATFORMS
from .coordinator import Coordinator
from .storage import AcknowledgementStore

type StatusBadgeConfigEntry = ConfigEntry[Coordinator]


async def async_setup_entry(hass: HomeAssistant, entry: StatusBadgeConfigEntry) -> bool:
    try:
        core = Coordinator(hass, entry.entry_id, entry.options.get("rules", []))
    except (ValueError, TypeError) as err:
        raise ConfigEntryError(f"Invalid rules: {err}") from err
    try:
        await core.async_start()
    except Exception as err:
        # Do not quietly discard unreadable persistence and present a successful setup.
        raise ConfigEntryNotReady(f"Cannot load acknowledgements: {err}") from err
    entry.runtime_data = core
    try:
        if DOMAIN not in hass.data:
            await hass.http.async_register_static_paths(
                [
                    StaticPathConfig(
                        "/lightweight_status_badge/frontend",
                        str(Path(__file__).parent / "www"),
                        False,
                    )
                ]
            )
            async_register(hass)
            hass.data[DOMAIN] = True
        entry.async_on_unload(entry.add_update_listener(async_options_updated))
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await core.async_close()
        raise
    return True


async def async_options_updated(hass: HomeAssistant, entry: StatusBadgeConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: StatusBadgeConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.async_close()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: StatusBadgeConfigEntry) -> None:
    await AcknowledgementStore(hass, entry.entry_id).store.async_remove()
