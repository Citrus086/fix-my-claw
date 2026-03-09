import AppKit
import Foundation
import SwiftUI

private struct RawConfigSnapshot {
    let payload: [String: Any]
    let config: AppConfig
}

@MainActor
class ConfigManager: ObservableObject {
    static let shared = ConfigManager()
    nonisolated static let configPathOverrideEnvironmentKey = "FIX_MY_CLAW_GUI_CONFIG_PATH"

    let defaultConfigPath: String
    let defaultStateDirectoryURL: URL
    let cli = CLIWrapper()

    @Published var config: AppConfig?
    @Published var isLoading = false
    @Published var lastError: String?
    @Published var saveError: String?

    private var rawConfigPayload: [String: Any] = [:]

    init() {
        defaultConfigPath = Self.resolveDefaultConfigPath()
        defaultStateDirectoryURL = URL(fileURLWithPath: defaultConfigPath).deletingLastPathComponent()
    }

    var configExists: Bool {
        FileManager.default.fileExists(atPath: defaultConfigPath)
    }

    func loadConfig() {
        Task {
            isLoading = true
            defer { isLoading = false }

            do {
                let snapshot = try await fetchConfigSnapshot()
                rawConfigPayload = snapshot.payload
                config = snapshot.config
                lastError = nil
                saveError = nil
            } catch {
                lastError = "加载配置失败: \(error.localizedDescription)"
            }
        }
    }

    func saveConfig() {
        guard let config else { return }
        Task {
            isLoading = true
            defer { isLoading = false }

            do {
                let mergedPayload = try mergedPayload(with: config)
                let jsonData = try Self.serializeJSON(mergedPayload)
                _ = try await runConfigCommand(args: configCommandArgs(subcommand: ["config", "set", "--json"]), input: jsonData)

                let snapshot = try await fetchConfigSnapshot()
                rawConfigPayload = snapshot.payload
                self.config = snapshot.config
                saveError = nil
                lastError = nil
            } catch {
                saveError = "保存配置失败: \(error.localizedDescription)"
            }
        }
    }

    func openConfigFile() {
        let path = (defaultConfigPath as NSString).expandingTildeInPath
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }

    func resetToDefault() {
        Task {
            isLoading = true
            defer { isLoading = false }

            do {
                _ = try await cli.initializeConfig(at: defaultConfigPath, force: true)
                lastError = nil
                saveError = nil
                let snapshot = try await fetchConfigSnapshot()
                rawConfigPayload = snapshot.payload
                config = snapshot.config
            } catch {
                lastError = "重置配置失败: \(error.localizedDescription)"
            }
        }
    }

    private func fetchConfigSnapshot() async throws -> RawConfigSnapshot {
        let stdout = try await runConfigCommand(args: configCommandArgs(subcommand: ["config", "show", "--json"]))
        let payload = try Self.decodeJSONObject(from: stdout)
        let decoded = try JSONDecoder().decode(AppConfig.self, from: stdout)
        return RawConfigSnapshot(payload: payload, config: decoded)
    }

    private func mergedPayload(with config: AppConfig) throws -> [String: Any] {
        let modelData = try JSONEncoder().encode(config)
        let modelPayload = try Self.decodeJSONObject(from: modelData)
        return Self.deepMerge(base: rawConfigPayload, overrides: modelPayload)
    }

    private func configCommandArgs(subcommand: [String]) -> [String] {
        subcommand + ["--config", defaultConfigPath]
    }

    private func runConfigCommand(args: [String], input: Data? = nil) async throws -> Data {
        let binaryPath = cli.binaryPath
        return try await Task.detached(priority: .userInitiated) {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = [binaryPath] + args

            let stdoutPipe = Pipe()
            let stderrPipe = Pipe()
            process.standardOutput = stdoutPipe
            process.standardError = stderrPipe

            let stdinPipe = Pipe()
            if input != nil {
                process.standardInput = stdinPipe
            }

            do {
                try process.run()
            } catch {
                throw CLIError.commandNotFound(path: binaryPath)
            }

            if let input {
                stdinPipe.fileHandleForWriting.write(input)
                stdinPipe.fileHandleForWriting.closeFile()
            }

            process.waitUntilExit()

            let stdout = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
            let stderr = String(
                data: stderrPipe.fileHandleForReading.readDataToEndOfFile(),
                encoding: .utf8
            )?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""

            guard process.terminationStatus == 0 else {
                throw CLIError.commandFailed(
                    exitCode: process.terminationStatus,
                    stderr: stderr.isEmpty ? "未知错误" : stderr
                )
            }

            return stdout
        }.value
    }

    private static func decodeJSONObject(from data: Data) throws -> [String: Any] {
        let object = try JSONSerialization.jsonObject(with: data)
        guard let payload = object as? [String: Any] else {
            throw CLIError.decodingFailed(NSError(
                domain: "FixMyClawGUI.ConfigManager",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "配置 JSON 顶层不是对象"]
            ))
        }
        return payload
    }

    private static func serializeJSON(_ payload: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
    }

    private static func deepMerge(base: [String: Any], overrides: [String: Any]) -> [String: Any] {
        var merged = base
        for (key, overrideValue) in overrides {
            if let overrideDict = overrideValue as? [String: Any],
               let baseDict = merged[key] as? [String: Any] {
                merged[key] = deepMerge(base: baseDict, overrides: overrideDict)
            } else {
                merged[key] = overrideValue
            }
        }
        return merged
    }

    nonisolated static func resolveDefaultConfigPath(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        homeDirectoryPath: String = FileManager.default.homeDirectoryForCurrentUser.path
    ) -> String {
        if let override = environment[configPathOverrideEnvironmentKey]?
            .trimmingCharacters(in: .whitespacesAndNewlines),
           !override.isEmpty {
            return normalizePath(override)
        }

        let homePath = normalizePath(homeDirectoryPath)
        return URL(fileURLWithPath: homePath, isDirectory: true)
            .appendingPathComponent(".fix-my-claw", isDirectory: true)
            .appendingPathComponent("config.toml", isDirectory: false)
            .path
    }

    nonisolated private static func normalizePath(_ path: String) -> String {
        URL(fileURLWithPath: (path as NSString).expandingTildeInPath).standardizedFileURL.path
    }
}
