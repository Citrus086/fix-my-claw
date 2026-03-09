import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var configManager: ConfigManager
    @State private var activeTab: SettingsTab = .monitor

    var body: some View {
        VStack(spacing: 0) {
            Picker("设置", selection: $activeTab) {
                ForEach(SettingsTab.allCases) { tab in
                    Text(tab.displayName).tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .padding()

            Divider()

            Group {
                if configManager.config == nil && configManager.isLoading {
                    VStack {
                        Spacer()
                        ProgressView("加载配置中...")
                        Spacer()
                    }
                } else if configManager.config != nil {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 24) {
                            switch activeTab {
                            case .monitor:
                                MonitorSettingsView()
                            case .repair:
                                RepairSettingsView()
                            case .ai:
                                AiSettingsView()
                            case .ids:
                                IdSettingsView()
                            case .advanced:
                                AdvancedSettingsView()
                            }
                        }
                        .padding()
                    }
                } else {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("无法加载配置")
                            .font(.headline)
                        if let error = configManager.lastError {
                            Text(error)
                                .foregroundColor(.red)
                        }
                        Button("重试") {
                            configManager.loadConfig()
                        }
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
                    .padding()
                }
            }

            Divider()

            HStack {
                Button("重置默认") {
                    configManager.resetToDefault()
                }
                .buttonStyle(.bordered)

                Button("打开配置文件") {
                    configManager.openConfigFile()
                }
                .buttonStyle(.bordered)

                Spacer()

                if let error = configManager.saveError ?? configManager.lastError {
                    Text(error)
                        .foregroundColor(.red)
                        .font(.caption)
                }

                Button("保存") {
                    configManager.saveConfig()
                }
                .buttonStyle(.borderedProminent)
                .disabled(configManager.config == nil || configManager.isLoading)
            }
            .padding()
        }
        .frame(minWidth: 780, minHeight: 720)
        .onAppear {
            if configManager.config == nil {
                configManager.loadConfig()
            }
        }
    }
}

enum SettingsTab: String, CaseIterable, Identifiable {
    case monitor
    case repair
    case ai
    case ids
    case advanced

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .monitor: return "监控"
        case .repair: return "修复"
        case .ai: return "AI"
        case .ids: return "ID 配置"
        case .advanced: return "高级"
        }
    }
}

@MainActor
private protocol ConfigBindable: View {
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

@MainActor
struct MonitorSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SectionHeader(title: "监控轮询", description: "控制健康检查和修复冷却的基础节奏。")

            IntField(
                title: "检查间隔",
                value: binding(
                    default: 60,
                    get: { $0.monitor.intervalSeconds },
                    set: { $0.monitor.intervalSeconds = $1 }
                ),
                unit: "秒",
                range: 10...3600
            )

            IntField(
                title: "探测超时",
                value: binding(
                    default: 30,
                    get: { $0.monitor.probeTimeoutSeconds },
                    set: { $0.monitor.probeTimeoutSeconds = $1 }
                ),
                unit: "秒",
                range: 5...300
            )

            IntField(
                title: "修复冷却",
                value: binding(
                    default: 300,
                    get: { $0.monitor.repairCooldownSeconds },
                    set: { $0.monitor.repairCooldownSeconds = $1 }
                ),
                unit: "秒",
                range: 0...86400
            )

            SectionHeader(title: "状态与日志路径", description: "fix-my-claw 自身状态目录和运行日志位置。")

            TextFieldRow(
                title: "状态目录",
                text: binding(
                    default: "~/.fix-my-claw",
                    get: { $0.monitor.stateDir },
                    set: { $0.monitor.stateDir = $1 }
                )
            )

            TextFieldRow(
                title: "日志文件",
                text: binding(
                    default: "~/.fix-my-claw/fix-my-claw.log",
                    get: { $0.monitor.logFile },
                    set: { $0.monitor.logFile = $1 }
                )
            )

            PickerRow(
                title: "日志级别",
                selection: binding(
                    default: "INFO",
                    get: { $0.monitor.logLevel },
                    set: { $0.monitor.logLevel = $1 }
                ),
                options: ["DEBUG", "INFO", "WARNING", "ERROR"]
            )

            SectionHeader(title: "日志轮转", description: "控制单文件大小、备份份数和保留天数。")

            IntField(
                title: "单文件上限",
                value: binding(
                    default: 5_242_880,
                    get: { $0.monitor.logMaxBytes },
                    set: { $0.monitor.logMaxBytes = $1 }
                ),
                unit: "字节",
                range: 1_024...104_857_600
            )

            IntField(
                title: "备份份数",
                value: binding(
                    default: 5,
                    get: { $0.monitor.logBackupCount },
                    set: { $0.monitor.logBackupCount = $1 }
                ),
                unit: "份",
                range: 0...100
            )

