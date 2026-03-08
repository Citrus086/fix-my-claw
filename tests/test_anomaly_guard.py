from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fix_my_claw import anomaly_guard as anomaly_guard_module
from fix_my_claw import cli
from fix_my_claw import config as config_module
from fix_my_claw import health as health_module
from fix_my_claw import monitor
from fix_my_claw import notify as notify_module
from fix_my_claw import repair as repair_module
from fix_my_claw import runtime as runtime_module
from fix_my_claw import shared as shared_module
from fix_my_claw import state as state_module

# Test constants for Discord IDs (example values, not real)
TEST_CHANNEL_ID = "1479011917367476347"
TEST_BOT_USER_ID = "1479170394580848660"
TEST_BOT_USERNAME = "fix-my-claw"


def _make_cmd_result(
    argv: list[str] | None = None,
    *,
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> runtime_module.CmdResult:
    return runtime_module.CmdResult(
        argv=argv or ["openclaw"],
        cwd=None,
        exit_code=exit_code,
        duration_ms=1,
        stdout=stdout,
        stderr=stderr,
    )


def _make_probe(
    name: str,
    *,
    exit_code: int = 0,
    stdout: str = "{}",
    stderr: str = "",
    json_data: dict | list | None = None,
) -> health_module.Probe:
    return health_module.Probe(
        name=name,
        cmd=_make_cmd_result(
            argv=["openclaw", "gateway", name, "--json"],
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
        ),
        json_data={} if json_data is None and exit_code == 0 else json_data,
    )


def _make_health_evaluation(
    *,
    effective_healthy: bool,
    probe_healthy: bool = True,
    anomaly_guard: dict | None = None,
    reason: str | None = None,
    health_probe: health_module.Probe | None = None,
    status_probe: health_module.Probe | None = None,
    logs_probe: runtime_module.CmdResult | None = None,
) -> health_module.HealthEvaluation:
    if health_probe is None:
        health_probe = _make_probe("health", exit_code=0 if probe_healthy else 1, stdout="{}" if probe_healthy else "")
    if status_probe is None:
        status_probe = _make_probe("status")
    if logs_probe is None:
        logs_probe = _make_cmd_result(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            exit_code=0,
            stdout="logs",
        )
    return health_module.HealthEvaluation(
        health_probe=health_probe,
        status_probe=status_probe,
        logs_probe=logs_probe,
        anomaly_guard=anomaly_guard,
        probe_healthy=probe_healthy,
        effective_healthy=effective_healthy,
        reason=reason,
    )


def _make_official_steps_result(
    *,
    effective_healthy: bool,
    break_reason: str | None = None,
    anomaly_guard: dict | None = None,
) -> tuple[list[dict], health_module.HealthEvaluation, str]:
    return (
        [],
        _make_health_evaluation(
            effective_healthy=effective_healthy,
            anomaly_guard=anomaly_guard,
            reason="anomaly_guard" if anomaly_guard and anomaly_guard.get("triggered") else None,
        ),
        break_reason or ("healthy" if effective_healthy else "steps_exhausted"),
    )


class TestAnomalyGuardConfigCompat(unittest.TestCase):
    def test_defaults_match_current_openclaw_cli(self) -> None:
        cfg = config_module.AppConfig()
        self.assertEqual(cfg.monitor.probe_timeout_seconds, 30)
        self.assertEqual(cfg.anomaly_guard.probe_timeout_seconds, 30)
        self.assertEqual(cfg.openclaw.logs_args, ["logs", "--limit", "200", "--plain"])
        self.assertTrue(cfg.repair.soft_pause_enabled)
        self.assertEqual(cfg.repair.pause_wait_seconds, 20)
        self.assertIn("Action: PAUSE", cfg.repair.pause_message)

    def test_legacy_loop_guard_key_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.toml"
            cfg_path.write_text(
                """
[monitor]
interval_seconds = 60

[openclaw]
command = "openclaw"

[repair]
enabled = true

[loop_guard]
enabled = true
min_ping_pong_turns = 7
max_repeat_same_signature = 9
""".strip(),
                encoding="utf-8",
            )
            cfg = config_module.load_config(str(cfg_path))
            self.assertTrue(cfg.anomaly_guard.enabled)
            self.assertEqual(cfg.anomaly_guard.min_cycle_repeated_turns, 7)
            self.assertEqual(cfg.anomaly_guard.min_ping_pong_turns, 7)
            self.assertEqual(cfg.anomaly_guard.max_repeat_same_signature, 9)

    def test_new_cycle_config_keys_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.toml"
            cfg_path.write_text(
                """
[anomaly_guard]
enabled = true
min_cycle_repeated_turns = 5
max_cycle_period = 6
""".strip(),
                encoding="utf-8",
            )
            cfg = config_module.load_config(str(cfg_path))
            self.assertTrue(cfg.anomaly_guard.enabled)
            self.assertEqual(cfg.anomaly_guard.min_cycle_repeated_turns, 5)
            self.assertEqual(cfg.anomaly_guard.min_ping_pong_turns, 5)
            self.assertEqual(cfg.anomaly_guard.max_cycle_period, 6)

    def test_new_stagnation_config_keys_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.toml"
            cfg_path.write_text(
                """
[anomaly_guard]
enabled = true
stagnation_enabled = true
stagnation_min_events = 7
stagnation_min_roles = 3
stagnation_max_novel_cluster_ratio = 0.4
""".strip(),
                encoding="utf-8",
            )
            cfg = config_module.load_config(str(cfg_path))
            self.assertTrue(cfg.anomaly_guard.stagnation_enabled)
            self.assertEqual(cfg.anomaly_guard.stagnation_min_events, 7)
            self.assertEqual(cfg.anomaly_guard.stagnation_min_roles, 3)
            self.assertAlmostEqual(cfg.anomaly_guard.stagnation_max_novel_cluster_ratio, 0.4)

    def test_parse_repair_filters_empty_official_steps(self) -> None:
        repair = config_module._parse_repair(
            {
                "enabled": True,
                "official_steps": [
                    [],
                    ["openclaw", "doctor", "--repair"],
                    [],
                ],
            }
        )
        self.assertEqual(repair.official_steps, [["openclaw", "doctor", "--repair"]])

    def test_parse_repair_filters_disallowed_commands_from_official_steps(self) -> None:
        """Test that only whitelisted commands are allowed in official_steps."""
        repair = config_module._parse_repair(
            {
                "enabled": True,
                "official_steps": [
                    ["openclaw", "doctor", "--repair"],  # allowed
                    ["/bin/bash", "-c", "rm -rf /"],  # disallowed, should be filtered
                    ["openclaw", "gateway", "restart"],  # allowed
                    ["curl", "http://evil.com"],  # disallowed, should be filtered
                ],
            }
        )
        self.assertEqual(
            repair.official_steps,
            [["openclaw", "doctor", "--repair"], ["openclaw", "gateway", "restart"]],
        )

    def test_parse_notify_read_timeout_falls_back_to_send_timeout(self) -> None:
        notify = config_module._parse_notify(
            {
                "send_timeout_seconds": 42,
            }
        )
        self.assertEqual(notify.send_timeout_seconds, 42)
        self.assertEqual(notify.read_timeout_seconds, 42)

    def test_parse_monitor_sanitizes_invalid_timing_values(self) -> None:
        monitor = config_module._parse_monitor(
            {
                "interval_seconds": -5,
                "probe_timeout_seconds": 0,
                "repair_cooldown_seconds": -1,
            }
        )
        self.assertEqual(monitor.interval_seconds, 1)
        self.assertEqual(monitor.probe_timeout_seconds, 1)
        self.assertEqual(monitor.repair_cooldown_seconds, 0)

    def test_parse_ai_sanitizes_invalid_limits(self) -> None:
        ai = config_module._parse_ai(
            {
                "timeout_seconds": 0,
                "max_attempts_per_day": -2,
                "cooldown_seconds": -3,
            }
        )
        self.assertEqual(ai.timeout_seconds, 1)
        self.assertEqual(ai.max_attempts_per_day, 0)
        self.assertEqual(ai.cooldown_seconds, 0)


class TestAnomalyGuardBehavior(unittest.TestCase):
    def test_run_check_marks_unhealthy_when_anomaly_triggered(self) -> None:
        cfg = config_module.AppConfig()
        store = state_module.StateStore(Path(tempfile.mkdtemp()))

        ok_probe = health_module.Probe(
            name="health",
            cmd=runtime_module.CmdResult(
                argv=["openclaw", "gateway", "health", "--json"],
                cwd=None,
                exit_code=0,
                duration_ms=1,
                stdout="{}",
                stderr="",
            ),
            json_data={},
        )
        status_probe = health_module.Probe(
            name="status",
            cmd=runtime_module.CmdResult(
                argv=["openclaw", "gateway", "status", "--json"],
                cwd=None,
                exit_code=0,
                duration_ms=1,
                stdout="{}",
                stderr="",
            ),
            json_data={},
        )

        with patch.object(repair_module, "probe_health", return_value=ok_probe), patch.object(
            repair_module, "probe_status", return_value=status_probe
        ), patch.object(
            repair_module,
            "_analyze_anomaly_guard",
            return_value={"triggered": True, "signals": {"ping_pong_trigger": True}},
        ):
            result = monitor.run_check(cfg, store)
            self.assertFalse(result.healthy)
            self.assertIsNotNone(result.anomaly_guard)
            self.assertTrue(result.anomaly_guard["triggered"])

    def test_detector_triggers_on_ping_pong_pattern(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_cycle_repeated_turns=2,
            )
        )
        log_text = "\n".join(
            [
                "orchestrator: stop now, repeating dispatch plan",
                "builder: stop now, repeating implementation status",
                "orchestrator: stop now, repeating dispatch plan",
                "builder: stop now, repeating implementation status",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        self.assertTrue(info["triggered"])
        self.assertTrue(info["signals"]["ping_pong_trigger"])
        self.assertTrue(info["signals"]["cycle_trigger"])
        self.assertEqual(info["metrics"]["cycle_event"]["period"], 2)
        self.assertEqual(info["metrics"]["cycle_repeated_turns"], 2)

    def test_detector_triggers_on_ping_pong_without_stop_signal(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_cycle_repeated_turns=2,
            )
        )
        log_text = "\n".join(
            [
                "orchestrator: repeating dispatch plan",
                "builder: repeating dispatch plan",
                "orchestrator: repeating dispatch plan",
                "builder: repeating dispatch plan",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        self.assertTrue(info["triggered"])
        self.assertTrue(info["signals"]["ping_pong_trigger"])
        self.assertTrue(info["signals"]["cycle_trigger"])

    def test_detector_triggers_on_bracket_prefixed_ping_pong_pattern(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_cycle_repeated_turns=2,
            )
        )
        log_text = "\n".join(
            [
                "[builder] ping",
                "[orchestrator] pong",
                "[builder] ping",
                "[orchestrator] pong",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        self.assertTrue(info["triggered"])
        self.assertTrue(info["signals"]["ping_pong_trigger"])
        self.assertEqual(info["metrics"]["events_analyzed"], 4)

    def test_detector_does_not_treat_progress_sequence_as_repeat(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=3,
                min_cycle_repeated_turns=99,
            )
        )
        log_text = "\n".join(
            [
                "builder: progress batch 1 completed",
                "builder: progress batch 2 completed",
                "builder: progress batch 3 completed",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        self.assertFalse(info["triggered"])
        self.assertFalse(info["signals"]["repeat_trigger"])
        self.assertFalse(info["signals"]["similar_repeat_trigger"])
        self.assertFalse(info["signals"]["cycle_trigger"])

    def test_detector_triggers_on_similarity_repeat_for_single_agent(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_cycle_repeated_turns=99,
                auto_dispatch_check=False,
                keywords_repeat=[],
                similarity_enabled=True,
                similarity_threshold=0.8,
                similarity_min_chars=8,
                max_similar_repeat=3,
            )
        )
        log_text = "\n".join(
            [
                "builder: implementing order service endpoint alpha",
                "builder: implementing order service endpoint beta",
                "builder: implementing order service endpoint gamma",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        self.assertTrue(info["triggered"])
        self.assertTrue(info["signals"]["similar_repeat_trigger"])
        self.assertEqual(info["metrics"]["max_similar_repeat_run_repetitions"], 3)
        self.assertEqual(info["metrics"]["max_similar_repeats"], 3)
        self.assertEqual(info["metrics"]["top_similar_group"]["role"], "builder")

    def test_detector_triggers_on_architect_research_cycle(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_cycle_repeated_turns=2,
                auto_dispatch_check=False,
                keywords_repeat=[],
            )
        )
        log_text = "\n".join(
            [
                "architect: refine the API migration plan",
                "research: collect API migration constraints",
                "architect: refine the API migration plan",
                "research: collect API migration constraints",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        self.assertTrue(info["triggered"])
        self.assertTrue(info["signals"]["cycle_trigger"])
        self.assertTrue(info["signals"]["ping_pong_trigger"])
        self.assertEqual(info["metrics"]["cycle_event"]["period"], 2)
        self.assertEqual(info["metrics"]["cycle_event"]["involved_roles"], ["architect", "research"])

    def test_detector_triggers_on_three_role_cycle(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_cycle_repeated_turns=3,
                auto_dispatch_check=False,
                keywords_repeat=[],
            )
        )
        log_text = "\n".join(
            [
                "orchestrator: coordinate deploy checklist",
                "builder: update deploy checklist implementation",
                "architect: review deploy checklist constraints",
                "orchestrator: coordinate deploy checklist",
                "builder: update deploy checklist implementation",
                "architect: review deploy checklist constraints",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        self.assertTrue(info["triggered"])
        self.assertTrue(info["signals"]["cycle_trigger"])
        self.assertFalse(info["signals"]["ping_pong_trigger"])
        self.assertEqual(info["metrics"]["cycle_event"]["period"], 3)
        self.assertEqual(
            info["metrics"]["cycle_event"]["involved_roles"],
            ["orchestrator", "builder", "architect"],
        )

    def test_detector_output_exposes_structured_detector_findings(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_cycle_repeated_turns=3,
                auto_dispatch_check=False,
                keywords_repeat=[],
            )
        )
        log_text = "\n".join(
            [
                "orchestrator: coordinate deploy checklist",
                "builder: update deploy checklist implementation",
                "architect: review deploy checklist constraints",
                "orchestrator: coordinate deploy checklist",
                "builder: update deploy checklist implementation",
                "architect: review deploy checklist constraints",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        cycle_detector = next(detector for detector in info["detectors"] if detector["detector"] == "cycle")
        self.assertTrue(cycle_detector["triggered"])
        self.assertEqual(cycle_detector["period"], 3)
        self.assertEqual(cycle_detector["repetitions"], 2)
        self.assertEqual(cycle_detector["involved_roles"], ["orchestrator", "builder", "architect"])
        self.assertEqual(len(cycle_detector["evidence"]), 6)

    def test_detector_triggers_on_four_role_cycle_with_noise(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_cycle_repeated_turns=4,
                auto_dispatch_check=False,
                keywords_repeat=[],
            )
        )
        log_text = "\n".join(
            [
                "user: please keep going",
                "orchestrator: coordinate release checklist",
                "[system] heart beat ok",
                "builder: implement release checklist changes",
                "architect: review release checklist design",
                "research: verify release checklist assumptions",
                "user: any blockers?",
                "orchestrator: coordinate release checklist",
                "builder: implement release checklist changes",
                "architect: review release checklist design",
                "research: verify release checklist assumptions",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        self.assertTrue(info["triggered"])
        self.assertTrue(info["signals"]["cycle_trigger"])
        self.assertEqual(info["metrics"]["events_analyzed"], 8)
        self.assertEqual(info["metrics"]["cycle_event"]["period"], 4)
        self.assertEqual(
            info["metrics"]["cycle_event"]["involved_roles"],
            ["orchestrator", "builder", "architect", "research"],
        )

    def test_detector_triggers_on_low_novelty_stagnation_without_cycle(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_cycle_repeated_turns=99,
                auto_dispatch_check=False,
                keywords_repeat=[],
                stagnation_enabled=True,
                stagnation_min_events=6,
                stagnation_min_roles=2,
                stagnation_max_novel_cluster_ratio=0.34,
            )
        )
        log_text = "\n".join(
            [
                "orchestrator: schema mismatch remains unresolved",
                "builder: schema mismatch remains unresolved",
                "architect: schema mismatch remains unresolved",
                "research: schema mismatch remains unresolved",
                "orchestrator: schema mismatch remains unresolved",
                "builder: schema mismatch remains unresolved",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        self.assertTrue(info["triggered"])
        self.assertTrue(info["signals"]["stagnation_trigger"])
        self.assertFalse(info["signals"]["cycle_trigger"])
        self.assertIsNotNone(info["metrics"]["stagnation_event"])
        self.assertEqual(info["metrics"]["stagnation_event"]["event_count"], 6)
        self.assertEqual(info["metrics"]["stagnation_event"]["distinct_cluster_count"], 1)
        self.assertAlmostEqual(info["metrics"]["stagnation_event"]["novel_cluster_ratio"], 1 / 6, places=4)

    def test_stagnation_detector_does_not_trigger_on_diverse_recent_window(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_cycle_repeated_turns=99,
                auto_dispatch_check=False,
                keywords_repeat=[],
                stagnation_enabled=True,
                stagnation_min_events=6,
                stagnation_min_roles=2,
                stagnation_max_novel_cluster_ratio=0.34,
            )
        )
        log_text = "\n".join(
            [
                "orchestrator: draft service migration plan",
                "builder: implement service migration changes",
                "architect: review service migration risks",
                "research: verify service migration assumptions",
                "orchestrator: prepare rollout checklist",
                "builder: update rollback procedure",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        self.assertFalse(info["signals"]["stagnation_trigger"])
        self.assertIsNone(info["metrics"]["stagnation_event"])

    def test_similarity_repeat_does_not_mix_different_roles(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_cycle_repeated_turns=99,
                auto_dispatch_check=False,
                keywords_repeat=[],
                similarity_enabled=True,
                similarity_threshold=0.8,
                similarity_min_chars=8,
                max_similar_repeat=3,
            )
        )
        log_text = "\n".join(
            [
                "orchestrator: drafting migration plan alpha",
                "builder: drafting migration plan beta",
                "orchestrator: drafting migration plan gamma",
                "builder: drafting migration plan delta",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        self.assertFalse(info["triggered"])
        self.assertFalse(info["signals"]["similar_repeat_trigger"])

    def test_auto_dispatch_requires_unexpected_post_handoff_speaker_streak(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_cycle_repeated_turns=99,
                keywords_repeat=[],
                similarity_enabled=False,
                min_post_dispatch_unexpected_turns=2,
            )
        )
        log_text = "\n".join(
            [
                "orchestrator: dispatch to builder for implementation",
                "orchestrator: I will keep drafting the implementation details",
                "orchestrator: still driving the implementation after handoff",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        self.assertTrue(info["triggered"])
        self.assertTrue(info["signals"]["auto_dispatch_trigger"])
        self.assertEqual(info["metrics"]["auto_dispatch_event"]["initiator_role"], "orchestrator")
        self.assertEqual(info["metrics"]["auto_dispatch_event"]["target_role"], "builder")
        self.assertEqual(info["metrics"]["auto_dispatch_event"]["unexpected_role"], "orchestrator")
        self.assertEqual(info["metrics"]["auto_dispatch_event"]["dispatch_line_index"], 0)
        self.assertEqual(info["metrics"]["auto_dispatch_event"]["unexpected_line_index"], 2)

    def test_auto_dispatch_does_not_trigger_on_role_mentions_without_streak(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_cycle_repeated_turns=99,
                keywords_repeat=[],
                similarity_enabled=False,
                min_post_dispatch_unexpected_turns=2,
            )
        )
        log_text = "\n".join(
            [
                "orchestrator: dispatch task to builder for implementation",
                "builder: working on feature branch",
                "user: architect will review once coding is done",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        self.assertFalse(info["triggered"])
        self.assertFalse(info["signals"]["auto_dispatch_trigger"])

    def test_auto_dispatch_supports_research_as_handoff_target(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_cycle_repeated_turns=99,
                keywords_repeat=[],
                similarity_enabled=False,
                min_post_dispatch_unexpected_turns=2,
            )
        )
        log_text = "\n".join(
            [
                "orchestrator: handoff to research for validation",
                "architect: I will keep refining the validation plan",
                "architect: still producing validation notes after handoff",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        self.assertTrue(info["triggered"])
        self.assertTrue(info["signals"]["auto_dispatch_trigger"])
        self.assertEqual(info["metrics"]["auto_dispatch_event"]["target_role"], "research")

    def test_auto_dispatch_supports_timestamped_log_prefixes(self) -> None:
        cfg = config_module.AppConfig(
            anomaly_guard=config_module.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_cycle_repeated_turns=99,
                keywords_repeat=[],
                similarity_enabled=False,
                min_post_dispatch_unexpected_turns=2,
            )
        )
        log_text = "\n".join(
            [
                "2026-03-06 12:00:00 orchestrator: dispatch to builder for implementation",
                "2026-03-06 12:00:01 orchestrator: still driving implementation details",
                "2026-03-06 12:00:02 orchestrator: continuing after the handoff",
            ]
        )
        log_result = runtime_module.CmdResult(
            argv=["openclaw", "logs", "--limit", "200", "--plain"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        info = anomaly_guard_module._analyze_anomaly_guard(cfg, logs=log_result)
        self.assertTrue(info["triggered"])
        self.assertTrue(info["signals"]["auto_dispatch_trigger"])
        self.assertEqual(info["metrics"]["auto_dispatch_event"]["initiator_role"], "orchestrator")
        self.assertEqual(info["metrics"]["auto_dispatch_event"]["target_role"], "builder")
        self.assertEqual(info["metrics"]["auto_dispatch_event"]["unexpected_role"], "orchestrator")
        self.assertEqual(info["metrics"]["auto_dispatch_event"]["unexpected_line_index"], 2)
        handoff_detector = next(detector for detector in info["detectors"] if detector["detector"] == "handoff_violation")
        self.assertTrue(handoff_detector["triggered"])
        self.assertEqual(handoff_detector["involved_roles"], ["orchestrator", "builder"])
        self.assertEqual(len(handoff_detector["evidence"]), 2)


class TestNotifyDecision(unittest.TestCase):
    def test_extract_ai_decision_respects_operator_filter(self) -> None:
        cfg = config_module.AppConfig(
            notify=config_module.NotifyConfig(
                target="user:u1",
                operator_user_ids=["u1"],
            )
        )
        yes_msg = {"content": "yes", "author": {"id": "u1", "bot": False}}
        no_msg = {"content": "no", "author": {"id": "u1", "bot": False}}
        invalid_msg = {"content": "yes, go ahead", "author": {"id": "u1", "bot": False}}
        outsider_msg = {"content": "yes", "author": {"id": "u2", "bot": False}}
        bot_msg = {"content": "yes", "author": {"id": "u1", "bot": True}}

        self.assertEqual(notify_module._extract_ai_decision(cfg, yes_msg), "yes")
        self.assertEqual(notify_module._extract_ai_decision(cfg, no_msg), "no")
        self.assertIsNone(notify_module._extract_ai_decision(cfg, invalid_msg))
        self.assertIsNone(notify_module._extract_ai_decision(cfg, outsider_msg))
        self.assertIsNone(notify_module._extract_ai_decision(cfg, bot_msg))

    def test_extract_ai_decision_requires_mention_for_channel_target(self) -> None:
        cfg = config_module.AppConfig(
            notify=config_module.NotifyConfig(
                account=TEST_BOT_USERNAME,
                target="channel:123",
            )
        )
        plain_yes = {"content": "yes", "author": {"id": "u1", "bot": False}}
        mention_yes = {
            "content": f"<@{TEST_BOT_USER_ID}> yes",
            "author": {"id": "u1", "bot": False},
            "mentions": [{"id": TEST_BOT_USER_ID, "username": TEST_BOT_USERNAME}],
        }
        wrong_mention = {
            "content": "<@222> yes",
            "author": {"id": "u1", "bot": False},
            "mentions": [{"id": "222", "username": "someone-else"}],
        }

        self.assertIsNone(notify_module._extract_ai_decision(cfg, plain_yes))
        self.assertEqual(notify_module._extract_ai_decision(cfg, mention_yes), "yes")
        self.assertIsNone(notify_module._extract_ai_decision(cfg, wrong_mention, required_mention_id=TEST_BOT_USER_ID))
        self.assertEqual(
            notify_module._extract_ai_decision(cfg, mention_yes, required_mention_id=TEST_BOT_USER_ID),
            "yes",
        )
        self.assertEqual(
            notify_module._extract_ai_decision(
                cfg,
                {"content": f"<@{TEST_BOT_USER_ID}> yes", "author": {"id": "u1", "bot": False}},
                required_mention_id=TEST_BOT_USER_ID,
            ),
            "yes",
        )

    def test_ask_user_enable_ai_stops_after_three_invalid_replies(self) -> None:
        cfg = config_module.AppConfig(
            notify=config_module.NotifyConfig(
                account=TEST_BOT_USERNAME,
                target=f"channel:{TEST_CHANNEL_ID}",
                ask_enable_ai=True,
                ask_timeout_seconds=60,
                poll_interval_seconds=1,
            )
        )
        attempt_dir = Path(tempfile.mkdtemp())
        sent_payload = {"sent": True, "message_id": "m-ask"}
        invalid_replies = [
            {
                "id": "m1",
                "content": f"<@{TEST_BOT_USER_ID}> maybe",
                "author": {"id": "u1", "bot": False},
                "mentions": [{"id": TEST_BOT_USER_ID, "username": TEST_BOT_USERNAME}],
            },
            {
                "id": "m2",
                "content": f"<@{TEST_BOT_USER_ID}> 好的",
                "author": {"id": "u1", "bot": False},
                "mentions": [{"id": TEST_BOT_USER_ID, "username": TEST_BOT_USERNAME}],
            },
            {
                "id": "m3",
                "content": f"<@{TEST_BOT_USER_ID}> 继续",
                "author": {"id": "u1", "bot": False},
                "mentions": [{"id": TEST_BOT_USER_ID, "username": TEST_BOT_USERNAME}],
            },
        ]
        with patch.object(
            notify_module,
            "_notify_send",
            side_effect=[sent_payload, {"sent": True}, {"sent": True}],
        ) as notify_mock, patch.object(
            notify_module, "_resolve_sent_message_author_id", return_value=TEST_BOT_USER_ID
        ), patch.object(notify_module, "_notify_read_messages", side_effect=[invalid_replies]):
            out = notify_module._ask_user_enable_ai(cfg, attempt_dir)
            self.assertEqual(out.get("decision"), "invalid_limit")
            self.assertEqual(out.get("invalid_replies"), 3)
            self.assertEqual(notify_mock.call_count, 3)

    def test_ask_user_enable_ai_advances_last_seen_by_batch_max_id(self) -> None:
        cfg = config_module.AppConfig(
            notify=config_module.NotifyConfig(
                account=TEST_BOT_USERNAME,
                target=f"channel:{TEST_CHANNEL_ID}",
                ask_enable_ai=True,
                ask_timeout_seconds=1,
                poll_interval_seconds=0,
            )
        )
        attempt_dir = Path(tempfile.mkdtemp())
        after_ids: list[str | None] = []

        def _read_side_effect(_cfg: config_module.AppConfig, *, after_id: str | None = None) -> list[dict]:
            after_ids.append(after_id)
            if len(after_ids) == 1:
                # Return out-of-order IDs; next poll should still advance to max("10", "9") => "10".
                return [
                    {"id": "10", "content": "", "author": {"id": "u1", "bot": True}},
                    {"id": "9", "content": "", "author": {"id": "u2", "bot": True}},
                ]
            return []

        with patch.object(notify_module, "_notify_send", return_value={"sent": True, "message_id": "m-ask"}), patch.object(
            notify_module, "_resolve_sent_message_author_id", return_value=TEST_BOT_USER_ID
        ), patch.object(
            notify_module, "_notify_read_messages", side_effect=_read_side_effect
        ), patch.object(
            notify_module.time, "monotonic", side_effect=[0, 0, 0.5, 2]
        ), patch.object(
            notify_module.time, "sleep", return_value=None
        ):
            out = notify_module._ask_user_enable_ai(cfg, attempt_dir)
            self.assertEqual(out.get("decision"), "timeout")
            self.assertEqual(after_ids, ["m-ask", "10"])

    def test_ask_user_enable_ai_stops_when_gui_claims_first(self) -> None:
        state_dir = Path(tempfile.mkdtemp())
        cfg = config_module.AppConfig(
            monitor=config_module.MonitorConfig(
                state_dir=state_dir,
                log_file=state_dir / "fix-my-claw.log",
            ),
            notify=config_module.NotifyConfig(
                account=TEST_BOT_USERNAME,
                target=f"channel:{TEST_CHANNEL_ID}",
                ask_enable_ai=True,
                ask_timeout_seconds=1,
                poll_interval_seconds=0,
            ),
        )
        attempt_dir = state_dir / "attempts" / "a-1"
        attempt_dir.mkdir(parents=True)

        def _read_side_effect(_cfg: config_module.AppConfig, *, after_id: str | None = None) -> list[dict]:
            active = shared_module._read_ai_approval_request(state_dir)
            self.assertIsNotNone(active)
            request_id = str((active or {}).get("request_id", ""))
            claimed, payload = shared_module._claim_ai_approval_decision(
                state_dir,
                request_id=request_id,
                decision="no",
                source="gui",
            )
            self.assertTrue(claimed)
            self.assertEqual((payload or {}).get("source"), "gui")
            return []

        with patch.object(notify_module, "_notify_send", return_value={"sent": True, "message_id": "m-ask"}), patch.object(
            notify_module, "_resolve_sent_message_author_id", return_value=TEST_BOT_USER_ID
        ), patch.object(
            notify_module, "_notify_read_messages", side_effect=_read_side_effect
        ), patch.object(
            notify_module.time, "monotonic", side_effect=[0, 0, 0.5, 2]
        ), patch.object(
            notify_module.time, "sleep", return_value=None
        ):
            out = notify_module._ask_user_enable_ai(cfg, attempt_dir)
            self.assertEqual(out.get("decision"), "no")
            self.assertEqual(out.get("source"), "gui")
            self.assertFalse((state_dir / "ai_approval.active.json").exists())

    def test_ai_approval_decision_claim_is_first_writer_wins(self) -> None:
        state_dir = Path(tempfile.mkdtemp())
        attempt_dir = state_dir / "attempts" / "a-1"
        attempt_dir.mkdir(parents=True)
        shared_module._create_ai_approval_request(
            state_dir,
            request_id="req-1",
            attempt_dir=attempt_dir,
            prompt="approve?",
        )
        first_claimed, first_payload = shared_module._claim_ai_approval_decision(
            state_dir,
            request_id="req-1",
            decision="no",
            source="discord",
        )
        second_claimed, second_payload = shared_module._claim_ai_approval_decision(
            state_dir,
            request_id="req-1",
            decision="yes",
            source="gui",
        )
        self.assertTrue(first_claimed)
        self.assertEqual((first_payload or {}).get("source"), "discord")
        self.assertFalse(second_claimed)
        self.assertEqual((second_payload or {}).get("decision"), "no")
        self.assertEqual((second_payload or {}).get("source"), "discord")

    def test_notify_read_messages_uses_read_timeout(self) -> None:
        cfg = config_module.AppConfig(
            notify=config_module.NotifyConfig(
                send_timeout_seconds=5,
                read_timeout_seconds=33,
            )
        )
        payload = {"payload": {"messages": [{"id": "m1"}]}}
        cmd = runtime_module.CmdResult(
            argv=["openclaw", "message", "read"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=json.dumps(payload),
            stderr="",
        )
        with patch.object(notify_module, "run_cmd", return_value=cmd) as run_cmd_mock:
            out = notify_module._notify_read_messages(cfg)
            self.assertEqual(out, [{"id": "m1"}])
            self.assertEqual(run_cmd_mock.call_args.kwargs["timeout_seconds"], 33)


class TestStateStoreAiRateLimit(unittest.TestCase):
    def test_monitor_enabled_defaults_to_true_and_persists(self) -> None:
        store = state_module.StateStore(Path(tempfile.mkdtemp()))
        self.assertTrue(store.is_enabled())
        store.set_enabled(False)
        self.assertFalse(store.is_enabled())

    def test_legacy_desired_state_is_still_accepted_in_state_file(self) -> None:
        store = state_module.StateStore(Path(tempfile.mkdtemp()))
        store.path.write_text(json.dumps({"desired_state": "stopped"}), encoding="utf-8")
        self.assertFalse(store.is_enabled())

    def test_can_attempt_ai_resets_last_ai_ts_on_day_rollover(self) -> None:
        store = state_module.StateStore(Path(tempfile.mkdtemp()))
        store.save(
            state_module.State(
                last_ai_ts=1_000,
                ai_attempts_day="2026-03-05",
                ai_attempts_count=1,
            )
        )
        with patch.object(state_module, "_today_ymd", return_value="2026-03-06"), patch.object(
            state_module, "_now_ts", return_value=1_100
        ):
            self.assertTrue(store.can_attempt_ai(max_attempts_per_day=2, cooldown_seconds=3_600))
        state = store.load()
        self.assertEqual(state.ai_attempts_day, "2026-03-06")
        self.assertEqual(state.ai_attempts_count, 0)
        self.assertIsNone(state.last_ai_ts)

    def test_mark_ok_preserves_existing_ai_tracking_fields(self) -> None:
        store = state_module.StateStore(Path(tempfile.mkdtemp()))
        store.save(
            state_module.State(
                last_ai_ts=1_000,
                ai_attempts_day="2026-03-06",
                ai_attempts_count=2,
            )
        )
        with patch.object(state_module, "_now_ts", return_value=2_000):
            store.mark_ok()
        state = store.load()
        self.assertEqual(state.last_ok_ts, 2_000)
        self.assertEqual(state.last_ai_ts, 1_000)
        self.assertEqual(state.ai_attempts_day, "2026-03-06")
        self.assertEqual(state.ai_attempts_count, 2)


class TestRepairFlow(unittest.TestCase):
    def _cfg(self) -> config_module.AppConfig:
        return config_module.AppConfig(
            repair=config_module.RepairConfig(enabled=True, official_steps=[], soft_pause_enabled=False),
            notify=config_module.NotifyConfig(ask_enable_ai=True),
            ai=config_module.AiConfig(enabled=True, allow_code_changes=False),
        )

    def _isolated_cfg(
        self,
        *,
        state_dir: Path | None = None,
        repair: config_module.RepairConfig | None = None,
        notify: config_module.NotifyConfig | None = None,
        ai: config_module.AiConfig | None = None,
        monitor: config_module.MonitorConfig | None = None,
    ) -> config_module.AppConfig:
        base_dir = state_dir or Path(tempfile.mkdtemp())
        return config_module.AppConfig(
            monitor=monitor
            or config_module.MonitorConfig(
                state_dir=base_dir,
                log_file=base_dir / "fix-my-claw.log",
            ),
            repair=repair or config_module.RepairConfig(enabled=True, official_steps=[], soft_pause_enabled=False),
            notify=notify or config_module.NotifyConfig(ask_enable_ai=True),
            ai=ai or config_module.AiConfig(enabled=True, allow_code_changes=False),
        )

    def _cmd_ok(self) -> runtime_module.CmdResult:
        return runtime_module.CmdResult(argv=["codex"], cwd=None, exit_code=0, duration_ms=1, stdout="", stderr="")

    def _stage_names(self, result: repair_module.RepairResult) -> list[str]:
        self.assertIsNotNone(result.outcome)
        outcome = result.outcome
        if outcome is None:
            self.fail("expected typed repair outcome")
        return [stage.name for stage in outcome.stages]

    def _notify_messages(self, notify_mock: Mock) -> list[str]:
        return [call.args[1] for call in notify_mock.call_args_list]

    def _progress_events(self, write_mock: Mock) -> list[tuple[str, str]]:
        return [(str(call.kwargs["stage"]), str(call.kwargs["status"])) for call in write_mock.call_args_list]

    def _assert_progress_flow(self, write_mock: Mock, expected: list[tuple[str, str]]) -> None:
        self.assertEqual(self._progress_events(write_mock), expected)

    def _assert_progress_cleared(self, cfg: config_module.AppConfig, clear_mock: Mock) -> None:
        clear_mock.assert_called_once_with(cfg.monitor.state_dir)
        self.assertFalse((cfg.monitor.state_dir / "repair_progress.json").exists())

    def test_attempt_repair_skips_when_already_healthy(self) -> None:
        cfg = self._isolated_cfg()
        store = state_module.StateStore(cfg.monitor.state_dir)
        with patch.object(
            repair_module,
            "_evaluate_health",
            return_value=_make_health_evaluation(effective_healthy=True),
        ), patch.object(
            repair_module, "_notify_send"
        ) as notify_mock, patch.object(
            repair_module,
            "write_repair_progress",
            wraps=shared_module.write_repair_progress,
        ) as write_progress_mock, patch.object(
            repair_module,
            "clear_repair_progress",
            wraps=shared_module.clear_repair_progress,
        ) as clear_progress_mock:
            result = repair_module.attempt_repair(cfg, store, force=True, reason=None)
            self.assertFalse(result.attempted)
            self.assertTrue(result.fixed)
            self.assertFalse(result.used_ai)
            self.assertIsNone(result.outcome)
            self.assertTrue(result.details.get("already_healthy"))
            notify_mock.assert_not_called()
            self.assertEqual(write_progress_mock.call_count, 0)
            self._assert_progress_cleared(cfg, clear_progress_mock)

    def test_attempt_repair_skips_when_repair_disabled(self) -> None:
        cfg = self._isolated_cfg(
            repair=config_module.RepairConfig(enabled=False, official_steps=[], soft_pause_enabled=False),
        )
        store = state_module.StateStore(cfg.monitor.state_dir)
        with patch.object(
            repair_module,
            "_evaluate_health",
            return_value=_make_health_evaluation(effective_healthy=False),
        ), patch.object(
            repair_module, "_notify_send"
        ) as notify_mock, patch.object(
            repair_module,
            "write_repair_progress",
            wraps=shared_module.write_repair_progress,
        ) as write_progress_mock, patch.object(
            repair_module,
            "clear_repair_progress",
            wraps=shared_module.clear_repair_progress,
        ) as clear_progress_mock:
            result = repair_module.attempt_repair(cfg, store, force=True, reason=None)
            self.assertFalse(result.attempted)
            self.assertFalse(result.fixed)
            self.assertFalse(result.used_ai)
            self.assertIsNone(result.outcome)
            self.assertTrue(result.details.get("repair_disabled"))
            notify_mock.assert_not_called()
            self.assertEqual(write_progress_mock.call_count, 0)
            self._assert_progress_cleared(cfg, clear_progress_mock)

    def test_attempt_repair_skips_when_cooldown_is_active(self) -> None:
        state_dir = Path(tempfile.mkdtemp())
        cfg = self._isolated_cfg(
            monitor=config_module.MonitorConfig(
                state_dir=state_dir,
                log_file=state_dir / "fix-my-claw.log",
                repair_cooldown_seconds=60,
            ),
        )
        store = state_module.StateStore(cfg.monitor.state_dir)
        store.save(state_module.State(last_repair_ts=1_000))
        with patch.object(
            repair_module,
            "_evaluate_health",
            return_value=_make_health_evaluation(effective_healthy=False),
        ), patch.object(
            state_module, "_now_ts", return_value=1_010
        ), patch.object(
            repair_module, "_now_ts", return_value=1_010
        ), patch.object(
            repair_module, "_notify_send"
        ) as notify_mock, patch.object(
            repair_module,
            "write_repair_progress",
            wraps=shared_module.write_repair_progress,
        ) as write_progress_mock, patch.object(
            repair_module,
            "clear_repair_progress",
            wraps=shared_module.clear_repair_progress,
        ) as clear_progress_mock:
            result = repair_module.attempt_repair(cfg, store, force=False, reason=None)
            self.assertFalse(result.attempted)
            self.assertFalse(result.fixed)
            self.assertFalse(result.used_ai)
            self.assertIsNone(result.outcome)
            self.assertTrue(result.details.get("cooldown"))
            self.assertEqual(result.details.get("cooldown_remaining_seconds"), 50)
            notify_mock.assert_not_called()
            self.assertEqual(write_progress_mock.call_count, 0)
            self._assert_progress_cleared(cfg, clear_progress_mock)

    def test_yes_runs_backup_then_ai(self) -> None:
        cfg = self._isolated_cfg()
        store = state_module.StateStore(cfg.monitor.state_dir)
        with patch.object(repair_module, "_collect_context", return_value={}), patch.object(
            repair_module, "_run_session_command_stage", return_value=[]
        ), patch.object(
            repair_module, "_run_official_steps", return_value=_make_official_steps_result(effective_healthy=False)
        ), patch.object(
            repair_module,
            "_evaluate_health",
            side_effect=[
                _make_health_evaluation(effective_healthy=False),
                _make_health_evaluation(effective_healthy=True),
            ],
        ), patch.object(
            repair_module, "_ask_user_enable_ai", return_value={"asked": True, "decision": "yes"}
        ), patch.object(
            repair_module, "_backup_openclaw_state", return_value={"archive": "/tmp/openclaw.backup.tar.gz"}
        ) as backup_mock, patch.object(
            repair_module, "_run_ai_repair", return_value=self._cmd_ok()
        ) as ai_mock, patch.object(
            repair_module, "_notify_send", return_value={"sent": True}
        ) as notify_mock, patch.object(
            repair_module,
            "write_repair_progress",
            wraps=shared_module.write_repair_progress,
        ) as write_progress_mock, patch.object(
            repair_module,
            "clear_repair_progress",
            wraps=shared_module.clear_repair_progress,
        ) as clear_progress_mock:
            result = repair_module.attempt_repair(cfg, store, force=True, reason=None)
            self.assertTrue(result.attempted)
            self.assertTrue(result.fixed)
            self.assertTrue(result.used_ai)
            backup_mock.assert_called_once()
            ai_mock.assert_called_once()
            self.assertEqual(
                self._stage_names(result),
                ["terminate", "new", "official", "ai_decision", "backup", "ai_config"],
            )
            self.assertEqual(result.details.get("ai_stage"), "config")
            self.assertIn("backup_before_ai", result.details)
            self.assertTrue(any("Codex 配置阶段修复成功" in msg for msg in self._notify_messages(notify_mock)))
            self._assert_progress_flow(
                write_progress_mock,
                [
                    ("starting", "running"),
                    ("official", "running"),
                    ("official", "completed"),
                    ("ai_decision", "running"),
                    ("ai_decision", "completed"),
                    ("backup", "running"),
                    ("backup", "completed"),
                ],
            )
            self._assert_progress_cleared(cfg, clear_progress_mock)

    def test_attempt_repair_exposes_typed_stage_pipeline(self) -> None:
        cfg = self._isolated_cfg()
        store = state_module.StateStore(cfg.monitor.state_dir)
        with patch.object(repair_module, "_collect_context", return_value={"healthy": True}), patch.object(
            repair_module, "_run_session_command_stage", side_effect=[[{"agent": "macs-orchestrator"}], []]
        ), patch.object(
            repair_module, "_run_official_steps", return_value=_make_official_steps_result(effective_healthy=True)
        ), patch.object(
            repair_module,
            "_evaluate_health",
            return_value=_make_health_evaluation(effective_healthy=False),
        ), patch.object(
            repair_module, "_notify_send", return_value={"sent": True}
        ) as notify_mock, patch.object(
            repair_module,
            "write_repair_progress",
            wraps=shared_module.write_repair_progress,
        ) as write_progress_mock, patch.object(
            repair_module,
            "clear_repair_progress",
            wraps=shared_module.clear_repair_progress,
        ) as clear_progress_mock:
            result = repair_module.attempt_repair(cfg, store, force=True, reason="anomaly_guard")
            self.assertTrue(result.attempted)
            self.assertTrue(result.fixed)
            self.assertFalse(result.used_ai)
            self.assertIsNotNone(result.outcome)
            outcome = result.outcome
            if outcome is None:
                self.fail("expected typed repair outcome")
            self.assertEqual([stage.name for stage in outcome.stages], ["terminate", "new", "official"])
            self.assertIsInstance(outcome.stages[0].payload, repair_module.SessionStageData)
            self.assertIsInstance(outcome.stages[2].payload, repair_module.OfficialRepairStageData)
            self.assertEqual(result.details.get("official_break_reason"), "healthy")
            self.assertEqual(result.details.get("reason"), "anomaly_guard")
            self.assertTrue(any("分层修复已完成" in msg for msg in self._notify_messages(notify_mock)))
            self._assert_progress_flow(
                write_progress_mock,
                [
                    ("starting", "running"),
                    ("official", "running"),
                    ("official", "completed"),
                ],
            )
            self._assert_progress_cleared(cfg, clear_progress_mock)

    def test_attempt_repair_recovers_after_soft_pause_before_hard_reset(self) -> None:
        cfg = self._isolated_cfg(
            repair=config_module.RepairConfig(
                enabled=True,
                official_steps=[],
                soft_pause_enabled=True,
                pause_wait_seconds=7,
            ),
            ai=config_module.AiConfig(enabled=False, allow_code_changes=False),
        )
        store = state_module.StateStore(cfg.monitor.state_dir)
        pause_command = {
            "agent": "macs-orchestrator",
            "session_id": "s-1",
            "argv": ["openclaw", "agent"],
            "exit_code": 0,
            "duration_ms": 1,
            "stdout_path": "/tmp/pause.stdout",
            "stderr_path": "/tmp/pause.stderr",
        }
        with patch.object(repair_module, "_collect_context", return_value={}), patch.object(
            repair_module, "_run_session_command_stage", return_value=[pause_command]
        ), patch.object(
            repair_module, "_run_official_steps"
        ) as official_mock, patch.object(
            repair_module,
            "_evaluate_health",
            side_effect=[
                _make_health_evaluation(effective_healthy=False),
                _make_health_evaluation(effective_healthy=True),
            ],
        ), patch.object(
            repair_module, "_notify_send", return_value={"sent": True}
        ) as notify_mock, patch.object(
            repair_module.time, "sleep", return_value=None
        ) as sleep_mock, patch.object(
            repair_module,
            "write_repair_progress",
            wraps=shared_module.write_repair_progress,
        ) as write_progress_mock, patch.object(
            repair_module,
            "clear_repair_progress",
            wraps=shared_module.clear_repair_progress,
        ) as clear_progress_mock:
            result = repair_module.attempt_repair(cfg, store, force=True, reason=None)
            self.assertTrue(result.attempted)
            self.assertTrue(result.fixed)
            self.assertFalse(result.used_ai)
            official_mock.assert_not_called()
            self.assertIsNotNone(result.outcome)
            outcome = result.outcome
            if outcome is None:
                self.fail("expected typed repair outcome")
            self.assertEqual([stage.name for stage in outcome.stages], ["pause", "pause_check"])
            self.assertIn("pause_stage", result.details)
            self.assertEqual(result.details.get("pause_wait_seconds"), 7)
            sleep_mock.assert_called_once_with(7)
            self.assertTrue(any("已发送 PAUSE 并完成复检" in msg for msg in self._notify_messages(notify_mock)))
            self._assert_progress_flow(
                write_progress_mock,
                [
                    ("starting", "running"),
                    ("pause", "running"),
                    ("pause", "completed"),
                ],
            )
            self._assert_progress_cleared(cfg, clear_progress_mock)

    def test_attempt_repair_skips_soft_pause_when_status_probe_failed(self) -> None:
        cfg = self._isolated_cfg(
            repair=config_module.RepairConfig(enabled=True, official_steps=[], soft_pause_enabled=True),
            ai=config_module.AiConfig(enabled=False, allow_code_changes=False),
        )
        store = state_module.StateStore(cfg.monitor.state_dir)
        failed_status = _make_probe("status", exit_code=1, stdout="", json_data=None)
        with patch.object(repair_module, "_collect_context", return_value={}), patch.object(
            repair_module,
            "_run_session_command_stage",
            side_effect=[
                [{"agent": "macs-orchestrator", "argv": ["openclaw"], "exit_code": 0, "duration_ms": 1, "stdout_path": "a", "stderr_path": "b"}],
                [],
            ],
        ) as stage_mock, patch.object(
            repair_module,
            "_run_official_steps",
            return_value=_make_official_steps_result(effective_healthy=True, break_reason="healthy"),
        ), patch.object(
            repair_module,
            "_evaluate_health",
            return_value=_make_health_evaluation(
                effective_healthy=False,
                probe_healthy=False,
                reason="probe_failed",
                status_probe=failed_status,
            ),
        ), patch.object(
            repair_module, "_notify_send", return_value={"sent": True}
        ) as notify_mock, patch.object(
            repair_module,
            "write_repair_progress",
            wraps=shared_module.write_repair_progress,
        ) as write_progress_mock, patch.object(
            repair_module,
            "clear_repair_progress",
            wraps=shared_module.clear_repair_progress,
        ) as clear_progress_mock:
            result = repair_module.attempt_repair(cfg, store, force=True, reason=None)
            self.assertTrue(result.attempted)
            self.assertTrue(result.fixed)
            self.assertFalse(result.used_ai)
            self.assertIsNotNone(result.outcome)
            outcome = result.outcome
            if outcome is None:
                self.fail("expected typed repair outcome")
            self.assertEqual([stage.name for stage in outcome.stages], ["terminate", "new", "official"])
            self.assertEqual([call.kwargs["stage_name"] for call in stage_mock.call_args_list], ["terminate", "new"])
            self.assertEqual(result.details.get("official_break_reason"), "healthy")
            self.assertTrue(any("分层修复已完成" in msg for msg in self._notify_messages(notify_mock)))
            self._assert_progress_flow(
                write_progress_mock,
                [
                    ("starting", "running"),
                    ("official", "running"),
                    ("official", "completed"),
                ],
            )
            self._assert_progress_cleared(cfg, clear_progress_mock)

    def test_timeout_never_runs_ai(self) -> None:
        cfg = self._cfg()
        store = state_module.StateStore(Path(tempfile.mkdtemp()))
        with patch.object(repair_module, "_collect_context", return_value={}), patch.object(
            repair_module, "_run_session_command_stage", return_value=[]
        ), patch.object(
            repair_module, "_run_official_steps", return_value=_make_official_steps_result(effective_healthy=False)
        ), patch.object(
            repair_module,
            "_evaluate_health",
            side_effect=[
                _make_health_evaluation(effective_healthy=False),
                _make_health_evaluation(effective_healthy=False),
            ],
        ), patch.object(
            repair_module, "_ask_user_enable_ai", return_value={"asked": True, "decision": "timeout"}
        ), patch.object(
            repair_module, "_run_ai_repair"
        ) as ai_mock, patch.object(
            repair_module, "_notify_send", return_value={"sent": True}
        ):
            result = repair_module.attempt_repair(cfg, store, force=True, reason=None)
            self.assertFalse(result.used_ai)
            ai_mock.assert_not_called()

    def test_gui_no_decision_wins_and_is_notified_once(self) -> None:
        cfg = self._cfg()
        store = state_module.StateStore(Path(tempfile.mkdtemp()))
        with patch.object(repair_module, "_collect_context", return_value={}), patch.object(
            repair_module, "_run_session_command_stage", return_value=[]
        ), patch.object(
            repair_module, "_run_official_steps", return_value=_make_official_steps_result(effective_healthy=False)
        ), patch.object(
            repair_module,
            "_evaluate_health",
            side_effect=[
                _make_health_evaluation(effective_healthy=False),
                _make_health_evaluation(effective_healthy=False),
            ],
        ), patch.object(
            repair_module, "_ask_user_enable_ai", return_value={"asked": True, "decision": "no", "source": "gui"}
        ), patch.object(
            repair_module, "_run_ai_repair"
        ) as ai_mock, patch.object(
            repair_module, "_notify_send", return_value={"sent": True}
        ) as notify_mock:
            result = repair_module.attempt_repair(cfg, store, force=True, reason=None)
            self.assertFalse(result.used_ai)
            ai_mock.assert_not_called()
            messages = [call.args[1] for call in notify_mock.call_args_list]
            self.assertTrue(any("已收到 GUI 的 no" in message for message in messages))
            self.assertEqual(sum("已收到 GUI 的 no" in message for message in messages), 1)

    def test_ai_disabled_still_notifies_but_skips_yes_no_and_ai_flow(self) -> None:
        cfg = self._isolated_cfg(
            repair=config_module.RepairConfig(enabled=True, official_steps=[], soft_pause_enabled=False),
            ai=config_module.AiConfig(enabled=False, allow_code_changes=False),
        )
        store = state_module.StateStore(cfg.monitor.state_dir)
        with patch.object(repair_module, "_collect_context", return_value={}), patch.object(
            repair_module, "_run_session_command_stage", return_value=[]
        ), patch.object(
            repair_module, "_run_official_steps", return_value=_make_official_steps_result(effective_healthy=False)
        ), patch.object(
            repair_module,
            "_evaluate_health",
            side_effect=[
                _make_health_evaluation(effective_healthy=False),
                _make_health_evaluation(effective_healthy=False),
            ],
        ), patch.object(
            repair_module, "_ask_user_enable_ai"
        ) as ask_mock, patch.object(
            repair_module, "_run_ai_repair"
        ) as ai_mock, patch.object(
            repair_module, "_notify_send"
        ) as notify_mock, patch.object(
            repair_module,
            "write_repair_progress",
            wraps=shared_module.write_repair_progress,
        ) as write_progress_mock, patch.object(
            repair_module,
            "clear_repair_progress",
            wraps=shared_module.clear_repair_progress,
        ) as clear_progress_mock:
            result = repair_module.attempt_repair(cfg, store, force=True, reason=None)
            self.assertTrue(result.attempted)
            self.assertFalse(result.fixed)
            self.assertFalse(result.used_ai)
            ask_mock.assert_not_called()
            ai_mock.assert_not_called()
            self.assertEqual(notify_mock.call_count, 2)
            self.assertEqual(self._stage_names(result), ["terminate", "new", "official", "final"])
            self.assertEqual(result.details.get("official_break_reason"), "steps_exhausted")
            self.assertTrue(any("ai.enabled=false" in msg for msg in self._notify_messages(notify_mock)))
            self._assert_progress_flow(
                write_progress_mock,
                [
                    ("starting", "running"),
                    ("official", "running"),
                    ("official", "completed"),
                ],
            )
            self._assert_progress_cleared(cfg, clear_progress_mock)

    def test_ai_rate_limit_skips_ask_and_ai(self) -> None:
        cfg = self._isolated_cfg(
            repair=config_module.RepairConfig(enabled=True, official_steps=[], soft_pause_enabled=False),
            ai=config_module.AiConfig(enabled=True, allow_code_changes=False, max_attempts_per_day=0),
        )
        store = state_module.StateStore(cfg.monitor.state_dir)
        with patch.object(repair_module, "_collect_context", return_value={}), patch.object(
            repair_module, "_run_session_command_stage", return_value=[]
        ), patch.object(
            repair_module, "_run_official_steps", return_value=_make_official_steps_result(effective_healthy=False)
        ), patch.object(
            repair_module,
            "_evaluate_health",
            side_effect=[
                _make_health_evaluation(effective_healthy=False),
                _make_health_evaluation(effective_healthy=False),
            ],
        ), patch.object(
            repair_module, "_ask_user_enable_ai"
        ) as ask_mock, patch.object(
            repair_module, "_run_ai_repair"
        ) as ai_mock, patch.object(
            repair_module, "_notify_send", return_value={"sent": True}
        ) as notify_mock, patch.object(
            repair_module,
            "write_repair_progress",
            wraps=shared_module.write_repair_progress,
        ) as write_progress_mock, patch.object(
            repair_module,
            "clear_repair_progress",
            wraps=shared_module.clear_repair_progress,
        ) as clear_progress_mock:
            result = repair_module.attempt_repair(cfg, store, force=True, reason=None)
            self.assertTrue(result.attempted)
            self.assertFalse(result.fixed)
            self.assertFalse(result.used_ai)
            self.assertEqual(self._stage_names(result), ["terminate", "new", "official", "ai_decision", "final"])
            self.assertEqual(result.details.get("ai_decision", {}).get("decision"), "rate_limited")
            ask_mock.assert_not_called()
            ai_mock.assert_not_called()
            self.assertTrue(any("Codex 修复被限流" in msg for msg in self._notify_messages(notify_mock)))
            self._assert_progress_flow(
                write_progress_mock,
                [
                    ("starting", "running"),
                    ("official", "running"),
                    ("official", "completed"),
                ],
            )
            self._assert_progress_cleared(cfg, clear_progress_mock)

    def test_collect_context_keeps_stage_snapshots_immutable(self) -> None:
        attempt_dir = Path(tempfile.mkdtemp())
        evaluation = _make_health_evaluation(
            effective_healthy=True,
            health_probe=health_module.Probe(
                name="health",
                cmd=runtime_module.CmdResult(argv=["openclaw"], cwd=None, exit_code=0, duration_ms=1, stdout="h", stderr=""),
                json_data={},
            ),
            status_probe=health_module.Probe(
                name="status",
                cmd=runtime_module.CmdResult(argv=["openclaw"], cwd=None, exit_code=0, duration_ms=1, stdout="s", stderr=""),
                json_data={},
            ),
            logs_probe=runtime_module.CmdResult(argv=["openclaw"], cwd=None, exit_code=0, duration_ms=1, stdout="l", stderr=""),
        )
        before = repair_module._collect_context(evaluation, attempt_dir, stage_name="before")
        after = repair_module._collect_context(evaluation, attempt_dir, stage_name="after_official")
        self.assertNotEqual(before["logs"]["stdout_path"], after["logs"]["stdout_path"])
        self.assertTrue(Path(before["logs"]["stdout_path"]).exists())
        self.assertTrue(Path(after["logs"]["stdout_path"]).exists())

    def test_attempt_dir_is_unique_even_with_same_timestamp(self) -> None:
        cfg = config_module.AppConfig(
            monitor=config_module.MonitorConfig(
                state_dir=Path(tempfile.mkdtemp()),
                log_file=Path(tempfile.mkdtemp()) / "fix-my-claw.log",
            )
        )
        with patch.object(repair_module.time, "strftime", return_value="20260306-220000"):
            first = repair_module._attempt_dir(cfg)
            second = repair_module._attempt_dir(cfg)
        self.assertNotEqual(first, second)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())

    def test_attempt_repair_does_not_consume_cooldown_when_attempt_dir_creation_fails(self) -> None:
        state_dir = Path(tempfile.mkdtemp())
        cfg = config_module.AppConfig(
            monitor=config_module.MonitorConfig(
                state_dir=state_dir,
                log_file=state_dir / "fix-my-claw.log",
            )
        )
        store = state_module.StateStore(state_dir)
        with patch.object(repair_module, "_evaluate_health", return_value=_make_health_evaluation(effective_healthy=False)), patch.object(
            repair_module, "_attempt_dir", side_effect=RuntimeError("boom")
        ):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                repair_module.attempt_repair(cfg, store, force=False, reason=None)
        self.assertIsNone(store.load().last_repair_ts)

    def test_run_official_steps_skips_empty_step_at_runtime(self) -> None:
        cfg = config_module.AppConfig(repair=config_module.RepairConfig(official_steps=[[], ["openclaw", "gateway", "restart"]]))
        attempt_dir = Path(tempfile.mkdtemp())
        with patch.object(repair_module, "run_cmd", return_value=self._cmd_ok()) as run_cmd_mock, patch.object(
            repair_module, "_evaluate_health", return_value=_make_health_evaluation(effective_healthy=False)
        ), patch.object(
            repair_module.time, "sleep", return_value=None
        ):
            out, final_evaluation, break_reason = repair_module._run_official_steps(cfg, attempt_dir, break_on_healthy=False)
            self.assertEqual(len(out), 1)
            self.assertFalse(final_evaluation.effective_healthy)
            self.assertEqual(break_reason, "steps_exhausted")
            run_cmd_mock.assert_called_once()

    def test_attempt_repair_does_not_skip_anomaly_only_unhealthy_state(self) -> None:
        cfg = config_module.AppConfig(
            repair=config_module.RepairConfig(enabled=True, official_steps=[]),
            notify=config_module.NotifyConfig(ask_enable_ai=True),
            ai=config_module.AiConfig(enabled=False, allow_code_changes=False),
        )
        store = state_module.StateStore(Path(tempfile.mkdtemp()))
        with patch.object(
            repair_module,
            "_evaluate_health",
            side_effect=[
                _make_health_evaluation(
                    effective_healthy=False,
                    probe_healthy=True,
                    anomaly_guard={"triggered": True},
                    reason="anomaly_guard",
                ),
            ],
        ), patch.object(
            repair_module, "_collect_context", return_value={}
        ), patch.object(
            repair_module, "_run_session_command_stage", return_value=[]
        ), patch.object(
            repair_module,
            "_run_official_steps",
            return_value=_make_official_steps_result(effective_healthy=True, break_reason="healthy"),
        ) as official_mock, patch.object(
            repair_module, "_notify_send", return_value={"sent": True}
        ):
            result = repair_module.attempt_repair(cfg, store, force=True, reason=None)
            self.assertTrue(result.attempted)
            self.assertTrue(result.fixed)
            official_mock.assert_called_once()

    def test_run_ai_repair_writes_stage_scoped_logs(self) -> None:
        cfg = config_module.AppConfig()
        attempt_dir = Path(tempfile.mkdtemp())
        with patch.object(repair_module, "run_cmd", return_value=self._cmd_ok()):
            repair_module._run_ai_repair(cfg, attempt_dir, code_stage=False)
            repair_module._run_ai_repair(cfg, attempt_dir, code_stage=True)
        self.assertTrue((attempt_dir / "ai.config.stdout.txt").exists())
        self.assertTrue((attempt_dir / "ai.code.stdout.txt").exists())

    def test_session_stage_does_not_depend_on_notify_target(self) -> None:
        cfg = config_module.AppConfig(
            repair=config_module.RepairConfig(
                session_control_enabled=True,
                session_agents=["macs-orchestrator"],
                session_active_minutes=30,
                terminate_message="/stop",
            ),
            notify=config_module.NotifyConfig(
                channel="discord",
                target="channel:another-target",
            ),
        )
        attempt_dir = Path(tempfile.mkdtemp())
        sessions = [
            {
                "key": "agent:macs-orchestrator:any",
                "agentId": "macs-orchestrator",
                "sessionId": "s-1",
                "deliveryContext": "non-dict-still-should-not-block",
            }
        ]
        with patch.object(repair_module, "_list_active_sessions", return_value=sessions), patch.object(
            repair_module, "run_cmd", return_value=self._cmd_ok()
        ) as run_cmd_mock:
            out = repair_module._run_session_command_stage(
                cfg,
                attempt_dir,
                stage_name="terminate",
                message_text="/stop",
            )
            self.assertEqual(len(out), 1)
            run_cmd_mock.assert_called_once()

    def test_attempt_repair_waits_between_terminate_and_new_stage(self) -> None:
        cfg = config_module.AppConfig(
            repair=config_module.RepairConfig(
                enabled=True,
                official_steps=[],
                soft_pause_enabled=False,
                session_stage_wait_seconds=2,
            ),
            notify=config_module.NotifyConfig(ask_enable_ai=True),
            ai=config_module.AiConfig(enabled=False, allow_code_changes=False),
        )
        store = state_module.StateStore(Path(tempfile.mkdtemp()))
        with patch.object(repair_module, "_collect_context", return_value={}), patch.object(
            repair_module, "_run_session_command_stage", side_effect=[[{"agent": "macs-orchestrator"}], []]
        ), patch.object(
            repair_module, "_run_official_steps", return_value=_make_official_steps_result(effective_healthy=False)
        ), patch.object(
            repair_module,
            "_evaluate_health",
            side_effect=[
                _make_health_evaluation(effective_healthy=False),
                _make_health_evaluation(effective_healthy=False),
            ],
        ), patch.object(
            repair_module, "_notify_send", return_value={"sent": True}
        ), patch.object(
            repair_module.time, "sleep", return_value=None
        ) as sleep_mock:
            repair_module.attempt_repair(cfg, store, force=True, reason=None)
            sleep_mock.assert_called_once_with(2)

    def test_no_approval_skips_ai(self) -> None:
        """Test that 'no' decision skips AI repair and notifies correctly."""
        cfg = self._isolated_cfg()
        store = state_module.StateStore(cfg.monitor.state_dir)
        with patch.object(repair_module, "_collect_context", return_value={}), patch.object(
            repair_module, "_run_session_command_stage", return_value=[]
        ), patch.object(
            repair_module, "_run_official_steps", return_value=_make_official_steps_result(effective_healthy=False)
        ), patch.object(
            repair_module,
            "_evaluate_health",
            side_effect=[
                _make_health_evaluation(effective_healthy=False),
                _make_health_evaluation(effective_healthy=False),
            ],
        ), patch.object(
            repair_module, "_ask_user_enable_ai", return_value={"asked": True, "decision": "no"}
        ), patch.object(
            repair_module, "_run_ai_repair"
        ) as ai_mock, patch.object(
            repair_module, "_notify_send", return_value={"sent": True}
        ) as notify_mock, patch.object(
            repair_module,
            "write_repair_progress",
            wraps=shared_module.write_repair_progress,
        ) as write_progress_mock, patch.object(
            repair_module,
            "clear_repair_progress",
            wraps=shared_module.clear_repair_progress,
        ) as clear_progress_mock:
            result = repair_module.attempt_repair(cfg, store, force=True, reason=None)
            self.assertTrue(result.attempted)
            self.assertFalse(result.fixed)
            self.assertFalse(result.used_ai)
            ai_mock.assert_not_called()
            # Verify notification about no approval - when decision is "no", 
            # the ai_decision stage notification is reused (contains "已收到...的 no")
            messages = [call.args[1] for call in notify_mock.call_args_list]
            self.assertTrue(any("的 no" in msg for msg in messages))
            # Verify stage order: terminate, new, official, ai_decision, final
            self.assertIsNotNone(result.outcome)
            outcome = result.outcome
            if outcome is None:
                self.fail("expected typed repair outcome")
            self.assertEqual([stage.name for stage in outcome.stages], ["terminate", "new", "official", "ai_decision", "final"])
            # Verify details contains ai_decision
            self.assertEqual(result.details.get("ai_decision", {}).get("decision"), "no")
            self._assert_progress_flow(
                write_progress_mock,
                [
                    ("starting", "running"),
                    ("official", "running"),
                    ("official", "completed"),
                    ("ai_decision", "running"),
                    ("ai_decision", "completed"),
                ],
            )
            self._assert_progress_cleared(cfg, clear_progress_mock)

    def test_backup_error_stops_ai(self) -> None:
        """Test that backup error stops AI repair and notifies correctly."""
        cfg = self._isolated_cfg()
        store = state_module.StateStore(cfg.monitor.state_dir)
        with patch.object(repair_module, "_collect_context", return_value={}), patch.object(
            repair_module, "_run_session_command_stage", return_value=[]
        ), patch.object(
            repair_module, "_run_official_steps", return_value=_make_official_steps_result(effective_healthy=False)
        ), patch.object(
            repair_module,
            "_evaluate_health",
            side_effect=[
                _make_health_evaluation(effective_healthy=False),
                _make_health_evaluation(effective_healthy=False),
            ],
        ), patch.object(
            repair_module, "_ask_user_enable_ai", return_value={"asked": True, "decision": "yes"}
        ), patch.object(
            repair_module, "_backup_openclaw_state", side_effect=FileNotFoundError("state dir not found")
        ), patch.object(
            repair_module, "_run_ai_repair"
        ) as ai_mock, patch.object(
            repair_module, "_notify_send", return_value={"sent": True}
        ) as notify_mock, patch.object(
            repair_module,
            "write_repair_progress",
            wraps=shared_module.write_repair_progress,
        ) as write_progress_mock, patch.object(
            repair_module,
            "clear_repair_progress",
            wraps=shared_module.clear_repair_progress,
        ) as clear_progress_mock:
            result = repair_module.attempt_repair(cfg, store, force=True, reason=None)
            self.assertTrue(result.attempted)
            self.assertFalse(result.fixed)
            self.assertFalse(result.used_ai)
            ai_mock.assert_not_called()
            # Verify notification about backup error
            messages = [call.args[1] for call in notify_mock.call_args_list]
            self.assertTrue(any("备份失败" in msg for msg in messages))
            # Verify details contains backup error
            self.assertIn("backup_before_ai_error", result.details)
            self.assertIn("state dir not found", result.details.get("backup_before_ai_error", ""))
            self.assertEqual(
                self._stage_names(result),
                ["terminate", "new", "official", "ai_decision", "backup", "final"],
            )
            self._assert_progress_flow(
                write_progress_mock,
                [
                    ("starting", "running"),
                    ("official", "running"),
                    ("official", "completed"),
                    ("ai_decision", "running"),
                    ("ai_decision", "completed"),
                    ("backup", "running"),
                    ("backup", "failed"),
                ],
            )
            self._assert_progress_cleared(cfg, clear_progress_mock)

    def test_ai_code_stage_success(self) -> None:
        """Test AI code stage success when config stage fails but code stage succeeds."""
        cfg = self._isolated_cfg(
            ai=config_module.AiConfig(enabled=True, allow_code_changes=True),
        )
        store = state_module.StateStore(cfg.monitor.state_dir)
        # Mock _evaluate_with_context to control the evaluation returned to stages
        # _evaluate_with_context is called by AiRepairStage.run for each AI stage
        def _make_context_result(effective_healthy):
            evaluation = _make_health_evaluation(effective_healthy=effective_healthy)
            context = {"healthy": effective_healthy}
            return evaluation, context
        
        # Track calls to ensure correct order
        call_count = [0]
        def context_side_effect(cfg, attempt_dir, *, stage_name, log_probe_failures=False):
            call_count[0] += 1
            if "ai_code" in stage_name:
                return _make_context_result(True)   # after ai_code - success
            else:
                return _make_context_result(False)  # after ai_config - still unhealthy
        
        with patch.object(repair_module, "_collect_context", return_value={}), patch.object(
            repair_module, "_run_session_command_stage", return_value=[]
        ), patch.object(
            repair_module, "_run_official_steps", return_value=_make_official_steps_result(effective_healthy=False)
        ), patch.object(
            repair_module,
            "_evaluate_health",
            side_effect=[
                _make_health_evaluation(effective_healthy=False),  # initial
            ],
        ), patch.object(
            repair_module,
            "_evaluate_with_context",
            side_effect=context_side_effect,
        ), patch.object(
            repair_module, "_ask_user_enable_ai", return_value={"asked": True, "decision": "yes"}
        ), patch.object(
            repair_module, "_backup_openclaw_state", return_value={"archive": "/tmp/backup.tar.gz"}
        ), patch.object(
            repair_module, "_run_ai_repair", return_value=self._cmd_ok()
        ) as ai_mock, patch.object(
            repair_module, "_notify_send", return_value={"sent": True}
        ) as notify_mock, patch.object(
            repair_module,
            "write_repair_progress",
            wraps=shared_module.write_repair_progress,
        ) as write_progress_mock, patch.object(
            repair_module,
            "clear_repair_progress",
            wraps=shared_module.clear_repair_progress,
        ) as clear_progress_mock:
            result = repair_module.attempt_repair(cfg, store, force=True, reason=None)
            self.assertTrue(result.attempted)
            self.assertTrue(result.fixed)
            self.assertTrue(result.used_ai)
            # AI should be called twice: config and code
            self.assertEqual(ai_mock.call_count, 2)
            # Verify notification about code stage success
            messages = [call.args[1] for call in notify_mock.call_args_list]
            self.assertTrue(any("代码阶段修复成功" in msg for msg in messages), f"Messages: {messages}")
            # Verify stage order includes ai_config and ai_code
            self.assertIsNotNone(result.outcome)
            outcome = result.outcome
            if outcome is None:
                self.fail("expected typed repair outcome")
            stage_names = [stage.name for stage in outcome.stages]
            self.assertEqual(
                stage_names,
                ["terminate", "new", "official", "ai_decision", "backup", "ai_config", "ai_code"],
            )
            # Verify details
            self.assertEqual(result.details.get("ai_stage"), "code")
            self._assert_progress_flow(
                write_progress_mock,
                [
                    ("starting", "running"),
                    ("official", "running"),
                    ("official", "completed"),
                    ("ai_decision", "running"),
                    ("ai_decision", "completed"),
                    ("backup", "running"),
                    ("backup", "completed"),
                ],
            )
            self._assert_progress_cleared(cfg, clear_progress_mock)

    def test_final_failure_when_all_stages_fail(self) -> None:
        """Test final failure when all repair stages fail."""
        cfg = self._isolated_cfg()
        store = state_module.StateStore(cfg.monitor.state_dir)
        with patch.object(repair_module, "_collect_context", return_value={}), patch.object(
            repair_module, "_run_session_command_stage", return_value=[]
        ), patch.object(
            repair_module, "_run_official_steps", return_value=_make_official_steps_result(effective_healthy=False)
        ), patch.object(
            repair_module,
            "_evaluate_health",
            side_effect=[
                _make_health_evaluation(effective_healthy=False),  # initial
                _make_health_evaluation(effective_healthy=False),  # after official
                _make_health_evaluation(effective_healthy=False),  # after ai_config
            ],
        ), patch.object(
            repair_module, "_ask_user_enable_ai", return_value={"asked": True, "decision": "yes"}
        ), patch.object(
            repair_module, "_backup_openclaw_state", return_value={"archive": "/tmp/backup.tar.gz"}
        ), patch.object(
            repair_module, "_run_ai_repair", return_value=self._cmd_ok()
        ), patch.object(
            repair_module, "_notify_send", return_value={"sent": True}
        ) as notify_mock, patch.object(
            repair_module,
            "write_repair_progress",
            wraps=shared_module.write_repair_progress,
        ) as write_progress_mock, patch.object(
            repair_module,
            "clear_repair_progress",
            wraps=shared_module.clear_repair_progress,
        ) as clear_progress_mock:
            result = repair_module.attempt_repair(cfg, store, force=True, reason=None)
            self.assertTrue(result.attempted)
            self.assertFalse(result.fixed)
            self.assertTrue(result.used_ai)
            # Verify final failure notification
            messages = [call.args[1] for call in notify_mock.call_args_list]
            self.assertTrue(any("本轮修复结束，但系统仍异常" in msg for msg in messages))
            # Verify final stage exists
            self.assertIsNotNone(result.outcome)
            outcome = result.outcome
            if outcome is None:
                self.fail("expected typed repair outcome")
            self.assertEqual(
                [stage.name for stage in outcome.stages],
                ["terminate", "new", "official", "ai_decision", "backup", "ai_config", "final"],
            )
            # Verify details contains attempt_dir
            self.assertIn("attempt_dir", result.details)
            self.assertEqual(result.details.get("ai_stage"), "config")
            self._assert_progress_flow(
                write_progress_mock,
                [
                    ("starting", "running"),
                    ("official", "running"),
                    ("official", "completed"),
                    ("ai_decision", "running"),
                    ("ai_decision", "completed"),
                    ("backup", "running"),
                    ("backup", "completed"),
                ],
            )
            self._assert_progress_cleared(cfg, clear_progress_mock)


class TestHealthDetailsAndLogging(unittest.TestCase):
    def test_evaluate_health_returns_probe_failure_reason(self) -> None:
        cfg = config_module.AppConfig()
        failed_probe = health_module.Probe(
            name="health",
            cmd=runtime_module.CmdResult(
                argv=["openclaw", "gateway", "health", "--json"],
                cwd=None,
                exit_code=1,
                duration_ms=1,
                stdout="",
                stderr="health failed",
            ),
            json_data=None,
        )
        ok_probe = health_module.Probe(
            name="status",
            cmd=runtime_module.CmdResult(
                argv=["openclaw", "gateway", "status", "--json"],
                cwd=None,
                exit_code=0,
                duration_ms=1,
                stdout="{}",
                stderr="",
            ),
            json_data={},
        )
        with patch.object(repair_module, "probe_health", return_value=failed_probe), patch.object(
            repair_module, "probe_status", return_value=ok_probe
        ):
            evaluation = repair_module._evaluate_health(cfg)
            self.assertFalse(evaluation.effective_healthy)
            self.assertFalse(evaluation.probe_healthy)
            self.assertEqual(evaluation.reason, "probe_failed")
            self.assertEqual(evaluation.health["exit_code"], 1)
            self.assertEqual(evaluation.status["exit_code"], 0)

    def test_setup_logging_creates_private_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = config_module.AppConfig(
                monitor=config_module.MonitorConfig(
                    state_dir=Path(td),
                    log_file=Path(td) / "fix-my-claw.log",
                )
            )
            shared_module.setup_logging(cfg)
            mode = os.stat(cfg.monitor.log_file).st_mode & 0o777
            self.assertEqual(mode & 0o077, 0)


class TestFileLockSafety(unittest.TestCase):
    def test_recent_empty_lock_file_is_not_treated_as_stale(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            lock_path = Path(td) / "fix-my-claw.lock"
            lock_path.touch()
            lock = state_module.FileLock(lock_path)
            self.assertFalse(lock._try_break_stale_lock())
            self.assertTrue(lock_path.exists())

    def test_old_empty_lock_file_is_treated_as_stale(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            lock_path = Path(td) / "fix-my-claw.lock"
            lock_path.touch()
            stale_ts = os.path.getmtime(lock_path) - (state_module.LOCK_INITIALIZING_GRACE_SECONDS + 1)
            os.utime(lock_path, (stale_ts, stale_ts))
            lock = state_module.FileLock(lock_path)
            self.assertTrue(lock._try_break_stale_lock())
            self.assertFalse(lock_path.exists())

    def test_lock_is_not_broken_on_permission_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            lock_path = Path(td) / "fix-my-claw.lock"
            lock_path.write_text("12345", encoding="utf-8")
            lock = state_module.FileLock(lock_path)
            with patch.object(state_module.os, "kill", side_effect=PermissionError):
                self.assertFalse(lock._try_break_stale_lock())
            self.assertTrue(lock_path.exists())

    def test_stale_lock_replacement_is_not_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            lock_path = Path(td) / "fix-my-claw.lock"
            lock_path.touch()
            stale_ts = os.path.getmtime(lock_path) - (state_module.LOCK_INITIALIZING_GRACE_SECONDS + 1)
            os.utime(lock_path, (stale_ts, stale_ts))
            lock = state_module.FileLock(lock_path)
            original_unlink_if_same_lock = lock._unlink_if_same_lock

            def _replace_lock(expected_signature: tuple[int, int] | None) -> bool:
                lock_path.unlink()
                lock_path.write_text("fresh-owner", encoding="utf-8")
                return original_unlink_if_same_lock(expected_signature)

            with patch.object(lock, "_unlink_if_same_lock", side_effect=_replace_lock):
                self.assertFalse(lock._try_break_stale_lock())
            self.assertTrue(lock_path.exists())
            self.assertEqual(lock_path.read_text(encoding="utf-8"), "fresh-owner")


class TestCliCommands(unittest.TestCase):
    def test_with_single_instance_returns_2_when_lock_is_held(self) -> None:
        cfg = config_module.AppConfig()
        lock = Mock()
        lock.acquire.return_value = False
        stderr = io.StringIO()

        with patch.object(cli, "FileLock", return_value=lock), patch("sys.stderr", new=stderr):
            code = cli._with_single_instance(cfg, lambda: 0)

        self.assertEqual(code, 2)
        self.assertIn("another fix-my-claw instance is running", stderr.getvalue())
        lock.release.assert_not_called()

    def test_cmd_check_returns_failure_and_json_for_unhealthy_result(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = config_module.AppConfig(monitor=config_module.MonitorConfig(state_dir=Path(td)))
            args = argparse.Namespace(config="ignored.toml", json=True)
            evaluation = _make_health_evaluation(effective_healthy=False)
            stdout = io.StringIO()

            with patch.object(cli, "_load_or_init_config", return_value=cfg), patch.object(
                cli, "setup_logging"
            ), patch.object(
                cli, "run_check", return_value=evaluation
            ), patch("sys.stdout", new=stdout):
                code = cli.cmd_check(args)

        self.assertEqual(code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["healthy"])
        self.assertEqual(payload["reason"], evaluation.reason)

    def test_cmd_start_and_stop_update_enabled_flag_and_emit_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = config_module.AppConfig(monitor=config_module.MonitorConfig(state_dir=Path(td)))
            start_args = argparse.Namespace(config="ignored.toml", json=True)
            stop_args = argparse.Namespace(config="ignored.toml", json=True)

            stdout = io.StringIO()
            with patch.object(cli, "_load_or_init_config", return_value=cfg), patch.object(
                cli, "setup_logging"
            ), patch("sys.stdout", new=stdout):
                code = cli.cmd_start(start_args)

            self.assertEqual(code, 0)
            start_payload = json.loads(stdout.getvalue())
            self.assertTrue(start_payload["enabled"])

            store = state_module.StateStore(Path(td))
            self.assertTrue(store.is_enabled())

            stdout = io.StringIO()
            with patch.object(cli, "_load_or_init_config", return_value=cfg), patch.object(
                cli, "setup_logging"
            ), patch("sys.stdout", new=stdout):
                code = cli.cmd_stop(stop_args)

            self.assertEqual(code, 0)
            stop_payload = json.loads(stdout.getvalue())
            self.assertFalse(stop_payload["enabled"])
            self.assertFalse(store.is_enabled())

    def test_cmd_status_reports_enabled_flag(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = config_module.AppConfig(monitor=config_module.MonitorConfig(state_dir=Path(td)))
            store = state_module.StateStore(Path(td))
            store.set_enabled(False)
            args = argparse.Namespace(config="ignored.toml", json=True)
            stdout = io.StringIO()

            with patch.object(cli, "_load_config_or_default", return_value=(cfg, True)), patch.object(
                cli, "setup_logging"
            ), patch("sys.stdout", new=stdout):
                code = cli.cmd_status(args)

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["config_exists"])
        self.assertFalse(payload["enabled"])

    def test_cmd_repair_uses_force_flag_and_emits_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = config_module.AppConfig(monitor=config_module.MonitorConfig(state_dir=Path(td)))
            args = argparse.Namespace(config="ignored.toml", force=True, json=True)
            result = Mock()
            result.fixed = True
            result.to_json.return_value = {"fixed": True}
            lock = Mock()
            lock.acquire.return_value = True
            stdout = io.StringIO()

            with patch.object(cli, "_load_or_init_config", return_value=cfg), patch.object(
                cli, "setup_logging"
            ), patch.object(
                cli, "FileLock", return_value=lock
            ), patch.object(
                cli, "attempt_repair", return_value=result
            ) as attempt_repair_mock, patch("sys.stdout", new=stdout):
                code = cli.cmd_repair(args)

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), {"fixed": True})
        self.assertEqual(attempt_repair_mock.call_args.args[0], cfg)
        self.assertIsInstance(attempt_repair_mock.call_args.args[1], state_module.StateStore)
        self.assertEqual(
            attempt_repair_mock.call_args.kwargs,
            {"force": True, "reason": None},
        )
        lock.release.assert_called_once()

    def test_cmd_up_enables_monitoring_before_monitor(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = config_module.AppConfig(monitor=config_module.MonitorConfig(state_dir=Path(td)))
            args = argparse.Namespace(config="ignored.toml")
            lock = Mock()
            lock.acquire.return_value = True
            observed_enabled: list[bool] = []

            def _fake_monitor_loop(_cfg: config_module.AppConfig, store: state_module.StateStore) -> None:
                observed_enabled.append(store.is_enabled())

            with patch.object(cli, "_load_or_init_config", return_value=cfg), patch.object(
                cli, "setup_logging"
            ), patch.object(
                cli, "FileLock", return_value=lock
            ), patch.object(
                cli, "monitor_loop", side_effect=_fake_monitor_loop
            ):
                code = cli.cmd_up(args)

        self.assertEqual(code, 0)
        self.assertEqual(observed_enabled, [True])
        lock.release.assert_called_once()


class TestMonitorLoop(unittest.TestCase):
    def test_monitor_loop_idles_when_monitoring_is_disabled(self) -> None:
        class StopLoop(Exception):
            pass

        with tempfile.TemporaryDirectory() as td:
            cfg = config_module.AppConfig(
                monitor=config_module.MonitorConfig(
                    state_dir=Path(td),
                    interval_seconds=1,
                )
            )
            store = state_module.StateStore(Path(td))
            store.set_enabled(False)

            with patch.object(monitor, "run_check") as run_check_mock, patch.object(
                monitor, "attempt_repair"
            ) as attempt_repair_mock, patch.object(
                monitor.time, "sleep", side_effect=StopLoop
            ):
                with self.assertRaises(StopLoop):
                    monitor.monitor_loop(cfg, store)

        run_check_mock.assert_not_called()
        attempt_repair_mock.assert_not_called()

    def test_monitor_loop_attempts_repair_once_for_anomaly_guard(self) -> None:
        class StopLoop(Exception):
            pass

        with tempfile.TemporaryDirectory() as td:
            cfg = config_module.AppConfig(
                monitor=config_module.MonitorConfig(
                    state_dir=Path(td),
                    interval_seconds=1,
                )
            )
            store = state_module.StateStore(Path(td))
            evaluation = _make_health_evaluation(
                effective_healthy=False,
                anomaly_guard={"triggered": True, "signals": ["ping_pong"]},
                reason="anomaly_guard",
            )
            repair_result = SimpleNamespace(
                attempted=True,
                fixed=False,
                used_ai=False,
                details={"attempt_dir": str(Path(td) / "attempt-1")},
            )

            with patch.object(monitor, "run_check", return_value=evaluation), patch.object(
                monitor, "attempt_repair", return_value=repair_result
            ) as attempt_repair_mock, patch.object(
                monitor.time, "sleep", side_effect=StopLoop
            ):
                with self.assertRaises(StopLoop):
                    monitor.monitor_loop(cfg, store)

        attempt_repair_mock.assert_called_once_with(
            cfg,
            store,
            force=False,
            reason="anomaly_guard",
        )


if __name__ == "__main__":
    unittest.main()
