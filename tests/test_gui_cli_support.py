from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fix_my_claw import cli
from fix_my_claw import config as config_module
from fix_my_claw import health as health_module
from fix_my_claw import protocol as protocol_module
from fix_my_claw import repair_types
from fix_my_claw import state as state_module
from fix_my_claw.runtime import CmdResult


def _cmd_result(
    argv: list[str],
    *,
    exit_code: int = 0,
    duration_ms: int = 10,
    stdout: str = "",
    stderr: str = "",
    cwd: Path | None = None,
) -> CmdResult:
    return CmdResult(
        argv=argv,
        cwd=cwd,
        exit_code=exit_code,
        duration_ms=duration_ms,
        stdout=stdout,
        stderr=stderr,
    )


def _probe(
    name: str,
    argv: list[str],
    *,
    exit_code: int = 0,
    duration_ms: int = 10,
    stdout: str = "",
    stderr: str = "",
    json_data: dict | list | None = None,
    cwd: Path | None = None,
) -> health_module.Probe:
    return health_module.Probe(
        name=name,
        cmd=_cmd_result(
            argv,
            exit_code=exit_code,
            duration_ms=duration_ms,
            stdout=stdout,
            stderr=stderr,
            cwd=cwd,
        ),
        json_data=json_data,
    )


class TestConfigJsonSupport(unittest.TestCase):
    def test_config_to_dict_round_trips_paths_and_nested_sections(self) -> None:
        cfg = config_module.AppConfig(
            monitor=config_module.MonitorConfig(
                interval_seconds=90,
                state_dir=Path("/tmp/fix-my-claw-state"),
                log_file=Path("/tmp/fix-my-claw.log"),
            ),
            ai=config_module.AiConfig(enabled=True),
        )

        data = config_module._config_to_dict(cfg)

        self.assertEqual(data["monitor"]["interval_seconds"], 90)
        self.assertEqual(data["monitor"]["state_dir"], "/tmp/fix-my-claw-state")
        self.assertEqual(data["monitor"]["log_file"], "/tmp/fix-my-claw.log")
        self.assertTrue(data["ai"]["enabled"])

        rebuilt = config_module._dict_to_config(data)
        self.assertEqual(rebuilt.monitor.interval_seconds, 90)
        self.assertEqual(rebuilt.monitor.state_dir, Path("/tmp/fix-my-claw-state").resolve())
        self.assertEqual(rebuilt.monitor.log_file, Path("/tmp/fix-my-claw.log").resolve())
        self.assertTrue(rebuilt.ai.enabled)

    def test_agent_roles_round_trip_with_flat_structure(self) -> None:
        """Test that agent_roles is serialized as flat structure, not nested under 'roles'."""
        custom_roles = {
            "orchestrator": ("orch", "my-orch"),
            "builder": ("bld", "my-builder"),
            "architect": ("arch",),
            "research": ("res", "research-agent"),
        }
        cfg = config_module.AppConfig(
            agent_roles=config_module.AgentRolesConfig(roles=custom_roles)
        )

        data = config_module._config_to_dict(cfg)

        # Should be flat: {"orchestrator": [...], "builder": [...]}
        # NOT nested: {"roles": {"orchestrator": [...], ...}}
        self.assertIn("orchestrator", data["agent_roles"])
        self.assertIn("builder", data["agent_roles"])
        self.assertNotIn("roles", data["agent_roles"])

        # Verify the values are lists (JSON serializable)
        self.assertIsInstance(data["agent_roles"]["orchestrator"], list)
        self.assertEqual(data["agent_roles"]["orchestrator"], ["orch", "my-orch"])

        # Round-trip should preserve custom roles
        rebuilt = config_module._dict_to_config(data)
        self.assertEqual(rebuilt.agent_roles.roles["orchestrator"], ("orch", "my-orch"))
        self.assertEqual(rebuilt.agent_roles.roles["builder"], ("bld", "my-builder"))

    def test_agent_roles_merge_with_defaults(self) -> None:
        """Test that partial agent_roles config merges with defaults instead of replacing."""
        # Only override orchestrator
        merged = config_module._parse_agent_roles({"orchestrator": ["my-orch"]})

        # Custom value should be used
        self.assertEqual(merged.roles["orchestrator"], ("my-orch",))

        # Other roles should still have defaults
        self.assertIn("builder", merged.roles)
        self.assertIn("architect", merged.roles)
        self.assertIn("research", merged.roles)
        self.assertEqual(merged.roles["builder"], ("builder", "macs-builder"))

    def test_default_config_json_contains_gui_contract_fields(self) -> None:
        data = config_module._config_to_dict(config_module.AppConfig())

        self.assertEqual(data["monitor"]["log_max_bytes"], 5 * 1024 * 1024)
        self.assertEqual(data["openclaw"]["health_args"], ["gateway", "health", "--json"])
        self.assertEqual(
            data["repair"]["official_steps"],
            [["openclaw", "doctor", "--repair"], ["openclaw", "gateway", "restart"]],
        )
        self.assertEqual(
            data["notify"]["manual_repair_keywords"],
            ["手动修复", "manual repair", "修复", "repair"],
        )
        self.assertEqual(data["notify"]["required_mention_id"], "")
        self.assertEqual(data["notify"]["max_invalid_replies"], 3)
        self.assertEqual(data["notify"]["ai_approve_keywords"], ["yes", "是"])
        self.assertEqual(data["notify"]["ai_reject_keywords"], ["no", "否"])
        self.assertEqual(data["ai"]["provider"], "codex")
        self.assertEqual(data["ai"]["args_code"][0:3], ["exec", "-s", "danger-full-access"])
        self.assertEqual(
            data["agent_roles"]["orchestrator"],
            ["orchestrator", "macs-orchestrator"],
        )


