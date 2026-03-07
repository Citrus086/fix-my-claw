# fix-my-claw Change Note (2026-03-05)

## Scope

This change adds a generalized **anomaly guard** so fix-my-claw can detect and repair cases where:

- OpenClaw health/status probes still pass, but
- agent orchestration is stuck in repeated/ping-pong behavior.

## Completed Changes

1. Added new config section: `[anomaly_guard]`
2. Added anomaly detector based on recent log windows:
   - stop/cancel signal frequency
   - repeated orchestrator/builder message signatures
   - orchestrator↔builder ping-pong turns
   - optional real handoff analysis: initiator, target role, and unexpected post-handoff speaker streak
3. Integrated detector into `run_check`:
   - detector hit => `healthy = false`
4. Integrated detector into repair flow:
   - anomaly-triggered repair is no longer short-circuited by health/status
   - official steps do not early-break on probe health in anomaly mode
   - post-repair validation includes anomaly guard, not only health/status
5. Added compatibility alias:
   - preferred key is `[anomaly_guard]`
   - legacy key `[loop_guard]` is still accepted
6. Updated docs and example config.

## Files Updated

- `src/fix_my_claw/anomaly_guard.py`
- `src/fix_my_claw/config.py`
- `src/fix_my_claw/monitor.py`
- `src/fix_my_claw/repair.py`
- `examples/fix-my-claw.toml`
- `README.md`
- `README_ZH.md`

## Output Compatibility

- `fix-my-claw check --json` now emits `anomaly_guard`.
- For compatibility, it also emits legacy key `loop_guard` with the same value.

## Heuristic Nature

The detector is heuristic by design. Thresholds and keywords are configurable in `[anomaly_guard]`.
Tune for your workload to balance recall vs false positives.

### Current Default Sensitivity

Defaults are tuned for short multi-agent cycle incidents, plus a conservative stagnation fallback for low-novelty tails:

- `max_repeat_same_signature = 3`
- `min_cycle_repeated_turns = 4`
- `max_cycle_period = 4`
- `stagnation_enabled = true`
- `stagnation_min_events = 8`
- `stagnation_min_roles = 2`
- `stagnation_max_novel_cluster_ratio = 0.34`

Preferred config names:

- `min_cycle_repeated_turns`
- `max_cycle_period`
- `stagnation_enabled`
- `stagnation_min_events`
- `stagnation_min_roles`
- `stagnation_max_novel_cluster_ratio`

Legacy compatibility:

- `min_ping_pong_turns` is still accepted as an alias for `min_cycle_repeated_turns`

## Suggested Follow-up Contributions

1. Add unit tests for detector signals and threshold boundaries.
2. Add score-based detection mode (weighted signals) in addition to hard thresholds.
3. Add role extractor plugins for different log formats.
4. Add per-project profiles (e.g., coding agent, planner agent, worker agent).
