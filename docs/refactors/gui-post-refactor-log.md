# Fix-My-Claw GUI 前端重构收尾执行日志

## 使用说明
- 每个新窗口开始前，先读计划文档，再读本日志。
- 任意时刻只允许一个步骤处于 `in_progress`。
- 如果需要偏离计划，先在“变更建议记录”登记，再更新计划文档，不要直接实施。
- 本日志记录事实，不记录臆测。

配套计划文档:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-post-refactor-plan.md`

## 当前状态总览

| Step | 名称 | 状态 | 执行人 | 开始时间 | 结束时间 | Gate |
|------|------|------|--------|----------|----------|------|
| 0 | 审计与基线冻结 | done | Codex | 2026-03-09 | 2026-03-09 | passed |
| 1 | 运行态状态感知修复 | done | Claude | 2026-03-09 | 2026-03-09 | passed |
| 2 | 修复结果与进度展示对齐 | done | Codex | 2026-03-09 | 2026-03-09 | passed |
| 3 | 设置页 schema 覆盖补齐 | done | Codex | 2026-03-09 | 2026-03-09 | passed |
| 4 | 默认值与解码韧性收敛 | pending | - | - | - | - |
| 5 | GUI/CLI 合同测试补强 | pending | - | - | - | - |
| 6 | 验证与文档收尾 | pending | - | - | - | - |

状态约定:
- `pending`: 未开始
- `in_progress`: 正在执行
- `blocked`: 有阻塞，禁止进入下一步
- `done`: gate 已通过
- `rolled_back`: 已回滚

## 锁组占用

| 锁组 | 涉及文件 | 当前持有者 | 备注 |
|------|----------|------------|------|
| gui-runtime | `CLIWrapper.swift`、`MenuBarManager.swift`、`MenuBarController.swift` | - | Step 1 已完成；Step 2 增量修改了 `CLIWrapper.swift`、`MenuBarManager.swift` |
| gui-settings | `Models.swift`、`SettingsView.swift`、`ConfigManager.swift` | - | Step 3 已完成；设置页覆盖与保存路径已更新 |
| gui-contract | `tests/test_gui_cli_support.py`、`gui/Package.swift`、未来 `gui/Tests/` | - | 当前只有基线验证 |
| docs | `docs/refactors/` | Codex | Step 3 收尾，仅更新执行日志 |

## 执行记录

### Step 0: 审计与基线冻结
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-post-refactor-plan.md` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-post-refactor-log.md` (新建)

执行内容:
- [x] 审计 GUI runtime、settings、Swift model 与 Python 契约
- [x] 核对 `status/check/repair/config/service status` 的 JSON 结构
- [x] 核对 Swift 配置模型与 Python dataclass 的字段/默认值
- [x] 运行编译和测试基线命令
- [x] 输出本轮 GUI 收尾计划与日志

命令记录:
```bash
swift build
python -m pytest tests/test_gui_cli_support.py -q
python -m pytest tests/test_anomaly_guard.py -q
git status --short
```

结果摘要:
```text
swift build:
- Build complete! (0.17s)

tests/test_gui_cli_support.py:
- 9 passed in 0.13s

tests/test_anomaly_guard.py:
- 79 passed in 14.10s

git status --short:
- 审计开始前工作树干净
```

### 审计发现

#### 发现 1: GUI 冷启动时会乐观地把系统判成健康
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:313-331`

事实:
- `syncStatus()` 只读 `status --json` 的启停状态，然后把 `isHealthy` 设成 `lastCheckResult?.healthy ?? true`。
- 这意味着只要 GUI 还没有主动做过 `check --json`，健康态就默认是 `true`。
- 后端 `status --json` 本身不提供健康位，因此当前实现是在“没有证据时默认绿色”。

影响:
- GUI 冷启动、从睡眠恢复、后台服务在 GUI 外完成修复/失败后的状态，都可能被 GUI 误判。

结论:
- 这是 Step 1 的 P1 问题，必须先修。

#### 发现 2: 菜单栏按钮本身不会显示“修复中”
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarController.swift:43-47`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:68-73`

事实:
- `statusTitle` 已经能在 `currentRepairStage` 存在时返回 `🟡 修复中...(stage)`。
- 但 `updateStatusItem()` 只把 `manager.state.icon` 写到 `statusItem.button?.title`，`statusTitle` 只进了 tooltip。