class TestGuiCliCommands(unittest.TestCase):
    def test_cmd_config_show_emits_json_payload(self) -> None:
        cfg = config_module.AppConfig(
            monitor=config_module.MonitorConfig(interval_seconds=75),
            ai=config_module.AiConfig(enabled=True),
        )
        args = SimpleNamespace(config="~/.fix-my-claw/config.toml", json=True)

        stdout = io.StringIO()
        with patch.object(cli, "_load_or_init_config", return_value=cfg), patch("sys.stdout", new=stdout):
            code = cli.cmd_config_show(args)

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["api_version"], protocol_module.API_VERSION)
        self.assertEqual(payload["monitor"]["interval_seconds"], 75)
        self.assertTrue(payload["ai"]["enabled"])

    def test_notify_level_round_trips_correctly(self) -> None:
        """Test that notify.level field is preserved during config round-trip.

        This ensures GUI won't silently reset notify.level when saving existing config.
        See: Step 2 of repair-refactor-plan.md - GUI Schema Drift 修复
        """
        # Test all valid values
        for level_value in ("all", "important", "critical"):
            cfg = config_module.AppConfig(
                notify=config_module.NotifyConfig(level=level_value)
            )

            data = config_module._config_to_dict(cfg)
            self.assertEqual(data["notify"]["level"], level_value)

            # Round-trip
            rebuilt = config_module._dict_to_config(data)
            self.assertEqual(rebuilt.notify.level, level_value)

    def test_notify_level_defaults_to_all(self) -> None:
        """Test that notify.level defaults to 'all' when not specified."""
        cfg = config_module.NotifyConfig()
        self.assertEqual(cfg.level, "all")

        # Also test parsing from empty dict
        parsed = config_module._parse_notify({})
        self.assertEqual(parsed.level, "all")

    def test_cmd_config_set_reads_json_from_stdin_and_writes_normalized_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            args = SimpleNamespace(config=str(config_path), json=True)
            stdin_payload = {
                "monitor": {
                    "interval_seconds": 120,
                    "state_dir": str(Path(tmpdir) / "state"),
                    "log_file": str(Path(tmpdir) / "fix-my-claw.log"),
                },
                "ai": {"enabled": True},
            }

            stdout = io.StringIO()
            with patch("sys.stdin", new=io.StringIO(json.dumps(stdin_payload))), patch.object(
                cli, "_write_toml"
            ) as write_mock, patch("sys.stdout", new=stdout):
                code = cli.cmd_config_set(args)

            self.assertEqual(code, 0)
            write_mock.assert_called_once()
            written_path, written_data = write_mock.call_args.args
            self.assertEqual(written_path, config_path.resolve())
            self.assertEqual(written_data["monitor"]["interval_seconds"], 120)
            self.assertTrue(written_data["ai"]["enabled"])
            self.assertIn("openclaw", written_data)

    def test_cmd_config_set_ignores_api_version_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            args = SimpleNamespace(config=str(config_path), json=True)
            stdin_payload = {
                "api_version": "9.9",
                "monitor": {
                    "interval_seconds": 30,
                    "state_dir": str(Path(tmpdir) / "state"),
                    "log_file": str(Path(tmpdir) / "fix-my-claw.log"),
                },
            }

            with patch("sys.stdin", new=io.StringIO(json.dumps(stdin_payload))), patch.object(
                cli, "_write_toml"
            ) as write_mock, patch("sys.stdout", new=io.StringIO()):
                code = cli.cmd_config_set(args)

            self.assertEqual(code, 0)
            _, written_data = write_mock.call_args.args
            self.assertNotIn("api_version", written_data)
            self.assertEqual(written_data["monitor"]["interval_seconds"], 30)

    def test_cmd_config_set_preserves_gui_round_trip_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            args = SimpleNamespace(config=str(config_path), json=True)
            stdin_payload = {
                "monitor": {
                    "state_dir": str(Path(tmpdir) / "state"),
                    "log_file": str(Path(tmpdir) / "fix-my-claw.log"),
                },
                "openclaw": {
                    "command": "openclaw",
                    "health_args": ["gateway", "health", "--json"],
                    "status_args": ["gateway", "status", "--json"],
                    "logs_args": ["logs", "--limit", "300", "--plain"],
                },
                "repair": {
                    "session_agents": ["orch", "builder"],
                    "official_steps": [
                        ["openclaw", "doctor", "--repair"],
                        ["openclaw", "gateway", "restart"],
                    ],
                    "pause_message": "[CONTROL]\\nAction: PAUSE\\n",
                },
                "notify": {
                    "level": "important",
                    "required_mention_id": "123456",
                    "max_invalid_replies": 5,
                    "operator_user_ids": ["user-1"],
                    "manual_repair_keywords": ["repair now", "手动修复"],
                    "ai_approve_keywords": ["yes", "批准"],
                    "ai_reject_keywords": ["no", "拒绝"],
                },
                "ai": {
                    "enabled": True,
                    "args": [
                        "exec",
                        "-s",
                        "workspace-write",
                        "-C",
                        "$workspace_dir",
                    ],
                    "args_code": [
                        "exec",
                        "-s",
                        "danger-full-access",
                        "-C",
                        "$workspace_dir",
                    ],
                },
                "agent_roles": {
                    "orchestrator": ["orch", "macs-orchestrator"],
                    "builder": ["bld", "macs-builder"],
                    "architect": ["arch"],
                    "research": ["res"],
                },
            }

            with patch("sys.stdin", new=io.StringIO(json.dumps(stdin_payload))), patch.object(
                cli, "_write_toml"
            ) as write_mock, patch("sys.stdout", new=io.StringIO()):
                code = cli.cmd_config_set(args)

            self.assertEqual(code, 0)
            _, written_data = write_mock.call_args.args
            self.assertEqual(written_data["openclaw"]["logs_args"], ["logs", "--limit", "300", "--plain"])
            self.assertEqual(
                written_data["repair"]["official_steps"],
                [["openclaw", "doctor", "--repair"], ["openclaw", "gateway", "restart"]],
            )
            self.assertEqual(
                written_data["notify"]["manual_repair_keywords"],
                ["repair now", "手动修复"],
            )
            self.assertEqual(written_data["notify"]["required_mention_id"], "123456")
            self.assertEqual(written_data["notify"]["max_invalid_replies"], 5)
            self.assertEqual(written_data["notify"]["ai_approve_keywords"], ["yes", "批准"])
            self.assertEqual(written_data["notify"]["ai_reject_keywords"], ["no", "拒绝"])
            self.assertEqual(
                written_data["ai"]["args_code"],
                ["exec", "-s", "danger-full-access", "-C", "$workspace_dir"],
            )
            self.assertEqual(written_data["agent_roles"]["architect"], ["arch"])

    def test_cmd_status_emits_gui_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "state"
            store = state_module.StateStore(state_dir)
            store.save(
                state_module.State(
                    enabled=False,
                    last_ok_ts=11,
                    last_repair_ts=22,
                    last_ai_ts=33,
                    ai_attempts_day="2026-03-09",
                    ai_attempts_count=2,
                )
            )
            cfg = config_module.AppConfig(
                monitor=config_module.MonitorConfig(state_dir=state_dir)
            )
            config_path = Path(tmpdir) / "config.toml"
            args = SimpleNamespace(config=str(config_path), json=True)
            stdout = io.StringIO()

            with patch.object(cli, "_load_config_or_default", return_value=(cfg, True)), patch.object(
                cli, "setup_logging"
            ), patch("sys.stdout", new=stdout):
                code = cli.cmd_status(args)

            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["api_version"], protocol_module.API_VERSION)
            self.assertEqual(payload["enabled"], False)
            self.assertEqual(payload["config_path"], str(config_path.resolve()))
            self.assertEqual(payload["config_exists"], True)
            self.assertEqual(payload["state_path"], str(store.path))
            self.assertEqual(payload["last_ok_ts"], 11)
            self.assertEqual(payload["last_repair_ts"], 22)
            self.assertEqual(payload["last_ai_ts"], 33)
            self.assertEqual(payload["ai_attempts_day"], "2026-03-09")
            self.assertEqual(payload["ai_attempts_count"], 2)

    def test_cmd_check_emits_gui_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            evaluation = health_module.HealthEvaluation(
                health_probe=_probe(
                    "health",
                    ["openclaw", "gateway", "health", "--json"],
                    exit_code=1,
                    duration_ms=150,
                    stdout='{"ok": false}',
                    stderr="gateway unavailable",
                    json_data={"ok": False},
                    cwd=workspace,
                ),
                status_probe=_probe(
                    "status",
                    ["openclaw", "gateway", "status", "--json"],
                    duration_ms=80,
                    stdout='{"mode": "degraded"}',
                    json_data={"mode": "degraded"},
                    cwd=workspace,
                ),
                logs_probe=_cmd_result(
                    ["openclaw", "logs", "--limit", "200", "--plain"],
                    duration_ms=25,
                    stdout="recent logs",
                    cwd=workspace,
                ),
                anomaly_guard={
                    "enabled": True,
                    "triggered": True,
                    "probe_ok": True,
                    "probe_exit_code": 0,
                    "metrics": {
                        "lines_analyzed": 120,
                        "events_analyzed": 9,
                        "cycle_repeated_turns": 4,
                        "ping_pong_turns": 0,
                    },
                    "signals": {
                        "repeat_trigger": False,
                        "similar_repeat_trigger": False,
                        "ping_pong_trigger": False,
                        "cycle_trigger": True,
                        "stagnation_trigger": False,
                        "auto_dispatch_trigger": False,
                    },
                },
                probe_healthy=False,
                effective_healthy=False,
                reason="gateway unhealthy",
            )
            cfg = config_module.AppConfig()
            args = SimpleNamespace(config=str(Path(tmpdir) / "config.toml"), json=True)
            stdout = io.StringIO()

            with patch.object(cli, "_load_or_init_config", return_value=cfg), patch.object(
                cli, "setup_logging"
            ), patch.object(cli, "run_check", return_value=evaluation), patch(
                "sys.stdout", new=stdout
            ):
                code = cli.cmd_check(args)

            self.assertEqual(code, 1)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["api_version"], protocol_module.API_VERSION)
            self.assertEqual(payload["healthy"], False)
            self.assertEqual(payload["probe_healthy"], False)
            self.assertEqual(payload["reason"], "gateway unhealthy")
            self.assertEqual(payload["health"]["name"], "health")
            self.assertEqual(payload["health"]["exit_code"], 1)
            self.assertEqual(payload["status"]["name"], "status")
            self.assertEqual(payload["logs"]["argv"], ["openclaw", "logs", "--limit", "200", "--plain"])
            self.assertEqual(payload["anomaly_guard"]["triggered"], True)
            self.assertEqual(payload["loop_guard"]["signals"]["cycle_trigger"], True)

    def test_cmd_repair_emits_post_refactor_ai_config_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outcome = repair_types.RepairOutcome(
                attempt_dir=str(Path(tmpdir) / "attempt-001"),
                reason="gateway unhealthy",
                final_notification={
                    "sent": True,
                    "message_id": "msg-1",
                    "message_text": "fix-my-claw: AI config repair completed",
                },
            )
            outcome.add_stage(
                repair_types.StageResult(
                    name="official",
                    status="completed",
                    payload=repair_types.OfficialRepairStageData(
                        steps=(),
                        break_reason="still_unhealthy",
                    ),
                )
            )
            outcome.add_stage(
                repair_types.StageResult(
                    name="ai_decision",
                    status="completed",
                    payload=repair_types.AiDecision(
                        asked=True,
                        decision="yes",
                        raw={"asked": True, "decision": "yes", "source": "discord"},
                    ),
                )
            )
            outcome.add_stage(
                repair_types.StageResult(
                    name="ai_config",
                    status="completed",
                    payload=repair_types.AiRepairStageData(
                        stage_name="ai_config",
                        result=_cmd_result(
                            ["codex", "exec", "-C", str(Path(tmpdir) / "workspace")],
                            duration_ms=900,
                            stdout="patched config",
                        ),
                    ),
                    used_ai=True,
                )
            )
            repair_result = repair_types.RepairResult(
                attempted=True,
                fixed=True,
                used_ai=True,
                outcome=outcome,
            )
            args = SimpleNamespace(config=str(Path(tmpdir) / "config.toml"), json=True, force=False)
            stdout = io.StringIO()

            with patch.object(cli, "_load_or_init_config", return_value=config_module.AppConfig()), patch.object(
                cli, "setup_logging"
            ), patch.object(
                cli, "_with_single_instance", side_effect=lambda _cfg, action: action()
            ), patch.object(
                cli, "attempt_repair", return_value=repair_result
            ), patch("sys.stdout", new=stdout):
                code = cli.cmd_repair(args)

            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["api_version"], protocol_module.API_VERSION)
            self.assertEqual(payload["attempted"], True)
            self.assertEqual(payload["fixed"], True)
            self.assertEqual(payload["used_ai"], True)
            self.assertEqual(payload["details"]["attempt_dir"], str(Path(tmpdir) / "attempt-001"))
            self.assertEqual(payload["details"]["official_break_reason"], "still_unhealthy")
            self.assertEqual(payload["details"]["ai_decision"]["decision"], "yes")
            self.assertEqual(payload["details"]["ai_stage"], "config")
            self.assertEqual(
                payload["details"]["notify_final"]["message_text"],
                "fix-my-claw: AI config repair completed",
            )

    def test_cmd_repair_emits_backup_error_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outcome = repair_types.RepairOutcome(
                attempt_dir=str(Path(tmpdir) / "attempt-002"),
                reason="gateway unhealthy",
            )
            outcome.add_stage(
                repair_types.StageResult(
                    name="official",
                    status="completed",
                    payload=repair_types.OfficialRepairStageData(
                        steps=(),
                        break_reason="still_unhealthy",
                    ),
                )
            )
            outcome.add_stage(
                repair_types.StageResult(
                    name="ai_decision",
                    status="completed",
                    payload=repair_types.AiDecision(
                        asked=True,
                        decision="yes",
                        raw={"asked": True, "decision": "yes"},
                    ),
                )
            )
            outcome.add_stage(
                repair_types.StageResult(
                    name="backup",
                    status="failed",
                    payload=repair_types.BackupArtifact(error="disk full"),
                    notification={"sent": False, "message_text": "backup failed"},
                )
            )
            repair_result = repair_types.RepairResult(
                attempted=True,
                fixed=False,
                used_ai=False,
                outcome=outcome,
            )
            args = SimpleNamespace(config=str(Path(tmpdir) / "config.toml"), json=True, force=False)
            stdout = io.StringIO()

            with patch.object(cli, "_load_or_init_config", return_value=config_module.AppConfig()), patch.object(
                cli, "setup_logging"
            ), patch.object(
                cli, "_with_single_instance", side_effect=lambda _cfg, action: action()
            ), patch.object(
                cli, "attempt_repair", return_value=repair_result
            ), patch("sys.stdout", new=stdout):
                code = cli.cmd_repair(args)

            self.assertEqual(code, 1)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["api_version"], protocol_module.API_VERSION)
            self.assertEqual(payload["attempted"], True)
            self.assertEqual(payload["fixed"], False)
            self.assertEqual(payload["details"]["backup_before_ai_error"], "disk full")
            self.assertEqual(payload["details"]["notify_backup"]["message_text"], "backup failed")

    def test_cmd_service_status_emits_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plist_path = Path(tmpdir) / "com.fix-my-claw.monitor.plist"
            plist_path.write_text("plist", encoding="utf-8")
            args = SimpleNamespace(json=True)
            stdout = io.StringIO()

            with patch.object(cli, "_service_platform_supported", return_value=True), patch.object(
                cli, "_get_launchd_plist_path", return_value=plist_path
            ), patch.object(
                cli,
                "_launchctl_run",
                return_value=subprocess.CompletedProcess(["launchctl"], 0, "", ""),
            ), patch("sys.stdout", new=stdout):
                code = cli.cmd_service_status(args)

            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["api_version"], protocol_module.API_VERSION)
            self.assertTrue(payload["installed"])
            self.assertTrue(payload["running"])
            self.assertEqual(payload["label"], cli._get_launchd_label())
            self.assertEqual(payload["plist_path"], str(plist_path))
            self.assertEqual(payload["domain"], cli._get_launchd_domain())

    def test_cmd_service_start_bootstraps_launchd_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plist_path = Path(tmpdir) / "com.fix-my-claw.monitor.plist"
            plist_path.write_text("plist", encoding="utf-8")
            args = SimpleNamespace()
            launchctl_calls: list[tuple[tuple[str, ...], bool]] = []

            def _launchctl_side_effect(*call_args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
                launchctl_calls.append((call_args, check))
                return subprocess.CompletedProcess(["launchctl", *call_args], 0, "", "")

            with patch.object(cli, "_service_platform_supported", return_value=True), patch.object(
                cli, "_get_launchd_plist_path", return_value=plist_path
            ), patch.object(cli, "_bootout_launchd_service") as bootout_mock, patch.object(
                cli, "_launchctl_run", side_effect=_launchctl_side_effect
            ), patch("sys.stdout", new=io.StringIO()):
                code = cli.cmd_service_start(args)

            self.assertEqual(code, 0)
            bootout_mock.assert_called_once_with(plist_path)
            self.assertEqual(
                launchctl_calls,
                [
                    (("bootstrap", cli._get_launchd_domain(), str(plist_path)), True),
                    (("enable", f"{cli._get_launchd_domain()}/{cli._get_launchd_label()}"), True),
                    (("kickstart", "-k", f"{cli._get_launchd_domain()}/{cli._get_launchd_label()}"), True),
                ],
            )


if __name__ == "__main__":
    unittest.main()
