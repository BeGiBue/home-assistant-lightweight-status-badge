# Backend validation results

> Historical work-package report. Current installation: [INSTALLATION.md](INSTALLATION.md); independent review and current evidence: [REVIEW.md](REVIEW.md), [REVIEW_TEST_RESULTS.md](REVIEW_TEST_RESULTS.md).

Measured on 2026-10-17 in the Codex Linux x86_64 cloud environment with
Home Assistant 2026.10.2 and Python 3.14.8. No physical UPS,
UniFi, NAS, inverter, or other device was available.

## Automated checks

- `ruff check .`: passed.
- `ruff format --check .`: passed.
- `python -m pytest -q --timeout=30 --cov=custom_components.lightweight_status_badge --cov-report=term-missing`:
  **116 passed**, no failures, errors, skips or expected failures; 4.53 seconds.
- Statement coverage: **95%** (528 statements, 26 not executed).
- `git diff --exit-code 641895501d99ed1967051fdbfcf515b7e33f8c14 -- SPEC.md ARCHITECTURE.md README.md`:
  passed; product/architecture documents and existing README remain unchanged.

Coverage includes all rule families and custom operators; finite/malformed values;
availability policies and missing entities; UPS token/severity changes;
acknowledge/revoke, stale occurrences, resolve/recur, reconnection;
startup unknown/unavailable, actual HA final-write handling, atomic temporary-file
storage, delayed snapshot reconciliation and bounded save windows during sustained acknowledgement bursts; display-only versus substantive
rule edits; multiple rules per source; options reload/unload; sensor aggregates;
pagination, escaping and attribute whitelists; two live authenticated WebSocket
clients, subscriptions across reload, source-entity read/control permissions,
HA auth-phase rejection of unauthenticated commands and service caller checks.
CI is configured; a remote CI run is not claimed by this local report.

## Selected-entity event burst

Command: `python -m pytest -q -s tests/test_performance.py` (2 passed).
One rule per selected entity, 100 rounds of changing positive counts plus one
unselected state change each round. Changes pass through the actual HA state
machine and filtered event listener. Each round drains HA's job queue. CPU is
process CPU time; wall time uses the monotonic performance counter. Python
tracemalloc is enabled during the measured loop, so these are instrumented test
costs including HA event/test-harness overhead, not standalone evaluator costs.

| Selected entities | Selected events | CPU seconds | Wall seconds | Traced retained KiB | Traced peak KiB | Refresh dispatches |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | 3000 | 0.3605 | 0.3612 | 374.2 | 858.8 | 6 |
| 100 | 10000 | 1.1071 | 1.109 | 2719.9 | 2726.3 | 16 |

Assertions verify exactly one evaluation per selected event, no evaluations for
unselected events, correct final counts/details, coalesced notifications and zero
scheduled acknowledgement saves for ordinary state changes. Rule indexing and
listener setup occur before the timed loop. Retained/peak numbers are traced
Python allocations during that loop, **not process RSS, steady-state integration
memory**. The cloud host is shared; timings and refresh
counts vary with scheduling. No hardware-specific performance threshold is
asserted.

## Known boundaries

- Backend only. Full GUI rule management, template picker, badge/dialog and the
  secondary acknowledged-alert UI are not implemented by work package A.
- HACS/public-release validation and physical-device end-to-end checks are unrun.
- Tested HA version is 2026.10.2; compatibility with other versions is unverified.
- A graceful HA stop/restart flushes acknowledgements; abrupt power/process loss
  can lose changes still in the one-second save queue. Atomic replacement is not
  a power-loss journal. Storage errors remain visible in HA's logs.
- Startup reconciliation completes at `homeassistant_started`. Sources still
  unavailable then follow their configured policy; unseen resolve/recur cycles
  entirely during downtime cannot be reconstructed without history.
- Global invalidation notifications carry no source content, but indicate that
  backend state changed; detailed data is permission-filtered.
