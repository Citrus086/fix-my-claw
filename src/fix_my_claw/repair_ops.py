"""Operational helpers for the repair pipeline."""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from string import Template
from typing import Any, TypeVar

from .config import AppConfig
from .health import HealthEvaluation, probe_health, probe_logs, probe_status
from .messages import ai_decision_no, ai_decision_yes
from .repair_types import AiDecision, SessionStageData, StageResult
from .runtime import CmdResult, run_cmd
from .shared import (
    _parse_json_maybe,
    _write_attempt_file,
    ensure_dir,
    redact_text,
    truncate_for_log,
)


NOTIFY_LEVEL_ALL = "all"
NOTIFY_LEVEL_IMPORTANT = "important"
NOTIFY_LEVEL_CRITICAL = "critical"

_T = TypeVar("_T")


def _resolve_default(value: _T | None, default: _T) -> _T:
    return default if value is None else value


def _parse_agent_id_from_session_key(key: str) -> str | None:
    match = re.match(r"^agent:([^:]+):", key or "")
    if not match:
        return None
    return match.group(1)


def _list_active_sessions(
    cfg: AppConfig,
    *,
    active_minutes: int,
    run_cmd_fn: Callable[..., CmdResult] | None = None,
    parse_json_maybe_fn: Callable[[str], Any] | None = None,
) -> list[dict[str, Any]]:
    run_cmd_fn = _resolve_default(run_cmd_fn, run_cmd)
    parse_json_maybe_fn = _resolve_default(parse_json_maybe_fn, _parse_json_maybe)
    argv = [
        cfg.openclaw.command,
        "sessions",
        "--all-agents",
        "--active",
        str(active_minutes),
        "--json",
    ]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    res = run_cmd_fn(argv, timeout_seconds=max(15, cfg.monitor.probe_timeout_seconds), cwd=cwd)
    data = parse_json_maybe_fn(res.stdout)
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


def _backup_openclaw_state(
    cfg: AppConfig,
    attempt_dir: Path,
    *,
    write_attempt_file_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    write_attempt_file_fn = _resolve_default(write_attempt_file_fn, _write_attempt_file)
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
    write_attempt_file_fn(attempt_dir, "backup.json", json.dumps(out, ensure_ascii=False, indent=2))
    return out


def _run_session_command_stage(
    cfg: AppConfig,
    attempt_dir: Path,
    *,
    stage_name: str,
    message_text: str,
    list_active_sessions_fn: Callable[..., list[dict[str, Any]]] | None = None,
    parse_agent_id_from_session_key_fn: Callable[[str], str | None] | None = None,
    run_cmd_fn: Callable[..., CmdResult] | None = None,
    write_attempt_file_fn: Callable[..., Any] | None = None,
    redact_text_fn: Callable[[str], str] | None = None,
) -> list[dict[str, Any]]:
    list_active_sessions_fn = _resolve_default(list_active_sessions_fn, _list_active_sessions)
    parse_agent_id_from_session_key_fn = _resolve_default(parse_agent_id_from_session_key_fn, _parse_agent_id_from_session_key)
    run_cmd_fn = _resolve_default(run_cmd_fn, run_cmd)
    write_attempt_file_fn = _resolve_default(write_attempt_file_fn, _write_attempt_file)
    redact_text_fn = _resolve_default(redact_text_fn, redact_text)
    repair_log = logging.getLogger("fix_my_claw.repair")
    results: list[dict[str, Any]] = []
    if not cfg.repair.session_control_enabled or not message_text.strip():
        return results
    sessions = list_active_sessions_fn(cfg, active_minutes=cfg.repair.session_active_minutes)
    allow_agents = set(cfg.repair.session_agents)
    for session in sessions:
        key = str(session.get("key", ""))
        agent_id = parse_agent_id_from_session_key_fn(key) or str(session.get("agentId", ""))
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
        res = run_cmd_fn(argv, timeout_seconds=cfg.repair.session_command_timeout_seconds, cwd=cwd)
        repair_log.warning(
            "%s stage: agent=%s session=%s exit=%s", stage_name, agent_id, session_id, res.exit_code
        )
        idx = len(results) + 1
        stdout_name = f"{stage_name}.{idx}.stdout.txt"
        stderr_name = f"{stage_name}.{idx}.stderr.txt"
        write_attempt_file_fn(attempt_dir, stdout_name, redact_text_fn(res.stdout))
        write_attempt_file_fn(attempt_dir, stderr_name, redact_text_fn(res.stderr))
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


MAX_ATTEMPT_DIR_AGE_SECONDS = 7 * 24 * 60 * 60


def _cleanup_old_attempt_dirs(cfg: AppConfig) -> int:
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
                dir_mtime = entry.stat().st_mtime
                if now - dir_mtime > MAX_ATTEMPT_DIR_AGE_SECONDS:
                    shutil.rmtree(entry)
                    removed_count += 1
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        pass
    return removed_count


def _attempt_dir(
    cfg: AppConfig,
    *,
    ensure_dir_fn: Callable[[Path], Any] | None = None,
    cleanup_old_attempt_dirs_fn: Callable[[AppConfig], int] | None = None,
) -> Path:
    ensure_dir_fn = _resolve_default(ensure_dir_fn, ensure_dir)
    cleanup_old_attempt_dirs_fn = _resolve_default(cleanup_old_attempt_dirs_fn, _cleanup_old_attempt_dirs)
    base = cfg.monitor.state_dir / "attempts"
    ensure_dir_fn(base)
    cleanup_old_attempt_dirs_fn(cfg)
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
    evaluate_health_fn: Callable[..., HealthEvaluation] | None = None,
    context_logs_timeout_seconds_fn: Callable[[AppConfig], int] | None = None,
    collect_context_fn: Callable[..., dict[str, Any]] | None = None,
) -> tuple[HealthEvaluation, dict]:
    evaluate_health_fn = _resolve_default(evaluate_health_fn, _evaluate_health)
    context_logs_timeout_seconds_fn = _resolve_default(context_logs_timeout_seconds_fn, _context_logs_timeout_seconds)
    collect_context_fn = _resolve_default(collect_context_fn, _collect_context)
    evaluation = evaluate_health_fn(
        cfg,
        log_probe_failures=log_probe_failures,
        capture_logs=True,
        logs_timeout_seconds=context_logs_timeout_seconds_fn(cfg),
    )
    context = collect_context_fn(evaluation, attempt_dir, stage_name=stage_name)
    return evaluation, context


