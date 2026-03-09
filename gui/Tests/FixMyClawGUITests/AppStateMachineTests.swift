import XCTest
@testable import FixMyClawGUI

/// AppStateMachineTests 验证权威状态机的状态转换逻辑
@MainActor
final class AppStateMachineTests: XCTestCase {
    private func healthyResult() -> CheckPayload {
        CheckPayload(
            healthy: true,
            probeHealthy: true,
            reason: nil,
            health: ProbeResult(name: "health", ok: true, exitCode: 0, durationMs: 100, argv: [], stdout: "", stderr: ""),
            status: ProbeResult(name: "status", ok: true, exitCode: 0, durationMs: 100, argv: [], stdout: "", stderr: ""),
            logs: nil,
            anomalyGuard: nil,
            loopGuard: nil
        )
    }
    
    private func unhealthyResult(reason: String = "test failure") -> CheckPayload {
        CheckPayload(
            healthy: false,
            probeHealthy: false,
            reason: reason,
            health: ProbeResult(name: "health", ok: false, exitCode: 1, durationMs: 100, argv: [], stdout: "", stderr: ""),
            status: ProbeResult(name: "status", ok: false, exitCode: 1, durationMs: 100, argv: [], stdout: "", stderr: ""),
            logs: nil,
            anomalyGuard: nil,
            loopGuard: nil
        )
    }
    
    private func statusPayload(enabled: Bool, configExists: Bool = true) -> StatusPayload {
        StatusPayload(
            enabled: enabled,
            configPath: "/tmp/config.toml",
            configExists: configExists,
            statePath: "/tmp/state.json",
            lastOkTs: nil,
            lastRepairTs: nil,
            lastAiTs: nil,
            aiAttemptsDay: nil,
            aiAttemptsCount: 0
        )
    }
    
    private func driveStoreToHealthy(_ store: MenuBarStore, monitoringEnabled: Bool = true) {
        store.send(.configLoaded(exists: true))
        store.send(.healthCheckCompleted(result: healthyResult(), monitoringEnabled: monitoringEnabled))
    }
    
    private func driveStoreToUnhealthy(
        _ store: MenuBarStore,
        monitoringEnabled: Bool = true,
        reason: String = "test"
    ) {
        store.send(.configLoaded(exists: true))
        store.send(.healthCheckCompleted(result: unhealthyResult(reason: reason), monitoringEnabled: monitoringEnabled))
    }
    
    // MARK: - 初始状态测试
    
    func testInitialStateIsUninitialized() {
        let store = MenuBarStore()
        XCTAssertEqual(store.state, .uninitialized)
    }
    
    func testConfigLoadedEventTransitionsToNoConfigWhenMissing() {
        let store = MenuBarStore()
        store.send(.configLoaded(exists: false))
        XCTAssertEqual(store.state, .noConfig)
    }
    
    func testConfigLoadedEventTransitionsToUnknownWhenExists() {
        let store = MenuBarStore()
        store.send(.configLoaded(exists: true))
        XCTAssertEqual(store.state, .unknown)
    }

    func testOpenClawSetupRequiredBlocksHealthChecksUntilConfigured() {
        let store = MenuBarStore()
        store.send(.openClawSetupRequired)
        XCTAssertEqual(store.state, .setupRequired)

        store.send(.healthCheckStarted)
        XCTAssertEqual(store.state, .setupRequired)

        store.send(.openClawSetupSatisfied)
        XCTAssertEqual(store.state, .unknown)
    }
    
    // MARK: - 健康检查状态转换测试
    
    func testHealthCheckStartedTransitionsToChecking() {
        let store = MenuBarStore()
        store.send(.configLoaded(exists: true))
        store.send(.healthCheckStarted)
        XCTAssertEqual(store.state, .checking)
    }
    
    func testHealthCheckCompletedTransitionsToHealthyWhenEnabledAndHealthy() {
        let store = MenuBarStore()
        store.send(.configLoaded(exists: true))

        store.send(.healthCheckCompleted(result: healthyResult(), monitoringEnabled: false))
        XCTAssertEqual(store.state, .pausedHealthy)

        store.send(.healthCheckCompleted(result: healthyResult(), monitoringEnabled: true))
        XCTAssertEqual(store.state, .healthy)
    }
    
