"""A native conditional-visibility input; false when every active alert is acknowledged."""

from homeassistant.components.binary_sensor import BinarySensorEntity

from .entity import AggregateEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([HasUnread(entry.runtime_data, "has_unacknowledged_alerts")])


class HasUnread(AggregateEntity, BinarySensorEntity):
    @property
    def is_on(self):
        return self.core.counts[0] > 0
