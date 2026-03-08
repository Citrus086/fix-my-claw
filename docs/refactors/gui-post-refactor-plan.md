# Fix-My-Claw GUI 前端重构收尾计划

## 版本信息
- 创建日期: 2026-03-09
- 计划版本: v1.3.x
- 当前状态: pending
- 目标周期: 3-5 天
- 风险等级: 中

## 文档用途
这是 GUI 前端在后端 repair/runtime/config 重构完成后的唯一计划文档。所有窗口在开始执行前都必须先读完本文件，再读执行日志。

配套日志文件:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-post-refactor-log.md`

如果计划需要变更，先在日志里登记变更建议，再回到本文件修改。不要在实现过程中默默改范围、改顺序或改兼容约束。

## 本次审计的结论
当前 GUI 可以正常编译，也能与当前 CLI 通信，但它仍然保留了几处“重构前假设”:
- 运行态状态判断仍然偏乐观，GUI 会在没有真实健康检查结果时默认展示健康。
- 修复流程已经被后端拆成更细的阶段与 legacy details，但 GUI 仍然只消费极少数字段。
- 设置页只覆盖了部分配置；很多重构后新增或重新重要化的字段仍然只能手改 TOML。
- Swift 端仍然维护了一套手写默认值和解码逻辑，和 Python dataclass 默认值存在 drift。

额外说明:
- `notify.manual_repair_keywords`、`notify.ai_approve_keywords`、`notify.ai_reject_keywords` 已经出现在 Python `NotifyConfig` dataclass 中，但当前 `_parse_notify()` 还没有把这三个字段接回配置解析路径。这意味着它们不是纯 GUI 问题，而是 GUI/配置契约的联动缺口。GUI 侧需要记录并绕开这个风险，不能单独声称“通知配置已完全对齐”。

## 重构目标
将 `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/` 从“能调用 CLI 的最小壳层”提升为“与当前后端结构对齐的稳定控制面板”。

最终目标:
- GUI 的健康态、修复态、审批态展示建立在真实后端状态上，而不是乐观推断。
- GUI 能消费 post-refactor repair 结果中的关键信息，并向用户展示明确的阶段和失败原因。
- GUI 保存配置时不会静默丢失当前 CLI 已暴露的字段。
- GUI 设置页要么覆盖全部 `config show --json` 字段，要么对剩余字段提供明确的高级原始编辑入口。
- GUI 的 Swift 模型不再靠零散手写默认值维持兼容，而是具备更强的 decode 韧性。

## 核心原则
1. 不破坏 CLI 契约。`status --json`、`check --json`、`repair --json`、`config show --json`、`config set --json`、`service status --json` 的字段名默认保持兼容。
2. 不把“现在能 decode”误判为“已经前后端对齐”。只要 GUI 没有展示、编辑或验证一个字段，就仍然算未对齐。
3. GUI 的状态显示必须优先追求正确，再追求少轮询。宁可额外做一次真实检查，也不能在异常时点亮绿色。
4. 复杂配置优先做“高频字段表单 + 低频字段原始编辑”的混合方案，而不是为了看起来整洁而继续藏掉关键字段。
5. 测试要冻结契约，不只验证能编译，还要验证重构后新增字段不会被 GUI 保存时吃掉。

## 行为冻结
以下行为不允许改变，除非本计划明确更新:
- `config show --json` / `config set --json` 的现有结构与字段名
- `status --json` / `check --json` / `repair --json` / `service status --json` 的现有结构与字段名
- `repair_progress.json`、`ai_approval.active.json`、`ai_approval.decision.json` 的文件名和基础字段
- GUI 默认配置路径仍为 `~/.fix-my-claw/config.toml`
- 后端 repair stage 名称与顺序
- 现有 Python 测试通过状态
- `swift build` 可通过

## 锁组
- `gui-runtime`: `CLIWrapper.swift`、`MenuBarManager.swift`、`MenuBarController.swift`
- `gui-settings`: `Models.swift`、`SettingsView.swift`、`ConfigManager.swift`
- `gui-contract`: `tests/test_gui_cli_support.py`、`gui/Package.swift`、未来新增的 `gui/Tests/`
- `docs`: `docs/refactors/`

同一时间只允许一个窗口写同一锁组。开始实现前先看计划、日志和当前 `git status`。

## 执行顺序
0. 审计与基线冻结
1. 运行态状态感知修复
2. 修复结果与进度展示对齐
3. 设置页 schema 覆盖补齐
4. 默认值与解码韧性收敛
5. GUI/CLI 合同测试补强
6. 验证与文档收尾

## 步骤详情

### Step 0: 审计与基线冻结
状态: done

目标:
- 记录当前 GUI 与 CLI 的真实契约状态。
- 把“必须改”和“建议改”分开，避免后续范围膨胀。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-post-refactor-plan.md`
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-post-refactor-log.md`

执行内容:
1. 逐文件审计 GUI runtime、settings、Swift model。
2. 对照 Python `config.py`、`repair_types.py`、`health.py`、`cli.py` 的 JSON/TOML 契约。
3. 运行 `swift build`、`tests/test_gui_cli_support.py`、`tests/test_anomaly_guard.py` 作为基线。
4. 记录所有明确发现的问题和依赖项。

完成 gate:
- 审计结论已落日志
- 验证命令结果已记录
- 后续步骤的输入和范围已冻结

回滚:
- 只删除本次新增文档

### Step 1: 运行态状态感知修复
状态: pending
前置依赖: Step 0

目标:
- 去掉 GUI 对健康态的乐观推断。
- 让菜单栏图标和 tooltip 真实反映“健康 / 异常 / 修复中 / 等待 AI 审批”。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarController.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/CLIWrapper.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift`
- 如纯前端方案不够，再评估只读型后端扩展:
  - `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/cli.py`