    func testHealthCheckCompletedTransitionsToUnhealthyWhenEnabledAndUnhealthy() {
        let store = MenuBarStore()
        store.send(.configLoaded(exists: true))

        store.send(.healthCheckCompleted(result: unhealthyResult(), monitoringEnabled: false))
        XCTAssertEqual(store.state, .pausedUnhealthy(reason: "test failure"))

        store.send(.healthCheckCompleted(result: unhealthyResult(), monitoringEnabled: true))
        XCTAssertEqual(store.state, .unhealthy(reason: "test failure"))
    }
    
    // MARK: - 监控切换测试
    
    func testMonitoringToggledTransitionsToPausedHealthy() {
        let store = MenuBarStore()
        driveStoreToHealthy(store)
        
        store.send(.monitoringToggled(enabled: false))
        XCTAssertEqual(store.state, .pausedHealthy)
    }
    
    func testMonitoringToggledTransitionsToHealthyFromPaused() {
        let store = MenuBarStore()
        driveStoreToHealthy(store, monitoringEnabled: false)
        
        store.send(.monitoringToggled(enabled: true))
        XCTAssertEqual(store.state, .healthy)
    }
    
    func testStatusPayloadTransitionsHealthyStateToPausedWhenMonitoringDisabled() {
        let store = MenuBarStore()
        driveStoreToHealthy(store)
        
        store.updateStatusPayload(statusPayload(enabled: false))
        
        XCTAssertEqual(store.state, .pausedHealthy)
    }
    
    // MARK: - 修复状态测试
    
    func testRepairStartedTransitionsToRepairing() {
        let store = MenuBarStore()
        driveStoreToUnhealthy(store)
        
        store.send(.repairStarted)
        
        if case .repairing(let stage) = store.state {
            XCTAssertEqual(stage, .starting)
        } else {
            XCTFail("Expected repairing state")
        }
    }
    
    func testRepairProgressedUpdatesStage() {
        let store = MenuBarStore()
        store.send(.repairStarted)
        store.send(.repairProgressed(stage: "official"))
        
        if case .repairing(let stage) = store.state {
            XCTAssertEqual(stage, .official)
        } else {
            XCTFail("Expected repairing state")
        }
    }
    
    func testRepairCompletedTransitionsToUnknown() {
        let store = MenuBarStore()
        store.send(.repairStarted)
        store.send(.repairCompleted)
        
        XCTAssertEqual(store.state, .unknown)
    }
    
    // MARK: - 审批状态测试
    
    func testApprovalRequestedTransitionsToAwaitingApproval() {
        let store = MenuBarStore()
        driveStoreToUnhealthy(store)
        
        let request = ApprovalRequest(requestId: "test-123", prompt: "Test approval request")
        store.send(.approvalRequested(request: request))
        
        if case .awaitingApproval(let req) = store.state {
            XCTAssertEqual(req.requestId, "test-123")
            XCTAssertEqual(req.prompt, "Test approval request")
        } else {
            XCTFail("Expected awaitingApproval state")
        }
    }
    
    func testApprovalRespondedTransitionsToUnknown() {
        let store = MenuBarStore()
        let request = ApprovalRequest(requestId: "test-123", prompt: "Test")
        store.send(.approvalRequested(request: request))
        
        store.send(.approvalResponded)
        XCTAssertEqual(store.state, .unknown)
    }
    
    func testApprovalExpiredTransitionsToUnknown() {
        let store = MenuBarStore()
        let request = ApprovalRequest(requestId: "test-123", prompt: "Test")
        store.send(.approvalRequested(request: request))
        
        store.send(.approvalExpired)
        XCTAssertEqual(store.state, .unknown)
    }
    
    // MARK: - 状态优先级测试
    
    func testRepairingTakesPriorityOverHealthCheck() {
        let store = MenuBarStore()
        store.send(.repairStarted)
        
        // 尝试开始健康检查（应该保持修复状态）
        store.send(.healthCheckStarted)
        
        if case .repairing = store.state {
            // 正确：保持修复状态
        } else {
            XCTFail("Expected repairing state to take priority")
        }
    }
    