影响:
- 用户从菜单栏第一眼看到的仍然是健康/异常图标，而不是“修复中”。
- 这和后端新增的阶段化 repair_progress 设计目标不一致。

结论:
- 这是 Step 1 的 P1 问题，应与状态感知一起处理。

#### 发现 3: RepairResult.details 只解码了最小子集，GUI 基本没有消费 post-refactor 阶段信息
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/CLIWrapper.swift:294-322`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:388-410`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair_types.py:177-252`

事实:
- GUI 目前只解码了 `attempt_dir`、`reason`、`already_healthy`、`repair_disabled`、`cooldown`、`cooldown_remaining_seconds`。
- 后端现在会在 `details` 里输出 `ai_decision`、`official_break_reason`、`backup_before_ai_error`、`ai_stage`、`notify_final`、`context_after_*` 等大量 legacy keys。
- `sendRepairNotification()` 仍然只会显示“成功 / 未成功 / 跳过”三类泛化结果。

影响:
- GUI 无法解释“为什么没修”“卡在哪个阶段”“AI 分支是被禁用、限流、拒绝，还是备份失败”。
- post-refactor 阶段化结果对 GUI 几乎没有产生价值。

结论:
- 这是 Step 2 的 P1 问题。

#### 发现 4: 设置页只覆盖了配置模型的一部分，很多重构后的关键字段仍然没有 GUI 入口
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/SettingsView.swift:141-495`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config.py:201-380`

事实:
- 当前设置页主要覆盖:
  - monitor 的间隔/超时/冷却/日志级别/日志路径
  - repair 的 enabled / session_control / soft_pause / pause_wait / step_timeout
  - ai 的 enabled / allow_code_changes / max_attempts_per_day / cooldown
  - anomaly_guard 的 enabled / window_lines
  - notify 的 channel / target / level / ask_enable_ai / operator_user_ids
- 但 `openclaw.*`、`repair.official_steps`、`repair.pause_message`、`notify.account`、`notify.silent`、`notify.*timeout`、`ai.args`、`ai.args_code`、大量 anomaly guard 阈值/关键词等都还没有 GUI 控件。

影响:
- GUI 目前只能称为“部分配置面板”，不能称为“重构后完整前端”。
- 用户为了改核心行为仍要回到 TOML 手工编辑。

结论:
- 这是 Step 3 的 P1 问题。

#### 发现 5: Swift 默认值与 Python 默认值仍有多处 drift
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift:198-254`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config.py:202-297`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config.py:357-380`

已确认 drift:
- `repair.session_agents`
- `repair.pause_message`
- `anomaly_guard.keywords_stop`
- `anomaly_guard.keywords_repeat`
- `anomaly_guard.keywords_dispatch`
- `anomaly_guard.keywords_architect_active`
- `ai.args`
- `ai.args_code`

影响:
- 目前因为 GUI 主要依赖 `config show --json` 的归一化结果，所以这些 drift 还没有全部直接炸出来。
- 但只要未来某些字段缺省、局部 decode、或者 GUI 需要本地构造默认值，这些 drift 就会重新变成行为差异。

结论:
- 这是 Step 4 的 P1/P2 交界问题，不能继续放着。

#### 发现 6: NotifyConfig 在 GUI 端仍然漏掉了 Python 已暴露的字段
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config.py:305-329`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift:282-309`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config.py:523-547`

事实:
- Python `NotifyConfig` dataclass 已包含:
  - `manual_repair_keywords`
  - `ai_approve_keywords`
  - `ai_reject_keywords`
- Swift `NotifyConfig` 没有这三个字段。
- 同时，当前 `_parse_notify()` 也没有把这三个字段接进配置解析结果。

影响:
- 这三个字段现在不属于纯 GUI 缺失，而是 GUI/CLI 配置契约共同未闭环。
- 只修 GUI 没用；只修 parser 也不够。需要把它记录成联动依赖。

结论:
- 本项先记为 Step 3 的 blocked dependency，不在 GUI 侧单独宣称完成。

#### 发现 7: 自定义 `monitor.state_dir` 场景下，GUI 在配置加载前可能看不到早期审批/修复文件
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:588-613`

事实:
- `approvalStateDirectoryURL()` 在配置未加载完成前会回退到 `~/.fix-my-claw`。
- 如果用户把 `monitor.state_dir` 配到别处，而 GUI 启动时后端已经写入审批/修复进度文件，GUI 前几轮轮询可能会看不到它们。

