import Foundation
import SwiftUI

@MainActor
struct AdvancedSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    private let openClawDefaults = OpenClawConfig()
    private let anomalyDefaults = AnomalyGuardConfig()

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SectionHeader(
                title: "高级字段",
                description: "低频复杂字段使用多行原始编辑；保存时会按 CLI 返回的原始 JSON 深度合并，避免未触碰字段被 GUI 静默抹掉。"
            )

            Group {
                SectionHeader(
                    title: "OpenClaw CLI",
                    description: "这些字段会直接影响 fix-my-claw 如何找到 OpenClaw 和它的工作目录。改错后，health/status/logs 全都会失效。",
                    actionTitle: "恢复默认字段",
                    action: restoreOpenClawDefaults
                )

                TextFieldRow(
                    title: "OpenClaw 命令",
                    text: binding(
                        default: openClawDefaults.command,
                        get: { $0.openclaw.command },
                        set: { $0.openclaw.command = $1 }
                    ),
                    description: "GUI 启动链路要求这里保存为绝对可执行路径。裸命令会触发启动配置向导。",
                    message: openClawCommandMessage?.text,
                    messageTone: openClawCommandMessage?.tone ?? .info
                )

                TextFieldRow(
                    title: "OpenClaw 状态目录",
                    text: binding(
                        default: openClawDefaults.stateDir,
                        get: { $0.openclaw.stateDir },
                        set: { $0.openclaw.stateDir = $1 }
                    ),
                    description: "默认值来源: fix-my-claw 内置 `OpenClawConfig.stateDir`。",
                    message: stateDirectoryMessage?.text,
                    messageTone: stateDirectoryMessage?.tone ?? .info
                )

                TextFieldRow(
                    title: "OpenClaw 工作目录",
                    text: binding(
                        default: openClawDefaults.workspaceDir,
                        get: { $0.openclaw.workspaceDir },
                        set: { $0.openclaw.workspaceDir = $1 }
                    ),
                    description: "默认值来源: fix-my-claw 内置 `OpenClawConfig.workspaceDir`。",
                    message: workspaceDirectoryMessage?.text,
                    messageTone: workspaceDirectoryMessage?.tone ?? .info
                )

                LineListEditor(
                    title: "health_args",
                    description: "每行一个参数。默认值来源: fix-my-claw 内置 `OpenClawConfig.healthArgs`。",
                    text: lineListBinding(
                        default: openClawDefaults.healthArgs,
                        get: { $0.openclaw.healthArgs },
                        set: { $0.openclaw.healthArgs = $1 }
                    )
                )

                LineListEditor(
                    title: "status_args",
                    description: "每行一个参数。默认值来源: fix-my-claw 内置 `OpenClawConfig.statusArgs`。",
                    text: lineListBinding(
                        default: openClawDefaults.statusArgs,
                        get: { $0.openclaw.statusArgs },
                        set: { $0.openclaw.statusArgs = $1 }
                    )
                )

                LineListEditor(
                    title: "logs_args",
                    description: "每行一个参数。默认值来源: fix-my-claw 内置 `OpenClawConfig.logsArgs`。",
                    text: lineListBinding(
                        default: openClawDefaults.logsArgs,
                        get: { $0.openclaw.logsArgs },
                        set: { $0.openclaw.logsArgs = $1 }
                    )
                )
            }

            Divider()

            Group {
                SectionHeader(title: "通知", description: "通知发送、读取、审批轮询和关键词匹配。")

                TextFieldRow(
                    title: "渠道",
                    text: binding(
                        default: "discord",
                        get: { $0.notify.channel },
                        set: { $0.notify.channel = $1 }
                    )
                )

                TextFieldRow(
                    title: "账号",
                    text: binding(
                        default: "fix-my-claw",
                        get: { $0.notify.account },
                        set: { $0.notify.account = $1 }
                    )
                )

                TextFieldRow(
                    title: "目标",
                    text: binding(
                        default: "channel:YOUR_DISCORD_CHANNEL_ID",
                        get: { $0.notify.target },
                        set: { $0.notify.target = $1 }
                    )
                )

                TextFieldRow(
                    title: "必需 mention ID",
                    text: binding(
                        default: "",
                        get: { $0.notify.requiredMentionId },
                        set: { $0.notify.requiredMentionId = $1 }
                    )
                )

                Toggle(
                    "静默通知",
                    isOn: binding(
                        default: true,
                        get: { $0.notify.silent },
                        set: { $0.notify.silent = $1 }
                    )
                )

                Toggle(
                    "AI 前询问",
                    isOn: binding(
                        default: true,
                        get: { $0.notify.askEnableAi },
                        set: { $0.notify.askEnableAi = $1 }
                    )
                )

                PickerRow(
                    title: "通知级别",
                    selection: binding(
                        default: "all",
                        get: { $0.notify.level },
                        set: { $0.notify.level = $1 }
                    ),
                    options: ["all", "important", "critical"]
                )

                IntField(
                    title: "发送超时",
                    value: binding(
                        default: 20,
                        get: { $0.notify.sendTimeoutSeconds },
                        set: { $0.notify.sendTimeoutSeconds = $1 }
                    ),
                    unit: "秒",
                    range: 1...600
                )

                IntField(
                    title: "读取超时",
                    value: binding(
                        default: 20,
                        get: { $0.notify.readTimeoutSeconds },
                        set: { $0.notify.readTimeoutSeconds = $1 }
                    ),
                    unit: "秒",
                    range: 1...600
                )

                IntField(
                    title: "审批超时",
                    value: binding(
                        default: 300,
                        get: { $0.notify.askTimeoutSeconds },
                        set: { $0.notify.askTimeoutSeconds = $1 }
                    ),
                    unit: "秒",
                    range: 1...86_400
                )

                IntField(
                    title: "轮询间隔",
                    value: binding(
                        default: 5,
                        get: { $0.notify.pollIntervalSeconds },
                        set: { $0.notify.pollIntervalSeconds = $1 }
                    ),
                    unit: "秒",
                    range: 1...300
                )

                IntField(
                    title: "读取上限",
                    value: binding(
                        default: 20,
                        get: { $0.notify.readLimit },
                        set: { $0.notify.readLimit = $1 }
                    ),
                    unit: "条",
                    range: 1...500
                )

                IntField(
                    title: "无效回复上限",
                    value: binding(
                        default: 3,
                        get: { $0.notify.maxInvalidReplies },
                        set: { $0.notify.maxInvalidReplies = $1 }
                    ),
                    unit: "次",
                    range: 1...20
                )

                LineListEditor(
                    title: "manual_repair_keywords",
                    description: "每行一个手动修复关键词。",
                    text: lineListBinding(
                        default: ["手动修复", "manual repair", "修复", "repair"],
                        get: { $0.notify.manualRepairKeywords },
                        set: { $0.notify.manualRepairKeywords = $1 }
                    )
                )

                LineListEditor(
                    title: "ai_approve_keywords",
                    description: "每行一个 AI 批准关键词。",
                    text: lineListBinding(
                        default: ["yes", "是"],
                        get: { $0.notify.aiApproveKeywords },
                        set: { $0.notify.aiApproveKeywords = $1 }
                    )
                )

                LineListEditor(
                    title: "ai_reject_keywords",
                    description: "每行一个 AI 拒绝关键词。",
                    text: lineListBinding(
                        default: ["no", "否"],
                        get: { $0.notify.aiRejectKeywords },
                        set: { $0.notify.aiRejectKeywords = $1 }
                    )
                )
            }

            Divider()

            Group {
                SectionHeader(title: "异常检测", description: "阈值和窗口一般按默认即可；真正高风险的是下面的关键词列表。")

                Toggle(
                    "启用异常检测",
                    isOn: binding(
                        default: true,
                        get: { $0.anomalyGuard.enabled },
                        set: { $0.anomalyGuard.enabled = $1 }
                    )
                )

                Toggle(
                    "启用停滞检测",
                    isOn: binding(
                        default: true,
                        get: { $0.anomalyGuard.stagnationEnabled },
                        set: { $0.anomalyGuard.stagnationEnabled = $1 }
                    )
                )

                Toggle(
                    "启用自动派发检查",
                    isOn: binding(
                        default: true,
                        get: { $0.anomalyGuard.autoDispatchCheck },
                        set: { $0.anomalyGuard.autoDispatchCheck = $1 }
                    )
                )

                Toggle(
                    "启用相似度检测",
                    isOn: binding(
                        default: true,
                        get: { $0.anomalyGuard.similarityEnabled },
                        set: { $0.anomalyGuard.similarityEnabled = $1 }
                    )
                )

                IntField(
                    title: "分析窗口",
                    value: binding(
                        default: 200,
                        get: { $0.anomalyGuard.windowLines },
                        set: { $0.anomalyGuard.windowLines = $1 }
                    ),
                    unit: "行",
                    range: 10...10_000
                )

                IntField(
                    title: "探测超时",
                    value: binding(
                        default: 30,
                        get: { $0.anomalyGuard.probeTimeoutSeconds },
                        set: { $0.anomalyGuard.probeTimeoutSeconds = $1 }
                    ),
                    unit: "秒",
                    range: 1...600
                )

                IntField(
                    title: "重复签名上限",
                    value: binding(
                        default: 3,
                        get: { $0.anomalyGuard.maxRepeatSameSignature },
                        set: { $0.anomalyGuard.maxRepeatSameSignature = $1 }
                    ),
                    unit: "次",
                    range: 1...100
                )

                IntField(
                    title: "最小循环轮次",
                    value: binding(
                        default: 4,
                        get: { $0.anomalyGuard.minCycleRepeatedTurns },
                        set: { $0.anomalyGuard.minCycleRepeatedTurns = $1 }
                    ),
                    unit: "轮",
                    range: 1...100
                )

                IntField(
                    title: "最大循环周期",
                    value: binding(
                        default: 4,
                        get: { $0.anomalyGuard.maxCyclePeriod },
                        set: { $0.anomalyGuard.maxCyclePeriod = $1 }
                    ),
                    unit: "轮",
                    range: 1...100
                )

                IntField(
                    title: "停滞最少事件",
                    value: binding(
                        default: 8,
                        get: { $0.anomalyGuard.stagnationMinEvents },
                        set: { $0.anomalyGuard.stagnationMinEvents = $1 }
                    ),
                    unit: "个",
                    range: 1...1_000
                )

                IntField(
                    title: "停滞最少角色",
                    value: binding(
                        default: 2,
                        get: { $0.anomalyGuard.stagnationMinRoles },
                        set: { $0.anomalyGuard.stagnationMinRoles = $1 }
                    ),
                    unit: "个",
                    range: 1...32
                )

                DoubleField(
                    title: "停滞新簇比例",
                    value: binding(
                        default: 0.34,
                        get: { $0.anomalyGuard.stagnationMaxNovelClusterRatio },
                        set: { $0.anomalyGuard.stagnationMaxNovelClusterRatio = $1 }
                    ),
                    range: 0...1
                )

                IntField(
                    title: "最小签名字数",
                    value: binding(
                        default: 16,
                        get: { $0.anomalyGuard.minSignatureChars },
                        set: { $0.anomalyGuard.minSignatureChars = $1 }
                    ),
                    unit: "字",
                    range: 1...1_000
                )

                IntField(
                    title: "派发窗口",
                    value: binding(
                        default: 20,
                        get: { $0.anomalyGuard.dispatchWindowLines },
                        set: { $0.anomalyGuard.dispatchWindowLines = $1 }
                    ),
                    unit: "行",
                    range: 1...1_000
                )

                IntField(
                    title: "派发后最少异常轮次",
                    value: binding(
                        default: 2,
                        get: { $0.anomalyGuard.minPostDispatchUnexpectedTurns },
                        set: { $0.anomalyGuard.minPostDispatchUnexpectedTurns = $1 }
                    ),
                    unit: "轮",
                    range: 1...100
                )

                DoubleField(
                    title: "相似度阈值",
                    value: binding(
                        default: 0.82,
                        get: { $0.anomalyGuard.similarityThreshold },
                        set: { $0.anomalyGuard.similarityThreshold = $1 }
                    ),
                    range: 0...1
                )

                IntField(
                    title: "相似度最小字数",
                    value: binding(
                        default: 12,
                        get: { $0.anomalyGuard.similarityMinChars },
                        set: { $0.anomalyGuard.similarityMinChars = $1 }
                    ),
                    unit: "字",
                    range: 1...1_000
                )

                IntField(
                    title: "相似重复上限",
                    value: binding(
                        default: 4,
                        get: { $0.anomalyGuard.maxSimilarRepeat },
                        set: { $0.anomalyGuard.maxSimilarRepeat = $1 }
                    ),
                    unit: "次",
                    range: 1...100
                )

                SectionHeader(
                    title: "危险高级项：检测关键词",
                    description: "这些关键词直接决定何时触发 stop/repeat/dispatch/architect 活动判断。清空或误配会显著降低检测准确率。",
                    actionTitle: "恢复默认关键词",
                    action: restoreAnomalyKeywordDefaults
                )

                LineListEditor(
                    title: "keywords_stop",
                    description: "每行一个停机关键词。默认值来源: fix-my-claw 内置 `AnomalyGuardConfig.keywordsStop`。",
                    text: lineListBinding(
                        default: anomalyDefaults.keywordsStop,
                        get: { $0.anomalyGuard.keywordsStop },
                        set: { $0.anomalyGuard.keywordsStop = $1 }
                    ),
                    message: keywordValidationMessage(
                        configManager.config?.anomalyGuard.keywordsStop ?? anomalyDefaults.keywordsStop,
                        label: "stop 关键词"
                    ),
                    messageTone: .warning
                )

                LineListEditor(
                    title: "keywords_repeat",
                    description: "每行一个重复/死循环关键词。默认值来源: fix-my-claw 内置 `AnomalyGuardConfig.keywordsRepeat`。",
                    text: lineListBinding(
                        default: anomalyDefaults.keywordsRepeat,
                        get: { $0.anomalyGuard.keywordsRepeat },
                        set: { $0.anomalyGuard.keywordsRepeat = $1 }
                    ),
                    message: keywordValidationMessage(
                        configManager.config?.anomalyGuard.keywordsRepeat ?? anomalyDefaults.keywordsRepeat,
                        label: "repeat 关键词"
                    ),
                    messageTone: .warning
                )

                LineListEditor(
                    title: "keywords_dispatch",
                    description: "每行一个派发关键词。默认值来源: fix-my-claw 内置 `AnomalyGuardConfig.keywordsDispatch`。",
                    text: lineListBinding(
                        default: anomalyDefaults.keywordsDispatch,
                        get: { $0.anomalyGuard.keywordsDispatch },
                        set: { $0.anomalyGuard.keywordsDispatch = $1 }
                    ),
                    message: keywordValidationMessage(
                        configManager.config?.anomalyGuard.keywordsDispatch ?? anomalyDefaults.keywordsDispatch,
                        label: "dispatch 关键词"
                    ),
                    messageTone: .warning
                )

                LineListEditor(
                    title: "keywords_architect_active",
                    description: "每行一个 Architect 仍在输出的检测关键词。默认值来源: fix-my-claw 内置 `AnomalyGuardConfig.keywordsArchitectActive`。",
                    text: lineListBinding(
                        default: anomalyDefaults.keywordsArchitectActive,
                        get: { $0.anomalyGuard.keywordsArchitectActive },
                        set: { $0.anomalyGuard.keywordsArchitectActive = $1 }
                    ),
                    message: keywordValidationMessage(
                        configManager.config?.anomalyGuard.keywordsArchitectActive ?? anomalyDefaults.keywordsArchitectActive,
                        label: "architect_active 关键词"
                    ),
                    messageTone: .warning
                )
            }
        }
    }
}

