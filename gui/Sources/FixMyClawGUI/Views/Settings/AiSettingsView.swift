import Foundation
import SwiftUI

@MainActor
struct AiSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    private let defaults = AiConfig()
    private let providerPresets = ["codex", "claude"]

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SectionHeader(title: "AI 修复基础", description: "日常只建议调整开关、provider 和限流。底层命令参数放在下方危险区。")

            Toggle(
                "启用 AI 修复",
                isOn: binding(
                    default: false,
                    get: { $0.ai.enabled },
                    set: { $0.ai.enabled = $1 }
                )
            )

            Toggle(
                "允许代码修改",
                isOn: binding(
                    default: false,
                    get: { $0.ai.allowCodeChanges },
                    set: { $0.ai.allowCodeChanges = $1 }
                )
            )

            PickerRow(
                title: "Provider 预设",
                selection: presetProviderBinding,
                options: providerPresets,
                description: "优先用预设值，避免 provider 拼写错误。默认值来自 fix-my-claw 内置 AiConfig。"
            )

            TextFieldRow(
                title: "Provider",
                text: binding(
                    default: "codex",
                    get: { $0.ai.provider },
                    set: { $0.ai.provider = $1 }
                ),
                description: "默认值: `codex`。仅在你明确要覆盖预设时再手动填写。",
                message: providerValidationMessage,
                messageTone: .warning
            )

                TextFieldRow(
                    title: "执行命令",
                    text: binding(
                        default: "codex",
                        get: { $0.ai.command },
                        set: { $0.ai.command = $1 }
                    ),
                description: "默认值: `codex`。可以填命令名或绝对路径，但 GUI / Finder 链路更稳妥的是直接保存绝对路径。",
                message: aiCommandMessage?.text,
                messageTone: aiCommandMessage?.tone ?? .info
            )

            TextFieldRow(
                title: "模型",
                text: binding(
                    default: "",
                    get: { $0.ai.model ?? "" },
                    set: { $0.ai.model = $1.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : $1 }
                ),
                description: "留空时由 provider 自己决定默认模型。"
            )

            IntField(
                title: "执行超时",
                value: binding(
                    default: 1_800,
                    get: { $0.ai.timeoutSeconds },
                    set: { $0.ai.timeoutSeconds = $1 }
                ),
                unit: "秒",
                range: 1...21_600
            )

            IntField(
                title: "每日最大次数",
                value: binding(
                    default: 2,
                    get: { $0.ai.maxAttemptsPerDay },
                    set: { $0.ai.maxAttemptsPerDay = $1 }
                ),
                unit: "次",
                range: 0...100
            )

            IntField(
                title: "冷却时间",
                value: binding(
                    default: 3_600,
                    get: { $0.ai.cooldownSeconds },
                    set: { $0.ai.cooldownSeconds = $1 }
                ),
                unit: "秒",
                    range: 0...172_800
            )

            SectionHeader(
                title: "危险高级项：AI 命令参数",
                description: "这些字段会直接覆盖 fix-my-claw 调用 AI 的底层参数。误配通常会导致 AI 修复完全失效。",
                actionTitle: "恢复默认参数",
                action: restoreAiArgumentDefaults
            )

            LineListEditor(
                title: "args",
                description: "配置型 AI 修复参数。默认来源: fix-my-claw 内置 `AiConfig.args`，通常应保留 `exec`、`-C $workspace_dir` 以及状态目录挂载。",
                text: lineListBinding(
                    default: defaults.args,
                    get: { $0.ai.args },
                    set: { $0.ai.args = $1 }
                ),
                message: argsValidationMessage,
                messageTone: .warning
            )

            LineListEditor(
                title: "args_code",
                description: "代码型 AI 修复参数。默认来源: fix-my-claw 内置 `AiConfig.args_code`，通常应保留 `exec` 和 `-C $workspace_dir`。",
                text: lineListBinding(
                    default: defaults.argsCode,
                    get: { $0.ai.argsCode },
                    set: { $0.ai.argsCode = $1 }
                ),
                message: argsCodeValidationMessage,
                messageTone: .warning
            )
        }
    }
}

private extension AiSettingsView {
    var currentProvider: String {
        configManager.config?.ai.provider.trimmingCharacters(in: .whitespacesAndNewlines) ?? defaults.provider
    }

    var presetProviderBinding: Binding<String> {
        Binding(
            get: {
                let provider = currentProvider.lowercased()
                return providerPresets.contains(provider) ? provider : defaults.provider
            },
            set: { newValue in
                guard var config = configManager.config else { return }
                config.ai.provider = newValue
                configManager.config = config
            }
        )
    }

