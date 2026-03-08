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
        self.assertEqual(payload["monitor"]["interval_seconds"], 75)
        self.assertTrue(payload["ai"]["enabled"])

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
            self.assertTrue(payload["installed"])
            self.assertTrue(payload["running"])

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
