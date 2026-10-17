"""Evaluator matrix and malformed/availability policy coverage."""

import pytest

from custom_components.lightweight_status_badge.rules import Rule, evaluate


@pytest.mark.parametrize(
    ("kind", "state", "config", "matches"),
    [
        ("binary_on", "on", {}, True),
        ("binary_on", "off", {}, False),
        ("update_available", "on", {}, True),
        ("update_available", "off", {}, False),
        ("disk_health", "HeAlThY", {}, False),
        ("disk_health", "failed", {}, True),
        ("disk_health", "OK", {"allowlist": ["ok"]}, False),
        ("positive_count", "2", {}, True),
        ("positive_count", "0", {}, False),
        ("positive_count", "-1", {}, False),
        ("positive_count", "NaN", {}, False),
        ("positive_count", "inf", {}, False),
        ("positive_count", "oops", {}, False),
        ("positive_count", "4", {"threshold": 4}, False),
        ("positive_count", "4.5", {"threshold": 4}, True),
        *[
            ("unifi_state", s, {}, True)
            for s in ["disconnected", "offline", "isolated", "failed", "adopting_failed"]
        ],
        ("unifi_state", "connected", {}, False),
        ("ups_status", "OL CHRG", {}, False),
        ("ups_status", "OB", {}, True),
        ("ups_status", "OL RB", {}, True),
        ("ups_status", "UNFAMILIAR", {}, False),
        ("nonzero_code", "0", {}, False),
        ("nonzero_code", "-42", {}, True),
        ("nonzero_code", "nonsense", {}, False),
        ("nonzero_code", "ERROR", {"error_strings": ["error"]}, True),
        ("diagnostic_state", "warning", {"states": ["error", "warning"]}, True),
        ("diagnostic_state", "normal", {"states": ["error"]}, False),
        *[
            ("grid_fault", s, {}, True)
            for s in ["grid fault", "grid_fault", "grid failure", "fault"]
        ],
        ("grid_fault", "normal", {}, False),
        ("custom", "foo", {"operator": "eq", "value": "FOO"}, True),
        ("custom", "foo", {"operator": "ne", "value": "foo"}, False),
        ("custom", "x", {"operator": "in", "value": ["X", "y"]}, True),
        ("custom", "x", {"operator": "not_in", "value": ["x"]}, False),
        ("custom", "Alarm: fault", {"operator": "contains", "value": "FAULT"}, True),
        ("custom", "3", {"operator": "gt", "value": 2}, True),
        ("custom", "2", {"operator": "ge", "value": 2}, True),
        ("custom", "1", {"operator": "lt", "value": 2}, True),
        ("custom", "2", {"operator": "le", "value": 2}, True),
        ("custom", "NaN", {"operator": "ne", "value": "NaN"}, False),
        ("custom", "NaN", {"operator": "gt", "value": 2}, False),
    ],
)
def test_matrix(kind, state, config, matches):
    entity = "update.test" if kind == "update_available" else "sensor.test"
    rule = Rule.from_dict({"id": "test", "entity_id": entity, "kind": kind, "config": config})
    assert (evaluate(rule, state) is not None) is matches


@pytest.mark.parametrize(
    "policy,severity", [("ignore", 0), ("notice", 1), ("warning", 2), ("critical", 3)]
)
@pytest.mark.parametrize("state", ["unknown", "unavailable", None])
def test_availability(policy, severity, state):
    r = Rule.from_dict(
        {
            "id": "test",
            "entity_id": "sensor.test",
            "kind": "nonzero_code",
            "unknown_policy": policy,
            "unavailable_policy": policy,
        }
    )
    m = evaluate(r, state)
    assert (m.severity if m else 0) == severity
    if m:
        assert m.condition == (state or "unavailable")


def test_ups_severity_and_discriminator():
    r = Rule.from_dict({"id": "ups", "entity_id": "sensor.ups", "kind": "ups_status"})
    assert evaluate(r, "OB CHRG").condition == evaluate(r, "OB DISCHRG").condition
    assert evaluate(r, "OB LB FSD").severity == 3
    assert evaluate(r, "OB LB FSD").message_ids == ("ups_fsd", "ups_lb", "ups_ob")
    assert evaluate(r, "OL RB").severity == 2


@pytest.mark.parametrize(
    "override",
    [
        {"kind": "python"},
        {"severity": True},
        {"severity": 4},
        {"enabled": "false"},
        {"unknown_policy": "bad"},
        {"entity_id": "../bad"},
        {"id": ""},
        {"kind": "update_available"},
        {"config": {"extra": 1}},
        {"kind": "positive_count", "config": {"threshold": "inf"}},
        {"kind": "diagnostic_state"},
        {"kind": "disk_health", "config": {"allowlist": "healthy"}},
        {"kind": "custom", "config": {"operator": "eval", "value": "x"}},
        {"kind": "custom", "config": {"operator": "in", "value": "x"}},
        {"kind": "custom", "config": {"operator": "gt", "value": True}},
        {"attributes": ["secret.bad"]},
        {"message": "x" * 1001},
    ],
)
def test_invalid_rule(override):
    with pytest.raises(ValueError):
        Rule.from_dict({"id": "test", "entity_id": "sensor.test", "kind": "binary_on", **override})


def test_disabled_and_display_changes():
    data = {"id": "r", "entity_id": "sensor.test", "kind": "binary_on"}
    assert evaluate(Rule.from_dict({**data, "enabled": False}), "on") is None
    assert Rule.from_dict(data).fingerprint == Rule.from_dict({**data, "label": "New"}).fingerprint
    assert Rule.from_dict(data).fingerprint != Rule.from_dict({**data, "severity": 3}).fingerprint


@pytest.mark.parametrize(
    "kind,first,second",
    [
        ("disk_health", {}, {"allowlist": ["passed", "GOOD", "normal", "healthy", "good"]}),
        ("positive_count", {}, {"threshold": "0.0"}),
        (
            "custom",
            {"operator": "in", "value": ["a", "B"]},
            {"operator": "in", "value": ["b", "A", "a"]},
        ),
        ("custom", {"operator": "gt", "value": "2.0"}, {"operator": "gt", "value": 2}),
        (
            "custom",
            {"operator": "contains", "value": "ERROR"},
            {"operator": "contains", "value": "error"},
        ),
    ],
)
def test_equivalent_trigger_edits_keep_identity(kind, first, second):
    data = {"id": "r", "entity_id": "sensor.test", "kind": kind}
    assert (
        Rule.from_dict({**data, "config": first}).fingerprint
        == Rule.from_dict({**data, "config": second}).fingerprint
    )
