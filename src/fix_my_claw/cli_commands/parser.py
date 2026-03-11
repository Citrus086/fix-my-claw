"""Argument parser builder for fix-my-claw CLI."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import AppConfig


def build_parser(
    *,
    default_config_path: str,
    cmd_init: callable,
    cmd_check: callable,
    cmd_status: callable,
    cmd_start: callable,
    cmd_stop: callable,
    cmd_repair: callable,
    cmd_auto_repair: callable,
    cmd_monitor: callable,
    cmd_up: callable,
    cmd_config_show: callable,
    cmd_config_set: callable,
    cmd_service_install: callable,
    cmd_service_uninstall: callable,
    cmd_service_start: callable,
    cmd_service_stop: callable,
    cmd_service_status: callable,
    cmd_service_reconcile: callable,
) -> argparse.ArgumentParser:
    """Build the argument parser for fix-my-claw CLI."""

    def _add_config_arg(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--config",
            default=default_config_path,
            help=f"Path to TOML config file (default: {default_config_path}).",
        )

    parser = argparse.ArgumentParser(prog="fix-my-claw")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    parser_up = subparsers.add_parser("up", help="One-command start: init default config (if missing) then monitor.")
    _add_config_arg(parser_up)
    parser_up.set_defaults(func=cmd_up)

    parser_init = subparsers.add_parser("init", help="Write default config (prints config path).")
    _add_config_arg(parser_init)
    parser_init.add_argument("--force", action="store_true", help="Overwrite config if it already exists.")
    parser_init.set_defaults(func=cmd_init)

    parser_check = subparsers.add_parser("check", help="Probe OpenClaw health/status once.")
    _add_config_arg(parser_check)
    parser_check.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_check.set_defaults(func=cmd_check)

    parser_status = subparsers.add_parser(
        "status",
        help="Show whether monitoring is enabled plus persisted monitor state.",
    )
    _add_config_arg(parser_status)
    parser_status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_status.set_defaults(func=cmd_status)

    parser_start = subparsers.add_parser(
        "start",
        help="Enable monitoring so an active monitor loop resumes auto-heal.",
    )
    _add_config_arg(parser_start)
    parser_start.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_start.set_defaults(func=cmd_start)

    parser_stop = subparsers.add_parser(
        "stop",
        help="Disable monitoring so monitor loops idle instead of probing/repairing.",
    )
    _add_config_arg(parser_stop)
    parser_stop.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_stop.set_defaults(func=cmd_stop)

    parser_repair = subparsers.add_parser(
        "repair",
        help="Run a manual repair once, even if the initial health check already looks healthy.",
    )
    _add_config_arg(parser_repair)
    parser_repair.add_argument("--force", action="store_true", help="Ignore cooldown and attempt repair.")
    parser_repair.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_repair.set_defaults(func=cmd_repair)

    parser_auto_repair = subparsers.add_parser(
        "auto-repair",
        help="Run one automatic repair pass and skip the attempt if the initial health check is already healthy.",
    )
    _add_config_arg(parser_auto_repair)
    parser_auto_repair.add_argument("--force", action="store_true", help="Ignore cooldown and attempt repair.")
    parser_auto_repair.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_auto_repair.set_defaults(func=cmd_auto_repair)

    parser_monitor = subparsers.add_parser("monitor", help="Run 24/7 monitor loop (requires config to exist).")
    _add_config_arg(parser_monitor)
    parser_monitor.set_defaults(func=cmd_monitor)

    parser_config = subparsers.add_parser("config", help="Manage fix-my-claw configuration.")
    config_subparsers = parser_config.add_subparsers(dest="config_cmd", required=True)

    parser_config_show = config_subparsers.add_parser("show", help="Show current configuration.")
    _add_config_arg(parser_config_show)
    parser_config_show.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_config_show.set_defaults(func=cmd_config_show)

    parser_config_set = config_subparsers.add_parser("set", help="Replace configuration from stdin JSON.")
    _add_config_arg(parser_config_set)
    parser_config_set.add_argument("--json", action="store_true", help="Read JSON input from stdin.")
    parser_config_set.set_defaults(func=cmd_config_set)

    parser_service = subparsers.add_parser("service", help="Manage the macOS launchd monitor service.")
    service_subparsers = parser_service.add_subparsers(dest="service_cmd", required=True)

    parser_service_install = service_subparsers.add_parser("install", help="Install the launchd service.")
    _add_config_arg(parser_service_install)
    parser_service_install.set_defaults(func=cmd_service_install)

    parser_service_uninstall = service_subparsers.add_parser("uninstall", help="Uninstall the launchd service.")
    parser_service_uninstall.set_defaults(func=cmd_service_uninstall)

    parser_service_start = service_subparsers.add_parser("start", help="Start the launchd service.")
    _add_config_arg(parser_service_start)
    parser_service_start.set_defaults(func=cmd_service_start)

    parser_service_stop = service_subparsers.add_parser("stop", help="Stop the launchd service.")
    parser_service_stop.set_defaults(func=cmd_service_stop)

    parser_service_status = service_subparsers.add_parser("status", help="Show launchd service status.")
    _add_config_arg(parser_service_status)
    parser_service_status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_service_status.set_defaults(func=cmd_service_status)

    parser_service_reconcile = service_subparsers.add_parser(
        "reconcile",
        help="Align the launchd service plist, binary path, and loaded job.",
    )
    _add_config_arg(parser_service_reconcile)
    parser_service_reconcile.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_service_reconcile.set_defaults(func=cmd_service_reconcile)

    return parser
