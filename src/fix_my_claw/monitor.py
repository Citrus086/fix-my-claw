from __future__ import annotations

import logging
import time

from .config import AppConfig
from .health import HealthEvaluation
from .repair import _evaluate_health, attempt_repair
from .state import StateStore


def run_check(cfg: AppConfig, store: StateStore) -> HealthEvaluation:
    evaluation = _evaluate_health(cfg)
    if evaluation.effective_healthy:
        store.mark_ok()
    return evaluation


def monitor_loop(cfg: AppConfig, store: StateStore) -> None:
    watchdog_log = logging.getLogger("fix_my_claw.watchdog")
    watchdog_log.info("starting monitor loop: interval=%ss", cfg.monitor.interval_seconds)
    while True:
        try:
            evaluation = run_check(cfg, store)
            if not evaluation.effective_healthy:
                watchdog_log.warning(
                    "unhealthy: health_exit=%s status_exit=%s; attempting repair",
                    evaluation.health_probe.cmd.exit_code,
                    evaluation.status_probe.cmd.exit_code,
                )
                anomaly_triggered = bool(evaluation.anomaly_guard and evaluation.anomaly_guard.get("triggered"))
                if anomaly_triggered:
                    watchdog_log.warning(
                        "anomaly guard triggered: signals=%s",
                        evaluation.anomaly_guard.get("signals"),
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
            watchdog_log.exception("monitor loop error: %s", exc)
        time.sleep(cfg.monitor.interval_seconds)
