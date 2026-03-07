import AppKit
import Foundation
import SwiftUI

@MainActor
class ConfigManager: ObservableObject {
    static let shared = ConfigManager()

    let defaultConfigPath: String
    let cli = CLIWrapper()

    @Published var config: AppConfig?
    @Published var isLoading = false
    @Published var lastError: String?
    @Published var saveError: String?

    init() {
        defaultConfigPath = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".fix-my-claw/config.toml")
            .path
    }

    var configExists: Bool {
        FileManager.default.fileExists(atPath: defaultConfigPath)
    }

    func loadConfig() {
        Task {
            isLoading = true
            defer { isLoading = false }

            do {
                config = try await cli.getConfig(configPath: defaultConfigPath)
                lastError = nil
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
                try await cli.setConfig(config, configPath: defaultConfigPath)
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
                config = try await cli.getConfig(configPath: defaultConfigPath)
            } catch {
                lastError = "重置配置失败: \(error.localizedDescription)"
            }
        }
    }
}
