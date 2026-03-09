import SwiftUI

// MARK: - Config Bindable Protocol

@MainActor
protocol ConfigBindable: View {
    var configManager: ConfigManager { get }
}

extension ConfigBindable {
    func binding<T>(
        default defaultValue: T,
        get: @escaping (AppConfig) -> T,
        set: @escaping (inout AppConfig, T) -> Void
    ) -> Binding<T> {
        Binding(
            get: { configManager.config.map(get) ?? defaultValue },
            set: { newValue in
                guard var config = configManager.config else { return }
                set(&config, newValue)
                configManager.config = config
            }
        )
    }

    func lineListBinding(
        default defaultValue: [String],
        get: @escaping (AppConfig) -> [String],
        set: @escaping (inout AppConfig, [String]) -> Void
    ) -> Binding<String> {
        Binding(
            get: { normalizedLineList(configManager.config.map(get) ?? defaultValue) },
            set: { newValue in
                guard var config = configManager.config else { return }
                set(&config, parseLineList(newValue))
                configManager.config = config
            }
        )
    }

    func commandListBinding(
        default defaultValue: [[String]],
        get: @escaping (AppConfig) -> [[String]],
        set: @escaping (inout AppConfig, [[String]]) -> Void
    ) -> Binding<String> {
        Binding(
            get: { normalizedCommandList(configManager.config.map(get) ?? defaultValue) },
            set: { newValue in
                guard var config = configManager.config else { return }
                set(&config, parseCommandList(newValue))
                configManager.config = config
            }
        )
    }
}

// MARK: - List Parsing Helpers

func normalizedLineList(_ items: [String]) -> String {
    items.joined(separator: "\n")
}

func parseLineList(_ text: String) -> [String] {
    text
        .split(whereSeparator: \.isNewline)
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
}

func normalizedCommandList(_ commands: [[String]]) -> String {
    commands
        .map(renderCommandLine)
        .joined(separator: "\n")
}

func parseCommandList(_ text: String) -> [[String]] {
    text
        .split(whereSeparator: \.isNewline)
        .map { tokenizeCommandLine(String($0)) }
        .filter { !$0.isEmpty }
}

// MARK: - Command Line Tokenization

private func renderCommandLine(_ command: [String]) -> String {
    command.map(renderCommandToken).joined(separator: " ")
}

private func renderCommandToken(_ token: String) -> String {
    guard token.contains(where: { $0.isWhitespace || $0 == "\"" || $0 == "'" || $0 == "\\" }) else {
        return token
    }

    let escaped = token
        .replacingOccurrences(of: "\\", with: "\\\\")
        .replacingOccurrences(of: "\"", with: "\\\"")
    return "\"\(escaped)\""
}

private func tokenizeCommandLine(_ line: String) -> [String] {
    enum QuoteMode {
        case none
        case single
        case double
    }

    var tokens: [String] = []
    var current = ""
    var quoteMode: QuoteMode = .none
    var isEscaping = false

    func flushCurrent() {
        let trimmed = current.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            current = ""
            return
        }
        tokens.append(trimmed)
        current = ""
    }

    for character in line {
        if isEscaping {
            current.append(character)
            isEscaping = false
            continue
        }

        switch quoteMode {
        case .none:
            if character == "\\" {
                isEscaping = true
            } else if character == "\"" {
                quoteMode = .double
            } else if character == "'" {
                quoteMode = .single
            } else if character.isWhitespace {
                flushCurrent()
            } else {
                current.append(character)
            }

        case .single:
            if character == "'" {
                quoteMode = .none
            } else {
                current.append(character)
            }

        case .double:
            if character == "\\" {
                isEscaping = true
            } else if character == "\"" {
                quoteMode = .none
            } else {
                current.append(character)
            }
        }
    }

    if isEscaping {
        current.append("\\")
    }
    flushCurrent()
    return tokens
}
