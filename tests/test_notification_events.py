from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fix_my_claw import config as config_module
from fix_my_claw import notification_events
from fix_my_claw import repair_types


class TestNotificationEvents(unittest.TestCase):
    def _cfg(self, state_dir: Path) -> config_module.AppConfig:
        return config_module.AppConfig(
            monitor=config_module.MonitorConfig(
                state_dir=state_dir,
                log_file=state_dir / "fix-my-claw.log",
            ),
            notify=config_module.NotifyConfig(level="all"),
        )

    def test_dispatch_notification_event_persists_sequence_and_channel_result(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            cfg = self._cfg(state_dir)

            sent = notification_events.dispatch_notification_event(
                state_dir,
                kind="repair_started",
                source="repair",
                level="important",
                message_text="fix-my-claw: start",
                send_channel=True,
                notify_channel_fn=lambda _cfg, _text, *, silent=None: {
                    "sent": True,
                    "message_id": "m-1",
                    "silent": silent,
                },
                cfg=cfg,
                silent=False,
                local_title="🔧 修复已启动",
                local_body="修复正在后台运行，请稍候...",
                dedupe_key="repair_started:test",
            )

            self.assertEqual(sent["message_id"], "m-1")
            self.assertEqual(sent["sequence"], 1)

            events = notification_events.list_notification_events(state_dir)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["sequence"], 1)
            self.assertEqual(events[0]["kind"], "repair_started")
            self.assertEqual(events[0]["local_title"], "🔧 修复已启动")
            self.assertEqual(events[0]["channel"]["message_id"], "m-1")

    def test_dispatch_notification_event_skips_latest_duplicate_dedupe_key(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            cfg = self._cfg(state_dir)
            calls: list[str] = []

            def _send(_cfg: config_module.AppConfig, text: str, *, silent: bool | None = None) -> dict[str, object]:
                calls.append(text)
                return {"sent": True, "message_id": f"m-{len(calls)}"}

            for _ in range(2):
                notification_events.dispatch_notification_event(
                    state_dir,
                    kind="monitor_unhealthy",
                    source="monitor",
                    level="critical",
                    message_text="fix-my-claw: unhealthy",
                    send_channel=True,
                    notify_channel_fn=_send,
                    cfg=cfg,
                    local_title="🔴 OpenClaw 异常",
                    local_body="检测到异常状态。",
                    dedupe_key="monitor_unhealthy:cooldown",
                )

            events = notification_events.list_notification_events(state_dir)
            self.assertEqual(len(events), 1)
            self.assertEqual(len(calls), 1)

    def test_emit_repair_result_event_builds_local_notification(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            result = repair_types.RepairResult(
                attempted=False,
                fixed=False,
                used_ai=False,
                details_data={
                    "cooldown": True,
                    "cooldown_remaining_seconds": 42,
                },
            )

            notification_events.emit_repair_result_event(state_dir, result=result)

            events = notification_events.list_notification_events(state_dir)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["kind"], "repair_result")
            self.assertEqual(events[0]["local_title"], "⏳ 修复冷却中")
            self.assertEqual(events[0]["local_body"], "修复冷却期尚未结束，剩余 42 秒。")


if __name__ == "__main__":
    unittest.main()
