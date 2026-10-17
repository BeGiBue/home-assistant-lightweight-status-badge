"""Catalog, local heuristic and the automatic stage of the source picker."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lightweight_status_badge import catalog
from custom_components.lightweight_status_badge.autodetect import async_detect
from custom_components.lightweight_status_badge.const import (
    CATALOG_MAX_BYTES,
    CATALOG_URL,
    CATALOG_VERSION,
)
from custom_components.lightweight_status_badge.rules import Rule
from tests.test_config_flow import go, menu, start
from tests.test_source_picker import options, pick

# Imported before the autouse fixture patches the module attribute.
REAL_FETCH = catalog._fetch_online
BUNDLED = Path(catalog.__file__).with_name("catalog.json")


def rule(**overrides):
    return {
        "match": {"domain": "binary_sensor"},
        "kind": "binary_on",
        "severity": 2,
        **overrides,
    }


# -- catalog: validation of untrusted data ---------------------------------------------------


def test_bundled_catalog_is_valid_and_complete():
    data = json.loads(BUNDLED.read_text(encoding="utf-8"))
    entries = [*data["integrations"].values(), *data["devices"]]
    assert entries
    for entry in entries:
        assert entry["description"]
        cleaned = [catalog._clean_rule(raw) for raw in entry["rules"]]
        assert None not in cleaned, "every bundled rule must pass validation"
        assert catalog._text(entry["description"]) == entry["description"]  # Already plain text.
    assert data["version"] == CATALOG_VERSION


def test_hostile_description_is_reduced_to_plain_text():
    hostile = (
        "[click](https://evil.example/p) ![](https://t.example/x.png) <b>bold</b> "
        "`code` *em* <https://evil.example> see\nhttp://evil.example/q"
    )
    entry = catalog._entry("integration", "x", {"description": hostile, "rules": [rule()]})
    assert not set("[]()<>`*_\\|#~") & set(entry.description)
    assert "://" not in entry.description
    assert "\n" not in entry.description
    assert "evil" not in entry.description  # Whole URL-bearing tokens (links) are dropped.
    assert "bold" in entry.description
    assert len(catalog._text("x" * 1000)) == catalog.MAX_DESCRIPTION
    assert catalog._text(None) == catalog._text(5) == ""


def test_recursion_error_while_validating_drops_the_rule():
    with patch.object(catalog.Rule, "from_dict", side_effect=RecursionError):
        assert catalog._clean_rule(rule()) is None


@pytest.mark.parametrize(
    "raw",
    [
        "not a dict",
        {},
        rule(match={}),
        rule(match={"entity_id": "sensor.x"}),
        rule(match={"domain": 5}),
        rule(match={"domain": "x" * 65}),
        rule(kind="python"),
        rule(kind=["binary_on"]),
        rule(severity=9),
        rule(severity=True),
        rule(unknown_policy="explode"),
        rule(config={"states": ["a"]}),
        rule(kind="update_available", match={"domain": "sensor"}),
        rule(kind="diagnostic_state"),
        rule(kind="custom", config={"operator": "eval", "value": "1"}),
    ],
)
def test_untrusted_rules_are_dropped(raw):
    assert catalog._clean_rule(raw) is None


def test_valid_rule_keeps_only_validated_fields():
    cleaned = catalog._clean_rule(
        rule(
            kind="custom",
            config={"operator": "eq", "value": "off"},
            unknown_policy="ignore",
            extra="ignored",
        )
    )
    assert cleaned.kind == "custom"
    assert cleaned.config == {"operator": "eq", "value": "off"}
    assert cleaned.unknown_policy == "ignore"
    assert cleaned.unavailable_policy == "warning"


def test_device_entry_wins_over_integration_entry():
    data = {
        "integrations": {"fritz": {"description": "integration", "rules": [rule()]}},
        "devices": [
            {
                "manufacturer": "AVM",
                "model": "FRITZ!Box*",
                "description": "device",
                "rules": [rule()],
            }
        ],
    }
    found = catalog.match_catalog(data, ("fritz",), "avm", "FRITZ!Box 7590")
    assert (found.scope, found.description) == ("device", "device")
    found = catalog.match_catalog(data, ("fritz",), "Other", "Model")
    assert (found.scope, found.key) == ("integration", "fritz")
    assert catalog.match_catalog(data, ("unknown",), None, None) is None


def test_entries_without_valid_rules_do_not_match():
    data = {"integrations": {"x": {"rules": [rule(kind="python")]}, "y": {"rules": "no"}}}
    assert catalog.match_catalog(data, ("x", "y")) is None
    assert catalog.match_catalog({"integrations": [], "devices": {}}, ("x",), "a", "b") is None


# -- catalog: loading --------------------------------------------------------------------------


async def test_fetch_online_returns_catalog(hass, aioclient_mock):
    aioclient_mock.get(CATALOG_URL, json={"version": 1, "integrations": {}})
    assert await REAL_FETCH(hass) == {"version": 1, "integrations": {}}


@pytest.mark.parametrize(
    "response",
    [
        {"status": 404},
        {"text": "not json"},
        {"json": ["not", "a", "dict"]},
        {"json": {"padding": "x" * (CATALOG_MAX_BYTES + 1)}},
        {"exc": TimeoutError},
        {"text": "[" * 100000},  # Deeply nested JSON raises RecursionError, not ValueError.
        {"json": {"version": 2, "integrations": {}}},  # Unknown format version.
        {"json": {"integrations": {}}},  # Missing format version.
    ],
)
async def test_fetch_online_failures_mean_unavailable(hass, aioclient_mock, response):
    aioclient_mock.get(CATALOG_URL, **response)
    assert await REAL_FETCH(hass) is None


async def test_bundled_catalog_is_the_offline_fallback(hass):
    data, origin = await catalog.async_load_catalog(hass)
    assert origin == "bundled"
    assert "zha" in data["integrations"]


async def test_online_result_is_cached_briefly(hass):
    online = {"integrations": {}}
    with patch.object(catalog, "_fetch_online", AsyncMock(return_value=online)) as fetch:
        assert await catalog.async_load_catalog(hass) == (online, "online")
        assert await catalog.async_load_catalog(hass) == (online, "online")
    assert fetch.await_count == 1


async def test_missing_bundled_file_reports_none(hass):
    with patch.object(catalog, "_bundled", side_effect=OSError):
        assert await catalog.async_load_catalog(hass) == (None, "none")


# -- source fixtures -------------------------------------------------------------------------


def register(entity_registry, entry, device, domain, key, **kwargs):
    return entity_registry.async_get_or_create(
        domain,
        "test",
        key,
        config_entry=entry,
        device_id=device.id if device else None,
        original_name=key,
        **kwargs,
    )


@pytest.fixture
def zigbee(hass, entity_registry, device_registry):
    """An integration the bundled catalog knows (zha)."""
    entry = MockConfigEntry(domain="zha", title="Zigbee")
    entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("zha", "lamp")}, name="Lamp"
    )
    entities = {
        "battery": register(
            entity_registry,
            entry,
            device,
            "binary_sensor",
            "battery",
            original_device_class="battery",
        ),
        "problem": register(
            entity_registry,
            entry,
            device,
            "binary_sensor",
            "problem",
            original_device_class="problem",
        ),
        "update": register(entity_registry, entry, device, "update", "firmware"),
        "plain": register(entity_registry, entry, device, "sensor", "plain"),
        "disabled": register(
            entity_registry,
            entry,
            device,
            "binary_sensor",
            "off_battery",
            original_device_class="battery",
            disabled_by=er.RegistryEntryDisabler.USER,
        ),
    }
    for key in ("battery", "problem", "update"):
        hass.states.async_set(entities[key].entity_id, "off")
    hass.states.async_set(entities["plain"].entity_id, "21")
    return entry, device, entities


@pytest.fixture
def unknown_source(hass, entity_registry, device_registry):
    """An integration without a catalog entry: only the local heuristic can help."""
    entry = MockConfigEntry(domain="test", title="Unknown gadget")
    entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("test", "gadget")}, name="Gadget"
    )
    entities = {
        "safety": register(
            entity_registry,
            entry,
            device,
            "binary_sensor",
            "safety",
            original_device_class="safety",
        ),
        "link": register(
            entity_registry,
            entry,
            device,
            "binary_sensor",
            "link",
            original_device_class="connectivity",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        "client": register(
            entity_registry,
            entry,
            device,
            "binary_sensor",
            "client",
            original_device_class="connectivity",
        ),
        "mode": register(
            entity_registry,
            entry,
            device,
            "sensor",
            "mode",
            capabilities={"options": ["ok", "Failed", "idle"]},
        ),
        "idle": register(
            entity_registry, entry, device, "sensor", "idle", capabilities={"options": ["a", "b"]}
        ),
    }
    for key in ("safety", "link", "client"):
        hass.states.async_set(entities[key].entity_id, "off")
    hass.states.async_set(entities["mode"].entity_id, "ok")
    hass.states.async_set(entities["idle"].entity_id, "a")
    return entry, device, entities


# -- detection (no UI) -----------------------------------------------------------------------


async def test_catalog_proposals_use_catalog_rules(hass, zigbee):
    entry, _, entities = zigbee
    detection = await async_detect(hass, "integration", entry.entry_id)
    assert (detection.origin, detection.catalog_origin) == ("catalog", "bundled")
    assert detection.description
    found = {p.entity_id: p for p in detection.proposals}
    assert set(found) == {entities[k].entity_id for k in ("battery", "problem", "update")}
    assert (
        found[entities["battery"].entity_id].kind,
        found[entities["battery"].entity_id].severity,
    ) == (
        "binary_on",
        1,
    )
    assert found[entities["problem"].entity_id].severity == 2
    assert found[entities["update"].entity_id].kind == "update_available"
    for proposal in found.values():
        Rule.from_dict(proposal.to_rule())  # Always a valid, saveable rule.


async def test_proposals_skip_disabled_and_already_ruled_entities(hass, zigbee):
    entry, _, entities = zigbee
    skip = frozenset({entities["battery"].entity_id})
    detection = await async_detect(hass, "integration", entry.entry_id, skip)
    ids = {p.entity_id for p in detection.proposals}
    assert entities["battery"].entity_id not in ids  # Already has a rule.
    assert entities["disabled"].entity_id not in ids  # Would only raise unavailable alerts.


async def test_heuristic_uses_only_standard_metadata(hass, unknown_source):
    entry, _, entities = unknown_source
    detection = await async_detect(hass, "integration", entry.entry_id)
    assert detection.origin == "heuristic"
    found = {p.entity_id: p for p in detection.proposals}
    assert set(found) == {entities[k].entity_id for k in ("safety", "link", "mode")}
    safety = found[entities["safety"].entity_id]
    assert (safety.kind, safety.severity) == ("binary_on", 3)
    link = found[
        entities["link"].entity_id
    ]  # Only diagnostic connectivity: client entities are noise.
    assert (link.kind, link.config) == ("custom", {"operator": "eq", "value": "off"})
    mode = found[entities["mode"].entity_id]  # Only declared fault options, original spelling.
    assert (mode.kind, mode.config) == ("diagnostic_state", {"states": ["Failed"]})
    assert all(p.unknown_policy == "ignore" for p in detection.proposals)
    assert all(p.unavailable_policy == "warning" for p in detection.proposals)


async def test_nothing_found_means_manual(hass, entity_registry):
    entry = MockConfigEntry(domain="test", title="Plain")
    entry.add_to_hass(hass)
    register(entity_registry, entry, None, "sensor", "temperature")
    detection = await async_detect(hass, "integration", entry.entry_id)
    assert (detection.origin, detection.proposals) == ("none", ())
    assert (await async_detect(hass, "integration", "missing")).origin == "none"
    assert (await async_detect(hass, "device", "missing")).origin == "none"


async def test_device_catalog_entry_by_manufacturer_and_model(
    hass, entity_registry, device_registry
):
    entry = MockConfigEntry(domain="test", title="Router")
    entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("test", "box")},
        manufacturer="AVM",
        model="FRITZ!Box 7590",
    )
    link = register(
        entity_registry, entry, device, "binary_sensor", "wan", original_device_class="connectivity"
    )
    detection = await async_detect(hass, "device", device.id)
    assert detection.origin == "catalog"
    assert [p.entity_id for p in detection.proposals] == [link.entity_id]
    assert detection.proposals[0].config == {"operator": "eq", "value": "off"}


async def test_online_catalog_replaces_bundled_one(hass, entity_registry):
    entry = MockConfigEntry(domain="test", title="Custom")
    entry.add_to_hass(hass)
    counter = register(entity_registry, entry, None, "sensor", "errors", translation_key="errors")
    online = {
        "integrations": {
            "test": {
                "description": "Online entry",
                "rules": [
                    {
                        "match": {"domain": "sensor", "translation_key": "errors"},
                        "kind": "positive_count",
                        "severity": 3,
                        "config": {"threshold": 5},
                    }
                ],
            }
        }
    }
    with patch.object(catalog, "_fetch_online", AsyncMock(return_value=online)):
        detection = await async_detect(hass, "integration", entry.entry_id)
    assert (detection.origin, detection.catalog_origin) == ("catalog", "online")
    (proposal,) = detection.proposals
    assert proposal.entity_id == counter.entity_id
    assert (proposal.kind, proposal.severity, proposal.config) == (
        "positive_count",
        3,
        {"threshold": 5},
    )


async def test_catalog_without_matching_entities_falls_back_to_heuristic(hass, unknown_source):
    entry, _, entities = unknown_source
    online = {"integrations": {"test": {"rules": [rule(match={"domain": "cover"})]}}}
    with patch.object(catalog, "_fetch_online", AsyncMock(return_value=online)):
        detection = await async_detect(hass, "integration", entry.entry_id)
    assert detection.origin == "heuristic"
    assert detection.catalog_origin == "online"


# -- options flow ------------------------------------------------------------------------------


async def test_catalog_stage_saves_checked_proposals_at_once(hass, zigbee):
    source, _, entities = zigbee
    entry, result = await start(hass)
    result = await pick(hass, result, "integration", source.entry_id)
    assert result["step_id"] == "autodetect_catalog"
    assert result["description_placeholders"]["count"] == "3"
    assert result["description_placeholders"]["description"].endswith("\n\n")
    assert "→ binary_on (S1)" in result["description_placeholders"]["preview"]
    labels = {o["value"]: o["label"] for o in options(result, "entity_ids")}
    assert set(labels) == {e.entity_id for e in entities.values()}  # All stay selectable.
    proposed = {entities[k].entity_id for k in ("battery", "problem", "update")}
    assert {v for v, label in labels.items() if label.startswith("★ ")} == proposed
    assert set(result["data_schema"]({})["entity_ids"]) == proposed  # Preselected.
    assert not entry.options["rules"]  # Nothing saved before confirming.

    result = await go(hass, result, {})  # One confirmation.
    assert result["step_id"] == "init"
    await hass.async_block_till_done()
    rules = entry.options["rules"]
    assert {r["entity_id"] for r in rules} == proposed
    assert len({r["id"] for r in rules}) == 3
    assert all(r["message"] == "" for r in rules)  # Backend explanations stay locale-aware.
    by_entity = {r["entity_id"]: r for r in rules}
    assert by_entity[entities["update"].entity_id]["kind"] == "update_available"
    assert by_entity[entities["problem"].entity_id]["severity"] == 2

    assert not entry.runtime_data.alerts
    hass.states.async_set(entities["problem"].entity_id, "on")
    await hass.async_block_till_done()
    assert entry.runtime_data.counts == (1, 1, 2)


async def test_unchecked_entities_are_not_saved_and_extra_ones_go_manual(hass, zigbee):
    _, _, entities = zigbee
    entry, result = await start(hass)
    result = await pick(hass, result, "integration", zigbee[0].entry_id)
    chosen = [entities["problem"].entity_id, entities["plain"].entity_id]
    result = await go(hass, result, {"entity_ids": chosen})
    assert result["step_id"] == "preset"  # Only the entity without proposal needs hands-on work.
    assert result["description_placeholders"]["entity"] == entities["plain"].entity_id
    assert [r["entity_id"] for r in entry.options["rules"]] == [entities["problem"].entity_id]
    result = await go(hass, result, {"preset": "custom"})
    result = await go(hass, result, {"operator": "gt", "value": "30"})
    result = await menu(hass, result, "save")
    assert result["step_id"] == "init"
    await hass.async_block_till_done()
    assert [r["entity_id"] for r in entry.options["rules"]] == chosen


async def test_heuristic_stage_and_existing_rules_are_not_proposed_again(hass, unknown_source):
    source, _, entities = unknown_source
    entry, result = await start(hass)
    result = await pick(hass, result, "integration", source.entry_id)
    assert result["step_id"] == "autodetect_heuristic"
    assert result["description_placeholders"]["description"] == ""
    result = await go(hass, result, {})
    assert result["step_id"] == "init"
    await hass.async_block_till_done()
    kinds = {r["entity_id"]: r["kind"] for r in entry.options["rules"]}
    assert kinds == {
        entities["safety"].entity_id: "binary_on",
        entities["link"].entity_id: "custom",
        entities["mode"].entity_id: "diagnostic_state",
    }
    # Same source again: everything detectable is covered, so only the manual list remains.
    result = await menu(hass, result, "add")
    result = await menu(hass, result, "integration")
    result = await go(hass, result, {"entry_id": source.entry_id})
    assert result["step_id"] == "entities"
    assert result["data_schema"]({})["entity_ids"] == []


async def test_manual_list_when_nothing_is_detected(hass, entity_registry):
    source = MockConfigEntry(domain="test", title="Plain")
    source.add_to_hass(hass)
    plain = register(entity_registry, source, None, "sensor", "temperature")
    _, result = await start(hass)
    result = await pick(hass, result, "integration", source.entry_id)
    assert result["step_id"] == "entities"
    assert {o["value"] for o in options(result, "entity_ids")} == {plain.entity_id}
    assert not any(o["label"].startswith("★") for o in options(result, "entity_ids"))


async def test_autodetect_navigation_and_validation(hass, zigbee):
    _, _, entities = zigbee
    entry, result = await start(hass)
    result = await pick(hass, result, "integration", zigbee[0].entry_id)
    result = await go(hass, result, {"navigation": "back"})
    assert result["step_id"] == "integration"
    result = await go(hass, result, {"entry_id": zigbee[0].entry_id})
    result = await go(hass, result, {"entity_ids": []})
    assert result["errors"] == {"entity_ids": "select_entities"}
    chosen = [entities["problem"].entity_id, entities["battery"].entity_id]
    with patch("custom_components.lightweight_status_badge.config_flow.MAX_RULES", 1):
        result = await go(hass, result, {"entity_ids": chosen})
        assert result["errors"] == {"base": "too_many_rules"}
    # The user's own selection survives the error instead of resetting to all proposals.
    assert set(result["data_schema"]({})["entity_ids"]) == set(chosen)
    assert not entry.options["rules"]


async def test_device_source_runs_the_same_automatic_stage(hass, zigbee):
    _, device, entities = zigbee
    entry, result = await start(hass)
    result = await pick(hass, result, "device", device.id)
    assert result["step_id"] == "autodetect_catalog"
    result = await go(hass, result, {"navigation": "back"})
    assert result["step_id"] == "device"


# -- owner's installation (metadata taken from a real core.entity_registry) -------------------


def _inventory(entity_registry, entry, device, domain, key, platform, **kwargs):
    return entity_registry.async_get_or_create(
        domain, platform, key, config_entry=entry, device_id=device.id, original_name=key, **kwargs
    )


DIAG = EntityCategory.DIAGNOSTIC
OWNER_CASES = {
    "synology_dsm": [
        # (domain, key, device_class, category, translation_key, expected kind or None)
        ("binary_sensor", "sec", "safety", None, "status", "binary_on"),
        ("binary_sensor", "bad", "safety", DIAG, "disk_exceed_bad_sector_thr", "binary_on"),
        ("sensor", "d1", None, DIAG, "disk_status", "disk_health"),
        ("sensor", "d1s", None, DIAG, "disk_smart_status", "disk_health"),
        ("sensor", "vol", None, None, "volume_status", "disk_health"),
        ("update", "dsm", None, DIAG, "update", "update_available"),
        ("sensor", "cpu", None, None, "cpu_total_load", None),
        ("sensor", "temp", "temperature", DIAG, "disk_temp", None),
    ],
    "unifi": [
        ("sensor", "state", "enum", DIAG, "device_state", "diagnostic_state"),
        ("update", "fw", "firmware", None, None, "update_available"),
        ("sensor", "rx", "data_rate", DIAG, "client_bandwidth_rx", None),
        ("switch", "port", "switch", EntityCategory.CONFIG, None, None),
    ],
    "unifi_network_plus": [
        ("binary_sensor", "rt", "connectivity", DIAG, "realtime_connected", "custom"),
        ("binary_sensor", "hot", "problem", DIAG, "overheating", "binary_on"),
        ("binary_sensor", "client", "connectivity", None, None, None),
        ("update", "fw", None, DIAG, "firmware", "update_available"),
    ],
    "nut": [
        ("sensor", "status", None, None, "ups_status", "ups_status"),
        ("sensor", "display", None, None, "ups_status_display", None),
        ("sensor", "load", None, None, "ups_load", None),
    ],
    "rpi_power": [("binary_sensor", "power", "problem", DIAG, "rpi_power", "binary_on")],
    "smlight": [
        ("binary_sensor", "net", "connectivity", DIAG, "internet", "custom"),
        ("binary_sensor", "eth", "connectivity", DIAG, "ethernet", None),
        ("update", "core", "firmware", EntityCategory.CONFIG, "core_update", "update_available"),
        ("sensor", "mode", "enum", DIAG, "device_mode", None),
    ],
}


@pytest.mark.parametrize("platform", OWNER_CASES)
async def test_catalog_covers_the_owners_integrations(
    hass, entity_registry, device_registry, platform
):
    entry = MockConfigEntry(domain=platform, title=platform)
    entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(platform, "d")}, name="D"
    )
    expected = {}
    for domain, key, dclass, category, tkey, kind in OWNER_CASES[platform]:
        ent = _inventory(
            entity_registry,
            entry,
            device,
            domain,
            key,
            platform,
            original_device_class=dclass,
            entity_category=category,
            translation_key=tkey,
        )
        hass.states.async_set(ent.entity_id, "off")
        expected[ent.entity_id] = kind
    detection = await async_detect(hass, "integration", entry.entry_id)
    assert (detection.origin, detection.catalog_origin) == ("catalog", "bundled")
    found = {p.entity_id: p.kind for p in detection.proposals}
    assert found == {e: k for e, k in expected.items() if k}
    for proposal in detection.proposals:
        Rule.from_dict(proposal.to_rule())
