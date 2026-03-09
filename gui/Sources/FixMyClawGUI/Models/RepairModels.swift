import Foundation

// MARK: - Stage 映射

/// 将内部 repair stage 代号映射为用户可读文案
func localizedStageName(_ stage: String) -> String {
    switch stage {
    case "starting":
        return "启动中"
    case "pause":
        return "发送 PAUSE"
    case "pause_check":
        return "PAUSE 后复检"
    case "terminate":
        return "停止会话"
    case "new":
        return "重建会话"
    case "official":
        return "官方修复"
    case "backup":
        return "备份现场"
    case "ai_decision":
        return "等待 AI 审批"
    case "ai_config":
        return "AI 配置修复"
    case "ai_code":
        return "AI 代码修复"
    case "final":
        return "最终复检"
    case "completed":
        return "已完成"
    case "failed":
        return "失败"
    default:
        return stage
    }
}

// MARK: - 修复结果展示模型

enum RepairResultSource {
    case manual
    case background

    var label: String {
        switch self {
        case .manual:
            return "手动修复"
        case .background:
            return "后台修复"
        }
    }
}

struct RepairPresentation {
    let source: RepairResultSource
    let fingerprint: String
    let title: String
    let body: String
    let menuSummary: String
    let menuDetail: String?
    let stageLabel: String?
    let attemptLabel: String?
}

// MARK: - 修复历史记录

struct CheckHistoryItem: Identifiable {
    let id = UUID()
    let timestamp: Date
    let result: CheckPayload
}

struct RepairRecord: Identifiable {
    let id = UUID()
    let timestamp: Date
    let success: Bool
    let stage: String  // "pause" | "official" | "ai_config" | "ai_code" | "failed"
    let source: String // "auto" | "manual"
    let attemptDir: String
    
    var stageDescription: String {
        switch stage {
        case "pause": return "PAUSE 恢复"
        case "official": return "官方修复"
        case "ai_config": return "AI 配置修复"
        case "ai_code": return "AI 代码修复"
        case "failed": return "修复失败"
        default: return "未知"
        }
    }
    
    var icon: String {
        return success ? "✅" : "❌"
    }
}

// MARK: - RepairResult 扩展（用于展示）

extension RepairResult {
    var identityKey: String {
        if let attemptDir = details.attemptDir, !attemptDir.isEmpty {
            return "attempt:\(redactedAttemptIdentity(attemptDir))"
        }
        if details.alreadyHealthy == true {
            return "already_healthy"
        }
        if details.repairDisabled == true {
            return "repair_disabled"
        }
        if details.cooldown == true {
            return "cooldown:\(details.cooldownRemainingSeconds ?? -1)"
        }
        if let decision = details.aiDecision?.decision, !decision.isEmpty {
            return "ai_decision:\(decision)"
        }
        if let aiStage = details.aiStage, !aiStage.isEmpty {
            return "ai_stage:\(aiStage):fixed:\(fixed)"
        }
        if let backupBeforeAiError = details.backupBeforeAiError, !backupBeforeAiError.isEmpty {
            return "backup_error:\(backupBeforeAiError)"
        }
        return "attempted:\(attempted):fixed:\(fixed):used_ai:\(usedAi)"
    }

