from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Any

from .anomaly_guard import _analyze_anomaly_guard
from .config import AppConfig
from .health import HealthEvaluation, probe_health, probe_logs, probe_status
from .messages import (
    REPAIR_AI_CODE_SUCCESS,
    REPAIR_AI_CONFIG_SUCCESS,
    REPAIR_AI_DISABLED,
    REPAIR_AI_RATE_LIMITED,
    REPAIR_FINAL_STILL_UNHEALTHY,
    REPAIR_NO_YES_RECEIVED,
    REPAIR_RECOVERED_AFTER_PAUSE,
    REPAIR_RECOVERED_BY_OFFICIAL,
    REPAIR_STARTING,
    ai_decision_no,
    ai_decision_yes,
    ask_enable_ai_prompt,
    backup_completed,
    repair_backup_failed,
)
from .notify import _ask_user_enable_ai, _notify_send
from .runtime import CmdResult, run_cmd
from .shared import (
    _parse_json_maybe,
    _write_attempt_file,
    clear_repair_progress,
    ensure_dir,
    redact_text,
    truncate_for_log,
    write_repair_progress,
)
from .state import StateStore, _now_ts

# Import types from repair_types module
from .repair_types import (
    AiDecision,
    AiRepairStageData,
    BackupArtifact,
    CommandExecutionRecord,
    OfficialRepairStageData,
    PauseCheckStageData,
    RepairOutcome,
    RepairPipelineContext,
    RepairResult,
    SessionStageData,
    StagePayload,
    StageResult,
    _cmd_result_to_json,
    _coerce_execution_records,
    _records_to_json,
    _require_stage_payload,
)

# Re-export types for backward compatibility
__all__ = [
    "AiDecision",
    "AiRepairStageData",
    "BackupArtifact",
    "CommandExecutionRecord",
    "OfficialRepairStageData",
    "PauseCheckStageData",
    "RepairOutcome",
    "RepairPipelineContext",
    "RepairResult",
    "SessionStageData",
    "StagePayload",
    "StageResult",
    "_cmd_result_to_json",
    "_coerce_execution_records",
    "_records_to_json",
    "_require_stage_payload",
]


# Notification level constants
NOTIFY_LEVEL_ALL = "all"
NOTIFY_LEVEL_IMPORTANT = "important"
NOTIFY_LEVEL_CRITICAL = "critical"


def _should_notify(cfg: AppConfig, level: str) -> bool:
    """Check if a notification should be sent based on configured level.
    
    Args:
        cfg: Application configuration
        level: The notification level - "all", "important", or "critical"
    
    Returns:
        True if the notification should be sent
    """
    configured_level = cfg.notify.level.strip().lower()
    
    if configured_level == NOTIFY_LEVEL_ALL:
        return True
    
    if configured_level == NOTIFY_LEVEL_IMPORTANT:
        # important: notify on important and critical
        return level in {NOTIFY_LEVEL_IMPORTANT, NOTIFY_LEVEL_CRITICAL}
    
    if configured_level == NOTIFY_LEVEL_CRITICAL:
        # critical: only notify on critical events
        return level == NOTIFY_LEVEL_CRITICAL
    
    # Default to all if unknown level
    return True


def _notify_send_with_level(cfg: AppConfig, text: str, level: str, *, silent: bool | None = None) -> dict[str, Any] | None:
    """Send notification if level permits.
    
    Args:
        cfg: Application configuration
        text: Notification text
        level: Notification level - "all", "important", or "critical"
        silent: Override silent setting
    
    Returns:
        Notification result dict or None if not sent
    """
    if not _should_notify(cfg, level):
        return None
    return _notify_send(cfg, text, silent=silent)


def _parse_agent_id_from_session_key(key: str) -> str | None:
    match = re.match(r"^agent:([^:]+):", key or "")
    if not match:
        return None
    return match.group(1)


def _list_active_sessions(cfg: AppConfig, *, active_minutes: int) -> list[dict[str, Any]]:
    argv = [
        cfg.openclaw.command,
        "sessions",
        "--all-agents",
        "--active",
        str(active_minutes),
        "--json",
    ]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    res = run_cmd(argv, timeout_seconds=max(15, cfg.monitor.probe_timeout_seconds), cwd=cwd)
    data = _parse_json_maybe(res.stdout)
    if not res.ok or not isinstance(data, dict):
        return []
    sessions = data.get("sessions", [])
    if not isinstance(sessions, list):
        return []
    out: list[dict[str, Any]] = []
    for item in sessions:
        if isinstance(item, dict):
            out.append(item)
    return out


