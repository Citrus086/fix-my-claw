import Foundation

enum OpenClawCommandAssessment: Equatable {
    case valid(normalizedPath: String)
    case validNodeScript(normalizedPath: String, nodePath: String)
    case requiresNodePath(scriptPath: String, message: String)
    case requiresSetup(message: String)
}

enum OpenClawCommandValidator {
    private static let commonNodePaths = [
        "/opt/homebrew/bin/node",
        "/usr/local/bin/node",
        "/opt/anaconda3/bin/node",
    ]

    static func assess(
        _ rawCommand: String,
        explicitNodePath: String? = nil,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default
    ) -> OpenClawCommandAssessment {
        let trimmed = rawCommand.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return .requiresSetup(message: "OpenClaw CLI 路径不能为空。请填写绝对路径。")
        }

        if isAbsoluteLikePath(trimmed) {
            let normalizedPath = normalizePath(trimmed)
            guard fileManager.isExecutableFile(atPath: normalizedPath) else {
                return .requiresSetup(message: "当前路径不是可执行文件: \(normalizedPath)")
            }

            if usesEnvNodeShebang(atPath: normalizedPath, fileManager: fileManager) {
                guard let nodePath = resolveNodePath(
                    forCommandPath: normalizedPath,
                    explicitNodePath: explicitNodePath,
                    environment: environment,
                    fileManager: fileManager
                ) else {
                    return .requiresNodePath(
                        scriptPath: normalizedPath,
                        message: "当前 OpenClaw CLI 依赖 `node` 解释器，但自动找不到可执行的 node 路径。请手动指定 Node 的绝对路径。"
                    )
                }
                return .validNodeScript(normalizedPath: normalizedPath, nodePath: nodePath)
            }

            return .valid(normalizedPath: normalizedPath)
        }

        if trimmed.contains("/") {
            return .requiresSetup(message: "GUI 启动只接受绝对路径或 `~` 开头的路径，当前是相对路径: \(trimmed)")
        }

        if let resolvedPath = resolveFromPATH(commandName: trimmed, environment: environment, fileManager: fileManager) {
            return .requiresSetup(
                message: "当前值 `\(trimmed)` 是裸命令。GUI 启动时不会依赖 PATH，请改成绝对路径，例如: \(resolvedPath)"
            )
        }

        return .requiresSetup(
            message: "当前值 `\(trimmed)` 是裸命令，且当前环境里解析不到。请手动选择 OpenClaw CLI 的绝对路径。"
        )
    }

    static func normalizePath(_ rawPath: String) -> String {
        URL(fileURLWithPath: (rawPath as NSString).expandingTildeInPath).standardizedFileURL.path
    }

    static func resolveFromPATH(
        commandName: String,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default
    ) -> String? {
        let pathValue = environment["PATH"] ?? ""
        let candidates = pathValue
            .split(separator: ":")
            .map(String.init)
            .filter { !$0.isEmpty }
            .map { URL(fileURLWithPath: $0, isDirectory: true).appendingPathComponent(commandName).path }

        return candidates.first(where: { fileManager.isExecutableFile(atPath: $0) })
    }

    static func usesEnvNodeShebang(
        atPath path: String,
        fileManager: FileManager = .default
    ) -> Bool {
        guard fileManager.isExecutableFile(atPath: path),
              let handle = FileHandle(forReadingAtPath: path),
              let data = try? handle.read(upToCount: 256),
              let text = String(data: data, encoding: .utf8) else {
            return false
        }
        return text
            .split(whereSeparator: { $0.isNewline })
            .first
            .map(String.init)?
            .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines) == "#!/usr/bin/env node"
    }

    static func resolveNodePath(
        forCommandPath commandPath: String,
        explicitNodePath: String? = nil,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default
    ) -> String? {
        let normalizedCommandPath = normalizePath(commandPath)
        let commandDirectory = URL(fileURLWithPath: normalizedCommandPath).deletingLastPathComponent().path
        let sameDirectoryNode = URL(fileURLWithPath: commandDirectory, isDirectory: true)
            .appendingPathComponent("node")
            .path

        var candidates: [String] = []
        if let explicitNodePath,
           !explicitNodePath.trimmingCharacters(in: CharacterSet.whitespacesAndNewlines).isEmpty {
            candidates.append(explicitNodePath)
        }
        candidates.append(sameDirectoryNode)
        candidates.append(contentsOf: commonNodePaths)

        if let pathResolvedNode = resolveFromPATH(commandName: "node", environment: environment, fileManager: fileManager) {
            candidates.append(pathResolvedNode)
        }

        var seen = Set<String>()
        for candidate in candidates {
            let normalizedCandidate = normalizePath(candidate)
            guard seen.insert(normalizedCandidate).inserted else { continue }
            if fileManager.isExecutableFile(atPath: normalizedCandidate) {
                return normalizedCandidate
            }
        }
        return nil
    }

    static func assessNodePath(_ rawPath: String, fileManager: FileManager = .default) -> OpenClawCommandAssessment {
        let trimmed = rawPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return .requiresSetup(message: "Node 路径不能为空。请填写绝对路径。")
        }

        guard isAbsoluteLikePath(trimmed) else {
            return .requiresSetup(message: "Node 路径必须是绝对路径或 `~` 开头的路径。")
        }

        let normalizedPath = normalizePath(trimmed)
        guard fileManager.isExecutableFile(atPath: normalizedPath) else {
            return .requiresSetup(message: "当前 Node 路径不是可执行文件: \(normalizedPath)")
        }

        return .valid(normalizedPath: normalizedPath)
    }

    private static func isAbsoluteLikePath(_ value: String) -> Bool {
        value.hasPrefix("/") || value.hasPrefix("~")
    }
}
