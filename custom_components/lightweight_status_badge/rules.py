"""Validated rules and pure evaluators. No Home Assistant runtime dependencies."""

import json
import math
import re
from dataclasses import dataclass, field
from functools import cached_property
from hashlib import sha256
from typing import Any

TYPES = frozenset(
    {
        "binary_on",
        "update_available",
        "disk_health",
        "positive_count",
        "unifi_state",
        "ups_status",
        "nonzero_code",
        "diagnostic_state",
        "grid_fault",
        "custom",
    }
)
POLICIES = {"ignore": 0, "notice": 1, "warning": 2, "critical": 3}
OPERATORS = frozenset({"eq", "ne", "in", "not_in", "gt", "ge", "lt", "le", "contains"})
UPS = frozenset({"OB", "LB", "FSD", "RB"})
# Default allowlist of healthy states for the disk_health evaluator.
DISK_HEALTH_ALLOWLIST = ("normal", "healthy", "good", "passed")


def number(value: Any) -> float | None:
    """Reject booleans, infinities, NaNs and malformed numeric values."""
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except TypeError, ValueError, OverflowError:
        return None
    return result if math.isfinite(result) else None


@dataclass(frozen=True)
class Rule:
    """Stable rule identity; evaluator config is copied and never mutated."""

    id: str
    entity_id: str
    kind: str
    enabled: bool = True
    label: str = ""
    severity: int = 2
    message: str = ""
    recommendation: str = ""
    unknown_policy: str = "warning"
    unavailable_policy: str = "warning"
    config: dict = field(default_factory=dict)
    attributes: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict) -> Rule:
        if not isinstance(data, dict):
            raise ValueError("rule must be an object")
        if not isinstance(data.get("attributes", []), (list, tuple)):
            raise ValueError("attributes must be a list")
        try:
            rule = cls(
                **{
                    **data,
                    "config": json.loads(json.dumps(data.get("config", {}))),
                    "attributes": tuple(data.get("attributes", ())),
                }
            )
        except (TypeError, ValueError) as err:
            raise ValueError("invalid rule fields") from err
        if not isinstance(rule.id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", rule.id):
            raise ValueError("invalid rule id")
        if not isinstance(rule.entity_id, str) or not re.fullmatch(
            r"[a-z0-9_]+\.[a-z0-9_]+", rule.entity_id
        ):
            raise ValueError("invalid entity id")
        if (
            not isinstance(rule.kind, str)
            or rule.kind not in TYPES
            or type(rule.enabled) is not bool
        ):
            raise ValueError("invalid rule kind/enabled")
        if type(rule.severity) is not int or rule.severity not in (1, 2, 3):
            raise ValueError("invalid severity")
        if (
            not isinstance(rule.unknown_policy, str)
            or rule.unknown_policy not in POLICIES
            or not isinstance(rule.unavailable_policy, str)
            or rule.unavailable_policy not in POLICIES
        ):
            raise ValueError("invalid availability policy")
        for text in (rule.label, rule.message, rule.recommendation):
            if not isinstance(text, str) or len(text) > 1000:
                raise ValueError("text must be at most 1000 characters")
        if len(rule.attributes) > 10 or any(
            not isinstance(a, str) or not re.fullmatch(r"[a-zA-Z0-9_]{1,64}", a)
            for a in rule.attributes
        ):
            raise ValueError("invalid attribute whitelist")
        c = rule.config
        if not isinstance(c, dict) or len(json.dumps(c)) > 4096:
            raise ValueError("invalid evaluator configuration")
        allowed = {
            "binary_on": set(),
            "update_available": set(),
            "disk_health": {"allowlist"},
            "positive_count": {"threshold"},
            "unifi_state": set(),
            "ups_status": set(),
            "nonzero_code": {"error_strings"},
            "diagnostic_state": {"states"},
            "grid_fault": set(),
            "custom": {"operator", "value"},
        }[rule.kind]
        if c.keys() - allowed:
            raise ValueError("unsupported evaluator configuration")
        if rule.kind == "update_available" and not rule.entity_id.startswith("update."):
            raise ValueError("update_available requires an update entity")
        for key in ("allowlist", "error_strings", "states"):
            if key in c and (
                not isinstance(c[key], list)
                or not c[key]
                or any(not isinstance(v, str) or len(v) > 255 for v in c[key])
            ):
                raise ValueError(f"{key} must be a nonempty list of strings")
        if rule.kind == "diagnostic_state" and not c.get("states"):
            raise ValueError("diagnostic_state requires states")
        if rule.kind == "positive_count" and number(c.get("threshold", 0)) is None:
            raise ValueError("threshold must be finite")
        if rule.kind == "custom":
            op = c.get("operator")
            if not isinstance(op, str) or op not in OPERATORS or "value" not in c:
                raise ValueError("custom rule requires operator and value")
            v = c["value"]
            if op in {"gt", "ge", "lt", "le"}:
                if number(v) is None:
                    raise ValueError("numeric comparison requires a finite threshold")
            elif op in {"in", "not_in"}:
                if not isinstance(v, list) or not v or any(not isinstance(x, str) for x in v):
                    raise ValueError("set comparison requires strings")
            elif not isinstance(v, str):
                raise ValueError("string comparison requires a string")
        return rule

    @cached_property
    def fingerprint(self) -> str:
        """Display-only changes preserve acknowledgement; trigger/policy changes do not."""
        config = dict(self.config)
        defaults = {
            "disk_health": {"allowlist": list(DISK_HEALTH_ALLOWLIST)},
            "positive_count": {"threshold": 0},
            "nonzero_code": {"error_strings": []},
        }
        config = {**defaults.get(self.kind, {}), **config}
        for key in ("allowlist", "error_strings", "states"):
            if key in config:
                config[key] = sorted({v.casefold() for v in config[key]})
        if "threshold" in config:
            config["threshold"] = number(config["threshold"])
        if self.kind == "custom":
            op, value = config["operator"], config["value"]
            if op in {"in", "not_in"}:
                config["value"] = sorted({v.casefold() for v in value})
            elif op in {"gt", "ge", "lt", "le"}:
                config["value"] = number(value)
            else:
                config["value"] = value.casefold()
        return sha256(
            json.dumps(
                [
                    self.entity_id,
                    self.kind,
                    config,
                    self.severity,
                    self.unknown_policy,
                    self.unavailable_policy,
                ],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()


@dataclass(frozen=True)
class Match:
    severity: int
    condition: str
    message_ids: tuple[str, ...]


def evaluate(rule: Rule, state: str | None) -> Match | None:
    """Evaluate a single state, always handling availability before ordinary rules."""
    if not rule.enabled:
        return None
    raw = "unavailable" if state is None else state
    s = raw.casefold().strip()
    if s in {"unknown", "unavailable"}:
        severity = POLICIES[getattr(rule, f"{s}_policy")]
        return Match(severity, s, (s,)) if severity else None
    c = rule.config
    matched = False
    key = rule.kind
    if key in {"binary_on", "update_available"}:
        matched = s == "on"
    elif key == "disk_health":
        matched = s not in {v.casefold() for v in c.get("allowlist", DISK_HEALTH_ALLOWLIST)}
    elif key == "positive_count":
        n = number(raw)
        matched = n is not None and n > float(c.get("threshold", 0))
    elif key == "unifi_state":
        matched = s in {"disconnected", "offline", "isolated", "failed", "adopting_failed"}
    elif key == "ups_status":
        tokens = sorted(set(raw.upper().split()) & UPS)
        if tokens:
            return Match(
                3 if set(tokens) & {"LB", "FSD"} else rule.severity,
                "ups:" + ",".join(tokens),
                tuple("ups_" + t.lower() for t in tokens),
            )
    elif key == "nonzero_code":
        n = number(raw)
        matched = (n is not None and n != 0) or s in {
            v.casefold() for v in c.get("error_strings", [])
        }
    elif key == "diagnostic_state":
        matched = s in {v.casefold() for v in c["states"]}
    elif key == "grid_fault":
        matched = s in {"grid fault", "grid_fault", "grid failure", "fault"}
    elif key == "custom":
        op, value = c["operator"], c["value"]
        if op in {"gt", "ge", "lt", "le"}:
            n = number(raw)
            if n is not None:
                t = float(value)
                matched = {"gt": n > t, "ge": n >= t, "lt": n < t, "le": n <= t}[op]
        elif op in {"in", "not_in"}:
            matched = s in {v.casefold() for v in value}
            if op == "not_in":
                matched = not matched
        elif op == "contains":
            matched = value.casefold() in s
        else:
            matched = s == value.casefold()
            if op == "ne":
                matched = not matched
    condition = (
        f"{key}:{s}"
        if key in {"nonzero_code", "diagnostic_state", "unifi_state", "disk_health"}
        else key
    )
    return Match(rule.severity, condition, (key,)) if matched else None
