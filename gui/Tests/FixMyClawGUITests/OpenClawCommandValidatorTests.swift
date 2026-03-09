import XCTest
@testable import FixMyClawGUI

final class OpenClawCommandValidatorTests: XCTestCase {
    private final class RestrictedExecutableFileManager: FileManager {
        private let executablePaths: Set<String>

        init(executablePaths: Set<String>) {
            self.executablePaths = executablePaths
            super.init()
        }

        override func isExecutableFile(atPath path: String) -> Bool {
            executablePaths.contains(path)
        }
    }

    func testBareCommandRequiresSetupEvenWhenResolvableFromPATH() throws {
        try withTemporaryExecutable(named: "openclaw") { executablePath, directory in
            let assessment = OpenClawCommandValidator.assess(
                "openclaw",
                environment: ["PATH": directory.path]
            )

            guard case .requiresSetup(let message) = assessment else {
                return XCTFail("Expected bare command to require setup")
            }
            XCTAssertTrue(message.contains(executablePath.path))
        }
    }

    func testAbsoluteExecutablePathIsAccepted() throws {
        try withTemporaryExecutable(named: "openclaw") { executablePath, _ in
            let assessment = OpenClawCommandValidator.assess(executablePath.path)

            XCTAssertEqual(assessment, .valid(normalizedPath: executablePath.path))
        }
    }

    func testNodeShebangExecutableIsAcceptedViaLauncherPlan() throws {
        let tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)

        let executableURL = tempDirectory.appendingPathComponent("openclaw", isDirectory: false)
        let nodeURL = tempDirectory.appendingPathComponent("node", isDirectory: false)

        XCTAssertTrue(FileManager.default.createFile(
            atPath: executableURL.path,
            contents: Data("#!/usr/bin/env node\nconsole.log('ok')\n".utf8)
        ))
        XCTAssertTrue(FileManager.default.createFile(
            atPath: nodeURL.path,
            contents: Data("#!/bin/sh\nexit 0\n".utf8)
        ))

        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executableURL.path)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: nodeURL.path)

        defer {
            try? FileManager.default.removeItem(at: tempDirectory)
        }

        let assessment = OpenClawCommandValidator.assess(executableURL.path, environment: [:])

        XCTAssertEqual(
            assessment,
            .validNodeScript(normalizedPath: executableURL.path, nodePath: nodeURL.path)
        )
    }

    func testNodeShebangExecutableRequiresManualNodePathWhenNodeIsMissing() throws {
        let tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)

        let executableURL = tempDirectory.appendingPathComponent("openclaw", isDirectory: false)
        XCTAssertTrue(FileManager.default.createFile(
            atPath: executableURL.path,
            contents: Data("#!/usr/bin/env node\nconsole.log('ok')\n".utf8)
        ))
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executableURL.path)

        defer {
            try? FileManager.default.removeItem(at: tempDirectory)
        }

        let assessment = OpenClawCommandValidator.assess(
            executableURL.path,
            environment: [:],
            fileManager: RestrictedExecutableFileManager(executablePaths: [executableURL.path])
        )

        guard case .requiresNodePath(let scriptPath, let message) = assessment else {
            return XCTFail("Expected node-backed command to request manual node path")
        }
        XCTAssertEqual(scriptPath, executableURL.path)
        XCTAssertTrue(message.contains("Node"))
    }

    func testRelativePathRequiresSetup() {
        let assessment = OpenClawCommandValidator.assess("./openclaw")

        guard case .requiresSetup(let message) = assessment else {
            return XCTFail("Expected relative path to require setup")
        }
        XCTAssertTrue(message.contains("相对路径"))
    }

    private func withTemporaryExecutable(
        named name: String,
        test: (URL, URL) throws -> Void
    ) throws {
        let tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)

        let executableURL = tempDirectory.appendingPathComponent(name, isDirectory: false)
        let created = FileManager.default.createFile(
            atPath: executableURL.path,
            contents: Data("#!/bin/sh\nexit 0\n".utf8)
        )
        XCTAssertTrue(created)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executableURL.path)

        defer {
            try? FileManager.default.removeItem(at: tempDirectory)
        }

        try test(executableURL, tempDirectory)
    }
}