def _backup_openclaw_state(cfg: AppConfig, attempt_dir: Path) -> dict[str, Any]:
    src = cfg.openclaw.state_dir
    if not src.exists():
        raise FileNotFoundError(f"openclaw state dir not found: {src}")
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    parent = src.parent
    archive_base = parent / f"{src.name}.backup-{stamp}"
    archive_path = shutil.make_archive(
        base_name=str(archive_base),
        format="gztar",
        root_dir=str(parent),
        base_dir=src.name,
    )
    out = {"source": str(src), "archive": archive_path}
    _write_attempt_file(attempt_dir, "backup.json", json.dumps(out, ensure_ascii=False, indent=2))
    return out


def _run_session_command_stage(
    cfg: AppConfig,
    attempt_dir: Path,
    *,
    stage_name: str,
    message_text: str,
) -> list[dict[str, Any]]:
    repair_log = logging.getLogger("fix_my_claw.repair")
    results: list[dict[str, Any]] = []
    if not cfg.repair.session_control_enabled or not message_text.strip():
        return results
    sessions = _list_active_sessions(cfg, active_minutes=cfg.repair.session_active_minutes)
    allow_agents = set(cfg.repair.session_agents)
    for session in sessions:
        key = str(session.get("key", ""))
        agent_id = _parse_agent_id_from_session_key(key) or str(session.get("agentId", ""))
        if not agent_id or agent_id not in allow_agents:
            continue
        session_id = str(session.get("sessionId", "")).strip()
        if not session_id:
            continue
        argv = [
            cfg.openclaw.command,
            "agent",
            "--agent",
            agent_id,
            "--session-id",
            session_id,
            "--message",
            message_text,
        ]
        cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
        res = run_cmd(argv, timeout_seconds=cfg.repair.session_command_timeout_seconds, cwd=cwd)
        repair_log.warning(
            "%s stage: agent=%s session=%s exit=%s", stage_name, agent_id, session_id, res.exit_code
        )
        idx = len(results) + 1
        stdout_name = f"{stage_name}.{idx}.stdout.txt"
        stderr_name = f"{stage_name}.{idx}.stderr.txt"
        _write_attempt_file(attempt_dir, stdout_name, redact_text(res.stdout))
        _write_attempt_file(attempt_dir, stderr_name, redact_text(res.stderr))
        results.append(
            {
                "agent": agent_id,
                "session_id": session_id,
                "argv": res.argv,
                "exit_code": res.exit_code,
                "duration_ms": res.duration_ms,
                "stdout_path": str((attempt_dir / stdout_name).resolve()),
                "stderr_path": str((attempt_dir / stderr_name).resolve()),
            }
        )
    return results


# Maximum age in seconds for attempt directories (7 days)
MAX_ATTEMPT_DIR_AGE_SECONDS = 7 * 24 * 60 * 60


def _cleanup_old_attempt_dirs(cfg: AppConfig) -> int:
    """Remove attempt directories older than MAX_ATTEMPT_DIR_AGE_SECONDS.

    Returns the number of directories removed.
    """
    base = cfg.monitor.state_dir / "attempts"
    if not base.exists():
        return 0

    removed_count = 0
    now = time.time()
    try:
        for entry in base.iterdir():
            if not entry.is_dir():
                continue
            try:
                # Check directory modification time
                dir_mtime = entry.stat().st_mtime
                if now - dir_mtime > MAX_ATTEMPT_DIR_AGE_SECONDS:
                    shutil.rmtree(entry)
                    removed_count += 1
            except (OSError, PermissionError):
                # Skip directories we can't access or remove
                continue
    except (OSError, PermissionError):
        pass
    return removed_count


def _attempt_dir(cfg: AppConfig) -> Path:
    base = cfg.monitor.state_dir / "attempts"
    ensure_dir(base)
    # Clean up old attempt directories before creating a new one
    _cleanup_old_attempt_dirs(cfg)
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    return Path(tempfile.mkdtemp(prefix=f"{ts}-", dir=str(base)))