必须完成:
- 不再使用 `lastCheckResult?.healthy ?? true` 作为健康态来源。
- 为“启动后首次状态同步”建立真实健康检查路径。
- 为轮询建立清晰分层:
  - 服务安装/运行状态
  - 监控启停状态
  - 健康状态
  - 修复中 / 审批中瞬时状态
- 菜单栏图标本身要能反映 `currentRepairStage` / `pendingAiRequest`，不能只把信息藏在 tooltip。
- stage 内部代号要映射为用户可读文案，而不是直接显示 `starting`、`ai_decision` 之类的原始字符串。

建议实现顺序:
1. 优先尝试纯 GUI 方案:
   - 启动时主动做一次 `check --json`
   - 轮询时区分慢速 `status` 和低频 `check`
2. 如果 `check` 成本不可接受，再设计新的只读 summary 契约，并先写日志再改计划。

完成 gate:
- GUI 冷启动后，在 OpenClaw 实际异常时不会默认显示绿色。
- 修复进行中时，菜单栏图标、tooltip、菜单标题三处状态一致。
- AI 审批等待时，GUI 有显式状态，而不是只靠弹窗。

回滚:
- 恢复 GUI runtime 文件到当前基线

### Step 2: 修复结果与进度展示对齐
状态: pending
前置依赖: Step 1

目标:
- 让 GUI 能理解 post-refactor repair 结果，而不是只显示“成功 / 失败 / 跳过”三种粗粒度结果。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/CLIWrapper.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift`
- 如当前契约不足以支持后台修复结果展示，可评估新增只读型结果落盘或查询入口:
  - `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/shared.py`
  - `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair_state_machine.py`
  - `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/cli.py`

必须完成:
- 扩展 `RepairDetails`，至少消费这些高价值字段:
  - `ai_decision`
  - `ai_stage`
  - `official_break_reason`
  - `backup_before_ai_error`
  - `notify_final`
  - `attempt_dir`
- GUI 通知与菜单项要能区分:
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
- `repair_progress.json` 的阶段展示要做本地映射，不显示原始内部 stage id。
- 明确“GUI 手动触发修复”和“后台服务触发修复”两种场景的最终结果来源。

注意:
- 如果仅靠 `repair_progress.json` 无法可靠还原后台修复最终结果，就不要继续在 GUI 里猜。先记录契约缺口，再补一个只读结果来源。

完成 gate:
- 同一条修复链路的用户提示不再只剩泛化的“已尝试修复但问题仍存在”。
- GUI 可以明确指出最终停在哪个阶段，以及为什么停下。
- 后台服务触发修复时，GUI 至少能看到开始、进行中和结束后的真实系统状态。

回滚:
- 恢复 repair result 相关 Swift 文件到基线

### Step 3: 设置页 schema 覆盖补齐
状态: pending
前置依赖: Step 0

目标:
- 让 GUI 对后端配置结构的覆盖从“部分可调”提升为“全部字段可控或可见”。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/SettingsView.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/ConfigManager.swift`

必须完成:
- 定义“高频字段表单 + 低频复杂字段原始编辑”的边界，避免设置页无限膨胀。
- 至少补齐这些重构后高价值字段的可编辑入口:
  - `monitor.log_max_bytes`
  - `monitor.log_backup_count`
  - `monitor.log_retention_days`
  - `openclaw.command`
  - `openclaw.state_dir`
  - `openclaw.workspace_dir`
  - `openclaw.health_args`
  - `openclaw.status_args`
  - `openclaw.logs_args`
  - `repair.session_active_minutes`
  - `repair.pause_message`
  - `repair.terminate_message`
  - `repair.new_message`
  - `repair.session_command_timeout_seconds`
  - `repair.session_stage_wait_seconds`
  - `repair.official_steps`
  - `repair.post_step_wait_seconds`
  - `notify.account`
  - `notify.silent`
  - `notify.send_timeout_seconds`
  - `notify.read_timeout_seconds`
  - `notify.ask_timeout_seconds`
  - `notify.poll_interval_seconds`
  - `notify.read_limit`
  - `ai.provider`
  - `ai.command`
  - `ai.model`
  - `ai.timeout_seconds`
  - `ai.args`
  - `ai.args_code`
  - `anomaly_guard` 下的关键词和阈值字段
