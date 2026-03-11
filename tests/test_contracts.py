"""
Contract tests that validate CLI/GUI fixtures.

These tests ensure:
1. Fixtures contain valid JSON with api_version
2. Fixtures can be parsed by Python config modules
3. Python-generated payloads match fixture structure

Run with --update-fixtures to regenerate fixtures from Python code.
"""

from __future__ import annotations

import argparse
import json
import unittest
from pathlib import Path
from typing import Any

from fix_my_claw import config as config_module
from fix_my_claw import protocol as protocol_module

FIXTURES_DIR = Path(__file__).parent.parent / "contracts" / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    """Load a fixture file as JSON."""
    path = FIXTURES_DIR / name
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_fixture(name: str, data: dict[str, Any]) -> None:
    """Save data to a fixture file with pretty formatting."""
    path = FIXTURES_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


class TestContractFixturesExist(unittest.TestCase):
    """Verify all required fixture files exist."""

    def test_config_show_fixture_exists(self) -> None:
        self.assertTrue((FIXTURES_DIR / "config.show.v1.json").exists())

    def test_status_fixture_exists(self) -> None:
        self.assertTrue((FIXTURES_DIR / "status.v1.json").exists())

    def test_check_fixture_exists(self) -> None:
        self.assertTrue((FIXTURES_DIR / "check.v1.json").exists())

    def test_repair_fixture_exists(self) -> None:
        self.assertTrue((FIXTURES_DIR / "repair.v1.json").exists())

    def test_service_status_fixture_exists(self) -> None:
        self.assertTrue((FIXTURES_DIR / "service.status.v1.json").exists())

    def test_service_reconcile_fixture_exists(self) -> None:
        self.assertTrue((FIXTURES_DIR / "service.reconcile.v1.json").exists())


class TestContractFixturesHaveAPIVersion(unittest.TestCase):
    """Verify all fixtures contain api_version field."""

    def test_config_show_has_api_version(self) -> None:
        fixture = load_fixture("config.show.v1.json")
        self.assertEqual(fixture["api_version"], protocol_module.API_VERSION)

    def test_status_has_api_version(self) -> None:
        fixture = load_fixture("status.v1.json")
        self.assertEqual(fixture["api_version"], protocol_module.API_VERSION)

    def test_check_has_api_version(self) -> None:
        fixture = load_fixture("check.v1.json")
        self.assertEqual(fixture["api_version"], protocol_module.API_VERSION)

    def test_repair_has_api_version(self) -> None:
        fixture = load_fixture("repair.v1.json")
        self.assertEqual(fixture["api_version"], protocol_module.API_VERSION)

    def test_service_status_has_api_version(self) -> None:
        fixture = load_fixture("service.status.v1.json")
        self.assertEqual(fixture["api_version"], protocol_module.API_VERSION)

    def test_service_reconcile_has_api_version(self) -> None:
        fixture = load_fixture("service.reconcile.v1.json")
        self.assertEqual(fixture["api_version"], protocol_module.API_VERSION)


