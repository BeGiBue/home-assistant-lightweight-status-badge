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
        self._save_pending = False

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
            if not self._save_pending:
                # Bound the coalescing window from the first mutation. Repeated actions
                # must not postpone persistence indefinitely during a sustained burst.
                self._save_pending = True
                self.store.async_delay_save(self._snapshot_for_write, SAVE_DELAY)

    def _snapshot_for_write(self) -> dict[str, dict[str, str]]:
        self._save_pending = False
        return self._snapshot()

    async def flush(self) -> None:
        self._save_pending = False
        await self.store.async_save(self._snapshot())