            IntField(
                title: "保留天数",
                value: binding(
                    default: 30,
                    get: { $0.monitor.logRetentionDays },
                    set: { $0.monitor.logRetentionDays = $1 }
                ),
                unit: "天",
                range: 0...3650
            )
        }
    }
}

@MainActor
struct RepairSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SectionHeader(title: "自动修复开关", description: "基础修复流和会话控制策略。")

            Toggle(
                "启用自动修复",
                isOn: binding(
                    default: true,
                    get: { $0.repair.enabled },
                    set: { $0.repair.enabled = $1 }
                )
            )

            Toggle(
                "启用会话控制",
                isOn: binding(
                    default: true,
                    get: { $0.repair.sessionControlEnabled },
                    set: { $0.repair.sessionControlEnabled = $1 }
                )
            )

            Toggle(
                "启用软暂停",
                isOn: binding(
                    default: true,
                    get: { $0.repair.softPauseEnabled },
                    set: { $0.repair.softPauseEnabled = $1 }
                )
            )

            IntField(
                title: "会话活跃窗口",
                value: binding(
                    default: 30,
                    get: { $0.repair.sessionActiveMinutes },
                    set: { $0.repair.sessionActiveMinutes = $1 }
                ),
                unit: "分钟",
                range: 1...1_440
            )

            IntField(
                title: "PAUSE 等待",
                value: binding(
                    default: 20,
                    get: { $0.repair.pauseWaitSeconds },
                    set: { $0.repair.pauseWaitSeconds = $1 }
                ),
                unit: "秒",
                range: 0...600
            )

            IntField(
                title: "命令超时",
                value: binding(
                    default: 120,
                    get: { $0.repair.sessionCommandTimeoutSeconds },
                    set: { $0.repair.sessionCommandTimeoutSeconds = $1 }
                ),
                unit: "秒",
                range: 1...3_600
            )

            IntField(
                title: "阶段间隔",
                value: binding(
                    default: 1,
                    get: { $0.repair.sessionStageWaitSeconds },
                    set: { $0.repair.sessionStageWaitSeconds = $1 }
                ),
                unit: "秒",
                range: 0...300
            )

            IntField(
                title: "步骤超时",
                value: binding(
                    default: 600,
                    get: { $0.repair.stepTimeoutSeconds },
                    set: { $0.repair.stepTimeoutSeconds = $1 }
                ),
                unit: "秒",
                range: 1...7_200
            )

            IntField(
                title: "步骤后等待",
                value: binding(
                    default: 2,
                    get: { $0.repair.postStepWaitSeconds },
                    set: { $0.repair.postStepWaitSeconds = $1 }
                ),
                unit: "秒",
                range: 0...300
            )

            SectionHeader(title: "会话文案", description: "PAUSE / stop / new 向 OpenClaw 发送的控制内容。")

            MultilineTextField(
                title: "PAUSE 消息",
                description: "多行文本会原样写入 `repair.pause_message`。",
                text: binding(
                    default: "",
                    get: { $0.repair.pauseMessage },
                    set: { $0.repair.pauseMessage = $1 }
                ),
                minHeight: 120
            )

            TextFieldRow(
                title: "停止命令",
                text: binding(
                    default: "/stop",
                    get: { $0.repair.terminateMessage },
                    set: { $0.repair.terminateMessage = $1 }
                )
            )

            TextFieldRow(
                title: "新会话命令",
                text: binding(
                    default: "/new",
                    get: { $0.repair.newMessage },
                    set: { $0.repair.newMessage = $1 }
                )
            )

            SectionHeader(title: "官方修复步骤", description: "每行一条命令，按顺序执行；含空格参数请用引号。")

            CommandListEditor(
                title: "official_steps",
                description: "示例: `openclaw doctor --repair`",
                text: commandListBinding(
                    default: [["openclaw", "doctor", "--repair"], ["openclaw", "gateway", "restart"]],
                    get: { $0.repair.officialSteps },
                    set: { $0.repair.officialSteps = $1 }
                )
            )
        }
    }
}

@MainActor
struct AiSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SectionHeader(title: "AI 修复基础", description: "控制 AI provider、命令和限流。")

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

            TextFieldRow(
                title: "Provider",
                text: binding(
                    default: "codex",
                    get: { $0.ai.provider },
                    set: { $0.ai.provider = $1 }
                )
            )

            TextFieldRow(
                title: "执行命令",
                text: binding(
                    default: "codex",
                    get: { $0.ai.command },
                    set: { $0.ai.command = $1 }
                )
            )

            TextFieldRow(
                title: "模型",
                text: binding(
                    default: "",
                    get: { $0.ai.model ?? "" },
                    set: { $0.ai.model = $1.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : $1 }
                )
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

            SectionHeader(title: "AI 命令参数", description: "每行一个参数，顺序会原样保留。")

            LineListEditor(
                title: "args",
                description: "配置型 AI 修复命令参数。",
                text: lineListBinding(
                    default: [],
                    get: { $0.ai.args },
                    set: { $0.ai.args = $1 }
                )
            )

            LineListEditor(
                title: "args_code",
                description: "代码型 AI 修复命令参数。",
                text: lineListBinding(
                    default: [],
                    get: { $0.ai.argsCode },
                    set: { $0.ai.argsCode = $1 }
                )
            )
        }
    }
}