private extension AdvancedSettingsView {
    var openClawCommandMessage: (text: String, tone: FormMessageTone)? {
        executableMessage(
            for: configManager.config?.openclaw.command ?? openClawDefaults.command,
            label: "OpenClaw 命令"
        )
    }

    var stateDirectoryMessage: (text: String, tone: FormMessageTone)? {
        directoryMessage(
            for: configManager.config?.openclaw.stateDir ?? openClawDefaults.stateDir,
            label: "OpenClaw 状态目录"
        )
    }

    var workspaceDirectoryMessage: (text: String, tone: FormMessageTone)? {
        directoryMessage(
            for: configManager.config?.openclaw.workspaceDir ?? openClawDefaults.workspaceDir,
            label: "OpenClaw 工作目录"
        )
    }

    func restoreOpenClawDefaults() {
        guard var config = configManager.config else { return }
        config.openclaw = openClawDefaults
        configManager.config = config
    }

    func restoreAnomalyKeywordDefaults() {
        guard var config = configManager.config else { return }
        config.anomalyGuard.keywordsStop = anomalyDefaults.keywordsStop
        config.anomalyGuard.keywordsRepeat = anomalyDefaults.keywordsRepeat
        config.anomalyGuard.keywordsDispatch = anomalyDefaults.keywordsDispatch
        config.anomalyGuard.keywordsArchitectActive = anomalyDefaults.keywordsArchitectActive
        configManager.config = config
    }

