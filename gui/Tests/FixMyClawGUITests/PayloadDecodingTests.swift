import XCTest
@testable import FixMyClawGUI

final class PayloadDecodingTests: XCTestCase {
    private let decoder = JSONDecoder()

    private func decode<T: Decodable>(_ type: T.Type, from json: String) throws -> T {
        try decoder.decode(type, from: Data(json.utf8))
    }

    func testAppConfigDecodesWithMissingSectionsUsingDefaults() throws {
        let payload = "{}"

        let config = try decode(AppConfig.self, from: payload)

        XCTAssertEqual(config.monitor.intervalSeconds, 60)
        XCTAssertEqual(config.repair.enabled, true)
        XCTAssertEqual(config.openclaw.command, "openclaw")
        XCTAssertEqual(config.notify.level, "all")
        XCTAssertEqual(config.ai.argsCode, [
            "exec",
            "-s", "danger-full-access",
            "-c", "approval_policy=\"never\"",
            "--skip-git-repo-check",
            "-C", "$workspace_dir",
        ])
        XCTAssertEqual(config.agentRoles.builder, ["builder", "macs-builder"])
    }

    func testStatusPayloadDecodesGuiRequiredFields() throws {
        let payload = """
        {
          "enabled": true,
          "config_path": "/tmp/config.toml",
          "config_exists": true,
          "state_path": "/tmp/state.json",
          "last_ok_ts": 11,
          "last_repair_ts": 22,
          "last_ai_ts": 33,
          "ai_attempts_day": "2026-03-09",
          "ai_attempts_count": 2
        }
        """

        let status = try decode(StatusPayload.self, from: payload)

        XCTAssertEqual(status.enabled, true)
        XCTAssertEqual(status.configPath, "/tmp/config.toml")
        XCTAssertEqual(status.configExists, true)
        XCTAssertEqual(status.statePath, "/tmp/state.json")
        XCTAssertEqual(status.lastOkTs, 11)
        XCTAssertEqual(status.lastRepairTs, 22)
        XCTAssertEqual(status.lastAiTs, 33)
        XCTAssertEqual(status.aiAttemptsDay, "2026-03-09")
        XCTAssertEqual(status.aiAttemptsCount, 2)
    }

    func testCheckPayloadDecodesGuiRequiredFields() throws {
        let payload = """
        {
          "healthy": false,
          "probe_healthy": false,
          "reason": "gateway unhealthy",
          "health": {
            "name": "health",
            "ok": false,
            "exit_code": 1,
            "duration_ms": 150,
            "argv": ["openclaw", "gateway", "health", "--json"],
            "stdout": "{\\"ok\\": false}",
            "stderr": "gateway unavailable",
            "json": {"ok": false}
          },
          "status": {
            "name": "status",
            "ok": true,
            "exit_code": 0,
            "duration_ms": 80,
            "argv": ["openclaw", "gateway", "status", "--json"],
            "stdout": "{\\"mode\\": \\"degraded\\"}",
            "stderr": "",
            "json": {"mode": "degraded"}
          },
          "logs": {
            "ok": true,
            "exit_code": 0,
            "duration_ms": 25,
            "argv": ["openclaw", "logs", "--limit", "200", "--plain"]
          },
          "anomaly_guard": {
            "enabled": true,
            "triggered": true,
            "probe_ok": true,
            "probe_exit_code": 0,
            "metrics": {
              "lines_analyzed": 120,
              "events_analyzed": 9,
              "cycle_repeated_turns": 4,
              "ping_pong_turns": 0
            },
            "signals": {
              "repeat_trigger": false,
              "similar_repeat_trigger": false,
              "ping_pong_trigger": false,
              "cycle_trigger": true,
              "stagnation_trigger": false,
              "auto_dispatch_trigger": false
            }
          },
          "loop_guard": {
            "enabled": true,
            "triggered": true,
            "probe_ok": true,
            "probe_exit_code": 0,
            "metrics": {
              "lines_analyzed": 120,
              "events_analyzed": 9,
              "cycle_repeated_turns": 4,
              "ping_pong_turns": 0
            },
            "signals": {
              "repeat_trigger": false,
              "similar_repeat_trigger": false,
              "ping_pong_trigger": false,
              "cycle_trigger": true,
              "stagnation_trigger": false,
              "auto_dispatch_trigger": false
            }
          }
        }
        """

        let check = try decode(CheckPayload.self, from: payload)

        XCTAssertEqual(check.healthy, false)
        XCTAssertEqual(check.probeHealthy, false)
        XCTAssertEqual(check.reason, "gateway unhealthy")
        XCTAssertEqual(check.health.exitCode, 1)
        XCTAssertEqual(check.status.exitCode, 0)
        XCTAssertEqual(check.logs?.argv, ["openclaw", "logs", "--limit", "200", "--plain"])
        XCTAssertEqual(check.anomalyGuard?.triggered, true)
        XCTAssertEqual(check.loopGuard?.signals?.cycleTrigger, true)
    }

