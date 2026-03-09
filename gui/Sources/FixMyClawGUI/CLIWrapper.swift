import Foundation

actor CLIWrapper {
    let binaryPath: String
    
    init(binaryPath: String? = nil) {
        self.binaryPath = Self.resolveBinaryPath(explicit: binaryPath)
    }
    
    // MARK: - 基础命令
    
    func getStatus(configPath: String? = nil) async throws -> StatusPayload {
        var args = ["status", "--json"]
        if let path = configPath {
            args += ["--config", path]
        }
        let output = try await run(args: args)
        return try decode(StatusPayload.self, from: output.stdout)
    }
    
    func check(configPath: String? = nil) async throws -> CheckPayload {
        var args = ["check", "--json"]
        if let path = configPath {
            args += ["--config", path]
        }
        let output = try await run(args: args, allowNonZeroExit: true)
        return try decode(CheckPayload.self, from: output.stdout)
    }
    
    func enableMonitoring(configPath: String? = nil) async throws -> StatusPayload {
        var args = ["start", "--json"]
        if let path = configPath {
            args += ["--config", path]
        }
        let output = try await run(args: args)
        return try decode(StatusPayload.self, from: output.stdout)
    }
    
    func disableMonitoring(configPath: String? = nil) async throws -> StatusPayload {
        var args = ["stop", "--json"]
        if let path = configPath {
            args += ["--config", path]
        }
        let output = try await run(args: args)
        return try decode(StatusPayload.self, from: output.stdout)
    }
    
    func initializeConfig(at path: String? = nil, force: Bool = false) async throws -> String {
        var args = ["init"]
        if let path = path {
            args += ["--config", path]
        }
        if force {
            args.append("--force")
        }
        let output = try await run(args: args)
        let text = String(data: output.stdout, encoding: .utf8) ?? ""
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - 配置管理

    func getConfig(configPath: String? = nil) async throws -> AppConfig {
        var args = ["config", "show", "--json"]
        if let path = configPath {
            args += ["--config", path]
        }
        let output = try await run(args: args)
        return try decode(AppConfig.self, from: output.stdout)
    }

    func setConfig(_ config: AppConfig, configPath: String? = nil) async throws {
        var args = ["config", "set", "--json"]
        if let path = configPath {
            args += ["--config", path]
        }

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let jsonData = try encoder.encode(config)
        try await runWithInput(args: args, input: jsonData, timeout: 60)
    }
    
    func repair(force: Bool = false, configPath: String? = nil) async throws -> RepairResult {
        var args = ["repair", "--json"]
        if force {
            args.append("--force")
        }
        if let path = configPath {
            args += ["--config", path]
        }
        let output = try await run(args: args, timeout: 600, allowNonZeroExit: true)
        return try decode(RepairResult.self, from: output.stdout)
    }

    // MARK: - 服务管理

    func getServiceStatus() async throws -> ServiceStatus {
        let output = try await run(args: ["service", "status", "--json"], allowNonZeroExit: true)
        return try decode(ServiceStatus.self, from: output.stdout)
    }

    func installService(configPath: String? = nil) async throws {
        var args = ["service", "install"]
        if let path = configPath {
            args += ["--config", path]
        }
        _ = try await run(args: args, timeout: 60)
    }

    func uninstallService() async throws {
        _ = try await run(args: ["service", "uninstall"], timeout: 30)
    }

    func startService() async throws {
        _ = try await run(args: ["service", "start"], timeout: 30)
    }

    func stopService() async throws {
        _ = try await run(args: ["service", "stop"], timeout: 30)
    }
    
    // MARK: - 路径辅助
    
    func getLogPath(configPath: String? = nil) async throws -> String {
        let config = try await getConfig(configPath: configPath)
        return config.monitor.logFile
    }
    
    func getAttemptsPath(configPath: String? = nil) async throws -> String {
        let config = try await getConfig(configPath: configPath)
        return (config.monitor.stateDir as NSString).appendingPathComponent("attempts")
    }
    
    // MARK: - 内部执行
    
    private func run(
        args: [String],
        timeout: TimeInterval = 60,
        allowNonZeroExit: Bool = false
    ) async throws -> CLIExecutionResult {
        try await runSystemCommand(
            executablePath: binaryPath,
            args: args,
            timeout: timeout,
            allowNonZeroExit: allowNonZeroExit
        )
    }

    private func runWithInput(
        args: [String],
        input: Data,
        timeout: TimeInterval = 60
    ) async throws {
        _ = try await runSystemCommand(
            executablePath: binaryPath,
            args: args,
            timeout: timeout,
            allowNonZeroExit: false,
            inputData: input
        )
    }

    private func runSystemCommand(
        executablePath: String,
        args: [String],
        timeout: TimeInterval = 60,
        allowNonZeroExit: Bool = false,
        inputData: Data? = nil
    ) async throws -> CLIExecutionResult {
        guard FileManager.default.isExecutableFile(atPath: executablePath) else {
            throw CLIError.commandNotFound(path: executablePath)
        }

        return try await withCheckedThrowingContinuation { continuation in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: executablePath)
            process.arguments = args
            
            let stdinPipe = Pipe()
            let stdoutPipe = Pipe()
            let stderrPipe = Pipe()
            process.standardInput = stdinPipe
            process.standardOutput = stdoutPipe
            process.standardError = stderrPipe
            let resumeGate = ContinuationGate()
            
            let timeoutTask = Task {
                try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
                if process.isRunning {
                    process.terminate()
                    resumeGate.resumeOnce {
                        continuation.resume(throwing: CLIError.timeout)
                    }
                }
            }
            
            process.terminationHandler = { process in
                timeoutTask.cancel()
                
                let stdoutData = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
                let stderrData = stderrPipe.fileHandleForReading.readDataToEndOfFile()
                let stderr = String(data: stderrData, encoding: .utf8) ?? "Unknown error"
                
                if process.terminationStatus == 0 || allowNonZeroExit {
                    let result = CLIExecutionResult(
                        stdout: stdoutData,
                        stderr: stderr,
                        exitCode: process.terminationStatus
                    )
                    resumeGate.resumeOnce {
                        continuation.resume(returning: result)
                    }
                } else {
                    resumeGate.resumeOnce {
                        continuation.resume(throwing: CLIError.commandFailed(
                            exitCode: process.terminationStatus,
                            stderr: stderr
                        ))
                    }
                }
            }
            
            do {
                try process.run()
                if let inputData {
                    stdinPipe.fileHandleForWriting.write(inputData)
                }
                try? stdinPipe.fileHandleForWriting.close()
            } catch {
                timeoutTask.cancel()
                resumeGate.resumeOnce {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        do {
            return try JSONDecoder().decode(type, from: data)
        } catch {
            throw CLIError.decodingFailed(error)
        }
    }

    private static func resolveBinaryPath(explicit: String?) -> String {
        if let explicit, !explicit.isEmpty {
            return explicit
        }

        let fileManager = FileManager.default

        // 优先查找 .app 包内的 CLI
        if let bundlePath = Bundle.main.path(forResource: "fix-my-claw", ofType: nil, inDirectory: "Contents/MacOS"),
           fileManager.isExecutableFile(atPath: bundlePath) {
            return bundlePath
        }

        let envPaths = (ProcessInfo.processInfo.environment["PATH"] ?? "")
            .split(separator: ":")
            .map(String.init)
        let candidates = envPaths.map { ($0 as NSString).appendingPathComponent("fix-my-claw") } + [
            "/opt/homebrew/bin/fix-my-claw",
            "/usr/local/bin/fix-my-claw",
            "/opt/anaconda3/bin/fix-my-claw",
            "\(FileManager.default.homeDirectoryForCurrentUser.path)/.local/bin/fix-my-claw",
        ]
        return candidates.first(where: { fileManager.isExecutableFile(atPath: $0) }) ?? "fix-my-claw"
    }
}

private struct CLIExecutionResult {
    let stdout: Data
    let stderr: String
    let exitCode: Int32
}

private final class ContinuationGate: @unchecked Sendable {
    private let lock = NSLock()
    private var resumed = false

    func resumeOnce(_ action: () -> Void) {
        lock.lock()
        defer { lock.unlock() }
        guard !resumed else { return }
        resumed = true
        action()
    }
}

// MARK: - Repair Result

struct RepairResult: Codable {
    let attempted: Bool
    let fixed: Bool
    let usedAi: Bool
    let details: RepairDetails
    
    enum CodingKeys: String, CodingKey {
        case attempted, fixed, details
        case usedAi = "used_ai"
    }
}

struct PersistedRepairResult: Codable {
    let timestamp: Double
    let result: RepairResult
}

struct RepairDetails: Codable {
    let attemptDir: String?
    let reason: String?
    let alreadyHealthy: Bool?
    let repairDisabled: Bool?
    let cooldown: Bool?
    let cooldownRemainingSeconds: Int?
    let pauseWaitSeconds: Int?
    let aiDecision: RepairAiDecision?
    let aiStage: String?
    let officialBreakReason: String?
    let backupBeforeAiError: String?
    let notifyFinal: RepairNotificationPayload?
    
    enum CodingKeys: String, CodingKey {
        case attemptDir = "attempt_dir"
        case reason
        case alreadyHealthy = "already_healthy"
        case repairDisabled = "repair_disabled"
        case cooldown
        case cooldownRemainingSeconds = "cooldown_remaining_seconds"
        case pauseWaitSeconds = "pause_wait_seconds"
        case aiDecision = "ai_decision"
        case aiStage = "ai_stage"
        case officialBreakReason = "official_break_reason"
        case backupBeforeAiError = "backup_before_ai_error"
        case notifyFinal = "notify_final"
    }
}

struct RepairAiDecision: Codable {
    let asked: Bool?
    let decision: String?  // 改为可选，增强 decode 韧性
    let source: String?
    let error: String?
    let invalidReplies: Int?

    enum CodingKeys: String, CodingKey {
        case asked
        case decision
        case source
        case error
        case invalidReplies = "invalid_replies"
    }
}

struct RepairNotificationPayload: Codable {
    let sent: Bool?
    let messageId: String?
    let exitCode: Int?
    let argv: [String]?
    let stderr: String?
    let stdout: String?

    enum CodingKeys: String, CodingKey {
        case sent
        case messageId = "message_id"
        case exitCode = "exit_code"
        case argv
        case stderr
        case stdout
    }

    var messageText: String? {
        guard let argv else { return nil }
        guard let messageFlagIndex = argv.firstIndex(of: "--message") else { return nil }
        let messageIndex = argv.index(after: messageFlagIndex)
        guard messageIndex < argv.endIndex else { return nil }
        return argv[messageIndex]
    }
}
