from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fix_my_claw import core


class TestAnomalyGuardConfigCompat(unittest.TestCase):
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
            cfg = core.load_config(str(cfg_path))
            self.assertTrue(cfg.anomaly_guard.enabled)
            self.assertEqual(cfg.anomaly_guard.min_ping_pong_turns, 7)
            self.assertEqual(cfg.anomaly_guard.max_repeat_same_signature, 9)

    def test_parse_repair_filters_empty_official_steps(self) -> None:
        repair = core._parse_repair(
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

    def test_parse_notify_read_timeout_falls_back_to_send_timeout(self) -> None:
        notify = core._parse_notify(
            {
                "send_timeout_seconds": 42,
            }
        )
        self.assertEqual(notify.send_timeout_seconds, 42)
        self.assertEqual(notify.read_timeout_seconds, 42)

    def test_parse_monitor_sanitizes_invalid_timing_values(self) -> None:
        monitor = core._parse_monitor(
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
        ai = core._parse_ai(
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
        cfg = core.AppConfig()
        store = core.StateStore(Path(tempfile.mkdtemp()))

        ok_probe = core.Probe(
            name="health",
            cmd=core.CmdResult(
                argv=["openclaw", "gateway", "health", "--json"],
                cwd=None,
                exit_code=0,
                duration_ms=1,
                stdout="{}",
                stderr="",
            ),
            json_data={},
        )
        status_probe = core.Probe(
            name="status",
            cmd=core.CmdResult(
                argv=["openclaw", "gateway", "status", "--json"],
                cwd=None,
                exit_code=0,
                duration_ms=1,
                stdout="{}",
                stderr="",
            ),
            json_data={},
        )

        with patch.object(core, "probe_health", return_value=ok_probe), patch.object(
            core, "probe_status", return_value=status_probe
        ), patch.object(
            core,
            "_analyze_anomaly_guard",
            return_value={"triggered": True, "signals": {"ping_pong_trigger": True}},
        ):
            result = core.run_check(cfg, store)
            self.assertFalse(result.healthy)
            self.assertIsNotNone(result.anomaly_guard)
            self.assertTrue(result.anomaly_guard["triggered"])

    def test_detector_triggers_on_ping_pong_pattern(self) -> None:
        cfg = core.AppConfig(
            anomaly_guard=core.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_ping_pong_turns=2,
            )
        )
        log_text = "\n".join(
            [
                "orchestrator: user says stop now",
                "builder: received stop, repeating status",
                "orchestrator: stop immediately, loop detected",
                "builder: force stop command sent",
            ]
        )
        log_result = core.CmdResult(
            argv=["openclaw", "logs", "--tail", "200"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        with patch.object(core, "probe_logs", return_value=log_result):
            info = core._analyze_anomaly_guard(cfg)
            self.assertTrue(info["triggered"])
            self.assertTrue(info["signals"]["ping_pong_trigger"])

    def test_detector_triggers_on_ping_pong_without_stop_signal(self) -> None:
        cfg = core.AppConfig(
            anomaly_guard=core.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_ping_pong_turns=2,
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
        log_result = core.CmdResult(
            argv=["openclaw", "logs", "--tail", "200"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        with patch.object(core, "probe_logs", return_value=log_result):
            info = core._analyze_anomaly_guard(cfg)
            self.assertTrue(info["triggered"])
            self.assertTrue(info["signals"]["ping_pong_trigger"])

    def test_detector_triggers_on_repeated_signature_without_stop_signal(self) -> None:
        cfg = core.AppConfig(
            anomaly_guard=core.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=3,
                min_ping_pong_turns=99,
            )
        )
        log_text = "\n".join(
            [
                "builder: progress batch 1 completed",
                "builder: progress batch 2 completed",
                "builder: progress batch 3 completed",
            ]
        )
        log_result = core.CmdResult(
            argv=["openclaw", "logs", "--tail", "200"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        with patch.object(core, "probe_logs", return_value=log_result):
            info = core._analyze_anomaly_guard(cfg)
            self.assertTrue(info["triggered"])
            self.assertTrue(info["signals"]["repeat_trigger"])

    def test_detector_triggers_on_similarity_repeat_for_single_agent(self) -> None:
        cfg = core.AppConfig(
            anomaly_guard=core.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_ping_pong_turns=99,
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
        log_result = core.CmdResult(
            argv=["openclaw", "logs", "--tail", "200"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        with patch.object(core, "probe_logs", return_value=log_result):
            info = core._analyze_anomaly_guard(cfg)
            self.assertTrue(info["triggered"])
            self.assertTrue(info["signals"]["similar_repeat_trigger"])
            self.assertEqual(info["metrics"]["max_similar_repeats"], 3)
            self.assertEqual(info["metrics"]["top_similar_group"]["role"], "builder")

    def test_similarity_repeat_does_not_mix_different_roles(self) -> None:
        cfg = core.AppConfig(
            anomaly_guard=core.AnomalyGuardConfig(
                enabled=True,
                max_repeat_same_signature=99,
                min_ping_pong_turns=99,
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
        log_result = core.CmdResult(
            argv=["openclaw", "logs", "--tail", "200"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=log_text,
            stderr="",
        )
        with patch.object(core, "probe_logs", return_value=log_result):
            info = core._analyze_anomaly_guard(cfg)
            self.assertFalse(info["triggered"])
            self.assertFalse(info["signals"]["similar_repeat_trigger"])


class TestNotifyDecision(unittest.TestCase):
    def test_extract_ai_decision_respects_operator_filter(self) -> None:
        cfg = core.AppConfig(
            notify=core.NotifyConfig(
                target="user:u1",
                operator_user_ids=["u1"],
            )
        )
        yes_msg = {"content": "yes", "author": {"id": "u1", "bot": False}}
        no_msg = {"content": "no", "author": {"id": "u1", "bot": False}}
        invalid_msg = {"content": "yes, go ahead", "author": {"id": "u1", "bot": False}}
        outsider_msg = {"content": "yes", "author": {"id": "u2", "bot": False}}
        bot_msg = {"content": "yes", "author": {"id": "u1", "bot": True}}

        self.assertEqual(core._extract_ai_decision(cfg, yes_msg), "yes")
        self.assertEqual(core._extract_ai_decision(cfg, no_msg), "no")
        self.assertIsNone(core._extract_ai_decision(cfg, invalid_msg))
        self.assertIsNone(core._extract_ai_decision(cfg, outsider_msg))
        self.assertIsNone(core._extract_ai_decision(cfg, bot_msg))

    def test_extract_ai_decision_requires_mention_for_channel_target(self) -> None:
        cfg = core.AppConfig(
            notify=core.NotifyConfig(
                account="fix-my-claw",
                target="channel:123",
            )
        )
        plain_yes = {"content": "yes", "author": {"id": "u1", "bot": False}}
        mention_yes = {
            "content": "<@1479170394580848660> yes",
            "author": {"id": "u1", "bot": False},
            "mentions": [{"id": "1479170394580848660", "username": "fix-my-claw"}],
        }
        wrong_mention = {
            "content": "<@222> yes",
            "author": {"id": "u1", "bot": False},
            "mentions": [{"id": "222", "username": "someone-else"}],
        }

        self.assertIsNone(core._extract_ai_decision(cfg, plain_yes))
        self.assertEqual(core._extract_ai_decision(cfg, mention_yes), "yes")
        self.assertIsNone(core._extract_ai_decision(cfg, wrong_mention, required_mention_id="1479170394580848660"))
        self.assertEqual(
            core._extract_ai_decision(cfg, mention_yes, required_mention_id="1479170394580848660"),
            "yes",
        )
        self.assertEqual(
            core._extract_ai_decision(
                cfg,
                {"content": "<@1479170394580848660> yes", "author": {"id": "u1", "bot": False}},
                required_mention_id="1479170394580848660",
            ),
            "yes",
        )

    def test_ask_user_enable_ai_stops_after_three_invalid_replies(self) -> None:
        cfg = core.AppConfig(
            notify=core.NotifyConfig(
                account="fix-my-claw",
                target="channel:1479011917367476347",
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
                "content": "<@1479170394580848660> maybe",
                "author": {"id": "u1", "bot": False},
                "mentions": [{"id": "1479170394580848660", "username": "fix-my-claw"}],
            },
            {
                "id": "m2",
                "content": "<@1479170394580848660> 好的",
                "author": {"id": "u1", "bot": False},
                "mentions": [{"id": "1479170394580848660", "username": "fix-my-claw"}],
            },
            {
                "id": "m3",
                "content": "<@1479170394580848660> 继续",
                "author": {"id": "u1", "bot": False},
                "mentions": [{"id": "1479170394580848660", "username": "fix-my-claw"}],
            },
        ]
        with patch.object(core, "_notify_send", side_effect=[sent_payload, {"sent": True}, {"sent": True}]) as notify_mock, patch.object(
            core, "_resolve_sent_message_author_id", return_value="1479170394580848660"
        ), patch.object(core, "_notify_read_messages", side_effect=[invalid_replies]):
            out = core._ask_user_enable_ai(cfg, attempt_dir)
            self.assertEqual(out.get("decision"), "invalid_limit")
            self.assertEqual(out.get("invalid_replies"), 3)
            self.assertEqual(notify_mock.call_count, 3)

    def test_ask_user_enable_ai_advances_last_seen_by_batch_max_id(self) -> None:
        cfg = core.AppConfig(
            notify=core.NotifyConfig(
                account="fix-my-claw",
                target="channel:1479011917367476347",
                ask_enable_ai=True,
                ask_timeout_seconds=1,
                poll_interval_seconds=0,
            )
        )
        attempt_dir = Path(tempfile.mkdtemp())
        after_ids: list[str | None] = []

        def _read_side_effect(_cfg: core.AppConfig, *, after_id: str | None = None) -> list[dict]:
            after_ids.append(after_id)
            if len(after_ids) == 1:
                # Return out-of-order IDs; next poll should still advance to max("10", "9") => "10".
                return [
                    {"id": "10", "content": "", "author": {"id": "u1", "bot": True}},
                    {"id": "9", "content": "", "author": {"id": "u2", "bot": True}},
                ]
            return []

        with patch.object(core, "_notify_send", return_value={"sent": True, "message_id": "m-ask"}), patch.object(
            core, "_resolve_sent_message_author_id", return_value="1479170394580848660"
        ), patch.object(
            core, "_notify_read_messages", side_effect=_read_side_effect
        ), patch.object(
            core.time, "monotonic", side_effect=[0, 0, 0.5, 2]
        ), patch.object(
            core.time, "sleep", return_value=None
        ):
            out = core._ask_user_enable_ai(cfg, attempt_dir)
            self.assertEqual(out.get("decision"), "timeout")
            self.assertEqual(after_ids, ["m-ask", "10"])

    def test_notify_read_messages_uses_read_timeout(self) -> None:
        cfg = core.AppConfig(
            notify=core.NotifyConfig(
                send_timeout_seconds=5,
                read_timeout_seconds=33,
            )
        )
        payload = {"payload": {"messages": [{"id": "m1"}]}}
        cmd = core.CmdResult(
            argv=["openclaw", "message", "read"],
            cwd=None,
            exit_code=0,
            duration_ms=1,
            stdout=json.dumps(payload),
            stderr="",
        )
        with patch.object(core, "run_cmd", return_value=cmd) as run_cmd_mock:
            out = core._notify_read_messages(cfg)
            self.assertEqual(out, [{"id": "m1"}])
            self.assertEqual(run_cmd_mock.call_args.kwargs["timeout_seconds"], 33)


class TestStateStoreAiRateLimit(unittest.TestCase):
    def test_can_attempt_ai_resets_last_ai_ts_on_day_rollover(self) -> None:
        store = core.StateStore(Path(tempfile.mkdtemp()))
        store.save(
            core.State(
                last_ai_ts=1_000,
                ai_attempts_day="2026-03-05",
                ai_attempts_count=1,
            )
        )
        with patch.object(core, "_today_ymd", return_value="2026-03-06"), patch.object(
            core, "_now_ts", return_value=1_100
        ):
            self.assertTrue(store.can_attempt_ai(max_attempts_per_day=2, cooldown_seconds=3_600))
        state = store.load()
        self.assertEqual(state.ai_attempts_day, "2026-03-06")
        self.assertEqual(state.ai_attempts_count, 0)
        self.assertIsNone(state.last_ai_ts)


class TestRepairFlow(unittest.TestCase):
    def _cfg(self) -> core.AppConfig:
        return core.AppConfig(
            repair=core.RepairConfig(enabled=True, official_steps=[]),
            notify=core.NotifyConfig(ask_enable_ai=True),
            ai=core.AiConfig(enabled=True, allow_code_changes=False),
        )

    def _cmd_ok(self) -> core.CmdResult:
        return core.CmdResult(argv=["codex"], cwd=None, exit_code=0, duration_ms=1, stdout="", stderr="")

    def test_yes_runs_backup_then_ai(self) -> None:
        cfg = self._cfg()
        store = core.StateStore(Path(tempfile.mkdtemp()))
        with patch.object(core, "_probe_is_healthy", return_value=False), patch.object(
            core, "_collect_context", return_value={}
        ), patch.object(core, "_run_session_command_stage", return_value=[]), patch.object(
            core, "_run_official_steps", return_value=[]
        ), patch.object(
            core, "_is_effectively_healthy", side_effect=[(False, None), (True, None)]
        ), patch.object(
            core, "_ask_user_enable_ai", return_value={"asked": True, "decision": "yes"}
        ), patch.object(
            core, "_backup_openclaw_state", return_value={"archive": "/tmp/openclaw.backup.tar.gz"}
        ) as backup_mock, patch.object(
            core, "_run_ai_repair", return_value=self._cmd_ok()
        ) as ai_mock, patch.object(
            core, "_notify_send", return_value={"sent": True}
        ):
            result = core.attempt_repair(cfg, store, force=True, reason=None)
            self.assertTrue(result.used_ai)
            backup_mock.assert_called_once()
            ai_mock.assert_called_once()

    def test_timeout_never_runs_ai(self) -> None:
        cfg = self._cfg()
        store = core.StateStore(Path(tempfile.mkdtemp()))
        with patch.object(core, "_probe_is_healthy", return_value=False), patch.object(
            core, "_collect_context", return_value={}
        ), patch.object(core, "_run_session_command_stage", return_value=[]), patch.object(
            core, "_run_official_steps", return_value=[]
        ), patch.object(
            core, "_is_effectively_healthy", side_effect=[(False, None), (False, None)]
        ), patch.object(
            core, "_ask_user_enable_ai", return_value={"asked": True, "decision": "timeout"}
        ), patch.object(
            core, "_run_ai_repair"
        ) as ai_mock, patch.object(
            core, "_notify_send", return_value={"sent": True}
        ):
            result = core.attempt_repair(cfg, store, force=True, reason=None)
            self.assertFalse(result.used_ai)
            ai_mock.assert_not_called()

    def test_ai_disabled_still_notifies_but_skips_yes_no_and_ai_flow(self) -> None:
        cfg = core.AppConfig(
            repair=core.RepairConfig(enabled=True, official_steps=[]),
            notify=core.NotifyConfig(ask_enable_ai=True),
            ai=core.AiConfig(enabled=False, allow_code_changes=False),
        )
        store = core.StateStore(Path(tempfile.mkdtemp()))
        with patch.object(core, "_probe_is_healthy", return_value=False), patch.object(
            core, "_collect_context", return_value={}
        ), patch.object(core, "_run_session_command_stage", return_value=[]), patch.object(
            core, "_run_official_steps", return_value=[]
        ), patch.object(
            core, "_is_effectively_healthy", side_effect=[(False, None), (False, None)]
        ), patch.object(
            core, "_ask_user_enable_ai"
        ) as ask_mock, patch.object(
            core, "_run_ai_repair"
        ) as ai_mock, patch.object(
            core, "_notify_send"
        ) as notify_mock:
            result = core.attempt_repair(cfg, store, force=True, reason=None)
            self.assertFalse(result.used_ai)
            ask_mock.assert_not_called()
            ai_mock.assert_not_called()
            self.assertEqual(notify_mock.call_count, 2)

    def test_ai_rate_limit_skips_ask_and_ai(self) -> None:
        cfg = core.AppConfig(
            repair=core.RepairConfig(enabled=True, official_steps=[]),
            notify=core.NotifyConfig(ask_enable_ai=True),
            ai=core.AiConfig(enabled=True, allow_code_changes=False, max_attempts_per_day=0),
        )
        store = core.StateStore(Path(tempfile.mkdtemp()))
        with patch.object(core, "_probe_is_healthy", return_value=False), patch.object(
            core, "_collect_context", return_value={}
        ), patch.object(core, "_run_session_command_stage", return_value=[]), patch.object(
            core, "_run_official_steps", return_value=[]
        ), patch.object(
            core, "_is_effectively_healthy", side_effect=[(False, None), (False, None)]
        ), patch.object(
            core, "_ask_user_enable_ai"
        ) as ask_mock, patch.object(
            core, "_run_ai_repair"
        ) as ai_mock, patch.object(
            core, "_notify_send", return_value={"sent": True}
        ):
            result = core.attempt_repair(cfg, store, force=True, reason=None)
            self.assertFalse(result.used_ai)
            self.assertEqual(result.details.get("ai_decision", {}).get("decision"), "rate_limited")
            ask_mock.assert_not_called()
            ai_mock.assert_not_called()

    def test_collect_context_keeps_stage_snapshots_immutable(self) -> None:
        cfg = core.AppConfig()
        attempt_dir = Path(tempfile.mkdtemp())
        health = core.Probe(
            name="health",
            cmd=core.CmdResult(argv=["openclaw"], cwd=None, exit_code=0, duration_ms=1, stdout="h", stderr=""),
            json_data={},
        )
        status = core.Probe(
            name="status",
            cmd=core.CmdResult(argv=["openclaw"], cwd=None, exit_code=0, duration_ms=1, stdout="s", stderr=""),
            json_data={},
        )
        logs = core.CmdResult(argv=["openclaw"], cwd=None, exit_code=0, duration_ms=1, stdout="l", stderr="")
        with patch.object(core, "probe_health", return_value=health), patch.object(
            core, "probe_status", return_value=status
        ), patch.object(core, "probe_logs", return_value=logs):
            before = core._collect_context(cfg, attempt_dir, stage_name="before")
            after = core._collect_context(cfg, attempt_dir, stage_name="after_official")
            self.assertNotEqual(before["logs"]["stdout_path"], after["logs"]["stdout_path"])
            self.assertTrue(Path(before["logs"]["stdout_path"]).exists())
            self.assertTrue(Path(after["logs"]["stdout_path"]).exists())

    def test_run_official_steps_skips_empty_step_at_runtime(self) -> None:
        cfg = core.AppConfig(repair=core.RepairConfig(official_steps=[[], ["openclaw", "gateway", "restart"]]))
        attempt_dir = Path(tempfile.mkdtemp())
        with patch.object(core, "run_cmd", return_value=self._cmd_ok()) as run_cmd_mock, patch.object(
            core, "_probe_is_healthy", return_value=False
        ), patch.object(core.time, "sleep", return_value=None):
            out = core._run_official_steps(cfg, attempt_dir, break_on_healthy=False)
            self.assertEqual(len(out), 1)
            run_cmd_mock.assert_called_once()

    def test_run_ai_repair_writes_stage_scoped_logs(self) -> None:
        cfg = core.AppConfig()
        attempt_dir = Path(tempfile.mkdtemp())
        with patch.object(core, "run_cmd", return_value=self._cmd_ok()):
            core._run_ai_repair(cfg, attempt_dir, code_stage=False)
            core._run_ai_repair(cfg, attempt_dir, code_stage=True)
        self.assertTrue((attempt_dir / "ai.config.stdout.txt").exists())
        self.assertTrue((attempt_dir / "ai.code.stdout.txt").exists())

    def test_session_stage_does_not_depend_on_notify_target(self) -> None:
        cfg = core.AppConfig(
            repair=core.RepairConfig(
                session_control_enabled=True,
                session_agents=["macs-orchestrator"],
                session_active_minutes=30,
                terminate_message="/stop",
            ),
            notify=core.NotifyConfig(
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
        with patch.object(core, "_list_active_sessions", return_value=sessions), patch.object(
            core, "run_cmd", return_value=self._cmd_ok()
        ) as run_cmd_mock:
            out = core._run_session_command_stage(
                cfg,
                attempt_dir,
                stage_name="terminate",
                message_text="/stop",
            )
            self.assertEqual(len(out), 1)
            run_cmd_mock.assert_called_once()

    def test_attempt_repair_waits_between_terminate_and_new_stage(self) -> None:
        cfg = core.AppConfig(
            repair=core.RepairConfig(enabled=True, official_steps=[], session_stage_wait_seconds=2),
            notify=core.NotifyConfig(ask_enable_ai=True),
            ai=core.AiConfig(enabled=False, allow_code_changes=False),
        )
        store = core.StateStore(Path(tempfile.mkdtemp()))
        with patch.object(core, "_probe_is_healthy", return_value=False), patch.object(
            core, "_collect_context", return_value={}
        ), patch.object(
            core, "_run_session_command_stage", side_effect=[[{"agent": "macs-orchestrator"}], []]
        ), patch.object(
            core, "_run_official_steps", return_value=[]
        ), patch.object(
            core, "_is_effectively_healthy", side_effect=[(False, None), (False, None)]
        ), patch.object(
            core, "_notify_send", return_value={"sent": True}
        ), patch.object(
            core.time, "sleep", return_value=None
        ) as sleep_mock:
            core.attempt_repair(cfg, store, force=True, reason=None)
            sleep_mock.assert_called_once_with(2)


class TestHealthDetailsAndLogging(unittest.TestCase):
    def test_is_effectively_healthy_returns_probe_details_for_anomaly_reason(self) -> None:
        cfg = core.AppConfig()
        failed_probe = core.Probe(
            name="health",
            cmd=core.CmdResult(
                argv=["openclaw", "gateway", "health", "--json"],
                cwd=None,
                exit_code=1,
                duration_ms=1,
                stdout="",
                stderr="health failed",
            ),
            json_data=None,
        )
        ok_probe = core.Probe(
            name="status",
            cmd=core.CmdResult(
                argv=["openclaw", "gateway", "status", "--json"],
                cwd=None,
                exit_code=0,
                duration_ms=1,
                stdout="{}",
                stderr="",
            ),
            json_data={},
        )
        with patch.object(core, "probe_health", return_value=failed_probe), patch.object(
            core, "probe_status", return_value=ok_probe
        ):
            healthy, info = core._is_effectively_healthy(cfg, reason="anomaly_guard")
            self.assertFalse(healthy)
            self.assertIsNotNone(info)
            self.assertFalse(info["probe_ok"])
            self.assertEqual(info["health"]["exit_code"], 1)
            self.assertEqual(info["status"]["exit_code"], 0)

    def test_setup_logging_creates_private_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = core.AppConfig(
                monitor=core.MonitorConfig(
                    state_dir=Path(td),
                    log_file=Path(td) / "fix-my-claw.log",
                )
            )
            core.setup_logging(cfg)
            mode = os.stat(cfg.monitor.log_file).st_mode & 0o777
            self.assertEqual(mode & 0o077, 0)


class TestFileLockSafety(unittest.TestCase):
    def test_lock_is_not_broken_on_permission_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            lock_path = Path(td) / "fix-my-claw.lock"
            lock_path.write_text("12345", encoding="utf-8")
            lock = core.FileLock(lock_path)
            with patch.object(core.os, "kill", side_effect=PermissionError):
                self.assertFalse(lock._try_break_stale_lock())
            self.assertTrue(lock_path.exists())


if __name__ == "__main__":
    unittest.main()
