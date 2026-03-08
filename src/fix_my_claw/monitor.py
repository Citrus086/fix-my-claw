from __future__ import annotations

import logging
import time

from .config import AppConfig
from .health import HealthEvaluation
from .repair import _evaluate_health, attempt_repair
from .state import StateStore

# Constants for monitor loop behavior
MAX_BACKOFF_SECONDS = 300  # 5 minutes max backoff on repeated errors


def run_check(cfg: AppConfig, store: StateStore) -> HealthEvaluation:
    evaluation = _evaluate_health(cfg)
    if evaluation.effective_healthy:
        store.mark_ok()
    return evaluation


def monitor_loop(cfg: AppConfig, store: StateStore) -> None:
    watchdog_log = logging.getLogger("fix_my_claw.watchdog")
    watchdog_log.info("starting monitor loop: interval=%ss", cfg.monitor.interval_seconds)
    monitor_disabled = False
    # Error backoff to prevent log spam on repeated failures
    consecutive_errors = 0

    while True:
        try:
            enabled = store.is_enabled()
            if not enabled:
                if not monitor_disabled:
                    watchdog_log.info(
                        "monitor is disabled; loop is idling until re-enabled",
                    )
                    monitor_disabled = True
                time.sleep(cfg.monitor.interval_seconds)
                continue
            else:
                if monitor_disabled:
                    watchdog_log.info("monitor is enabled again; loop resumed")
                    monitor_disabled = False
            evaluation = run_check(cfg, store)
            # Reset error counter on successful check
            consecutive_errors = 0
            if not evaluation.effective_healthy:
                anomaly_triggered = bool(evaluation.anomaly_guard and evaluation.anomaly_guard.get("triggered"))
                if anomaly_triggered:
                    watchdog_log.warning(
                        "unhealthy: health_exit=%s status_exit=%s; anomaly guard triggered: signals=%s",
                        evaluation.health_probe.cmd.exit_code,
                        evaluation.status_probe.cmd.exit_code,
                        evaluation.anomaly_guard.get("signals"),
                    )
                else:
                    watchdog_log.warning(
                        "unhealthy: health_exit=%s status_exit=%s; attempting repair",
                        evaluation.health_probe.cmd.exit_code,
                        evaluation.status_probe.cmd.exit_code,
                    )
                result = attempt_repair(
                    cfg,
                    store,
                    force=False,
                    reason="anomaly_guard" if anomaly_triggered else None,
                )
                if result.attempted:
                    watchdog_log.warning(
                        "repair finished: fixed=%s used_codex=%s dir=%s",
                        result.fixed,
                        result.used_ai,
                        result.details.get("attempt_dir"),
                    )
                elif result.details.get("cooldown"):
                    remaining = result.details.get("cooldown_remaining_seconds")
                    watchdog_log.info(
                        "repair skipped: cooldown (%ss remaining)",
                        remaining if remaining is not None else "?",
                    )
                else:
                    watchdog_log.info("repair skipped: %s", result.details)
        except Exception as exc:
            consecutive_errors += 1
            # Log with backoff info to help diagnose persistent issues
            backoff = min(MAX_BACKOFF_SECONDS, cfg.monitor.interval_seconds * (2 ** min(consecutive_errors - 1, 5)))
            if consecutive_errors <= 3:
                # Log full exception for first few errors
                watchdog_log.exception("monitor loop error (attempt %s): %s", consecutive_errors, exc)
            else:
                # Log summary for repeated errors to reduce noise
                watchdog_log.error(
                    "monitor loop error (attempt %s, backing off %ss): %s",
                    consecutive_errors,
                    backoff,
                    exc,
                )
            time.sleep(backoff)
            continue  # Skip the normal sleep since we already slept with backoff

        time.sleep(cfg.monitor.interval_seconds)