    func executableMessage(for command: String, label: String) -> (text: String, tone: FormMessageTone)? {
        switch OpenClawCommandValidator.assess(command) {
        case .valid(let normalizedPath):
            return ("\(label) 已锁定为可执行绝对路径: \(normalizedPath)", .info)
        case .validNodeScript(let normalizedPath, let nodePath):
            return ("\(label) 是 Node 启动脚本。保存时会自动生成固定 launcher，使用 \(nodePath) 启动 \(normalizedPath)。", .info)
        case .requiresNodePath(_, let message):
            return (message, .warning)
        case .requiresSetup(let message):
            return (message, .warning)
        }
    }

    func directoryMessage(for rawPath: String, label: String) -> (text: String, tone: FormMessageTone)? {
        let trimmed = rawPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return ("\(label) 不能为空。", .warning)
        }

        if !trimmed.hasPrefix("/") && !trimmed.hasPrefix("~") {
            return ("建议使用绝对路径或 `~` 开头的路径，避免相对路径受启动目录影响。", .warning)
        }

        let expanded = (trimmed as NSString).expandingTildeInPath
        var isDirectory: ObjCBool = false
        let exists = FileManager.default.fileExists(atPath: expanded, isDirectory: &isDirectory)
        if exists && isDirectory.boolValue {
            return ("目录存在: \(expanded)", .info)
        }
        if exists {
            return ("路径存在但不是目录: \(expanded)", .warning)
        }
        return ("目录当前不存在: \(expanded)。首次运行前确认 OpenClaw 会创建它。", .warning)
    }

    func keywordValidationMessage(_ items: [String], label: String) -> String? {
        if items.isEmpty {
            return "\(label) 为空时，对应异常模式几乎不会被文本关键词触发。"
        }

        let normalized = items.map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
        let uniqueCount = Set(normalized.filter { !$0.isEmpty }).count
        if uniqueCount < items.count {
            return "\(label) 存在重复项。重复关键词不会增强检测，只会增加维护负担。"
        }

        if uniqueCount < 2 {
            return "\(label) 过少。至少保留 2 个以上关键词更稳妥。"
        }

        return nil
    }
}