def _collect_context(
    evaluation: HealthEvaluation,
    attempt_dir: Path,
    *,
    stage_name: str,
    write_attempt_file_fn: Callable[..., Any] | None = None,
    redact_text_fn: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    write_attempt_file_fn = _resolve_default(write_attempt_file_fn, _write_attempt_file)
    redact_text_fn = _resolve_default(redact_text_fn, redact_text)
    logs = evaluation.logs_probe
    prefix = f"context.{stage_name}"
    health_stdout = f"{prefix}.health.stdout.txt"
    health_stderr = f"{prefix}.health.stderr.txt"
    status_stdout = f"{prefix}.status.stdout.txt"
    status_stderr = f"{prefix}.status.stderr.txt"
    logs_file = f"{prefix}.openclaw.logs.txt" if logs is not None else None

    write_attempt_file_fn(attempt_dir, health_stdout, redact_text_fn(evaluation.health_probe.cmd.stdout))
    write_attempt_file_fn(attempt_dir, health_stderr, redact_text_fn(evaluation.health_probe.cmd.stderr))
    write_attempt_file_fn(attempt_dir, status_stdout, redact_text_fn(evaluation.status_probe.cmd.stdout))
    write_attempt_file_fn(attempt_dir, status_stderr, redact_text_fn(evaluation.status_probe.cmd.stderr))
    if logs is not None and logs_file is not None:
        logs_text = logs.stdout + ("\n" + logs.stderr if logs.stderr else "")
        write_attempt_file_fn(attempt_dir, logs_file, redact_text_fn(logs_text))

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
    probe_health_fn: Callable[..., Any] | None = None,
    probe_status_fn: Callable[..., Any] | None = None,
    probe_logs_fn: Callable[..., CmdResult] | None = None,
    analyze_anomaly_guard_fn: Callable[..., dict[str, Any]] | None = None,
) -> HealthEvaluation:
    probe_health_fn = _resolve_default(probe_health_fn, probe_health)
    probe_status_fn = _resolve_default(probe_status_fn, probe_status)
    probe_logs_fn = _resolve_default(probe_logs_fn, probe_logs)
    if analyze_anomaly_guard_fn is None:
        from .anomaly_guard import _analyze_anomaly_guard

        analyze_anomaly_guard_fn = _analyze_anomaly_guard

    health = probe_health_fn(cfg, log_on_fail=log_probe_failures)
    status = probe_status_fn(cfg, log_on_fail=log_probe_failures)
    probe_healthy = health.ok and status.ok
    effective_healthy = probe_healthy
    reason: str | None = None
    logs_probe: CmdResult | None = None
    anomaly_guard: dict | None = None
    should_collect_logs = capture_logs or (probe_healthy and cfg.anomaly_guard.enabled)
    if should_collect_logs:
        logs_probe = probe_logs_fn(
            cfg,
            timeout_seconds=logs_timeout_seconds or cfg.anomaly_guard.probe_timeout_seconds,
        )
    if not probe_healthy:
        reason = "probe_failed"
    elif cfg.anomaly_guard.enabled:
        if logs_probe is None:
            raise RuntimeError("anomaly guard requires a logs probe")
        anomaly_guard = analyze_anomaly_guard_fn(cfg, logs=logs_probe)
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
    run_cmd_fn: Callable[..., CmdResult] | None = None,
    write_attempt_file_fn: Callable[..., Any] | None = None,
    redact_text_fn: Callable[[str], str] | None = None,
    truncate_for_log_fn: Callable[[str], str] | None = None,
    evaluate_health_fn: Callable[..., HealthEvaluation] | None = None,
    context_logs_timeout_seconds_fn: Callable[[AppConfig], int] | None = None,
    sleep_fn: Callable[[float], Any] | None = None,
) -> tuple[list[dict], HealthEvaluation, str]:
    run_cmd_fn = _resolve_default(run_cmd_fn, run_cmd)
    write_attempt_file_fn = _resolve_default(write_attempt_file_fn, _write_attempt_file)
    redact_text_fn = _resolve_default(redact_text_fn, redact_text)
    truncate_for_log_fn = _resolve_default(truncate_for_log_fn, truncate_for_log)
    evaluate_health_fn = _resolve_default(evaluate_health_fn, _evaluate_health)
    context_logs_timeout_seconds_fn = _resolve_default(context_logs_timeout_seconds_fn, _context_logs_timeout_seconds)
    sleep_fn = _resolve_default(sleep_fn, time.sleep)
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
        res = run_cmd_fn(argv, timeout_seconds=cfg.repair.step_timeout_seconds, cwd=cwd)
        repair_log.info(
            "official step %d/%d done: exit=%s duration_ms=%s",
            idx,
            total,
            res.exit_code,
            res.duration_ms,
        )
        if res.stderr:
            repair_log.info("official step %d/%d stderr: %s", idx, total, truncate_for_log_fn(res.stderr))
        stdout_name = f"official.{idx}.stdout.txt"
        stderr_name = f"official.{idx}.stderr.txt"
        write_attempt_file_fn(attempt_dir, stdout_name, redact_text_fn(res.stdout))
        write_attempt_file_fn(attempt_dir, stderr_name, redact_text_fn(res.stderr))
        results.append(
            {
                "argv": res.argv,
                "exit_code": res.exit_code,
                "duration_ms": res.duration_ms,
                "stdout_path": str((attempt_dir / stdout_name).resolve()),
                "stderr_path": str((attempt_dir / stderr_name).resolve()),
            }
        )
        sleep_fn(cfg.repair.post_step_wait_seconds)
        last_evaluation = evaluate_health_fn(
            cfg,
            log_probe_failures=False,
            capture_logs=True,
            logs_timeout_seconds=context_logs_timeout_seconds_fn(cfg),
        )
        break_reason = "steps_exhausted"
        if break_on_healthy and last_evaluation.effective_healthy:
            break_reason = "healthy"
            repair_log.info("OpenClaw is healthy after official step %d/%d", idx, total)
            break
    if last_evaluation is None:
        last_evaluation = evaluate_health_fn(
            cfg,
            log_probe_failures=False,
            capture_logs=True,
            logs_timeout_seconds=context_logs_timeout_seconds_fn(cfg),
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


def _run_ai_repair(
    cfg: AppConfig,
    attempt_dir: Path,
    *,
    code_stage: bool,
    load_prompt_text_fn: Callable[[str], str] | None = None,
    build_ai_cmd_fn: Callable[..., list[str]] | None = None,
    run_cmd_fn: Callable[..., CmdResult] | None = None,
    write_attempt_file_fn: Callable[..., Any] | None = None,
    redact_text_fn: Callable[[str], str] | None = None,
    truncate_for_log_fn: Callable[[str], str] | None = None,
) -> CmdResult:
    load_prompt_text_fn = _resolve_default(load_prompt_text_fn, _load_prompt_text)
    build_ai_cmd_fn = _resolve_default(build_ai_cmd_fn, _build_ai_cmd)
    run_cmd_fn = _resolve_default(run_cmd_fn, run_cmd)
    write_attempt_file_fn = _resolve_default(write_attempt_file_fn, _write_attempt_file)
    redact_text_fn = _resolve_default(redact_text_fn, redact_text)
    truncate_for_log_fn = _resolve_default(truncate_for_log_fn, truncate_for_log)
    prompt_name = "repair_code.md" if code_stage else "repair.md"
    prompt = Template(load_prompt_text_fn(prompt_name)).safe_substitute(
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

    argv = build_ai_cmd_fn(cfg, code_stage=code_stage)
    logging.getLogger("fix_my_claw.repair").warning(
        "AI repair (%s) starting: %s", "code" if code_stage else "config", argv
    )
    res = run_cmd_fn(
        argv,
        timeout_seconds=cfg.ai.timeout_seconds,
        cwd=cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None,
        stdin_text=prompt,
    )
    stage_name = "code" if code_stage else "config"
    write_attempt_file_fn(attempt_dir, f"ai.{stage_name}.argv.txt", " ".join(argv))
    write_attempt_file_fn(attempt_dir, f"ai.{stage_name}.stdout.txt", redact_text_fn(res.stdout))
    write_attempt_file_fn(attempt_dir, f"ai.{stage_name}.stderr.txt", redact_text_fn(res.stderr))
    logging.getLogger("fix_my_claw.repair").warning("AI repair done: exit=%s", res.exit_code)
    if res.stderr:
        logging.getLogger("fix_my_claw.repair").warning("AI stderr: %s", truncate_for_log_fn(res.stderr))
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
