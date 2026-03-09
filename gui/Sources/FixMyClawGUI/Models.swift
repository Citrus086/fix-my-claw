import Foundation

// MARK: - 模型兼容层
// 本文件是过渡兼容层，所有模型定义已迁移到 Models/ 目录下的独立文件。
// 由于所有文件都在同一模块内，类型自动可见，无需显式导入。
//
// 模型文件组织：
// - Models/CLIPayloads.swift: CLI 输出模型 (StatusPayload, CheckPayload, etc.)
// - Models/ConfigModels.swift: 配置模型 (AppConfig, MonitorConfig, etc.)
// - Models/LegacyServiceState.swift: 旧 ServiceState 兼容层
// - Models/RepairModels.swift: 修复相关模型和展示逻辑
// - Models/CLIError.swift: CLI 错误类型
//
// 注意：此文件保留是为了标记迁移完成，并作为目录结构的文档说明。
// 后续可以安全删除此文件，所有类型已通过独立文件暴露。

// 文件保留作为迁移标记，内容已移至 Models/ 目录
