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

struct SettingsView_Previews: PreviewProvider {
    static var previews: some View {
        SettingsView()
            .environmentObject(ConfigManager.shared)
    }
}
