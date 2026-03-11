from __future__ import annotations

import logging
import time

from .config import AppConfig
from .health import HealthEvaluation
from .messages import manual_repair_acknowledged, monitor_unhealthy_skipped
from .notification_events import _clean_fix_my_claw_message, dispatch_notification_event
from .notify import _notify_send, _poll_manual_repair_command
from .repair import _evaluate_health, attempt_repair
from .state import StateStore

# Constants for monitor loop behavior
MAX_BACKOFF_SECONDS = 300  # 5 minutes max backoff on repeated errors


def run_check(cfg: AppConfig, store: StateStore) -> HealthEvaluation:
    evaluation = _evaluate_health(cfg)
    if evaluation.effective_healthy:
        store.mark_ok()
    return evaluation


def _log_repair_result(watchdog_log: logging.Logger, result: object, *, prefix: str) -> None:
    details = getattr(result, "details", {}) or {}
    if getattr(result, "attempted", False):
        watchdog_log.warning(
            "%s finished: fixed=%s used_codex=%s dir=%s",
            prefix,
            getattr(result, "fixed", False),
            getattr(result, "used_ai", False),
            details.get("attempt_dir"),
        )
        return
    if details.get("cooldown"):
        remaining = details.get("cooldown_remaining_seconds")
        watchdog_log.info(
            "%s skipped: cooldown (%ss remaining)",
            prefix,
            remaining if remaining is not None else "?",
        )
        return
    watchdog_log.info("%s skipped: %s", prefix, details)


def _handle_manual_repair_request(cfg: AppConfig, store: StateStore, watchdog_log: logging.Logger) -> bool:
    command = _poll_manual_repair_command(cfg)
    if not command:
        return False
    content = command.get("content", "")
    watchdog_log.warning(
        "manual repair requested via %s: message_id=%s author_id=%s monitoring_enabled=%s",
        command.get("source"),
        command.get("message_id"),
        command.get("author_id"),
        store.is_enabled(),
    )
    # Send acknowledgment notification to Discord
    try:
        dispatch_notification_event(
            cfg.monitor.state_dir,
            kind="manual_repair_acknowledged",
            source="monitor",
            level="all",
            message_text=manual_repair_acknowledged(content),
            send_channel=True,
            notify_channel_fn=_notify_send,
            cfg=cfg,
            silent=False,
            local_title="🛠️ 收到手动修复请求",
            local_body="频道命令已确认，立即开始修复流程。",
            dedupe_key=f"manual_repair_acknowledged:{command.get('message_id') or content}",
        )
    except Exception as exc:
        watchdog_log.warning("failed to send manual repair acknowledgment: %s", exc)
    result = attempt_repair(
        cfg,
        store,
        force=True,
        reason="manual_discord",
    )
    _log_repair_result(watchdog_log, result, prefix="manual repair")
    return True


def monitor_loop(cfg: AppConfig, store: StateStore) -> None:
    watchdog_log = logging.getLogger("fix_my_claw.watchdog")
    watchdog_log.info("starting monitor loop: interval=%ss", cfg.monitor.interval_seconds)
    monitor_disabled = False
    # Error backoff to prevent log spam on repeated failures
    consecutive_errors = 0

    while True:
        try:
            if _handle_manual_repair_request(cfg, store, watchdog_log):
                consecutive_errors = 0
                time.sleep(cfg.monitor.interval_seconds)
                continue
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
                        "unhealthy: health_exit=%s status_exit=%s; anomaly guard triggered: reason=%s signals=%s",
                        evaluation.health_probe.cmd.exit_code,
                        evaluation.status_probe.cmd.exit_code,
                        evaluation.reason,
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
                    reason=evaluation.reason if anomaly_triggered else None,
                )
                details = getattr(result, "details", {}) or {}
                if not getattr(result, "attempted", False):
                    if details.get("repair_disabled"):
                        dedupe_key = "monitor_unhealthy:repair_disabled"
                    elif details.get("cooldown"):
                        dedupe_key = "monitor_unhealthy:cooldown"
                    else:
                        dedupe_key = "monitor_unhealthy:generic"
                    skipped_message = monitor_unhealthy_skipped(
                        repair_disabled=bool(details.get("repair_disabled")),
                        cooldown_remaining_seconds=details.get("cooldown_remaining_seconds"),
                    )
                    dispatch_notification_event(
                        cfg.monitor.state_dir,
                        kind="monitor_unhealthy",
                        source="monitor",
                        level="critical",
                        message_text=skipped_message,
                        send_channel=True,
                        notify_channel_fn=_notify_send,
                        cfg=cfg,
                        silent=False,
                        local_title="🔴 OpenClaw 异常",
                        local_body=_clean_fix_my_claw_message(skipped_message) or "检测到异常状态。",
                        dedupe_key=dedupe_key,
                    )
                _log_repair_result(watchdog_log, result, prefix="repair")
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
