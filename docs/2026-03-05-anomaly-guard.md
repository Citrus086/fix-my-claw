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
   - optional architect-active + dispatch-nearby signal
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

- `src/fix_my_claw/core.py`
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

Defaults are tuned to be more sensitive for ping-pong incidents:

- `min_stop_signals = 2`
- `max_repeat_same_signature = 3`
- `min_ping_pong_turns = 4`

## Suggested Follow-up Contributions

1. Add unit tests for detector signals and threshold boundaries.
2. Add score-based detection mode (weighted signals) in addition to hard thresholds.
3. Add role extractor plugins for different log formats.
4. Add per-project profiles (e.g., coding agent, planner agent, worker agent).