def _context_logs_timeout_seconds(cfg: AppConfig) -> int:
    return max(cfg.monitor.probe_timeout_seconds, cfg.anomaly_guard.probe_timeout_seconds)


def _evaluate_with_context(
    cfg: AppConfig,
    attempt_dir: Path,
    *,
    stage_name: str,
    log_probe_failures: bool = False,
) -> tuple[HealthEvaluation, dict]:
    evaluation = _evaluate_health(
        cfg,
        log_probe_failures=log_probe_failures,
        capture_logs=True,
        logs_timeout_seconds=_context_logs_timeout_seconds(cfg),
    )
    context = _collect_context(evaluation, attempt_dir, stage_name=stage_name)
    return evaluation, context


def _collect_context(evaluation: HealthEvaluation, attempt_dir: Path, *, stage_name: str) -> dict:
    logs = evaluation.logs_probe
    prefix = f"context.{stage_name}"
    health_stdout = f"{prefix}.health.stdout.txt"
    health_stderr = f"{prefix}.health.stderr.txt"
    status_stdout = f"{prefix}.status.stdout.txt"
    status_stderr = f"{prefix}.status.stderr.txt"
    logs_file = f"{prefix}.openclaw.logs.txt" if logs is not None else None

    _write_attempt_file(attempt_dir, health_stdout, redact_text(evaluation.health_probe.cmd.stdout))
    _write_attempt_file(attempt_dir, health_stderr, redact_text(evaluation.health_probe.cmd.stderr))
    _write_attempt_file(attempt_dir, status_stdout, redact_text(evaluation.status_probe.cmd.stdout))
    _write_attempt_file(attempt_dir, status_stderr, redact_text(evaluation.status_probe.cmd.stderr))
    if logs is not None and logs_file is not None:
        logs_text = logs.stdout + ("\n" + logs.stderr if logs.stderr else "")
        _write_attempt_file(attempt_dir, logs_file, redact_text(logs_text))

    return {
        "healthy": evaluation.effective_healthy,
        "probe_healthy": evaluation.probe_healthy,
        "reason": evaluation.reason,
        "health": evaluation.health,
        "status": evaluation.status,
        "logs": (
            {
                "ok": logs.ok,
                "exit_code": logs.exit_code,
                "duration_ms": logs.duration_ms,
                "argv": logs.argv,
                "stdout_path": str((attempt_dir / logs_file).resolve()),
            }
            if logs is not None and logs_file is not None
            else None
        ),
        "attempt_dir": str(attempt_dir.resolve()),
    }


def _evaluate_health(
    cfg: AppConfig,
    *,
    log_probe_failures: bool = False,
    capture_logs: bool = False,
    logs_timeout_seconds: int | None = None,
) -> HealthEvaluation:
    health = probe_health(cfg, log_on_fail=log_probe_failures)
    status = probe_status(cfg, log_on_fail=log_probe_failures)
    probe_healthy = health.ok and status.ok
    effective_healthy = probe_healthy
    reason: str | None = None
    logs_probe: CmdResult | None = None
    anomaly_guard: dict | None = None
    should_collect_logs = capture_logs or (probe_healthy and cfg.anomaly_guard.enabled)
    if should_collect_logs:
        logs_probe = probe_logs(
            cfg,
            timeout_seconds=logs_timeout_seconds or cfg.anomaly_guard.probe_timeout_seconds,
        )
    if not probe_healthy:
        reason = "probe_failed"
    elif cfg.anomaly_guard.enabled:
        if logs_probe is None:
            raise RuntimeError("anomaly guard requires a logs probe")
        anomaly_guard = _analyze_anomaly_guard(cfg, logs=logs_probe)
        if anomaly_guard.get("triggered"):
            effective_healthy = False
            reason = "anomaly_guard"
    return HealthEvaluation(
        health_probe=health,
        status_probe=status,
        logs_probe=logs_probe,
        anomaly_guard=anomaly_guard,
        probe_healthy=probe_healthy,
        effective_healthy=effective_healthy,
        reason=reason,
    )