    func testRepairResultDecodesPostRefactorDetails() throws {
        let payload = """
        {
          "attempted": true,
          "fixed": true,
          "used_ai": true,
          "details": {
            "attempt_dir": "/tmp/attempt-001",
            "reason": "gateway unhealthy",
            "already_healthy": false,
            "repair_disabled": false,
            "cooldown": false,
            "cooldown_remaining_seconds": 0,
            "pause_wait_seconds": 20,
            "ai_decision": {
              "asked": true,
              "decision": "yes",
              "source": "discord",
              "invalid_replies": 0
            },
            "ai_stage": "config",
            "official_break_reason": "still_unhealthy",
            "backup_before_ai_error": "disk full",
            "notify_final": {
              "sent": true,
              "message_id": "msg-1",
              "exit_code": 0,
              "argv": ["notify", "--message", "fix-my-claw: AI config repair completed"]
            }
          }
        }
        """

        let result = try decode(RepairResult.self, from: payload)

        XCTAssertEqual(result.attempted, true)
        XCTAssertEqual(result.fixed, true)
        XCTAssertEqual(result.usedAi, true)
        XCTAssertEqual(result.details.attemptDir, "/tmp/attempt-001")
        XCTAssertEqual(result.details.aiDecision?.decision, "yes")
        XCTAssertEqual(result.details.aiStage, "config")
        XCTAssertEqual(result.details.officialBreakReason, "still_unhealthy")
        XCTAssertEqual(result.details.backupBeforeAiError, "disk full")
        XCTAssertEqual(result.details.notifyFinal?.messageText, "fix-my-claw: AI config repair completed")
    }

    func testRepairResultDecodesWhenAiDecisionStringIsMissing() throws {
        let payload = """
        {
          "attempted": true,
          "fixed": false,
          "used_ai": false,
          "details": {
            "attempt_dir": "/tmp/attempt-002",
            "ai_decision": {
              "asked": true,
              "source": "discord"
            }
          }
        }
        """

        let result = try decode(RepairResult.self, from: payload)

        XCTAssertEqual(result.details.aiDecision?.asked, true)
        XCTAssertNil(result.details.aiDecision?.decision)
        XCTAssertEqual(result.details.aiDecision?.source, "discord")
    }

    func testServiceStatusDecodes() throws {
        let payload = """
        {
          "installed": true,
          "running": false,
          "label": "com.fix-my-claw.monitor",
          "plist_path": "/tmp/com.fix-my-claw.monitor.plist",
          "domain": "gui/501"
        }
        """

        let status = try decode(ServiceStatus.self, from: payload)

        XCTAssertEqual(status.installed, true)
        XCTAssertEqual(status.running, false)
    }

    func testConfigManagerResolvesOverrideConfigPath() {
        let resolved = ConfigManager.resolveDefaultConfigPath(
            environment: [ConfigManager.configPathOverrideEnvironmentKey: "/tmp/fix-my-claw-gui/config.toml"],
            homeDirectoryPath: "/Users/example"
        )

        XCTAssertEqual(resolved, "/tmp/fix-my-claw-gui/config.toml")
    }

    func testConfigManagerFallsBackToHomeDirectoryConfigPath() {
        let resolved = ConfigManager.resolveDefaultConfigPath(
            environment: [:],
            homeDirectoryPath: "/Users/example"
        )

        XCTAssertEqual(resolved, "/Users/example/.fix-my-claw/config.toml")
    }

    func testMenuBarManagerDisablesLocalNotificationsOutsideAppBundle() {
        XCTAssertFalse(MenuBarManager.canPostLocalNotifications(
            bundlePath: "/tmp/gui/.build/debug/fix-my-claw-gui",
            bundleIdentifier: nil
        ))
        XCTAssertTrue(MenuBarManager.canPostLocalNotifications(
            bundlePath: "/Applications/fix-my-claw-gui.app",
            bundleIdentifier: "com.example.fix-my-claw-gui"
        ))
    }
}