class TestConfigShowFixtureMatchesPython(unittest.TestCase):
    """Verify config.show fixture matches Python's _config_to_dict output."""

    def test_fixture_keys_match_python_output(self) -> None:
        """All top-level keys in fixture should exist in Python output."""
        fixture = load_fixture("config.show.v1.json")
        python_output = config_module._config_to_dict(config_module.AppConfig())
        python_output_with_version = protocol_module.with_api_version(python_output)

        # Check top-level keys (excluding api_version)
        fixture_keys = set(fixture.keys()) - {"api_version"}
        python_keys = set(python_output_with_version.keys()) - {"api_version"}
        self.assertEqual(fixture_keys, python_keys)

    def test_monitor_section_structure(self) -> None:
        """Monitor section should have expected fields."""
        fixture = load_fixture("config.show.v1.json")
        monitor = fixture["monitor"]

        expected_fields = {
            "interval_seconds",
            "probe_timeout_seconds",
            "repair_cooldown_seconds",
            "state_dir",
            "log_file",
            "log_level",
            "log_max_bytes",
            "log_backup_count",
            "log_retention_days",
        }
        self.assertEqual(set(monitor.keys()), expected_fields)

    def test_agent_roles_is_flat_not_nested(self) -> None:
        """agent_roles should be flat, not nested under 'roles'."""
        fixture = load_fixture("config.show.v1.json")
        agent_roles = fixture["agent_roles"]

        # Should have role names as keys
        self.assertIn("orchestrator", agent_roles)
        self.assertIn("builder", agent_roles)
        self.assertNotIn("roles", agent_roles)

    def test_fixture_can_be_parsed_by_dict_to_config(self) -> None:
        """Fixture should be parseable by _dict_to_config."""
        fixture = load_fixture("config.show.v1.json")

        # Should not raise
        config = config_module._dict_to_config(fixture)

        # Verify some key values (Python uses snake_case)
        self.assertEqual(config.monitor.interval_seconds, 60)
        self.assertEqual(config.repair.enabled, True)
        self.assertEqual(config.notify.level, "all")
        self.assertEqual(config.notify.required_mention_id, "")
        self.assertEqual(config.notify.max_invalid_replies, 3)

    def test_notify_fixture_exposes_new_configurable_fields(self) -> None:
        fixture = load_fixture("config.show.v1.json")
        notify = fixture["notify"]

        self.assertIn("required_mention_id", notify)
        self.assertIn("max_invalid_replies", notify)
        self.assertEqual(notify["required_mention_id"], "")
        self.assertEqual(notify["max_invalid_replies"], 3)


class TestStatusFixtureStructure(unittest.TestCase):
    """Verify status fixture has required fields."""

    def test_status_has_required_fields(self) -> None:
        fixture = load_fixture("status.v1.json")
        required = {
            "api_version",
            "enabled",
            "config_path",
            "config_exists",
            "state_path",
            "last_ok_ts",
            "last_repair_ts",
            "last_ai_ts",
            "ai_attempts_day",
            "ai_attempts_count",
        }
        self.assertEqual(set(fixture.keys()), required)


class TestCheckFixtureStructure(unittest.TestCase):
    """Verify check fixture has required fields."""

    def test_check_has_required_top_level_fields(self) -> None:
        fixture = load_fixture("check.v1.json")
        required = {
            "api_version",
            "healthy",
            "probe_healthy",
            "reason",
            "health",
            "status",
            "logs",
            "anomaly_guard",
            "loop_guard",
        }
        self.assertEqual(set(fixture.keys()), required)

    def test_probe_result_has_required_fields(self) -> None:
        fixture = load_fixture("check.v1.json")
        health = fixture["health"]
        required = {"name", "ok", "exit_code", "duration_ms", "argv", "stdout", "stderr"}
        self.assertTrue(required.issubset(set(health.keys())))

    def test_anomaly_guard_has_required_fields(self) -> None:
        fixture = load_fixture("check.v1.json")
        ag = fixture["anomaly_guard"]
        required = {"enabled", "triggered", "metrics", "signals"}
        self.assertTrue(required.issubset(set(ag.keys())))


class TestRepairFixtureStructure(unittest.TestCase):
    """Verify repair fixture has required fields."""

    def test_repair_has_required_top_level_fields(self) -> None:
        fixture = load_fixture("repair.v1.json")
        required = {"api_version", "attempted", "fixed", "used_ai", "details"}
        self.assertEqual(set(fixture.keys()), required)

    def test_repair_details_has_key_fields(self) -> None:
        fixture = load_fixture("repair.v1.json")
        details = fixture["details"]
        # Core fields that should always exist
        core_fields = {"attempt_dir", "reason"}
        self.assertTrue(core_fields.issubset(set(details.keys())))


class TestServiceStatusFixtureStructure(unittest.TestCase):
    """Verify service status fixture has required fields."""

    def test_service_status_has_required_fields(self) -> None:
        fixture = load_fixture("service.status.v1.json")
        required = {
            "api_version",
            "installed",
            "running",
            "label",
            "plist_path",
            "domain",
            "program_path",
            "config_path",
            "expected_program_path",
            "expected_config_path",
            "drifted",
        }
        self.assertEqual(set(fixture.keys()), required)


class TestServiceReconcileFixtureStructure(unittest.TestCase):
    """Verify service reconcile fixture has required fields."""

    def test_service_reconcile_has_required_fields(self) -> None:
        fixture = load_fixture("service.reconcile.v1.json")
        required = {"api_version", "action", "reasons", "service"}
        self.assertEqual(set(fixture.keys()), required)
        self.assertIsInstance(fixture["reasons"], list)
        self.assertIsInstance(fixture["service"], dict)


