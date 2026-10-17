"""Rule catalog for automatic proposals: online first, bundled copy when offline.

The catalog is untrusted input. Every rule is reduced to a fixed vocabulary and validated
through ``Rule.from_dict`` before it can influence the configuration flow.
"""

import asyncio
import fnmatch
import json
import time
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CATALOG_CACHE_KEY, CATALOG_MAX_BYTES, CATALOG_TIMEOUT, CATALOG_TTL, CATALOG_URL
from .rules import Rule

MATCH_KEYS = frozenset({"domain", "device_class", "translation_key", "entity_category"})
MAX_RULES_PER_ENTRY = 50
MAX_TEXT = 64


@dataclass(frozen=True)
class CatalogRule:
    """Entity selector plus the rule fields to propose for matching entities."""

    match: dict
    kind: str
    severity: int
    unknown_policy: str
    unavailable_policy: str
    config: dict


@dataclass(frozen=True)
class CatalogMatch:
    scope: str  # "device" or "integration"
    key: str
    description: str
    rules: tuple[CatalogRule, ...]


def _bundled() -> dict:
    return json.loads(Path(__file__).with_name("catalog.json").read_text(encoding="utf-8"))


async def _fetch_online(hass: HomeAssistant) -> dict | None:
    """Download the catalog; any failure means "not available", never an exception."""
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(CATALOG_TIMEOUT):
            async with session.get(CATALOG_URL) as response:
                response.raise_for_status()
                chunks, size = [], 0
                async for chunk in response.content.iter_chunked(16384):
                    size += len(chunk)
                    if size > CATALOG_MAX_BYTES:
                        return None
                    chunks.append(chunk)
        data = json.loads(b"".join(chunks))
    except TimeoutError, aiohttp.ClientError, OSError, ValueError:
        return None
    return data if isinstance(data, dict) else None


async def async_load_catalog(hass: HomeAssistant) -> tuple[dict | None, str]:
    """Return ``(catalog, origin)`` with origin ``online``, ``bundled`` or ``none``.

    Only online results are cached (briefly) so going back and forth in the flow does not
    repeat the request; the bundled file is cheap and always correct for this version.
    """
    cache = hass.data.setdefault(CATALOG_CACHE_KEY, {})
    if cache and time.monotonic() - cache["at"] < CATALOG_TTL:
        return cache["catalog"], "online"
    catalog = await _fetch_online(hass)
    if catalog is not None:
        cache.update(at=time.monotonic(), catalog=catalog)
        return catalog, "online"
    try:
        catalog = await hass.async_add_executor_job(_bundled)
    except OSError, ValueError:
        return None, "none"
    return (catalog, "bundled") if isinstance(catalog, dict) else (None, "none")


def _clean_rule(raw: object) -> CatalogRule | None:
    """Validate one catalog rule; ``None`` drops it silently."""
    if not isinstance(raw, dict):
        return None
    match = raw.get("match")
    if not isinstance(match, dict) or not match or match.keys() - MATCH_KEYS:
        return None
    if any(not isinstance(v, str) or not 1 <= len(v) <= MAX_TEXT for v in match.values()):
        return None
    candidate = {
        "id": "catalog",
        "entity_id": f"{match.get('domain', 'sensor')}.placeholder",
        "kind": raw.get("kind"),
        "severity": raw.get("severity", 2),
        "unknown_policy": raw.get("unknown_policy", "warning"),
        "unavailable_policy": raw.get("unavailable_policy", "warning"),
        "config": raw.get("config", {}),
    }
    try:
        rule = Rule.from_dict(candidate)
    except ValueError, TypeError:
        return None
    return CatalogRule(
        dict(match),
        rule.kind,
        rule.severity,
        rule.unknown_policy,
        rule.unavailable_policy,
        rule.config,
    )


def _entry(scope: str, key: str, raw: dict) -> CatalogMatch | None:
    raw_rules = raw.get("rules")
    if not isinstance(raw_rules, list):
        return None
    rules = tuple(r for r in map(_clean_rule, raw_rules[:MAX_RULES_PER_ENTRY]) if r)
    if not rules:
        return None
    description = raw.get("description", "")
    return CatalogMatch(
        scope, key, description[:200] if isinstance(description, str) else "", rules
    )


def _pattern(value: str | None, pattern: object) -> bool:
    return (
        value is not None
        and isinstance(pattern, str)
        and len(pattern) <= MAX_TEXT
        and fnmatch.fnmatchcase(value.casefold(), pattern.casefold())
    )


def match_catalog(
    catalog: dict,
    domains: tuple[str, ...],
    manufacturer: str | None = None,
    model: str | None = None,
) -> CatalogMatch | None:
    """Find the entry for a source. A device entry wins over an integration entry."""
    devices = catalog.get("devices")
    if manufacturer and model and isinstance(devices, list):
        for item in devices:
            if (
                isinstance(item, dict)
                and _pattern(manufacturer, item.get("manufacturer"))
                and _pattern(model, item.get("model", "*"))
                and (found := _entry("device", f"{manufacturer} {model}", item))
            ):
                return found
    integrations = catalog.get("integrations")
    if isinstance(integrations, dict):
        for domain in domains:
            item = integrations.get(domain)
            if isinstance(item, dict) and (found := _entry("integration", domain, item)):
                return found
    return None