def _run_official_steps(
    cfg: AppConfig,
    attempt_dir: Path,
    *,
    break_on_healthy: bool = True,
) -> tuple[list[dict], HealthEvaluation, str]:
    repair_log = logging.getLogger("fix_my_claw.repair")
    results: list[dict] = []
    last_evaluation: HealthEvaluation | None = None
    break_reason = "no_steps"
    total = len(cfg.repair.official_steps)
    for idx, step in enumerate(cfg.repair.official_steps, start=1):
        if not step:
            continue
        argv = [cfg.openclaw.command if step[0] == "openclaw" else step[0], *step[1:]]
        repair_log.info("official step %d/%d: %s", idx, total, " ".join(argv))
        cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
        res = run_cmd(argv, timeout_seconds=cfg.repair.step_timeout_seconds, cwd=cwd)
        repair_log.info(
            "official step %d/%d done: exit=%s duration_ms=%s",
            idx,
            total,
            res.exit_code,
            res.duration_ms,
        )
        if res.stderr:
            repair_log.info("official step %d/%d stderr: %s", idx, total, truncate_for_log(res.stderr))
        stdout_name = f"official.{idx}.stdout.txt"
        stderr_name = f"official.{idx}.stderr.txt"
        _write_attempt_file(attempt_dir, stdout_name, redact_text(res.stdout))
        _write_attempt_file(attempt_dir, stderr_name, redact_text(res.stderr))
        results.append(
            {
                "argv": res.argv,
                "exit_code": res.exit_code,
                "duration_ms": res.duration_ms,
                "stdout_path": str((attempt_dir / stdout_name).resolve()),
                "stderr_path": str((attempt_dir / stderr_name).resolve()),
            }
        )
        time.sleep(cfg.repair.post_step_wait_seconds)
        last_evaluation = _evaluate_health(
            cfg,
            log_probe_failures=False,
            capture_logs=True,
            logs_timeout_seconds=_context_logs_timeout_seconds(cfg),
        )
        break_reason = "steps_exhausted"
        if break_on_healthy and last_evaluation.effective_healthy:
            break_reason = "healthy"
            repair_log.info("OpenClaw is healthy after official step %d/%d", idx, total)
            break
    if last_evaluation is None:
        last_evaluation = _evaluate_health(
            cfg,
            log_probe_failures=False,
            capture_logs=True,
            logs_timeout_seconds=_context_logs_timeout_seconds(cfg),
        )
    return results, last_evaluation, break_reason


def _load_prompt_text(name: str) -> str:
    from importlib.resources import files

    return (files("fix_my_claw.prompts") / name).read_text(encoding="utf-8")


def _build_ai_cmd(cfg: AppConfig, *, code_stage: bool) -> list[str]:
    variables = {
        "workspace_dir": str(cfg.openclaw.workspace_dir),
        "openclaw_state_dir": str(cfg.openclaw.state_dir),
        "monitor_state_dir": str(cfg.monitor.state_dir),
    }
    args = cfg.ai.args_code if code_stage else cfg.ai.args
    rendered = [Template(arg).safe_substitute(variables) for arg in args]
    argv = [cfg.ai.command]
    if cfg.ai.model:
        argv += ["-m", cfg.ai.model]
    argv += rendered
    return argv


def _run_ai_repair(cfg: AppConfig, attempt_dir: Path, *, code_stage: bool) -> CmdResult:
    prompt_name = "repair_code.md" if code_stage else "repair.md"
    prompt = Template(_load_prompt_text(prompt_name)).safe_substitute(
        {
            "attempt_dir": str(attempt_dir.resolve()),
            "workspace_dir": str(cfg.openclaw.workspace_dir),
            "openclaw_state_dir": str(cfg.openclaw.state_dir),
            "monitor_state_dir": str(cfg.monitor.state_dir),
            "health_cmd": " ".join([cfg.openclaw.command, *cfg.openclaw.health_args]),
            "status_cmd": " ".join([cfg.openclaw.command, *cfg.openclaw.status_args]),
            "logs_cmd": " ".join([cfg.openclaw.command, *cfg.openclaw.logs_args]),
        }
    )

    argv = _build_ai_cmd(cfg, code_stage=code_stage)
    logging.getLogger("fix_my_claw.repair").warning(
        "AI repair (%s) starting: %s", "code" if code_stage else "config", argv
    )
    res = run_cmd(
        argv,
        timeout_seconds=cfg.ai.timeout_seconds,
        cwd=cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None,
        stdin_text=prompt,
    )
    stage_name = "code" if code_stage else "config"
    _write_attempt_file(attempt_dir, f"ai.{stage_name}.argv.txt", " ".join(argv))
    _write_attempt_file(attempt_dir, f"ai.{stage_name}.stdout.txt", redact_text(res.stdout))
    _write_attempt_file(attempt_dir, f"ai.{stage_name}.stderr.txt", redact_text(res.stderr))
    logging.getLogger("fix_my_claw.repair").warning("AI repair done: exit=%s", res.exit_code)
    if res.stderr:
        logging.getLogger("fix_my_claw.repair").warning("AI stderr: %s", truncate_for_log(res.stderr))
    return res