@MainActor
struct IdSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SectionHeader(title: "会话 Agent IDs", description: "有权接收会话控制命令的 Agent 列表，每行一个。")

            LineListEditor(
                title: "session_agents",
                description: "会被写入 `repair.session_agents`。",
                text: lineListBinding(
                    default: [],
                    get: { $0.repair.sessionAgents },
                    set: { $0.repair.sessionAgents = $1 }
                )
            )

            SectionHeader(title: "Agent 角色别名", description: "异常检测时用于识别各类角色的别名。")

            LineListEditor(
                title: "orchestrator",
                description: "每行一个别名。",
                text: lineListBinding(
                    default: [],
                    get: { $0.agentRoles.orchestrator },
                    set: { $0.agentRoles.orchestrator = $1 }
                )
            )

            LineListEditor(
                title: "builder",
                description: "每行一个别名。",
                text: lineListBinding(
                    default: [],
                    get: { $0.agentRoles.builder },
                    set: { $0.agentRoles.builder = $1 }
                )
            )

            LineListEditor(
                title: "architect",
                description: "每行一个别名。",
                text: lineListBinding(
                    default: [],
                    get: { $0.agentRoles.architect },
                    set: { $0.agentRoles.architect = $1 }
                )
            )

            LineListEditor(
                title: "research",
                description: "每行一个别名。",
                text: lineListBinding(
                    default: [],
                    get: { $0.agentRoles.research },
                    set: { $0.agentRoles.research = $1 }
                )
            )

            SectionHeader(title: "通知接收人", description: "频道场景下，哪些用户被当作操作员。")

            LineListEditor(
                title: "operator_user_ids",
                description: "每行一个 Discord user id。",
                text: lineListBinding(
                    default: [],
                    get: { $0.notify.operatorUserIds },
                    set: { $0.notify.operatorUserIds = $1 }
                )
            )
        }
    }
}

@MainActor
struct AdvancedSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SectionHeader(
                title: "高级字段",
                description: "低频复杂字段使用多行原始编辑；保存时会按 CLI 返回的原始 JSON 深度合并，避免未触碰字段被 GUI 静默抹掉。"
            )

            Group {
                SectionHeader(title: "OpenClaw CLI", description: "fix-my-claw 调用 OpenClaw 所用的命令、目录和参数。")

                TextFieldRow(
                    title: "OpenClaw 命令",
                    text: binding(
                        default: "openclaw",
                        get: { $0.openclaw.command },
                        set: { $0.openclaw.command = $1 }
                    )
                )

                TextFieldRow(
                    title: "OpenClaw 状态目录",
                    text: binding(
                        default: "~/.openclaw",
                        get: { $0.openclaw.stateDir },
                        set: { $0.openclaw.stateDir = $1 }
                    )
                )

                TextFieldRow(
                    title: "OpenClaw 工作目录",
                    text: binding(
                        default: "~/.openclaw/workspace",
                        get: { $0.openclaw.workspaceDir },
                        set: { $0.openclaw.workspaceDir = $1 }
                    )
                )

                LineListEditor(
                    title: "health_args",
                    description: "每行一个参数。",
                    text: lineListBinding(
                        default: ["gateway", "health", "--json"],
                        get: { $0.openclaw.healthArgs },
                        set: { $0.openclaw.healthArgs = $1 }
                    )
                )

                LineListEditor(
                    title: "status_args",
                    description: "每行一个参数。",
                    text: lineListBinding(
                        default: ["gateway", "status", "--json"],
                        get: { $0.openclaw.statusArgs },
                        set: { $0.openclaw.statusArgs = $1 }
                    )
                )

                LineListEditor(
                    title: "logs_args",
                    description: "每行一个参数。",
                    text: lineListBinding(
                        default: ["logs", "--limit", "200", "--plain"],
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
                SectionHeader(title: "异常检测", description: "日志窗口、关键词和相似度阈值。")

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

                LineListEditor(
                    title: "keywords_stop",
                    description: "每行一个停机关键词。",
                    text: lineListBinding(
                        default: [],
                        get: { $0.anomalyGuard.keywordsStop },
                        set: { $0.anomalyGuard.keywordsStop = $1 }
                    )
                )

                LineListEditor(
                    title: "keywords_repeat",
                    description: "每行一个重复/死循环关键词。",
                    text: lineListBinding(
                        default: [],
                        get: { $0.anomalyGuard.keywordsRepeat },
                        set: { $0.anomalyGuard.keywordsRepeat = $1 }
                    )
                )

                LineListEditor(
                    title: "keywords_dispatch",
                    description: "每行一个派发关键词。",
                    text: lineListBinding(
                        default: [],
                        get: { $0.anomalyGuard.keywordsDispatch },
                        set: { $0.anomalyGuard.keywordsDispatch = $1 }
                    )
                )

                LineListEditor(
                    title: "keywords_architect_active",
                    description: "每行一个 Architect 仍在输出的检测关键词。",
                    text: lineListBinding(
                        default: [],
                        get: { $0.anomalyGuard.keywordsArchitectActive },
                        set: { $0.anomalyGuard.keywordsArchitectActive = $1 }
                    )
                )
            }
        }
    }
}

