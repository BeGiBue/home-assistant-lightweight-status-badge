"""Active acknowledgement storage using HA's queued, atomic asynchronous storage."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, SAVE_DELAY


class AcknowledgementStore:
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.store = Store(
            hass,
            1,
            f"{DOMAIN}.{entry_id}.acknowledgements",
            atomic_writes=True,
            serialize_in_event_loop=True,
        )
        self.data: dict[str, str] = {}

    async def load(self) -> dict[str, str]:
        data = await self.store.async_load()
        if data is None:
            return {}
        if not isinstance(data, dict) or not isinstance(data.get("acknowledgements"), dict):
            raise ValueError("Invalid acknowledgement storage")
        acks = data["acknowledgements"]
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in acks.items()):
            raise ValueError("Invalid acknowledgement identities")
        self.data = dict(acks)
        return dict(acks)

    def _snapshot(self) -> dict[str, dict[str, str]]:
        return {"acknowledgements": dict(self.data)}

    def update(self, data: dict[str, str]) -> None:
        if self.data != data:
            self.data = dict(data)
            # The callable reads the latest state at flush time, never a stale captured snapshot.
            self.store.async_delay_save(self._snapshot, SAVE_DELAY)

    async def flush(self) -> None:
        await self.store.async_save(self._snapshot())
