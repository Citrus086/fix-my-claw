import Foundation

// MARK: - CLI 错误

enum CLIError: LocalizedError {
    case commandNotFound(path: String)
    case commandFailed(exitCode: Int32, stderr: String)
    case decodingFailed(Error)
    case unsupportedAPIVersion(String)
    case timeout
    
    var errorDescription: String? {
        switch self {
        case .commandNotFound(let path):
            return "找不到 fix-my-claw CLI: \(path)"
        case .commandFailed(let code, let err):
            return "命令失败 (退出码 \(code)): \(err)"
        case .decodingFailed(let err):
            return "解析失败: \(err.localizedDescription)"
        case .unsupportedAPIVersion(let version):
            return "不支持的 CLI API 版本: \(version)"
        case .timeout:
            return "执行超时"
        }
    }
}