    func testHealthCheckCompletedDoesNotOverrideRepairingState() {
        let store = MenuBarStore()
        store.send(.repairStarted)
        
        store.send(.healthCheckCompleted(result: healthyResult(), monitoringEnabled: true))
        
        if case .repairing = store.state {
        } else {
            XCTFail("Expected repairing state to remain authoritative")
        }
    }
    
    func testAwaitingApprovalTakesPriorityOverHealthCheck() {
        let store = MenuBarStore()
        let request = ApprovalRequest(requestId: "test-123", prompt: "Test")
        store.send(.approvalRequested(request: request))
        
        // 尝试开始健康检查（应该保持审批状态）
        store.send(.healthCheckStarted)
        
        if case .awaitingApproval = store.state {
            // 正确：保持审批状态
        } else {
            XCTFail("Expected awaitingApproval state to take priority")
        }
    }
    
    func testRepairProgressDoesNotOverrideAwaitingApprovalState() {
        let store = MenuBarStore()
        let request = ApprovalRequest(requestId: "test-123", prompt: "Test")
        store.send(.approvalRequested(request: request))
        
        store.send(.repairProgressed(stage: "official"))
        
        if case .awaitingApproval(let pending) = store.state {
            XCTAssertEqual(pending.requestId, request.requestId)
        } else {
            XCTFail("Expected awaitingApproval state to remain authoritative")
        }
    }
    
    // MARK: - 状态属性测试
    
    func testHealthyStateProperties() {
        let state = AppState.healthy
        XCTAssertTrue(state.isHealthy)
        XCTAssertTrue(state.isMonitoringEnabled)
        XCTAssertFalse(state.isRepairing)
        XCTAssertFalse(state.isAwaitingApproval)
        XCTAssertFalse(state.canRepair)
        XCTAssertEqual(state.icon, "🟢")
    }
    
    func testUnhealthyStateProperties() {
        let state = AppState.unhealthy(reason: "test")
        XCTAssertFalse(state.isHealthy)
        XCTAssertTrue(state.isMonitoringEnabled)
        XCTAssertFalse(state.isRepairing)
        XCTAssertFalse(state.isAwaitingApproval)
        XCTAssertTrue(state.canRepair)
        XCTAssertEqual(state.icon, "🔴")
    }
    
    func testRepairingStateProperties() {
        let state = AppState.repairing(stage: .starting)
        XCTAssertFalse(state.isHealthy)
        XCTAssertFalse(state.isMonitoringEnabled)
        XCTAssertTrue(state.isRepairing)
        XCTAssertFalse(state.isAwaitingApproval)
        XCTAssertFalse(state.canRepair)
        XCTAssertEqual(state.icon, "🔧")
    }
    
    func testAwaitingApprovalStateProperties() {
        let request = ApprovalRequest(requestId: "test", prompt: "Test")
        let state = AppState.awaitingApproval(request: request)
        XCTAssertFalse(state.isHealthy)
        XCTAssertFalse(state.isMonitoringEnabled)
        XCTAssertFalse(state.isRepairing)
        XCTAssertTrue(state.isAwaitingApproval)
        XCTAssertFalse(state.canRepair)
        XCTAssertEqual(state.icon, "❓")
    }
    
    // MARK: - 状态一致性测试
    
    func testStateIconConsistency() {
        XCTAssertEqual(AppState.uninitialized.icon, "⚪")
        XCTAssertEqual(AppState.unknown.icon, "⚪")
        XCTAssertEqual(AppState.checking.icon, "🟡")
        XCTAssertEqual(AppState.healthy.icon, "🟢")
        XCTAssertEqual(AppState.unhealthy(reason: nil).icon, "🔴")
        XCTAssertEqual(AppState.pausedHealthy.icon, "🟢")
        XCTAssertEqual(AppState.pausedUnhealthy(reason: nil).icon, "🔴")
        XCTAssertEqual(AppState.repairing(stage: .starting).icon, "🔧")
        XCTAssertEqual(AppState.awaitingApproval(request: ApprovalRequest(requestId: "", prompt: "")).icon, "❓")
        XCTAssertEqual(AppState.noConfig.icon, "⚙️")
    }
}