def _session_stage_has_successful_commands(stage: StageResult) -> bool:
    if not isinstance(stage.payload, SessionStageData):
        return False
    return any(record.exit_code == 0 for record in stage.payload.commands)


def _should_try_soft_pause(cfg: AppConfig, evaluation: HealthEvaluation) -> bool:
    return (
        cfg.repair.soft_pause_enabled
        and cfg.repair.session_control_enabled
        and bool(cfg.repair.pause_message.strip())
        and evaluation.status_probe.ok
    )


def _ai_decision_source_label(decision: AiDecision) -> str:
    source = str(decision.raw.get("source", "")).strip().lower()
    if source == "gui":
        return "GUI"
    if source == "discord":
        return "Discord"
    return "用户"


def _ai_decision_notification_text(decision: AiDecision) -> str | None:
    source = _ai_decision_source_label(decision)
    if decision.decision == "yes":
        return ai_decision_yes(source)
    if decision.decision == "no":
        return ai_decision_no(source)
    return None


@dataclass(frozen=True)
class SessionPauseStage:
    def run(self, ctx: RepairPipelineContext) -> StageResult:
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="pause",
            status="running",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        commands = _coerce_execution_records(
            _run_session_command_stage(
                ctx.cfg,
                ctx.attempt_dir,
                stage_name="pause",
                message_text=ctx.cfg.repair.pause_message,
            )
        )
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="pause",
            status="completed",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        return StageResult(
            name="pause",
            status="completed",
            payload=SessionStageData(stage_name="pause", commands=commands),
        )


@dataclass(frozen=True)
class PauseAssessmentStage:
    def run(self, ctx: RepairPipelineContext, *, previous_stage: StageResult) -> StageResult:
        waited_before_seconds = 0
        payload = _require_stage_payload(previous_stage, SessionStageData)
        if payload.commands and ctx.cfg.repair.pause_wait_seconds > 0:
            time.sleep(ctx.cfg.repair.pause_wait_seconds)
            waited_before_seconds = ctx.cfg.repair.pause_wait_seconds
        evaluation, context = _evaluate_with_context(
            ctx.cfg,
            ctx.attempt_dir,
            stage_name="after_pause",
        )
        return StageResult(
            name="pause_check",
            status="completed",
            payload=PauseCheckStageData(waited_before_seconds=waited_before_seconds),
            evaluation=evaluation,
            context=context,
            stop_reason="healthy_after_pause" if evaluation.effective_healthy else "still_unhealthy_after_pause",
        )


@dataclass(frozen=True)
class SessionTerminateStage:
    def run(self, ctx: RepairPipelineContext) -> StageResult:
        commands = _coerce_execution_records(
            _run_session_command_stage(
                ctx.cfg,
                ctx.attempt_dir,
                stage_name="terminate",
                message_text=ctx.cfg.repair.terminate_message,
            )
        )
        return StageResult(
            name="terminate",
            status="completed",
            payload=SessionStageData(stage_name="terminate", commands=commands),
        )


@dataclass(frozen=True)
class SessionResetStage:
    def run(self, ctx: RepairPipelineContext, *, previous_stage: StageResult | None) -> StageResult:
        waited_before_seconds = 0
        if previous_stage is not None:
            payload = _require_stage_payload(previous_stage, SessionStageData)
            if payload.commands and ctx.cfg.repair.session_stage_wait_seconds > 0:
                time.sleep(ctx.cfg.repair.session_stage_wait_seconds)
                waited_before_seconds = ctx.cfg.repair.session_stage_wait_seconds
        commands = _coerce_execution_records(
            _run_session_command_stage(
                ctx.cfg,
                ctx.attempt_dir,
                stage_name="new",
                message_text=ctx.cfg.repair.new_message,
            )
        )
        return StageResult(
            name="new",
            status="completed",
            payload=SessionStageData(
                stage_name="new",
                commands=commands,
                waited_before_seconds=waited_before_seconds,
            ),
        )


