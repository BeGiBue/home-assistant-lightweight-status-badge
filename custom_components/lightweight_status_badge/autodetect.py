"""Automatic rule proposals for a chosen source: catalog first, then local heuristic.

Runs on demand inside the options flow only. It never subscribes to anything and never
writes configuration; the flow decides what to persist.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from uuid import uuid4

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .catalog import CatalogRule, async_load_catalog, match_catalog
from .discovery import declared_options, source_entities
from .rules import Rule

FAULT_STATES = frozenset({"error", "warning", "fault", "failed"})
# Binary sensor device class -> severity of an "on" state.
BINARY_SEVERITY = {
    "problem": 2,
    "tamper": 2,
    "moisture": 2,
    "battery": 1,
    "safety": 3,
    "smoke": 3,
    "gas": 3,
    "carbon_monoxide": 3,
}


@dataclass(frozen=True)
class Proposal:
    """A ready-to-save rule for one entity, not yet persisted."""

    entity_id: str
    kind: str
    severity: int
    unknown_policy: str
    unavailable_policy: str
    config: dict = field(default_factory=dict)

    def to_rule(self) -> dict:
        return {
            "id": uuid4().hex,
            "entity_id": self.entity_id,
            "kind": self.kind,
            "severity": self.severity,
            "unknown_policy": self.unknown_policy,
            "unavailable_policy": self.unavailable_policy,
            "config": deepcopy(self.config),
            "message": "",  # Empty: backend uses locale-aware, token-specific explanations.
        }


@dataclass(frozen=True)
class Detection:
    """Outcome of the automatic stage. ``origin`` is catalog, heuristic or none (manual)."""

    origin: str
    catalog_origin: str = "none"  # online, bundled or none
    description: str = ""
    proposals: tuple[Proposal, ...] = ()


def _device_class(hass: HomeAssistant, entry: er.RegistryEntry) -> str | None:
    if device_class := entry.device_class or entry.original_device_class:
        return device_class
    state = hass.states.get(entry.entity_id)
    return state.attributes.get("device_class") if state else None


def _matches(hass: HomeAssistant, match: dict, entry: er.RegistryEntry) -> bool:
    category = entry.entity_category.value if entry.entity_category else None
    actual = {
        "domain": entry.domain,
        "device_class": _device_class(hass, entry),
        "translation_key": entry.translation_key,
        "entity_category": category,
    }
    return all(actual[key] == value for key, value in match.items())


def _from_catalog(
    hass: HomeAssistant,
    entries: list[er.RegistryEntry],
    rules: tuple[CatalogRule, ...],
    skip: frozenset[str],
) -> list[Proposal]:
    proposals = []
    for entry in entries:
        if entry.entity_id in skip:
            continue
        for rule in rules:
            if not _matches(hass, rule.match, entry):
                continue
            proposal = Proposal(
                entry.entity_id,
                rule.kind,
                rule.severity,
                rule.unknown_policy,
                rule.unavailable_policy,
                rule.config,
            )
            try:
                Rule.from_dict(proposal.to_rule())
            except ValueError, TypeError:
                continue  # e.g. update_available for a non-update entity
            proposals.append(proposal)
            break  # First matching catalog rule wins per entity.
    return proposals


def _heuristic_for(hass: HomeAssistant, entry: er.RegistryEntry) -> Proposal | None:
    """Conservative rules from standard HA metadata only; never from guessed meanings."""
    device_class = _device_class(hass, entry)
    if entry.domain == "binary_sensor" and device_class in BINARY_SEVERITY:
        return Proposal(
            entry.entity_id, "binary_on", BINARY_SEVERITY[device_class], "ignore", "warning"
        )
    if (
        entry.domain == "binary_sensor"
        and device_class == "connectivity"
        and entry.entity_category == EntityCategory.DIAGNOSTIC
    ):
        return Proposal(
            entry.entity_id,
            "custom",
            2,
            "ignore",
            "warning",
            {"operator": "eq", "value": "off"},
        )
    if entry.domain == "update":
        return Proposal(entry.entity_id, "update_available", 1, "ignore", "warning")
    if entry.domain == "sensor":
        # Only options the entity itself declares; the current state alone proves nothing.
        states = [
            s for s in declared_options(hass, entry.entity_id) if s.casefold() in FAULT_STATES
        ]
        if states:
            return Proposal(
                entry.entity_id,
                "diagnostic_state",
                2,
                "ignore",
                "warning",
                {"states": list(dict.fromkeys(states))},
            )
    return None


def heuristic_proposals(
    hass: HomeAssistant, entries: list[er.RegistryEntry], skip: frozenset[str] = frozenset()
) -> list[Proposal]:
    return [
        proposal
        for entry in entries
        if entry.entity_id not in skip and (proposal := _heuristic_for(hass, entry))
    ]


def _identity(
    hass: HomeAssistant, source_type: str, source_id: str
) -> tuple[tuple[str, ...], str | None, str | None]:
    """Integration domains plus manufacturer/model (devices only) of the chosen source."""
    if source_type == "device":
        device = dr.async_get(hass).async_get(source_id)
        if device is None:
            return (), None, None
        domains = tuple(
            dict.fromkeys(
                config_entry.domain
                for entry_id in device.config_entries
                if (config_entry := hass.config_entries.async_get_entry(entry_id))
            )
        )
        return domains, device.manufacturer, device.model
    config_entry = hass.config_entries.async_get_entry(source_id)
    return ((config_entry.domain,) if config_entry else ()), None, None


async def async_detect(
    hass: HomeAssistant,
    source_type: str,
    source_id: str,
    skip: frozenset[str] = frozenset(),
) -> Detection:
    """1. catalog match, 2. local heuristic, 3. nothing (caller falls back to manual).

    Disabled entities are never proposed (they would only raise unavailable alerts) but stay
    selectable by hand. Entities in ``skip`` already have a rule.
    """
    entries = [e for e in source_entities(hass, source_type, source_id) if e.disabled_by is None]
    domains, manufacturer, model = _identity(hass, source_type, source_id)
    catalog, catalog_origin = await async_load_catalog(hass)
    if catalog is not None and (match := match_catalog(catalog, domains, manufacturer, model)):
        if proposals := _from_catalog(hass, entries, match.rules, skip):
            return Detection("catalog", catalog_origin, match.description, tuple(proposals))
    if proposals := heuristic_proposals(hass, entries, skip):
        return Detection("heuristic", catalog_origin, "", tuple(proposals))
    return Detection("none", catalog_origin)