- 对数组/命令列表类字段使用能看清结构的输入控件，不要继续把复杂值塞成单行 `TextField`。
- 保证 GUI 保存时不会改写用户未触碰的其他字段。

依赖说明:
- `notify.manual_repair_keywords` / `notify.ai_approve_keywords` / `notify.ai_reject_keywords` 当前属于配置契约未打通项。GUI 可以先在日志里标记 blocked，不要在 UI 里先行暴露一个后端并不会保存的入口。

完成 gate:
- `config show --json` 当前返回的每个字段，要么有 GUI 表单入口，要么在“高级原始编辑”中明确可见可改。
- 不再需要为了修改 post-refactor 核心能力而频繁跳回 TOML 手工编辑。

回滚:
- 恢复设置页与配置管理 Swift 文件到基线

### Step 4: 默认值与解码韧性收敛
状态: pending
前置依赖: Step 3

目标:
- 解决 Swift 默认值 drift 和强假设解码带来的后续脆弱性。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/CLIWrapper.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/tests/test_gui_cli_support.py`

必须完成:
- 对齐当前已确认的默认值 drift:
  - `repair.session_agents`
  - `repair.pause_message`
  - `anomaly_guard.keywords_stop`
  - `anomaly_guard.keywords_repeat`
  - `anomaly_guard.keywords_dispatch`
  - `anomaly_guard.keywords_architect_active`
  - `ai.args`
  - `ai.args_code`
- 让关键 Swift 模型在面对“字段缺失但可回落默认值”的场景时具备 decode 韧性。
- 对 `RepairDetails` 这类部分字段可选、结构会继续演进的 payload，优先采用更宽松的解码策略。

建议:
- 若继续手写 Swift 默认值，至少增加一个从 Python 默认配置导出的契约快照，作为 drift 检查基线。
- 如果能接受一些额外工程化，优先增加 Swift 侧显式 `init(from:)` 和 `decodeIfPresent`。

完成 gate:
- 本次审计列出的默认值 drift 已全部消除或记录为明确例外。
- GUI 在未来 CLI 缺失部分可回落字段时不会直接 decode 失败。

回滚:
- 恢复 Swift 模型与相关测试到基线

### Step 5: GUI/CLI 合同测试补强
状态: pending
前置依赖: Step 2, Step 4

目标:
- 建立 GUI 和 CLI 之间的最小契约测试围栏，防止下一轮后端重构再次把 GUI 拖出同步。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/tests/test_gui_cli_support.py`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Package.swift`
- 如需要，可新增:
  - `/Users/mima0000/.openclaw/fix-my-claw/gui/Tests/FixMyClawGUITests/`

必须完成:
- 扩展 Python 侧契约测试，至少冻结:
  - 默认配置 JSON 关键字段
  - `repair --json` 的典型场景 payload
  - `check --json` / `status --json` / `service status --json` 的 GUI 依赖字段
- 为 Swift 增加最小 decode 测试目标，验证 sample payload 能正常解码。
- 对“会导致 GUI 保存时丢字段”的配置项建立专门回归用例。

完成 gate:
- `python -m pytest tests/test_gui_cli_support.py -q` 通过
- 若新增 Swift 测试，则 `swift test` 通过
- `swift build` 继续通过

回滚:
- 删除新增测试并恢复 `Package.swift`

### Step 6: 验证与文档收尾
状态: pending
前置依赖: Step 1-5

目标:
- 用真实操作路径验证 GUI 在 post-refactor 后端上的行为闭环。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-post-refactor-log.md`
- 如有必要，补充 README/使用说明中的 GUI 章节

必须验证:
1. 首次启动且没有配置文件
2. 启动时服务已安装但 OpenClaw 不健康
3. GUI 手动触发检查
4. GUI 手动触发修复，且后台服务原本在运行
5. 等待 AI 审批文件出现时 GUI 的提示和抢占逻辑
6. 后台服务触发修复时 GUI 的状态变化
7. 保存配置后再次 `config show --json` 的 round-trip

完成 gate:
- 验证结论全部记录到日志
- 未解决问题都已标明 blocked / follow-up，不留隐性尾巴

回滚:
- 无需代码回滚，只需更新日志结论

## 当前已确认的优先级
P1:
- 健康态乐观推断导致冷启动/外部修复后的 GUI 状态失真
- 菜单栏图标不显示“修复中 / 审批中”
- 修复结果展示仍然过于粗糙，无法解释 post-refactor 阶段结果
- 设置页对核心配置覆盖不足

P2:
- Swift 默认值 drift
- 缺少 Swift 侧契约测试
- 自定义 `monitor.state_dir` 场景下，GUI 在配置加载前可能看不到早期审批/修复文件

P3:
- 复杂配置控件的易用性与布局优化

## 明确不在本计划内
- 重写整个 GUI 视觉风格
- 引入多配置文件切换能力
- 修改 repair state machine 的业务逻辑
- 修改 CLI 用户可见通知文案
