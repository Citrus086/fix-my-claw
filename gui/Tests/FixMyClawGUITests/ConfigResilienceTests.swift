import XCTest
@testable import FixMyClawGUI

final class ConfigResilienceTests: XCTestCase {
    private let decoder = JSONDecoder()

    private func decode<T: Decodable>(_ type: T.Type, from json: String) throws -> T {
        try decoder.decode(type, from: Data(json.utf8))
    }

    func testAppConfigDecodesPartialSectionsUsingFieldDefaults() throws {
        let payload = """
        {
          "monitor": {
            "state_dir": "/tmp/fix-my-claw-state"
          },
          "openclaw": {
            "command": "openclaw-dev"
          },
          "repair": {
            "enabled": false
          },
          "anomaly_guard": {
            "enabled": false
          },
          "notify": {
            "channel": "slack"
          },
          "ai": {
            "enabled": true
          },
          "agent_roles": {
            "builder": ["custom-builder"]
          }
        }
        """

        let config = try decode(AppConfig.self, from: payload)

        XCTAssertEqual(config.monitor.stateDir, "/tmp/fix-my-claw-state")
        XCTAssertEqual(config.monitor.intervalSeconds, 60)
        XCTAssertEqual(config.openclaw.command, "openclaw-dev")
        XCTAssertEqual(config.openclaw.logsArgs, ["logs", "--limit", "200", "--plain"])
        XCTAssertEqual(config.repair.enabled, false)
        XCTAssertEqual(config.repair.pauseWaitSeconds, 20)
        XCTAssertEqual(config.anomalyGuard.enabled, false)
        XCTAssertEqual(config.anomalyGuard.similarityThreshold, 0.82)
        XCTAssertEqual(config.notify.channel, "slack")
        XCTAssertEqual(config.notify.aiApproveKeywords, ["yes", "是"])
        XCTAssertEqual(config.ai.enabled, true)
        XCTAssertEqual(config.ai.argsCode, [
            "exec",
            "-s", "danger-full-access",
            "-c", "approval_policy=\"never\"",
            "--skip-git-repo-check",
            "-C", "$workspace_dir",
        ])
        XCTAssertEqual(config.agentRoles.builder, ["custom-builder"])
        XCTAssertEqual(config.agentRoles.orchestrator, ["orchestrator", "macs-orchestrator"])
    }

    func testRepairResultIdentityKeyRedactsAttemptDirectoryPath() throws {
        let result = try decode(RepairResult.self, from: repairResultJSON(attemptDir: "/Users/example/private/run-001"))
        let samePath = try decode(RepairResult.self, from: repairResultJSON(attemptDir: "/Users/example/private/run-001"))
        let differentPath = try decode(RepairResult.self, from: repairResultJSON(attemptDir: "/tmp/elsewhere/run-001"))

        XCTAssertTrue(result.identityKey.hasPrefix("attempt:run-001#"))
        XCTAssertFalse(result.identityKey.contains("/Users/example/private"))
        XCTAssertEqual(result.identityKey, samePath.identityKey)
        XCTAssertNotEqual(result.identityKey, differentPath.identityKey)
    }

    func testMergePayloadPreservesUnknownFieldsWhenSavingSettings() throws {
        var config = AppConfig()
        config.monitor.intervalSeconds = 15
        config.notify.level = "critical"

        let merged = try ConfigManager.mergePayloadPreservingUnknownFields(
            basePayload: [
                "monitor": [
                    "interval_seconds": 60,
                    "probe_timeout_seconds": 30,
                    "unknown_monitor_flag": "keep-me",
                ],
                "notify": [
                    "level": "all",
                    "custom_template": "keep-notify",
                ],
                "unknown_root": [
                    "nested": true,
                ],
            ],
            modelConfig: config
        )

        let monitor = try XCTUnwrap(merged["monitor"] as? [String: Any])
        let notify = try XCTUnwrap(merged["notify"] as? [String: Any])
        let unknownRoot = try XCTUnwrap(merged["unknown_root"] as? [String: Any])

        XCTAssertEqual(monitor["interval_seconds"] as? Int, 15)
        XCTAssertEqual(monitor["unknown_monitor_flag"] as? String, "keep-me")
        XCTAssertEqual(notify["level"] as? String, "critical")
        XCTAssertEqual(notify["custom_template"] as? String, "keep-notify")
        XCTAssertEqual(unknownRoot["nested"] as? Bool, true)
    }

    private func repairResultJSON(attemptDir: String) -> String {
        """
        {
          "attempted": true,
          "fixed": false,
          "used_ai": false,
          "details": {
            "attempt_dir": "\(attemptDir)"
          }
        }
        """
    }
}