影响:
- 这是边界场景，不会影响默认路径，但会影响“自定义状态目录 + GUI 冷启动 + 正好有活跃审批/修复”的组合。

结论:
- 这是 Step 1 / Step 4 的 P2 问题。

### Step 1: 运行态状态感知修复
执行日期: 2026-03-09
执行人: Claude
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarController.swift`

执行内容:
- [x] 扩展 ServiceState 模型，添加 `repairing` 和 `awaitingApproval` 状态
- [x] 添加 `localizedStageName()` 函数将内部 stage 代号映射为用户可读文案
- [x] 修复 `syncStatus()` 中的乐观推断：不再使用 `lastCheckResult?.healthy ?? true`
- [x] 添加 `performInitialHealthCheck()` 在启动时主动做一次真实健康检查
- [x] 添加 `effectiveState` 计算属性，综合考虑修复中/审批中/健康态
- [x] 更新 `statusTitle` 使用 stage 映射显示用户可读文案
- [x] 修改 `updateStatusItem()` 使用 `effectiveState.icon` 让菜单栏图标真正反映修复中/审批中状态
- [x] 建立分层轮询策略：
  - 快速轮询（30秒）：服务状态 `refreshStatus()`
  - 低频轮询（5分钟）：真实健康检查 `periodicHealthCheck()`
  - 高频轮询（1秒）：修复进度 `pollRepairProgress()`
  - 中频轮询（2秒）：AI 审批 `pollApprovalRequest()`
- [x] 在 `buildMenu()` 中添加对 `.repairing` 和 `.awaitingApproval` 状态的处理

命令记录:
```bash
swift build
python -m pytest tests/test_gui_cli_support.py -q
```

结果摘要:
```text
swift build:
- Build complete! (3.08s)

tests/test_gui_cli_support.py:
- 9 passed in 0.05s
```

### 本次修改解决的审计发现
- **发现 1 (GUI 冷启动时乐观健康态)**: 已修复
  - `syncStatus()` 不再默认假设健康，没有检查结果时保持 `unknown` 状态
  - 添加 `performInitialHealthCheck()` 在启动时主动执行真实健康检查

- **发现 2 (菜单栏按钮不显示修复中)**: 已修复
  - 添加 `effectiveState` 综合计算状态
  - `updateStatusItem()` 使用 `effectiveState.icon`
  - 菜单栏图标现在能显示 🔧(修复中) 和 ❓(等待审批)

### 关键代码变更

**Models.swift:345-423**
```swift
enum ServiceState: Equatable {
    // ... 新增 repairing 和 awaitingApproval
    case repairing        // 修复中
    case awaitingApproval // 等待 AI 审批
}

func localizedStageName(_ stage: String) -> String {
    // 将 "starting", "ai_decision" 等映射为 "启动中", "等待 AI 审批" 等
}
```

**MenuBarManager.swift:359-391**
```swift
private func syncStatus() async {
    // 关键修复：不再乐观假设健康
    guard let checkResult = lastCheckResult else {
        state = .unknown
        return
    }
    // ...
}
```

**MenuBarManager.swift:393-434**
```swift
private func startPolling() {
    // 分层轮询策略
    statusTimer = Timer.scheduledTimer(withTimeInterval: 30, ...)   // 服务状态
    checkTimer = Timer.scheduledTimer(withTimeInterval: 300, ...)   // 健康检查
    repairProgressTimer = Timer.scheduledTimer(withTimeInterval: 1, ...) // 修复进度
    approvalTimer = Timer.scheduledTimer(withTimeInterval: 2, ...)  // AI 审批
}
```

### 完成门检查
- [x] GUI 冷启动后，在 OpenClaw 实际异常时不会默认显示绿色
- [x] 修复进行中时，菜单栏图标、tooltip、菜单标题三处状态一致
- [x] AI 审批等待时，GUI 有显式状态（❓ 图标 + "等待 AI 审批..." 文案）

下一步建议:
- 可以进入 Step 2: 修复结果与进度展示对齐
- Step 2 需要扩展 RepairDetails 消费更多 post-refactor 字段

是否可进入下一步: 是，Step 1 Gate 已通过，可以开始 Step 2

### Step 2: 修复结果与进度展示对齐
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/CLIWrapper.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/shared.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair_state_machine.py`