struct SectionHeader: View {
    let title: String
    let description: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.headline)
            Text(description)
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}

struct TextFieldRow: View {
    let title: String
    @Binding var text: String

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(title)
                .frame(width: 150, alignment: .leading)

            TextField(title, text: $text)
                .textFieldStyle(.roundedBorder)
        }
    }
}

struct PickerRow: View {
    let title: String
    @Binding var selection: String
    let options: [String]

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Text(title)
                .frame(width: 150, alignment: .leading)

            Picker(title, selection: $selection) {
                ForEach(options, id: \.self) { option in
                    Text(option).tag(option)
                }
            }
            .pickerStyle(.menu)

            Spacer()
        }
    }
}

struct IntField: View {
    let title: String
    @Binding var value: Int
    let unit: String
    let range: ClosedRange<Int>

    private static let formatter: NumberFormatter = {
        let formatter = NumberFormatter()
        formatter.numberStyle = .none
        return formatter
    }()

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Text(title)
                .frame(width: 150, alignment: .leading)

            TextField("", value: $value, formatter: Self.formatter)
                .textFieldStyle(.roundedBorder)
                .frame(width: 120)
                .onChange(of: value) { newValue in
                    value = min(range.upperBound, max(range.lowerBound, newValue))
                }

            Text(unit)
                .foregroundColor(.secondary)
                .frame(width: 50, alignment: .leading)

            Spacer()

            Text("(\(range.lowerBound) - \(range.upperBound))")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}

struct DoubleField: View {
    let title: String
    @Binding var value: Double
    let range: ClosedRange<Double>

    private static let formatter: NumberFormatter = {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.minimumFractionDigits = 0
        formatter.maximumFractionDigits = 3
        return formatter
    }()

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Text(title)
                .frame(width: 150, alignment: .leading)

            TextField("", value: $value, formatter: Self.formatter)
                .textFieldStyle(.roundedBorder)
                .frame(width: 120)
                .onChange(of: value) { newValue in
                    value = min(range.upperBound, max(range.lowerBound, newValue))
                }

            Spacer()

            Text(String(format: "(%.2f - %.2f)", range.lowerBound, range.upperBound))
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}

struct MultilineTextField: View {
    let title: String
    let description: String
    @Binding var text: String
    let minHeight: CGFloat

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.subheadline)
                .fontWeight(.medium)
            Text(description)
                .font(.caption)
                .foregroundColor(.secondary)
            TextEditor(text: $text)
                .font(.system(.body, design: .monospaced))
                .frame(minHeight: minHeight)
                .padding(6)
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.secondary.opacity(0.25), lineWidth: 1)
                )
        }
    }
}

struct LineListEditor: View {
    let title: String
    let description: String
    @Binding var text: String

    var body: some View {
        MultilineTextField(
            title: title,
            description: description,
            text: $text,
            minHeight: 110
        )
    }
}

struct CommandListEditor: View {
    let title: String
    let description: String
    @Binding var text: String

    var body: some View {
        MultilineTextField(
            title: title,
            description: description,
            text: $text,
            minHeight: 130
        )
    }
}

private func normalizedLineList(_ items: [String]) -> String {
    items.joined(separator: "\n")
}

private func parseLineList(_ text: String) -> [String] {
    text
        .split(whereSeparator: \.isNewline)
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
}

private func normalizedCommandList(_ commands: [[String]]) -> String {
    commands
        .map(renderCommandLine)
        .joined(separator: "\n")
}

private func parseCommandList(_ text: String) -> [[String]] {
    text
        .split(whereSeparator: \.isNewline)
        .map { tokenizeCommandLine(String($0)) }
        .filter { !$0.isEmpty }
}

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

struct SettingsView_Previews: PreviewProvider {
    static var previews: some View {
        SettingsView()
            .environmentObject(ConfigManager.shared)
    }
}
