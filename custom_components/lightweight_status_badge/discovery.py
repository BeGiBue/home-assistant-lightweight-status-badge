"""On-demand registry and state discovery for the configuration UI, never polling."""

from homeassistant.components.lawn_mower.const import LawnMowerActivity
from homeassistant.components.vacuum.const import VacuumActivity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


def source_entities(
    hass: HomeAssistant, source_type: str, source_id: str
) -> list[er.RegistryEntry]:
    """Include operational, diagnostic, hidden and disabled entities from the selected source."""
    registry = er.async_get(hass)
    if source_type == "device":
        entries = er.async_entries_for_device(registry, source_id, include_disabled_entities=True)
    else:
        entries = er.async_entries_for_config_entry(registry, source_id)
    return sorted(
        entries,
        key=lambda entry: (entry.name or entry.original_name or entry.entity_id, entry.entity_id),
    )


def declared_options(hass: HomeAssistant, entity_id: str) -> list[str]:
    """Options the entity itself declares (registry capabilities, then state attributes)."""
    state = hass.states.get(entity_id)
    registered = er.async_get(hass).async_get(entity_id)
    values = []
    for metadata in (
        registered.capabilities if registered else None,
        state.attributes if state else None,
    ):
        options = (metadata or {}).get("options")
        if isinstance(options, (list, tuple)):
            values.extend(v for v in options if isinstance(v, str))
    return values


def state_choices(hass: HomeAssistant, entity_id: str) -> list[str]:
    """Declared options + standard HA activities + current state; never infer unknown codes."""
    state = hass.states.get(entity_id)
    values = declared_options(hass, entity_id)
    domain = entity_id.partition(".")[0]
    if domain == "vacuum":
        values.extend(VacuumActivity)
    elif domain == "lawn_mower":
        values.extend(LawnMowerActivity)
    elif domain in {"binary_sensor", "switch", "input_boolean", "update"}:
        values.extend(["on", "off"])
    if state:
        values.append(state.state)
    unique = {}
    for value in values:
        if value and len(value) <= 255 and value.casefold() not in {"unknown", "unavailable"}:
            unique.setdefault(value.casefold(), str(value))
    return sorted(unique.values(), key=str.casefold)
