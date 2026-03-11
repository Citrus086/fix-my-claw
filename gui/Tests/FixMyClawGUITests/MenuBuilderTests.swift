import AppKit
import XCTest
@testable import FixMyClawGUI

@MainActor
final class MenuBuilderTests: XCTestCase {
    func testBuildMenuShowsServiceStatusWithoutManualServiceControlsWhenRunning() {
        let menu = buildMenu(
            serviceStatus: ServiceStatus(
                installed: true,
                running: true,
                label: "com.fix-my-claw.monitor",
                plistPath: "/Users/example/Library/LaunchAgents/com.fix-my-claw.monitor.plist",
                domain: "gui/501"
            )
        )

        let titles = menu.items.map(\.title)
        XCTAssertTrue(titles.contains("后台服务: 运行中"))
        XCTAssertFalse(titles.contains("⏹️ 停止后台服务"))
        XCTAssertFalse(titles.contains("▶️ 启动后台服务"))
        XCTAssertFalse(titles.contains("🗑️ 卸载后台服务"))
        XCTAssertFalse(titles.contains("📦 安装后台服务"))
    }

    func testBuildMenuShowsMissingServiceStatusWithoutInstallControl() {
        let menu = buildMenu(
            serviceStatus: ServiceStatus(
                installed: false,
                running: false,
                label: "com.fix-my-claw.monitor",
                plistPath: "/Users/example/Library/LaunchAgents/com.fix-my-claw.monitor.plist",
                domain: "gui/501"
            )
        )

        let titles = menu.items.map(\.title)
        XCTAssertTrue(titles.contains("后台服务: 未安装"))
        XCTAssertFalse(titles.contains("⏹️ 停止后台服务"))
        XCTAssertFalse(titles.contains("▶️ 启动后台服务"))
        XCTAssertFalse(titles.contains("🗑️ 卸载后台服务"))
        XCTAssertFalse(titles.contains("📦 安装后台服务"))
    }

    func testQuitMenuItemTargetsControllerQuitAction() {
        let menu = buildMenu(serviceStatus: nil)

        guard let quitItem = menu.items.first(where: { $0.title == "退出" }) else {
            return XCTFail("Missing quit menu item")
        }

        XCTAssertEqual(quitItem.action, #selector(MenuBarController.quit))
    }

    func testBuildMenuShowsForceRepairActionWhenHealthy() {
        let menu = buildMenu(serviceStatus: nil, effectiveState: .healthy)

        guard let forceRepairItem = menu.items.first(where: { $0.title == "🛠️ 强制修复一次" }) else {
            return XCTFail("Missing force repair menu item")
        }

        XCTAssertEqual(forceRepairItem.action, #selector(MenuBarController.performForceRepair))
        XCTAssertTrue(forceRepairItem.isEnabled)
    }

    func testBuildMenuDisablesForceRepairWhenRepairAlreadyRunning() {
        let menu = buildMenu(
            serviceStatus: nil,
            effectiveState: .repairing(stage: .starting),
            isLoading: true
        )

        guard let forceRepairItem = menu.items.first(where: { $0.title == "🛠️ 强制修复一次" }) else {
            return XCTFail("Missing force repair menu item")
        }

        XCTAssertFalse(forceRepairItem.isEnabled)
    }

    func testBuildMenuShowsDisabledForceRepairWhenSetupIsRequired() {
        let menu = buildMenu(serviceStatus: nil, effectiveState: .setupRequired)

        guard let forceRepairItem = menu.items.first(where: { $0.title == "🛠️ 强制修复一次" }) else {
            return XCTFail("Missing force repair menu item")
        }

        XCTAssertFalse(forceRepairItem.isEnabled)
    }

    private func buildMenu(
        serviceStatus: ServiceStatus?,
        effectiveState: AppState = .healthy,
        isLoading: Bool = false
    ) -> NSMenu {
        MenuBuilder.buildMenu(
            state: .init(
                effectiveState: effectiveState,
                statusTitle: "🟢 健康",
                lastCheckText: nil,
                serviceStatus: serviceStatus,
                currentRepairStage: nil,
                lastRepairPresentation: nil,
                hasPendingAiRequest: false,
                lastCheckResult: nil,
                isLoading: isLoading
            ),
            target: MenuBarController()
        )
    }
}