执行内容:
- [x] 扩展 `RepairDetails` 解码，消费 `ai_decision`、`ai_stage`、`official_break_reason`、`backup_before_ai_error`、`notify_final`、`attempt_dir`
- [x] 新增 GUI 本地结果归类与文案映射，区分:
  - 已健康，无需修复
  - repair disabled
  - cooldown
  - AI disabled
  - AI rate limited
  - no approval / explicit no
  - backup error
  - official 修复成功
  - AI config 成功
  - AI code 成功
  - 最终仍不健康
- [x] 菜单栏菜单新增“最近手动修复 / 最近后台修复”结果摘要、结束阶段、尝试目录展示
- [x] 手动修复完成后立即执行真实健康检查，避免 GUI 继续停留在旧的健康态
- [x] 后台修复结束时，GUI 通过进度文件消失 + 立即健康检查 + 结果快照读取三段式收敛终态
- [x] 新增只读型 `repair_result.json` 快照，用于补齐后台修复最终结果来源
- [x] 保持既有 `repair_progress.json` 事件序列不变，避免扩大后端进度契约

设计说明:
- 评估结论：仅靠 `repair_progress.json` 不能可靠还原后台修复“为什么结束”，因为它只表示当前阶段，不持久化最终结果。
- 实施方案：不改 CLI 输出字段名，不改既有 progress 文件名和基础字段；新增只读型 `repair_result.json`，内容为带时间戳的最近一次 `repair --json` 结果快照，GUI 直接读取。
- 放弃方案：本轮未扩写 `repair_progress.json` 的阶段事件范围，避免把现有 Python 测试已冻结的 progress 序列变成隐式破坏性变更。

命令记录:
```bash
swift build --package-path gui
python -m pytest tests/test_gui_cli_support.py -q
python -m pytest tests/test_anomaly_guard.py -q
```

结果摘要:
```text
swift build --package-path gui:
- Build complete! (0.90s)

tests/test_gui_cli_support.py:
- 9 passed in 0.36s

tests/test_anomaly_guard.py:
- 81 passed in 24.99s
```

关键结果:
- 手动触发修复:
  - 不再只弹“成功 / 失败 / 跳过”三类泛化通知
  - 会根据 `RepairDetails` 生成精确分类文案，并在修复后立即刷新真实健康态
- 后台服务触发修复:
  - 开始/进行中仍沿用现有 `repair_progress.json`
  - 结束后通过 `repair_result.json` 读取最终分类，并立刻做一次真实健康检查更新 GUI 状态
- GUI 菜单项:
  - 新增最近一次修复结果摘要
  - 可见结束阶段、本轮说明、尝试目录 basename
  - 明确区分“手动修复”与“后台修复”来源

完成门检查:
- [x] 同一条修复链路的用户提示不再只剩泛化的“已尝试修复但问题仍存在”
- [x] GUI 可以指出本轮最终停在审批/备份/官方修复/AI config/AI code/最终复检等终态语义
- [x] 后台服务触发修复时，GUI 至少能看到开始、进行中和结束后的真实系统状态

下一步建议:
- 进入 Step 3: 设置页 schema 覆盖补齐
- Step 3 继续保留 blocked 依赖：`notify.manual_repair_keywords` / `notify.ai_approve_keywords` / `notify.ai_reject_keywords` 仍未接回 Python `_parse_notify()`，GUI 不应先行暴露可编辑入口
- Step 3 实现时继续遵守“高频字段表单 + 低频复杂字段原始编辑”边界，优先补 `openclaw.*`、`repair.*`、`notify.*timeout`、`ai.args*` 与 `anomaly_guard` 高价值字段

是否可进入下一步: 是，Step 2 Gate 已通过，可以开始 Step 3