    var providerValidationMessage: String? {
        let provider = currentProvider
        if provider.isEmpty {
            return "provider 不能为空；留空会把一个空 provider 直接写进配置。"
        }
        if providerPresets.contains(provider.lowercased()) {
            return nil
        }
        return "当前是自定义 provider。确认后端/执行器确实支持它，再保存。"
    }

    var aiCommandMessage: (text: String, tone: FormMessageTone)? {
        executableMessage(
            for: configManager.config?.ai.command ?? defaults.command,
            kind: "AI 执行命令"
        )
    }

    var argsValidationMessage: String? {
        commandArgumentWarning(
            configManager.config?.ai.args ?? defaults.args,
            expectedSubcommand: "exec",
            requiredMarkers: ["$workspace_dir", "$openclaw_state_dir", "$monitor_state_dir"]
        )
    }

    var argsCodeValidationMessage: String? {
        commandArgumentWarning(
            configManager.config?.ai.argsCode ?? defaults.argsCode,
            expectedSubcommand: "exec",
            requiredMarkers: ["$workspace_dir"]
        )
    }

    func restoreAiArgumentDefaults() {
        guard var config = configManager.config else { return }
        config.ai.args = defaults.args
        config.ai.argsCode = defaults.argsCode
        configManager.config = config
    }

    func executableMessage(for command: String, kind: String) -> (text: String, tone: FormMessageTone)? {
        let trimmed = command.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return ("\(kind) 不能为空。", .warning)
        }

        let expanded = (trimmed as NSString).expandingTildeInPath
        if trimmed.contains("/") {
            guard trimmed.hasPrefix("/") || trimmed.hasPrefix("~") else {
                return ("\(kind) 当前是相对路径。GUI / Finder 链路更稳妥的是绝对路径。", .warning)
            }
            let path = URL(fileURLWithPath: expanded).standardizedFileURL.path
            let isExecutable = FileManager.default.isExecutableFile(atPath: path)
            guard isExecutable else {
                return ("未找到可执行文件: \(path)", .warning)
            }
            return resolvedExecutableMessage(
                resolvedPath: path,
                sourceCommand: trimmed,
                kind: kind,
                resolvedViaPATH: false
            )
        }

        if let found = OpenClawCommandValidator.resolveFromPATH(commandName: trimmed) {
            return resolvedExecutableMessage(
                resolvedPath: found,
                sourceCommand: trimmed,
                kind: kind,
                resolvedViaPATH: true
            )
        }

        return ("当前 PATH 中找不到 `\(trimmed)`，运行时可能直接失败。", .warning)
    }

    func resolvedExecutableMessage(
        resolvedPath: String,
        sourceCommand: String,
        kind: String,
        resolvedViaPATH: Bool
    ) -> (text: String, tone: FormMessageTone) {
        if OpenClawCommandValidator.usesEnvNodeShebang(atPath: resolvedPath) {
            guard let nodePath = OpenClawCommandValidator.resolveNodePath(forCommandPath: resolvedPath) else {
                return (
                    "\(kind) 指向的是 Node 启动脚本 \(resolvedPath)，但当前环境找不到可执行的 node。AI 修复运行时很可能直接失败。",
                    .warning
                )
            }

            if resolvedViaPATH {
                return (
                    "\(kind) 当前会通过 PATH 把 `\(sourceCommand)` 解析成 Node 脚本 \(resolvedPath)，并依赖 \(nodePath)。当前机器可用，但 GUI / Finder 环境更稳妥的是改成绝对路径或固定 launcher。",
                    .warning
                )
            }

            return (
                "\(kind) 是 Node 启动脚本，将依赖 \(nodePath) 启动 \(resolvedPath)。迁移到别的机器时也要确认 node 路径可用。",
                .info
            )
        }

        if resolvedViaPATH {
            return (
                "\(kind) 当前会通过 PATH 解析为: \(resolvedPath)。你这台机器现在没问题，但 GUI / Finder 链路更稳妥的是直接保存绝对路径。",
                .warning
            )
        }

        return ("已解析到可执行路径: \(resolvedPath)", .info)
    }

    func commandArgumentWarning(
        _ args: [String],
        expectedSubcommand: String,
        requiredMarkers: [String]
    ) -> String? {
        if args.isEmpty {
            return "参数列表为空。fix-my-claw 会直接调用命令本身，通常不是你想要的行为。"
        }
        if args.first != expectedSubcommand {
            return "首个参数不是 `\(expectedSubcommand)`；这会改变底层 CLI 调用协议。"
        }
        let missing = requiredMarkers.filter { marker in
            !args.contains(where: { $0.contains(marker) })
        }
        if !missing.isEmpty {
            return "缺少常用占位符: \(missing.joined(separator: ", "))。保存前确认你真的不需要这些上下文。"
        }
        return nil
    }
}
