"""Entity-indexed event processing and global active-alert state."""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from html import escape
from typing import Any
from uuid import uuid4

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CoreState, Event, HomeAssistant, State, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .const import DISPATCH_DELAY, MAX_RULES, PAGE_SIZE, SIGNAL_UPDATED
from .messages import MESSAGES, render
from .rules import Rule, evaluate
from .storage import AcknowledgementStore


@dataclass
class Alert:
    rule: Rule
    identity: str
    condition: str
    severity: int
    message_ids: tuple[str, ...]
    raw_state: str
    attributes: dict
    occurrence: str
    started: str
    acknowledged: bool = False


class Coordinator:
    """All mutations run synchronously in HA's event loop, without intervening awaits."""

    def __init__(self, hass: HomeAssistant, entry_id: str, rule_data: list[dict]) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.rules = self.validate_rules(rule_data)
        self.by_entity = defaultdict(list)
        for rule in self.rules:
            if rule.enabled:
                self.by_entity[rule.entity_id].append(rule)
        self.alerts: dict[str, Alert] = {}
        self.storage = AcknowledgementStore(hass, entry_id)
        self.pending: dict[str, str] = {}
        self.listeners = set()
        self.unsubs = []
        self.cancel_dispatch = None
        self.initializing = True
        self.closed = False
        self.revision = 0
        self.evaluations = 0

    @staticmethod
    def validate_rules(data: list[dict]) -> list[Rule]:
        if not isinstance(data, list) or len(data) > MAX_RULES:
            raise ValueError(f"rules must be a list of at most {MAX_RULES}")
        rules = [Rule.from_dict(r) for r in data]
        if len({r.id for r in rules}) != len(rules):
            raise ValueError("duplicate rule ids")
        return rules

    async def async_start(self) -> None:
        self.pending = await self.storage.load()
        if self.by_entity:
            self.unsubs.append(
                async_track_state_change_event(self.hass, list(self.by_entity), self._state_changed)
            )
        self.unsubs.append(self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._stop))
        # Restore integrations may emit temporary unknown/unavailable during startup.
        # Do not destroy pending acks until HA has finished setting up integrations.
        if self.hass.state == CoreState.running:
            self._finish_startup(None)
        else:
            self._evaluate_all()
            self.unsubs.append(
                self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, self._finish_startup)
            )

    def _evaluate_all(self) -> None:
        for entity_id in self.by_entity:
            self._evaluate_entity(entity_id, self.hass.states.get(entity_id))

    @callback
    def _finish_startup(self, _event: Event | None) -> None:
        self.initializing = False
        self._evaluate_all()
        self.pending.clear()
        self._persist()
        self._changed()

    @callback
    def _state_changed(self, event: Event) -> None:
        if self.closed:
            return
        self._evaluate_entity(event.data["entity_id"], event.data.get("new_state"))

    def _evaluate_entity(self, entity_id: str, state: State | None) -> None:
        raw = state.state if state else "unavailable"
        attributes = state.attributes if state else {}
        changed = False
        persistence_changed = False
        for rule in self.by_entity.get(entity_id, ()):
            self.evaluations += 1
            match = evaluate(rule, raw)
            old = self.alerts.get(rule.id)
            deferred = self.initializing and raw in {"unknown", "unavailable"}
            if deferred and old and old.acknowledged:
                self.pending[rule.id] = old.identity
                persistence_changed = True
            if not deferred:
                pending = self.pending.pop(rule.id, None)
                persistence_changed |= pending is not None
            else:
                pending = None
            if match is None:
                if old:
                    del self.alerts[rule.id]
                    persistence_changed |= old.acknowledged
                    changed = True
                continue
            identity = sha256(f"{rule.fingerprint}:{match.condition}".encode()).hexdigest()
            attrs = {
                k: v
                for k in rule.attributes
                if isinstance(v := attributes.get(k), (str, int, float, bool))
            }
            # Only explicitly used attributes are retained; bound values as well as payloads.
            attrs = {k: str(v)[:255] for k, v in attrs.items()}
            if old and old.identity == identity:
                if pending == identity and not old.acknowledged:
                    old.acknowledged = True
                    persistence_changed = changed = True
                if old.raw_state != raw or old.attributes != attrs:
                    old.raw_state, old.attributes = raw, attrs
                    changed = True
                continue
            persistence_changed |= bool(old and old.acknowledged) or pending == identity
            self.alerts[rule.id] = Alert(
                rule,
                identity,
                match.condition,
                match.severity,
                match.message_ids,
                raw,
                attrs,
                uuid4().hex,
                datetime.now(UTC).isoformat(),
                pending == identity,
            )
            changed = True
        if persistence_changed:
            self._persist()
        if changed:
            self._changed()

    def _persist(self) -> None:
        data = dict(self.pending) if self.initializing else {}
        data.update(
            {key: alert.identity for key, alert in self.alerts.items() if alert.acknowledged}
        )
        self.storage.update(data)

    @callback
    def set_acknowledged(self, rule_id: str, occurrence: str, acknowledged: bool) -> None:
        if self.closed:
            raise ValueError("Integration is stopped")
        alert = self.alerts.get(rule_id)
        if alert is None or alert.occurrence != occurrence:
            raise ValueError("Alert no longer active or occurrence changed; refresh details")
        if alert.acknowledged != acknowledged:
            alert.acknowledged = acknowledged
            self._persist()
            self._changed()

    @property
    def counts(self) -> tuple[int, int, int]:
        unread = [a for a in self.alerts.values() if not a.acknowledged]
        return len(unread), len(self.alerts), max((a.severity for a in unread), default=0)

    def details(
        self,
        language: str = "en",
        offset: int = 0,
        can_read: Callable[[str], bool] = lambda _id: True,
    ) -> dict[str, Any]:
        messages = MESSAGES.get(language.split("-")[0], MESSAGES["en"])
        alerts = sorted(
            (a for a in self.alerts.values() if can_read(a.rule.entity_id)),
            key=lambda a: (-a.severity, a.rule.id),
        )
        records = []
        for a in alerts[offset : offset + PAGE_SIZE]:
            rule = a.rule
            default = " ".join(messages[key] for key in a.message_ids)
            # Availability always explains the specific condition, even with custom messages.
            description = (
                default if a.condition in {"unknown", "unavailable"} else (rule.message or default)
            )
            records.append(
                {
                    "rule_id": rule.id,
                    "occurrence": a.occurrence,
                    "entity_id": rule.entity_id,
                    "title": escape(rule.label or rule.entity_id),
                    "severity": a.severity,
                    "acknowledged": a.acknowledged,
                    "description": render(description, a.raw_state, a.attributes, rule.attributes),
                    "recommendation": render(
                        rule.recommendation, a.raw_state, a.attributes, rule.attributes
                    ),
                    "raw_state": escape(a.raw_state),
                    "started": a.started,
                    "message_ids": list(a.message_ids),
                }
            )
        return {
            "revision": self.revision,
            "alerts": records,
            "total": len(alerts),
            "next_offset": offset + PAGE_SIZE if offset + PAGE_SIZE < len(alerts) else None,
        }

    @callback
    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        self.listeners.add(listener)
        return lambda: self.listeners.discard(listener)

    def _changed(self) -> None:
        self.revision += 1
        if self.cancel_dispatch is None and not self.closed:
            self.cancel_dispatch = async_call_later(self.hass, DISPATCH_DELAY, self._dispatch)

    @callback
    def _dispatch(self, _now: datetime) -> None:
        self.cancel_dispatch = None
        for listener in tuple(self.listeners):
            listener()
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    async def _stop(self, _event: Event) -> None:
        # Ignore teardown-generated unavailable states; they are not resolved faults.
        await self.async_close()

    async def async_close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for unsub in self.unsubs:
            unsub()
        self.unsubs.clear()
        if self.cancel_dispatch:
            self.cancel_dispatch()
            self.cancel_dispatch = None
        self.listeners.clear()
        await self.storage.flush()
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)