### Step 3: 设置页 schema 覆盖补齐
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/SettingsView.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/ConfigManager.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift`

执行前复核:
- [x] 复核 Step 1 / Step 2 代码与 gate，确认两步已真实完成
- [x] 复核 `git status`，本轮仅写 `gui-settings` 锁组文件
- [x] 复核当前 `src/fix_my_claw/config.py`，确认 `notify.manual_repair_keywords` / `notify.ai_approve_keywords` / `notify.ai_reject_keywords` 已接入 `_parse_notify()`；此前日志里的 blocked 依赖在当前工作树中已解除

执行内容:
- [x] 将设置页扩展为“高频字段表单 + 低频复杂字段多行编辑”的混合结构
- [x] 补齐 `monitor.log_max_bytes`、`monitor.log_backup_count`、`monitor.log_retention_days`
- [x] 补齐 `openclaw.command`、`openclaw.state_dir`、`openclaw.workspace_dir`、`openclaw.health_args`、`openclaw.status_args`、`openclaw.logs_args`
- [x] 补齐 `repair.session_active_minutes`、`repair.pause_message`、`repair.terminate_message`、`repair.new_message`、`repair.session_command_timeout_seconds`、`repair.session_stage_wait_seconds`、`repair.official_steps`、`repair.post_step_wait_seconds`
- [x] 补齐 `notify.account`、`notify.silent`、`notify.send_timeout_seconds`、`notify.read_timeout_seconds`、`notify.ask_timeout_seconds`、`notify.poll_interval_seconds`、`notify.read_limit` 与通知关键词列表
- [x] 补齐 `ai.provider`、`ai.command`、`ai.model`、`ai.timeout_seconds`、`ai.args`、`ai.args_code`
- [x] 补齐 `anomaly_guard` 下的关键词和阈值字段
- [x] 将 `session_agents`、`operator_user_ids`、Agent 角色别名改为每行一个的多行编辑
- [x] 调整配置保存路径：保存时基于 CLI 原始 JSON 深度合并，再执行 `config set --json`，避免 GUI 覆盖未触碰字段

设计说明:
- 复杂数组/命令列表不再塞进单行 `TextField`。
- `official_steps` 使用“每行一条命令”的原始编辑；`args` / `args_code` / `health_args` 等参数数组使用“每行一个参数”的原始编辑。
- `ConfigManager` 不再只依赖 Swift `AppConfig` 重新编码；保存时会保留 CLI 原始配置里未被 GUI 当前模型覆盖的键，降低字段丢失风险。

命令记录:
```bash
git status --short
swift build --package-path gui
python -m pytest tests/test_gui_cli_support.py -q
```

结果摘要:
```text
swift build --package-path gui:
- Build complete! (15.47s)
- Build complete! (5.55s)

tests/test_gui_cli_support.py:
- 9 passed in 0.14s
- 9 passed in 0.10s

git status --short:
- 本轮新增改动仅落在 `gui-settings` 锁组；其余 dirty 文件来自 Step 1 / Step 2 既有工作树
```

关键结果:
- 设置页现在已覆盖 monitor / openclaw / repair / notify / ai / anomaly_guard / agent_roles 的当前高价值字段。
- 用户不再需要为本轮 plan 列出的 post-refactor 核心能力频繁回到 TOML 手工修改。
- 保存时会对原始 JSON 做深度合并，已有但当前 UI 没有直接渲染的键不会因为一次保存被静默抹掉。

完成门检查:
- [x] `config show --json` 当前主要字段已具备 GUI 入口，复杂值使用多行原始编辑
- [x] post-refactor 核心配置项已不再局限于 TOML 手改
- [x] 保存路径已降低“未触碰字段被改写/丢失”的风险

下一步建议:
- 进入 Step 4: 默认值与解码韧性收敛
- Step 4 重点先处理已审计出的默认值 drift：`repair.session_agents`、`repair.pause_message`、`anomaly_guard.keywords_*`、`ai.args`、`ai.args_code`
- 在 Step 4 顺手评估 `AgentRolesConfig` 对额外自定义 role key 的 decode/展示策略，决定是显式建模还是继续依赖 raw merge 保留

是否可进入下一步: 是，Step 3 Gate 已通过，可以开始 Step 4

### 本轮审计后的优先级排序
P1:
1. 修复健康态乐观推断
2. 让菜单栏真正显示修复中/审批中
3. 扩展 repair result 消费与展示
4. 补齐设置页对 post-refactor 核心配置的覆盖
5. 收敛 Swift 默认值 drift

P2:
1. 解决自定义 `state_dir` 的冷启动竞态
2. 建立 Swift 侧 decode 契约测试

P3:
1. 复杂配置编辑控件的易用性优化

问题记录:
- 当前无 Step 3 实现阻塞。
- Step 4 之前仍有默认值 drift 与 decode 韧性缺口，尤其是 `pause_message`、`session_agents`、`keywords_*`、`ai.args*`。

下一步建议:
- 以 Step 3 执行记录为新基线，下一步进入 Step 4。
- 后续步骤仍不要同时写 `gui-runtime` 与 `gui-settings` 的同一文件。

是否可进入下一步: 是，当前可进入 Step 4

## 变更建议记录
- 暂无