def update_fixtures() -> None:
    """Regenerate all fixtures from Python code."""
    print("Updating fixtures...")

    # config.show
    config_data = config_module._config_to_dict(config_module.AppConfig())
    save_fixture("config.show.v1.json", protocol_module.with_api_version(config_data))
    print("  Updated: config.show.v1.json")

    # status - use representative values
    status_data = protocol_module.build_status_payload(
        enabled=False,
        config_path="~/.fix-my-claw/config.toml",
        config_exists=True,
        state_path="~/.fix-my-claw/state.json",
        last_ok_ts=1709500000,
        last_repair_ts=1709510000,
        last_ai_ts=1709520000,
        ai_attempts_day="2026-03-09",
        ai_attempts_count=2,
    )
    save_fixture("status.v1.json", status_data)
    print("  Updated: status.v1.json")

    # check - manually constructed (complex structure)
    check_data = protocol_module.build_check_payload({
        "healthy": False,
        "probe_healthy": False,
        "reason": "gateway unhealthy",
        "health": {
            "name": "health",
            "ok": False,
            "exit_code": 1,
            "duration_ms": 150,
            "argv": ["openclaw", "gateway", "health", "--json"],
            "stdout": '{"ok": false}',
            "stderr": "gateway unavailable",
        },
        "status": {
            "name": "status",
            "ok": True,
            "exit_code": 0,
            "duration_ms": 80,
            "argv": ["openclaw", "gateway", "status", "--json"],
            "stdout": '{"mode": "degraded"}',
            "stderr": "",
        },
        "logs": {
            "ok": True,
            "exit_code": 0,
            "duration_ms": 25,
            "argv": ["openclaw", "logs", "--limit", "200", "--plain"],
        },
        "anomaly_guard": {
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
        "loop_guard": {
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
    })
    save_fixture("check.v1.json", check_data)
    print("  Updated: check.v1.json")

    # repair - manually constructed
    repair_data = protocol_module.build_repair_payload({
        "attempted": True,
        "fixed": True,
        "used_ai": True,
        "details": {
            "attempt_dir": "/tmp/fix-my-claw/attempts/attempt-001",
            "reason": "gateway unhealthy",
            "already_healthy": False,
            "repair_disabled": False,
            "cooldown": False,
            "cooldown_remaining_seconds": 0,
            "pause_wait_seconds": 20,
            "ai_decision": {
                "asked": True,
                "decision": "yes",
                "source": "discord",
                "invalid_replies": 0,
            },
            "ai_stage": "config",
            "official_break_reason": "still_unhealthy",
            "backup_before_ai_error": None,
            "notify_final": {
                "sent": True,
                "message_id": "msg-123456789",
                "exit_code": 0,
                "argv": ["notify", "--message", "fix-my-claw: AI config repair completed"],
                "stderr": "",
                "stdout": "",
            },
        },
    })
    save_fixture("repair.v1.json", repair_data)
    print("  Updated: repair.v1.json")

    # service.status
    service_data = protocol_module.build_service_status_payload(
        installed=True,
        running=True,
        label="com.fix-my-claw.monitor",
        plist_path="~/Library/LaunchAgents/com.fix-my-claw.monitor.plist",
        domain="gui/501",
        program_path="~/.fix-my-claw/bin/fix-my-claw-service",
        config_path="~/.fix-my-claw/config.toml",
        expected_program_path="~/.fix-my-claw/bin/fix-my-claw-service",
        expected_config_path="~/.fix-my-claw/config.toml",
        drifted=False,
    )
    save_fixture("service.status.v1.json", service_data)
    print("  Updated: service.status.v1.json")

    service_reconcile_data = protocol_module.build_service_reconcile_payload(
        action="noop",
        reasons=[],
        service=service_data,
    )
    save_fixture("service.reconcile.v1.json", service_reconcile_data)
    print("  Updated: service.reconcile.v1.json")

    print("Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-fixtures", action="store_true", help="Regenerate fixtures")
    args, remaining = parser.parse_known_args()

    if args.update_fixtures:
        update_fixtures()
    else:
        unittest.main(argv=[""] + remaining)
