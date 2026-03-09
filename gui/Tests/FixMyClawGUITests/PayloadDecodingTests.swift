import XCTest
@testable import FixMyClawGUI

final class PayloadDecodingTests: XCTestCase {
    private let decoder = JSONDecoder()

    private func decode<T: Decodable>(_ type: T.Type, from json: String) throws -> T {
        try decoder.decode(type, from: Data(json.utf8))
    }

    // MARK: - Contract Tests (using shared fixtures)

    func testContract_ConfigShowFixture() throws {
        let dto = try FixtureLoader.load(AppConfigDTO.self, from: "config.show.v1.json")
        let config = AppConfig(dto: dto)

        // Verify key defaults
        XCTAssertEqual(config.monitor.intervalSeconds, 60)
        XCTAssertEqual(config.repair.enabled, true)
        XCTAssertEqual(config.openclaw.command, "openclaw")
        XCTAssertEqual(config.notify.level, "all")
        XCTAssertEqual(config.agentRoles.orchestrator, ["orchestrator", "macs-orchestrator"])
        XCTAssertEqual(config.agentRoles.builder, ["builder", "macs-builder"])
    }

    func testContract_StatusFixture() throws {
        let status = try FixtureLoader.load(StatusPayload.self, from: "status.v1.json")

        XCTAssertEqual(status.enabled, false)
        XCTAssertEqual(status.configExists, true)
        XCTAssertEqual(status.lastOkTs, 1709500000)
        XCTAssertEqual(status.lastRepairTs, 1709510000)
        XCTAssertEqual(status.lastAiTs, 1709520000)
        XCTAssertEqual(status.aiAttemptsDay, "2026-03-09")
        XCTAssertEqual(status.aiAttemptsCount, 2)
    }

    func testContract_CheckFixture() throws {
        let check = try FixtureLoader.load(CheckPayload.self, from: "check.v1.json")

        XCTAssertEqual(check.healthy, false)
        XCTAssertEqual(check.probeHealthy, false)
        XCTAssertEqual(check.reason, "gateway unhealthy")
        XCTAssertEqual(check.health.exitCode, 1)
        XCTAssertEqual(check.status.exitCode, 0)
        XCTAssertEqual(check.logs?.argv, ["openclaw", "logs", "--limit", "200", "--plain"])
        XCTAssertEqual(check.anomalyGuard?.triggered, true)
        XCTAssertEqual(check.loopGuard?.signals?.cycleTrigger, true)
    }

    func testContract_RepairFixture() throws {
        let result = try FixtureLoader.load(RepairResult.self, from: "repair.v1.json")

        XCTAssertEqual(result.attempted, true)
        XCTAssertEqual(result.fixed, true)
        XCTAssertEqual(result.usedAi, true)
        XCTAssertEqual(result.details.attemptDir, "/tmp/fix-my-claw/attempts/attempt-001")
        XCTAssertEqual(result.details.aiDecision?.decision, "yes")
        XCTAssertEqual(result.details.aiStage, "config")
        XCTAssertEqual(result.details.officialBreakReason, "still_unhealthy")
        XCTAssertEqual(result.details.notifyFinal?.messageText, "fix-my-claw: AI config repair completed")
    }

    func testContract_ServiceStatusFixture() throws {
        let status = try FixtureLoader.load(ServiceStatus.self, from: "service.status.v1.json")

        XCTAssertEqual(status.installed, true)
        XCTAssertEqual(status.running, true)
        XCTAssertEqual(status.label, "com.fix-my-claw.monitor")
    }

    func testContract_AllFixturesHaveValidAPIVersion() throws {
        let fixtures = [
            "config.show.v1.json",
            "status.v1.json",
            "check.v1.json",
            "repair.v1.json",
            "service.status.v1.json",
        ]

        for fixtureName in fixtures {
            let data = try FixtureLoader.loadData(name: fixtureName)
            XCTAssertNoThrow(try validateTopLevelAPIVersion(in: data), "Failed for \(fixtureName)")
        }
    }

    // MARK: - Edge Case Tests (inline JSON)

    func testAppConfigDecodesWithMissingSectionsUsingDefaults() throws {
        let payload = """
        {
          "api_version": "1.0"
        }
        """

        let config = AppConfig(dto: try decode(AppConfigDTO.self, from: payload))

        XCTAssertEqual(config.monitor.intervalSeconds, 60)
        XCTAssertEqual(config.repair.enabled, true)
        XCTAssertEqual(config.openclaw.command, "openclaw")
        XCTAssertEqual(config.notify.level, "all")
        XCTAssertEqual(config.notify.requiredMentionId, "")
        XCTAssertEqual(config.notify.maxInvalidReplies, 3)
        XCTAssertEqual(config.ai.argsCode, [
            "exec",
            "-s", "danger-full-access",
            "-c", "approval_policy=\"never\"",
            "--skip-git-repo-check",
            "-C", "$workspace_dir",
        ])
        XCTAssertEqual(config.agentRoles.builder, ["builder", "macs-builder"])
    }

    func testRepairResultDecodesWhenAiDecisionStringIsMissing() throws {
        let payload = """
        {
          "api_version": "1.0",
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

    func testTopLevelAPIVersionValidationAllowsSupportedVersion() throws {
        let payload = """
        {
          "api_version": "1.2",
          "enabled": true
        }
        """

        XCTAssertNoThrow(try validateTopLevelAPIVersion(in: Data(payload.utf8)))
    }

    func testTopLevelAPIVersionValidationAllowsMissingVersionForBackwardCompatibility() throws {
        let payload = """
        {
          "enabled": true
        }
        """

        XCTAssertNoThrow(try validateTopLevelAPIVersion(in: Data(payload.utf8)))
    }

    func testTopLevelAPIVersionValidationRejectsUnsupportedMajorVersion() throws {
        let payload = """
        {
          "api_version": "2.0",
          "enabled": true
        }
        """

        XCTAssertThrowsError(try validateTopLevelAPIVersion(in: Data(payload.utf8))) { error in
            guard case CLIError.unsupportedAPIVersion(let version) = error else {
                return XCTFail("Expected unsupportedAPIVersion, got \(error)")
            }
            XCTAssertEqual(version, "2.0")
        }
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
