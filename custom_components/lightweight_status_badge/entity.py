"""Small event-driven aggregate entities. Alert payloads stay off the state machine."""

from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class AggregateEntity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, core, metric):
        self.core = core
        self.metric = metric
        self._attr_unique_id = f"{core.entry_id}_{metric}"
        self._attr_translation_key = metric
        self._attr_device_info = {
            "identifiers": {(DOMAIN, core.entry_id)},
            "name": "Lightweight Status Badge",
            "manufacturer": "Lightweight Status Badge",
        }

    async def async_added_to_hass(self):
        self.async_on_remove(self.core.subscribe(self.async_write_ha_state))
