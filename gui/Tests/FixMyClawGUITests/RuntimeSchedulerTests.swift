import Foundation
import XCTest
@testable import FixMyClawGUI

final class RuntimeSchedulerTests: XCTestCase {
    @MainActor
    func testRefreshNowExecutesStatusAndHealthActions() async {
        let scheduler = RuntimeScheduler()
        defer { scheduler.stop() }

        let statusExpectation = expectation(description: "status action")
        let healthExpectation = expectation(description: "health action")

        scheduler.refreshNow(
            statusAction: {
                statusExpectation.fulfill()
                return true
            },
            healthAction: {
                healthExpectation.fulfill()
                return true
            }
        )

        await fulfillment(of: [statusExpectation, healthExpectation], timeout: 1.0)
    }

    @MainActor
    func testStateDirectoryObservationTriggersOnFileWrite() async throws {
        let scheduler = RuntimeScheduler()
        let fileChangeExpectation = expectation(description: "file change")
        fileChangeExpectation.assertForOverFulfill = false

        let directoryURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)

        defer {
            scheduler.stop()
            try? FileManager.default.removeItem(at: directoryURL)
        }

        scheduler.start(
            statusAction: { true },
            healthAction: { true },
            stateDirectoryURL: directoryURL,
            fileChangeHandler: {
                fileChangeExpectation.fulfill()
            }
        )

        try await Task.sleep(for: .milliseconds(200))
        try Data("{}".utf8).write(to: directoryURL.appendingPathComponent("repair_progress.json"))

        await fulfillment(of: [fileChangeExpectation], timeout: 2.0)
    }
}