    func makePresentation(source: RepairResultSource) -> RepairPresentation {
        let finalNotice = cleanedRepairMessage(details.notifyFinal?.messageText)
        let notificationStatus = repairNotificationDeliveryLabel(details.notifyFinal)
        let attemptLabel = repairAttemptLabel(details.attemptDir)
        let stageLabel = derivedRepairStageLabel(details: details, attempted: attempted, fixed: fixed)

        let summary: String
        let body: String

        if details.alreadyHealthy == true {
            summary = "无需修复"
            body = finalNotice ?? "系统已处于健康状态，本轮未执行修复。"
        } else if details.repairDisabled == true {
            summary = "repair 已禁用"
            body = finalNotice ?? "repair.enabled=false，本轮未执行修复。"
        } else if details.cooldown == true {
            let remaining = details.cooldownRemainingSeconds.map { "\($0) 秒" } ?? "未知"
            summary = "冷却中"
            body = "修复冷却期尚未结束，剩余 \(remaining)。"
        } else if let backupBeforeAiError = details.backupBeforeAiError, !backupBeforeAiError.isEmpty {
            summary = "备份失败"
            body = finalNotice ?? "已收到 AI 修复批准，但备份失败：\(backupBeforeAiError)"
        } else if fixed, details.aiStage == "code" {
            summary = "AI 代码修复成功"
            body = finalNotice ?? "AI 代码修复后系统恢复健康。"
        } else if fixed, details.aiStage == "config" {
            summary = "AI 配置修复成功"
            body = finalNotice ?? "AI 配置修复后系统恢复健康。"
        } else if fixed, details.officialBreakReason == "healthy" {
            summary = "官方修复成功"
            body = finalNotice ?? "官方修复后系统恢复健康。"
        } else if fixed, details.pauseWaitSeconds != nil {
            summary = "PAUSE 复检已恢复"
            body = finalNotice ?? "发送 PAUSE 并复检后系统恢复健康。"
        } else if let aiDecision = details.aiDecision?.decision {
            switch aiDecision {
            case "rate_limited":
                summary = "AI 修复已限流"
                body = finalNotice ?? "已达到 AI 修复次数或冷却限制，本轮不进入 AI 修复。"
            case "no":
                summary = "已拒绝 AI 修复"
                body = finalNotice ?? "收到明确 no，本轮不进入 AI 修复。"
            case "timeout":
                summary = "AI 审批超时"
                body = finalNotice ?? "等待 AI 审批超时，本轮不进入 AI 修复。"
            case "invalid_limit":
                let invalidCount = details.aiDecision?.invalidReplies.map(String.init) ?? "多次"
                summary = "AI 审批无效"
                body = finalNotice ?? "连续 \(invalidCount) 次收到无效回复，本轮不进入 AI 修复。"
            case "send_failed":
                let error = details.aiDecision?.error ?? "未知错误"
                summary = "审批消息发送失败"
                body = finalNotice ?? "无法发送 AI 审批消息：\(error)"
            case "skip":
                summary = "已跳过 AI 审批"
                body = finalNotice ?? "notify.ask_enable_ai=false，本轮跳过 AI 修复审批。"
            default:
                summary = "未进入 AI 修复"
                body = finalNotice ?? "AI 审批阶段结束，decision=\(aiDecision)。"
            }
        } else if attempted, !fixed, details.officialBreakReason != nil, details.aiStage == nil {
            summary = "AI 修复已禁用"
            body = finalNotice ?? "官方修复后仍异常，且 ai.enabled=false，本轮停止。"
        } else if attempted, !fixed {
            summary = "修复结束但仍异常"
            body = finalNotice ?? "本轮修复已结束，但系统仍未恢复健康。"
        } else {
            summary = fixed ? "修复完成" : "修复结束"
            body = finalNotice ?? "已收到修复结果。"
        }

        let detail = joinRepairDetailParts([
            stageLabel.map { "结束阶段：\($0)" },
            notificationStatus,
        ])

        let icon = fixed ? "✅" : repairSummaryIcon(summary)
        return RepairPresentation(
            source: source,
            fingerprint: identityKey,
            title: "\(icon) \(source.label)：\(summary)",
            body: body,
            menuSummary: summary,
            menuDetail: detail,
            stageLabel: stageLabel,
            attemptLabel: attemptLabel,
        )
    }
}

// MARK: - 私有辅助函数

private func redactedAttemptIdentity(_ attemptDir: String) -> String {
    let standardizedPath = URL(fileURLWithPath: attemptDir).standardizedFileURL.path
    let basename = URL(fileURLWithPath: standardizedPath).lastPathComponent
    let safeBasename = basename.isEmpty ? "unknown" : basename
    let digest = stableIdentityHash(for: standardizedPath)
    return "\(safeBasename)#\(digest)"
}

private func stableIdentityHash(for value: String) -> String {
    var hash: UInt64 = 0xcbf29ce484222325
    for byte in value.utf8 {
        hash ^= UInt64(byte)
        hash &*= 0x100000001b3
    }
    return String(format: "%016llx", hash)
}

private func cleanedRepairMessage(_ message: String?) -> String? {
    guard let message else { return nil }
    let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    if trimmed.hasPrefix("fix-my-claw:") {
        let stripped = trimmed.dropFirst("fix-my-claw:".count)
        return String(stripped).trimmingCharacters(in: .whitespacesAndNewlines)
    }
    return trimmed
}

private func repairNotificationDeliveryLabel(_ payload: RepairNotificationPayload?) -> String? {
    guard let payload, let sent = payload.sent else { return nil }
    return sent ? "后端通知已发送" : "后端通知发送失败"
}

private func repairAttemptLabel(_ attemptDir: String?) -> String? {
    guard let attemptDir, !attemptDir.isEmpty else { return nil }
    return URL(fileURLWithPath: attemptDir).lastPathComponent
}

private func derivedRepairStageLabel(details: RepairDetails, attempted: Bool, fixed: Bool) -> String? {
    if details.alreadyHealthy == true || details.repairDisabled == true || details.cooldown == true {
        return nil
    }
    if details.backupBeforeAiError != nil {
        return localizedStageName("backup")
    }
    if let aiStage = details.aiStage, !aiStage.isEmpty {
        return localizedStageName("ai_\(aiStage)")
    }
    if details.aiDecision != nil {
        return localizedStageName("ai_decision")
    }
    if details.officialBreakReason != nil {
        return localizedStageName("official")
    }
    if fixed, details.pauseWaitSeconds != nil {
        return localizedStageName("pause_check")
    }
    if attempted {
        return localizedStageName("final")
    }
    return nil
}

private func joinRepairDetailParts(_ parts: [String?]) -> String? {
    let values = parts.compactMap { value -> String? in
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
    guard !values.isEmpty else { return nil }
    return values.joined(separator: " | ")
}

private func repairSummaryIcon(_ summary: String) -> String {
    if summary.contains("成功") || summary.contains("恢复") || summary.contains("无需") {
        return "✅"
    }
    if summary.contains("禁用") || summary.contains("冷却") || summary.contains("跳过") || summary.contains("拒绝") {
        return "⏸️"
    }
    return "⚠️"
}
