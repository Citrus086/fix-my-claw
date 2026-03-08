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
                        VStack(alignment: .leading, spacing: 20) {
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
        .frame(minWidth: 600, minHeight: 500)
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
}

@MainActor
struct MonitorSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "监控间隔", description: "检查 OpenClaw 状态的频率")

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

            SectionHeader(title: "超时设置", description: "探测操作的最大等待时间")

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
                range: 0...3600
            )

            SectionHeader(title: "日志", description: "日志级别和日志文件路径")

            TextField(
                "日志级别",
                text: binding(
                    default: "INFO",
                    get: { $0.monitor.logLevel },
                    set: { $0.monitor.logLevel = $1 }
                )
            )

            TextField(
                "日志文件路径",
                text: binding(
                    default: "~/.fix-my-claw/fix-my-claw.log",
                    get: { $0.monitor.logFile },
                    set: { $0.monitor.logFile = $1 }
                )
            )
        }
    }
}

@MainActor
struct RepairSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "自动修复", description: "检测到异常后是否自动触发修复流程")

            Toggle(
                "启用自动修复",
                isOn: binding(
                    default: true,
                    get: { $0.repair.enabled },
                    set: { $0.repair.enabled = $1 }
                )
            )

            SectionHeader(title: "会话控制", description: "是否通过会话命令发送 PAUSE、/stop、/new")

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
                title: "PAUSE 等待",
                value: binding(
                    default: 20,
                    get: { $0.repair.pauseWaitSeconds },
                    set: { $0.repair.pauseWaitSeconds = $1 }
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
                range: 60...3600
            )
        }
    }
}

@MainActor
struct AiSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "AI 修复", description: "是否允许 fix-my-claw 调用 AI 执行复杂修复")

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

            IntField(
                title: "每日最大尝试次数",
                value: binding(
                    default: 2,
                    get: { $0.ai.maxAttemptsPerDay },
                    set: { $0.ai.maxAttemptsPerDay = $1 }
                ),
                unit: "次",
                range: 0...10
            )

            IntField(
                title: "冷却时间",
                value: binding(
                    default: 3600,
                    get: { $0.ai.cooldownSeconds },
                    set: { $0.ai.cooldownSeconds = $1 }
                ),
                unit: "秒",
                range: 0...86400
            )
        }
    }
}

@MainActor
struct AdvancedSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "异常检测", description: "日志模式分析和异常检测配置")

            Toggle(
                "启用异常检测",
                isOn: binding(
                    default: true,
                    get: { $0.anomalyGuard.enabled },
                    set: { $0.anomalyGuard.enabled = $1 }
                )
            )

            IntField(
                title: "分析窗口大小",
                value: binding(
                    default: 200,
                    get: { $0.anomalyGuard.windowLines },
                    set: { $0.anomalyGuard.windowLines = $1 }
                ),
                unit: "行",
                range: 50...1000
            )

            SectionHeader(title: "通知", description: "Discord 通知和 AI 询问行为")

            TextField(
                "通知渠道",
                text: binding(
                    default: "discord",
                    get: { $0.notify.channel },
                    set: { $0.notify.channel = $1 }
                )
            )

            TextField(
                "通知目标",
                text: binding(
                    default: "channel:YOUR_DISCORD_CHANNEL_ID",
                    get: { $0.notify.target },
                    set: { $0.notify.target = $1 }
                )
            )

            Picker(
                "通知级别",
                selection: binding(
                    default: "all",
                    get: { $0.notify.level },
                    set: { $0.notify.level = $1 }
                )
            ) {
                Text("全部事件").tag("all")
                Text("重要事件").tag("important")
                Text("仅关键").tag("critical")
            }
            .pickerStyle(.menu)

            Toggle(
                "AI 前询问",
                isOn: binding(
                    default: true,
                    get: { $0.notify.askEnableAi },
                    set: { $0.notify.askEnableAi = $1 }
                )
            )
        }
    }
}

@MainActor
struct IdSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Agent ID 配置", description: "用于会话控制和异常检测的 Agent ID（每行一个）")

            // Session Agents
            SectionHeader(title: "会话 Agents", description: "有权接收 /stop、/new 命令的 Agent ID 列表")

            TextField(
                "Session Agents (逗号分隔)",
                text: binding(
                    default: "",
                    get: { $0.repair.sessionAgents.joined(separator: ", ") },
                    set: { $0.repair.sessionAgents = $1.components(separatedBy: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty } }
                )
            )
            .textFieldStyle(.roundedBorder)

            SectionHeader(title: "Agent 角色别名", description: "用于异常检测的角色别名（每行一个别名）")

            // Orchestrator
            Text("Orchestrator")
                .font(.subheadline)
                .fontWeight(.medium)
            TextField(
                "Orchestrator 别名",
                text: binding(
                    default: "",
                    get: { $0.agentRoles.orchestrator.joined(separator: ", ") },
                    set: { $0.agentRoles.orchestrator = $1.components(separatedBy: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty } }
                )
            )
            .textFieldStyle(.roundedBorder)

            // Builder
            Text("Builder")
                .font(.subheadline)
                .fontWeight(.medium)
            TextField(
                "Builder 别名",
                text: binding(
                    default: "",
                    get: { $0.agentRoles.builder.joined(separator: ", ") },
                    set: { $0.agentRoles.builder = $1.components(separatedBy: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty } }
                )
            )
            .textFieldStyle(.roundedBorder)

            // Architect
            Text("Architect")
                .font(.subheadline)
                .fontWeight(.medium)
            TextField(
                "Architect 别名",
                text: binding(
                    default: "",
                    get: { $0.agentRoles.architect.joined(separator: ", ") },
                    set: { $0.agentRoles.architect = $1.components(separatedBy: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty } }
                )
            )
            .textFieldStyle(.roundedBorder)

            // Research
            Text("Research")
                .font(.subheadline)
                .fontWeight(.medium)
            TextField(
                "Research 别名",
                text: binding(
                    default: "",
                    get: { $0.agentRoles.research.joined(separator: ", ") },
                    set: { $0.agentRoles.research = $1.components(separatedBy: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty } }
                )
            )
            .textFieldStyle(.roundedBorder)

            SectionHeader(title: "Discord 配置", description: "Discord 通知目标设置")

            TextField(
                "通知目标 (格式: channel:CHANNEL_ID 或 user:USER_ID)",
                text: binding(
                    default: "",
                    get: { $0.notify.target },
                    set: { $0.notify.target = $1 }
                )
            )
            .textFieldStyle(.roundedBorder)

            TextField(
                "操作员 User IDs (逗号分隔)",
                text: binding(
                    default: "",
                    get: { $0.notify.operatorUserIds.joined(separator: ", ") },
                    set: { $0.notify.operatorUserIds = $1.components(separatedBy: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty } }
                )
            )
            .textFieldStyle(.roundedBorder)
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
        .padding(.bottom, 4)
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
        HStack {
            Text(title)
                .frame(width: 120, alignment: .leading)

            TextField("", value: $value, formatter: Self.formatter)
                .textFieldStyle(.roundedBorder)
                .frame(width: 80)
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

struct SettingsView_Previews: PreviewProvider {
    static var previews: some View {
        SettingsView()
            .environmentObject(ConfigManager.shared)
    }
}
