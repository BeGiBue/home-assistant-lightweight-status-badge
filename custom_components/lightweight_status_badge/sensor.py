"""Unread count, active count and highest unread severity."""

from homeassistant.components.sensor import SensorEntity

from .entity import AggregateEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            AggregateSensor(entry.runtime_data, metric, index)
            for index, metric in enumerate(("unread_count", "active_count", "severity"))
        ]
    )


class AggregateSensor(AggregateEntity, SensorEntity):
    def __init__(self, core, metric, index):
        super().__init__(core, metric)
        self.index = index

    @property
    def native_value(self):
        return self.core.counts[self.index]