@dataclass(frozen=True)
class OfficialRepairStage:
    def run(self, ctx: RepairPipelineContext) -> StageResult:
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="official",
            status="running",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        steps, evaluation, break_reason = _run_official_steps(
            ctx.cfg,
            ctx.attempt_dir,
            break_on_healthy=True,
        )
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="official",
            status="completed",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        return StageResult(
            name="official",
            status="completed",
            payload=OfficialRepairStageData(
                steps=_coerce_execution_records(steps),
                break_reason=break_reason,
            ),
            evaluation=evaluation,
            context=_collect_context(evaluation, ctx.attempt_dir, stage_name="after_official"),
            stop_reason=break_reason,
        )


@dataclass(frozen=True)
class AiDecisionStage:
    preset: dict[str, Any] | None = None

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="ai_decision",
            status="running",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        decision = self.preset or _ask_user_enable_ai(ctx.cfg, ctx.attempt_dir)
        payload = AiDecision.from_mapping(decision)
        notification_text = _ai_decision_notification_text(payload)
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="ai_decision",
            status="completed",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        return StageResult(
            name="ai_decision",
            status="completed",
            payload=payload,
            notification=(
                _notify_send_with_level(ctx.cfg, notification_text, NOTIFY_LEVEL_ALL, silent=False)
                if notification_text is not None
                else None
            ),
        )


@dataclass(frozen=True)
class BackupStage:
    def run(self, ctx: RepairPipelineContext) -> StageResult:
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="backup",
            status="running",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        try:
            artifact = BackupArtifact.from_mapping(_backup_openclaw_state(ctx.cfg, ctx.attempt_dir))
        except Exception as exc:
            write_repair_progress(
                ctx.cfg.monitor.state_dir,
                stage="backup",
                status="failed",
                attempt_dir=str(ctx.attempt_dir.resolve()),
            )
            return StageResult(
                name="backup",
                status="failed",
                payload=BackupArtifact(error=str(exc)),
                stop_reason="backup_error",
            )
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="backup",
            status="completed",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        return StageResult(
            name="backup",
            status="completed",
            payload=artifact,
            notification=_notify_send_with_level(
                ctx.cfg,
                backup_completed(artifact.archive),
                NOTIFY_LEVEL_IMPORTANT,
                silent=False,
            ),
        )


@dataclass(frozen=True)
class AiRepairStage:
    code_stage: bool

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        result = _run_ai_repair(ctx.cfg, ctx.attempt_dir, code_stage=self.code_stage)
        stage_suffix = "code" if self.code_stage else "config"
        evaluation, context = _evaluate_with_context(
            ctx.cfg,
            ctx.attempt_dir,
            stage_name=f"after_ai_{stage_suffix}",
        )
        return StageResult(
            name=f"ai_{stage_suffix}",
            status="completed",
            payload=AiRepairStageData(stage_name=stage_suffix, result=result),
            evaluation=evaluation,
            context=context,
            used_ai=True,
        )


@dataclass(frozen=True)
class FinalAssessmentStage:
    stage_name: str

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        evaluation, context = _evaluate_with_context(
            ctx.cfg,
            ctx.attempt_dir,
            stage_name=self.stage_name,
        )
        return StageResult(
            name="final",
            status="completed",
            evaluation=evaluation,
            context=context,
        )


def _result_from_outcome(*, attempted: bool, outcome: RepairOutcome) -> RepairResult:
    return RepairResult(
        attempted=attempted,
        fixed=outcome.fixed,
        used_ai=outcome.used_ai,
        outcome=outcome,
    )


