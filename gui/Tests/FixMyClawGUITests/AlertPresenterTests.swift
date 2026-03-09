import AppKit
import XCTest
@testable import FixMyClawGUI

@MainActor
final class AlertPresenterTests: XCTestCase {
    func testPresenterQueuesSecondAlertUntilFirstCompletes() {
        var presentedMessages: [String] = []
        var completions: [@MainActor (NSApplication.ModalResponse) -> Void] = []
        var completedAlerts: [String] = []

        let presenter = AlertPresenter(presentationHook: { request, completion in
            presentedMessages.append(request.messageText)
            completions.append(completion)
        })

        presenter.present(
            AlertRequest(
                windowTitle: "fix-my-claw",
                messageText: "first",
                informativeText: "first alert",
                style: .informational,
                buttonTitles: ["OK"]
            ) { response in
                if response == .alertFirstButtonReturn {
                    completedAlerts.append("first")
                }
            }
        )

        presenter.present(
            AlertRequest(
                windowTitle: "fix-my-claw",
                messageText: "second",
                informativeText: "second alert",
                style: .warning,
                buttonTitles: ["OK"]
            ) { response in
                if response == .alertSecondButtonReturn {
                    completedAlerts.append("second")
                }
            }
        )

        XCTAssertEqual(presentedMessages, ["first"])
        XCTAssertTrue(presenter.isPresentingAlert)
        XCTAssertEqual(presenter.queuedRequestCount, 1)
        XCTAssertEqual(completions.count, 1)

        completions.removeFirst()(.alertFirstButtonReturn)

        XCTAssertEqual(completedAlerts, ["first"])
        XCTAssertEqual(presentedMessages, ["first", "second"])
        XCTAssertTrue(presenter.isPresentingAlert)
        XCTAssertEqual(presenter.queuedRequestCount, 0)
        XCTAssertEqual(completions.count, 1)

        completions.removeFirst()(.alertSecondButtonReturn)

        XCTAssertEqual(completedAlerts, ["first", "second"])
        XCTAssertFalse(presenter.isPresentingAlert)
        XCTAssertEqual(presenter.queuedRequestCount, 0)
    }
}
