import AppKit
import SwiftUI

@MainActor
struct OpenClawSetupView: View {
    @EnvironmentObject var configManager: ConfigManager

    let guidanceMessage: String?
    let onComplete: @MainActor () -> Void

    @State private var draftCommand: String
    @State private var draftNodePath = ""
    @State private var isSaving = false
    @State private var saveError: String?

    init(
        initialCommand: String,
        guidanceMessage: String? = nil,
        onComplete: @escaping @MainActor () -> Void
    ) {
        self.guidanceMessage = guidanceMessage
        self.onComplete = onComplete
        _draftCommand = State(initialValue: initialCommand)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("配置 OpenClaw CLI")
                        .font(.title2)
                        .fontWeight(.semibold)

                    Text("fix-my-claw GUI 启动时不再依赖 PATH。请先填入 OpenClaw CLI 的绝对路径，保存后才会继续健康检查。")
                        .foregroundColor(.secondary)
                }

                VStack(alignment: .leading, spacing: 12) {
                    Text("怎么获取这个地址")
                        .font(.headline)

                    instructionRow(
                        title: "终端查路径",
                        detail: "在终端运行 `which openclaw`。如果没有输出，再试一次 `command -v openclaw`。"
                    )
                    instructionRow(
                        title: "复制完整结果",
                        detail: "把终端输出的整行路径粘贴到下面，例如 `/opt/homebrew/bin/openclaw`。"
                    )
                    instructionRow(
                        title: "也可以直接选文件",
                        detail: "点击下面的“选择文件”，在 Finder 里选中名为 `openclaw` 的可执行文件。"
                    )

                    if requiresManualNodePath {
                        instructionRow(
                            title: "Node 路径",
                            detail: "这个 OpenClaw 是 Node 脚本。请在终端运行 `which node`，把输出的绝对路径填到下面的 Node 字段。"
                        )
                    }

                    Text("常见安装位置: `/opt/homebrew/bin/openclaw`、`/usr/local/bin/openclaw`、`/opt/anaconda3/bin/openclaw`")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    if let supplementalMessage {
                        FormMessage(text: supplementalMessage.text, tone: supplementalMessage.tone)
                    }
                }
                .padding(16)
                .background(
                    RoundedRectangle(cornerRadius: 12)
                        .fill(Color.secondary.opacity(0.08))
                )

                VStack(alignment: .leading, spacing: 12) {
                    Text("OpenClaw CLI 绝对路径")
                        .font(.headline)

                    Text("把路径粘贴到这里，或直接选择文件。")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    HStack(alignment: .center, spacing: 12) {
                        TextField("/opt/homebrew/bin/openclaw", text: $draftCommand)
                            .textFieldStyle(.roundedBorder)
                            .font(.system(.body, design: .monospaced))

                        Button("选择文件") {
                            chooseExecutable()
                        }
                        .buttonStyle(.bordered)
                    }

                    FormMessage(text: statusMessage.text, tone: statusMessage.tone)

                    if requiresManualNodePath {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Node 绝对路径")
                                .font(.subheadline)
                                .fontWeight(.medium)

                            HStack(alignment: .center, spacing: 12) {
                                TextField("/opt/homebrew/bin/node", text: $draftNodePath)
                                    .textFieldStyle(.roundedBorder)
                                    .font(.system(.body, design: .monospaced))

                                Button("选择 Node") {
                                    chooseNodeExecutable()
                                }
                                .buttonStyle(.bordered)
                            }

                            FormMessage(text: nodeStatusMessage.text, tone: nodeStatusMessage.tone)
                        }
                    }

                    if let saveError, !saveError.isEmpty {
                        FormMessage(text: saveError, tone: .warning)
                    }
                }
                .padding(16)
                .background(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(Color.secondary.opacity(0.18), lineWidth: 1)
                )

                HStack {
                    Spacer()

                    Button("保存并继续") {
                        saveAndContinue()
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(normalizedPath == nil || isSaving)
                }
            }
            .padding(24)
        }
        .frame(minWidth: 720, minHeight: 420)
    }

    private var statusMessage: (text: String, tone: FormMessageTone) {
        switch OpenClawCommandValidator.assess(draftCommand, explicitNodePath: effectiveNodeOverride) {
        case .valid(let normalizedPath):
            return ("将保存为: \(normalizedPath)", .info)
        case .validNodeScript(let normalizedPath, let nodePath):
            return ("检测到 Node 版 OpenClaw。保存时会自动生成固定 launcher，并使用 \(nodePath) 启动 \(normalizedPath)。", .info)
        case .requiresNodePath(_, let message):
            return (message, .warning)
        case .requiresSetup(let message):
            return (message, .warning)
        }
    }

    private var normalizedPath: String? {
        switch OpenClawCommandValidator.assess(draftCommand, explicitNodePath: effectiveNodeOverride) {
        case .valid(let normalizedPath):
            return normalizedPath
        case .validNodeScript(let normalizedPath, _):
            return normalizedPath
        case .requiresNodePath, .requiresSetup:
            return nil
        }
    }

    private var requiresManualNodePath: Bool {
        if case .requiresNodePath = OpenClawCommandValidator.assess(draftCommand) {
            return true
        }
        return false
    }

    private var effectiveNodeOverride: String? {
        let trimmed = draftNodePath.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private var nodeStatusMessage: (text: String, tone: FormMessageTone) {
        switch OpenClawCommandValidator.assessNodePath(draftNodePath) {
        case .valid(let normalizedPath):
            return ("将使用 Node: \(normalizedPath)", .info)
        case .validNodeScript, .requiresNodePath:
            return ("Node 路径校验出现了意外状态。", .warning)
        case .requiresSetup(let message):
            return (message, .warning)
        }
    }

    private var supplementalMessage: (text: String, tone: FormMessageTone)? {
        guard let guidanceMessage, !guidanceMessage.isEmpty else {
            return nil
        }
        guard guidanceMessage != statusMessage.text else {
            return nil
        }
        return (guidanceMessage, .warning)
    }

    private func chooseExecutable() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.resolvesAliases = true
        panel.title = "选择 OpenClaw CLI"
        panel.prompt = "选择"

        if let normalizedPath, !normalizedPath.isEmpty {
            panel.directoryURL = URL(fileURLWithPath: (normalizedPath as NSString).deletingLastPathComponent, isDirectory: true)
            panel.nameFieldStringValue = (normalizedPath as NSString).lastPathComponent
        }

        guard panel.runModal() == .OK, let url = panel.url else { return }
        draftCommand = url.path
        saveError = nil
    }

    private func chooseNodeExecutable() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.resolvesAliases = true
        panel.title = "选择 Node"
        panel.prompt = "选择"

        guard panel.runModal() == .OK, let url = panel.url else { return }
        draftNodePath = url.path
        saveError = nil
    }

    private func saveAndContinue() {
        guard !isSaving else { return }

        Task {
            isSaving = true
            defer { isSaving = false }

            do {
                let savedPath = try await configManager.saveOpenClawCommand(
                    draftCommand,
                    nodePathOverride: effectiveNodeOverride
                )
                draftCommand = savedPath
                saveError = nil
                onComplete()
            } catch {
                saveError = error.localizedDescription
            }
        }
    }

    @ViewBuilder
    private func instructionRow(title: String, detail: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(title)
                .font(.subheadline)
                .fontWeight(.medium)
                .frame(width: 84, alignment: .leading)

            Text(detail)
                .font(.subheadline)
                .foregroundColor(.primary)
        }
    }
}
