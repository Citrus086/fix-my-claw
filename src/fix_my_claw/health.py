from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from .config import AppConfig
from .runtime import CmdResult, run_cmd
from .shared import truncate_for_log


@dataclass(frozen=True)
class Probe:
    name: str
    cmd: CmdResult
    json_data: dict | list | None

    @property
    def ok(self) -> bool:
        return self.cmd.ok

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "exit_code": self.cmd.exit_code,
            "duration_ms": self.cmd.duration_ms,
            "argv": self.cmd.argv,
            "stdout": self.cmd.stdout,
            "stderr": self.cmd.stderr,
            "json": self.json_data,
        }


@dataclass(frozen=True)
class HealthEvaluation:
    health_probe: Probe
    status_probe: Probe
    logs_probe: CmdResult | None
    anomaly_guard: dict | None
    probe_healthy: bool
    effective_healthy: bool
    reason: str | None = None

    @property
    def healthy(self) -> bool:
        return self.effective_healthy

    @property
    def health(self) -> dict:
        return self.health_probe.to_json()

    @property
    def status(self) -> dict:
        return self.status_probe.to_json()

    def to_check_json(self) -> dict:
        out = {
            "healthy": self.effective_healthy,
            "probe_healthy": self.probe_healthy,
            "reason": self.reason,
            "health": self.health,
            "status": self.status,
        }
        if self.logs_probe is not None:
            out["logs"] = {
                "ok": self.logs_probe.ok,
                "exit_code": self.logs_probe.exit_code,
                "duration_ms": self.logs_probe.duration_ms,
                "argv": self.logs_probe.argv,
            }
        if self.anomaly_guard is not None:
            out["anomaly_guard"] = self.anomaly_guard
            out["loop_guard"] = self.anomaly_guard
        return out


def _parse_json_maybe(stdout: str) -> dict | list | None:
    s = stdout.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def probe_health(cfg: AppConfig, *, log_on_fail: bool = True) -> Probe:
    argv = [cfg.openclaw.command, *cfg.openclaw.health_args]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    cmd = run_cmd(argv, timeout_seconds=cfg.monitor.probe_timeout_seconds, cwd=cwd)
    data = _parse_json_maybe(cmd.stdout)
    if log_on_fail and not cmd.ok:
        logging.getLogger("fix_my_claw.openclaw").warning(
            "health probe failed: %s", truncate_for_log(cmd.stderr or cmd.stdout)
        )
    return Probe(name="health", cmd=cmd, json_data=data)


def probe_status(cfg: AppConfig, *, log_on_fail: bool = True) -> Probe:
    argv = [cfg.openclaw.command, *cfg.openclaw.status_args]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    cmd = run_cmd(argv, timeout_seconds=cfg.monitor.probe_timeout_seconds, cwd=cwd)
    data = _parse_json_maybe(cmd.stdout)
    if log_on_fail and not cmd.ok:
        logging.getLogger("fix_my_claw.openclaw").warning(
            "status probe failed: %s", truncate_for_log(cmd.stderr or cmd.stdout)
        )
    return Probe(name="status", cmd=cmd, json_data=data)


def probe_logs(cfg: AppConfig, *, timeout_seconds: int = 15) -> CmdResult:
    argv = [cfg.openclaw.command, *cfg.openclaw.logs_args]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    return run_cmd(argv, timeout_seconds=timeout_seconds, cwd=cwd)