def attempt_repair(
    cfg: AppConfig,
    store: StateStore,
    *,
    force: bool,
    reason: str | None = None,
) -> RepairResult:
    repair_log = logging.getLogger("fix_my_claw.repair")
    initial_evaluation = _evaluate_health(
        cfg,
        log_probe_failures=False,
        capture_logs=True,
        logs_timeout_seconds=_context_logs_timeout_seconds(cfg),
    )
    if initial_evaluation.effective_healthy:
        repair_log.info("repair skipped: already healthy")
        clear_repair_progress(cfg.monitor.state_dir)
        return RepairResult(attempted=False, fixed=True, used_ai=False, details_data={"already_healthy": True})

    if not cfg.repair.enabled:
        repair_log.warning("repair skipped: disabled by config")
        clear_repair_progress(cfg.monitor.state_dir)
        return RepairResult(attempted=False, fixed=False, used_ai=False, details_data={"repair_disabled": True})

    if not store.can_attempt_repair(cfg.monitor.repair_cooldown_seconds, force=force):
        details: dict[str, object] = {"cooldown": True}
        state = store.load()
        if state.last_repair_ts is not None:
            elapsed = _now_ts() - state.last_repair_ts
            remaining = max(0, cfg.monitor.repair_cooldown_seconds - elapsed)
            details["cooldown_remaining_seconds"] = remaining
            repair_log.info("repair skipped: cooldown (%ss remaining)", remaining)
        else:
            repair_log.info("repair skipped: cooldown")
        clear_repair_progress(cfg.monitor.state_dir)
        return RepairResult(attempted=False, fixed=False, used_ai=False, details_data=details)

    attempt_dir = _attempt_dir(cfg)
    store.mark_repair_attempt()
    ctx = RepairPipelineContext(cfg=cfg, store=store, attempt_dir=attempt_dir)
    outcome = RepairOutcome(attempt_dir=str(attempt_dir.resolve()), reason=reason)
    repair_log.info("starting repair attempt: dir=%s", attempt_dir.resolve())
    
    # 写入初始进度
    write_repair_progress(
        cfg.monitor.state_dir,
        stage="starting",
        status="running",
        attempt_dir=str(attempt_dir.resolve()),
    )
    outcome.start_notification = _notify_send_with_level(
        cfg,
        REPAIR_STARTING,
        NOTIFY_LEVEL_IMPORTANT,
        silent=False,
    )

    outcome.before_context = _collect_context(initial_evaluation, attempt_dir, stage_name="before")
    if _should_try_soft_pause(cfg, initial_evaluation):
        pause_candidate = SessionPauseStage().run(ctx)
        pause_payload = _require_stage_payload(pause_candidate, SessionStageData)
        if pause_payload.commands:
            pause_stage = outcome.add_stage(pause_candidate)
            if _session_stage_has_successful_commands(pause_stage):
                pause_check_stage = outcome.add_stage(PauseAssessmentStage().run(ctx, previous_stage=pause_stage))
                if pause_check_stage.fixed:
                    outcome.final_stage = pause_check_stage
                    outcome.final_notification = _notify_send_with_level(
                        cfg,
                        REPAIR_RECOVERED_AFTER_PAUSE,
                        NOTIFY_LEVEL_IMPORTANT,
                    )
                    repair_log.info("recovered after soft pause: dir=%s", attempt_dir.resolve())
                    clear_repair_progress(cfg.monitor.state_dir)
                    return _result_from_outcome(attempted=True, outcome=outcome)
    terminate_stage = outcome.add_stage(SessionTerminateStage().run(ctx))
    outcome.add_stage(SessionResetStage().run(ctx, previous_stage=terminate_stage))
    official_stage = outcome.add_stage(OfficialRepairStage().run(ctx))

    if official_stage.fixed:
        outcome.final_stage = official_stage
        outcome.final_notification = _notify_send_with_level(
            cfg,
            REPAIR_RECOVERED_BY_OFFICIAL,
            NOTIFY_LEVEL_IMPORTANT,
        )
        repair_log.info("recovered by official steps: dir=%s", attempt_dir.resolve())
        clear_repair_progress(cfg.monitor.state_dir)
        return _result_from_outcome(attempted=True, outcome=outcome)

    if not cfg.ai.enabled:
        repair_log.info("Codex-assisted remediation disabled; leaving OpenClaw unhealthy")
        final_stage = outcome.add_stage(FinalAssessmentStage(stage_name="final_no_ai").run(ctx))
        outcome.final_stage = final_stage
        outcome.final_notification = _notify_send_with_level(
            cfg,
            REPAIR_AI_DISABLED,
            NOTIFY_LEVEL_IMPORTANT,
            silent=False,
        )
        clear_repair_progress(cfg.monitor.state_dir)
        return _result_from_outcome(attempted=True, outcome=outcome)

    if not store.can_attempt_ai(
        max_attempts_per_day=cfg.ai.max_attempts_per_day,
        cooldown_seconds=cfg.ai.cooldown_seconds,
    ):
        # 直接创建限流决策，不运行 stage（避免触发 GUI 标志检查）
        outcome.add_stage(StageResult(
            name="ai_decision",
            status="completed",
            payload=AiDecision.from_mapping({"asked": False, "decision": "rate_limited"}),
        ))
        final_stage = outcome.add_stage(FinalAssessmentStage(stage_name="final_rate_limited").run(ctx))
        outcome.final_stage = final_stage
        outcome.final_notification = _notify_send_with_level(
            cfg,
            REPAIR_AI_RATE_LIMITED,
            NOTIFY_LEVEL_ALL,
            silent=False,
        )
        clear_repair_progress(cfg.monitor.state_dir)
        return _result_from_outcome(attempted=True, outcome=outcome)

    ai_decision_stage = outcome.add_stage(AiDecisionStage().run(ctx))
    ai_decision = _require_stage_payload(ai_decision_stage, AiDecision)
    if ai_decision.decision != "yes":
        final_stage = outcome.add_stage(FinalAssessmentStage(stage_name="final_no_approval").run(ctx))
        outcome.final_stage = final_stage
        if ai_decision_stage.notification is not None:
            outcome.final_notification = ai_decision_stage.notification
        else:
            outcome.final_notification = _notify_send_with_level(
                cfg,
                REPAIR_NO_YES_RECEIVED,
                NOTIFY_LEVEL_IMPORTANT,
                silent=False,
            )
        clear_repair_progress(cfg.monitor.state_dir)
        return _result_from_outcome(attempted=True, outcome=outcome)

    backup_stage = outcome.add_stage(BackupStage().run(ctx))
    backup_artifact = _require_stage_payload(backup_stage, BackupArtifact)
    if backup_stage.status != "completed":
        outcome.final_stage = outcome.add_stage(FinalAssessmentStage(stage_name="final_backup_error").run(ctx))
        outcome.final_notification = _notify_send_with_level(
            cfg,
            repair_backup_failed(backup_artifact.error),
            NOTIFY_LEVEL_IMPORTANT,
            silent=False,
        )
        clear_repair_progress(cfg.monitor.state_dir)
        return _result_from_outcome(attempted=True, outcome=outcome)

    store.mark_ai_attempt()
    ai_config_stage = outcome.add_stage(AiRepairStage(code_stage=False).run(ctx))
    if ai_config_stage.fixed:
        outcome.final_stage = ai_config_stage
        outcome.final_notification = _notify_send_with_level(
            cfg,
            REPAIR_AI_CONFIG_SUCCESS,
            NOTIFY_LEVEL_IMPORTANT,
            silent=False,
        )
        repair_log.info("recovered by Codex-assisted remediation: dir=%s", attempt_dir.resolve())
        clear_repair_progress(cfg.monitor.state_dir)
        return _result_from_outcome(attempted=True, outcome=outcome)

    if cfg.ai.allow_code_changes:
        ai_code_stage = outcome.add_stage(AiRepairStage(code_stage=True).run(ctx))
        if ai_code_stage.fixed:
            outcome.final_stage = ai_code_stage
            outcome.final_notification = _notify_send_with_level(
                cfg,
                REPAIR_AI_CODE_SUCCESS,
                NOTIFY_LEVEL_IMPORTANT,
                silent=False,
            )
            repair_log.info("recovered by code-stage remediation: dir=%s", attempt_dir.resolve())
            clear_repair_progress(cfg.monitor.state_dir)
            return _result_from_outcome(attempted=True, outcome=outcome)

    final_stage = outcome.add_stage(FinalAssessmentStage(stage_name="final").run(ctx))
    outcome.final_stage = final_stage
    outcome.final_notification = _notify_send_with_level(
        cfg,
        REPAIR_FINAL_STILL_UNHEALTHY,
        NOTIFY_LEVEL_CRITICAL,
        silent=False,
    )
    repair_log.warning(
        "repair attempt finished: fixed=%s used_codex=%s dir=%s",
        outcome.fixed,
        outcome.used_ai,
        attempt_dir.resolve(),
    )
    clear_repair_progress(cfg.monitor.state_dir)
    return _result_from_outcome(attempted=True, outcome=outcome)
