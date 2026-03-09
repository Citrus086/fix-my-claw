# Fix-My-Claw GUI 前端架构优化计划

## 版本信息
- 创建日期: 2026-03-09
- 计划版本: v1.4.x
- 当前状态: done
- 目标周期: 4-7 天
- 风险等级: 中高

## 文档用途
这是 GUI 前端在 `gui-post-refactor-plan` 收尾完成后的第二轮重构计划，目标从“功能与契约对齐”推进到“运行时架构收敛”。所有窗口在开始执行前都必须先读完本文件，再读执行日志。

配套日志文件:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-architecture-optimization-log.md`

前序文档:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-post-refactor-plan.md`
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-post-refactor-log.md`

如果计划需要变更，先在日志里登记变更建议，再回到本文件修改。不要在实现过程中默默扩范围、换架构或引入新框架。

## 本轮审计结论
上一轮 GUI 收尾已经解决了几类“功能正确性”问题:
- 冷启动时乐观展示健康的问题已经修掉，GUI 会主动触发真实健康检查。
- `notify.*keywords`、`openclaw.*`、`repair.*`、`notify.*timeout` 等高价值字段已经补进当前模型和设置页。
- 修复结果展示已经能消费 `ai_decision`、`ai_stage`、`official_break_reason`、`backup_before_ai_error`、`notify_final` 等字段。

本轮真正剩下的是“结构债务”，不是再做一遍字段对齐:
- `MenuBarManager` 仍是 1000+ 行的多职责对象，同时管理状态、轮询、CLI 调用、文件读取、审批流程、通知投递和菜单构建。
- 运行态依然靠 4 个固定频率 `Timer` 驱动，没有统一调度、退避、生命周期感知或文件事件观察。
- `state` 和 `effectiveState` 仍然是并行状态源，显示正确性依赖调用方自己记住优先级。
- 错误弹窗、审批弹窗、确认弹窗仍用 `NSAlert.runModal()`，设置窗口仍由 `NSHostingController + NSWindow` 手工管理。
- `SettingsView.swift` 仍是 1359 行的单文件，包含 5 个 tab、通用表单控件和 preview，维护成本继续上升。
- Swift 测试仍然主要覆盖 payload 解码；没有 runtime 状态机、调度器、文件观察器或设置交互测试。
- 修复去重 fingerprint 仍然直接把 `attempt_dir` 路径拼进 identity key。
- 配置解码的韧性仍只在顶层 section；section 内字段缺失仍可能触发 `keyNotFound`。

## 重构目标
将 `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/` 从“契约已补齐但结构仍拥挤”的 GUI 壳层，推进到“职责明确、可测试、可继续演进”的前端架构。

最终目标:
- 运行时职责按“状态存储 / 调度 / IO / 展示协调”拆开，`MenuBarManager` 不再承担所有副作用。
- 轮询与文件监控统一到一个调度入口，减少无意义 wake-up，并为失败重试预留退避点。
- GUI 有单一权威状态模型，菜单图标、tooltip、菜单项、弹窗都消费同一份状态。
- 审批、错误、设置窗口不再依赖阻塞式 modal 调用。
- 设置页按 tab 或域拆文件，避免继续在一个 Swift 文件里堆更多字段。
- 测试覆盖从“能 decode”扩展到“状态流正确、调度可控、交互不回归”。

## 核心原则
1. 不破坏 CLI 契约。`status --json`、`check --json`、`repair --json`、`config show --json`、`config set --json`、`service status --json` 以及已有状态文件名默认保持兼容。
2. 优先做增量式架构收敛，不默认引入 TCA。除非 reducer 测试和 effect 管理证明现有方案无法承载，否则先采用 `Store + Coordinator + Service` 的轻量拆分。
3. 状态与副作用分离。状态聚合、CLI 调用、文件观察、菜单组装、弹窗展示必须是不同层次的对象。
4. 本地状态文件优先用事件驱动观察。只有在 `DispatchSourceFileSystemObject` / FSEvents 无法满足时，才评估 `DistributedNotificationCenter` 或 XPC。
5. 用户可见交互优先非阻塞。错误、审批、确认都不能长期占住主线程。
6. 测试要先冻结行为，再推动重排。重构过程允许换文件和对象边界，不允许静默改变用户可见语义。
7. 去重、日志、通知摘要不得泄露完整本地路径；若必须依赖路径，只保留 hash 或 basename。

## 非目标
以下内容不属于本轮默认范围，除非日志先登记并更新计划:
- 把整个 GUI 全量迁移到 TCA
- 为后端新增强依赖的 XPC service
- 重写 CLI 契约或更改现有 JSON 字段名
- 重做设置页视觉风格
- 引入数据库、持久缓存或远程遥测

## 行为冻结
以下行为不允许改变，除非本计划明确更新:
- `config show --json` / `config set --json` 的现有结构与字段名
- `status --json` / `check --json` / `repair --json` / `service status --json` 的现有结构与字段名
- `repair_progress.json`、`ai_approval.active.json`、`ai_approval.decision.json`、`repair_result.json` 的文件名和基础字段
- GUI 默认配置路径仍为 `~/.fix-my-claw/config.toml`
- 现有 repair stage 名称与顺序
- 现有本地通知能力判定逻辑和 app bundle 约束
- `swift build`、`swift test`、`tests/test_gui_cli_support.py` 通过状态

## 锁组
- `gui-runtime-core`: `MenuBarManager.swift`、`MenuBarController.swift`、`Models.swift`、`Runtime/WindowCoordinator.swift`、`Runtime/ApprovalCoordinator.swift`、未来 runtime 展示/presenter 文件
- `gui-runtime-io`: `CLIWrapper.swift`、未来新增 runtime service / observer / scheduler 文件
- `gui-settings`: `Views/SettingsView.swift`、未来新增 `Views/Settings/` 目录、`ConfigManager.swift`
- `gui-contract`: `gui/Tests/`、`tests/test_gui_cli_support.py`、`gui/Package.swift`
- `docs`: `docs/refactors/`

同一时间只允许一个窗口写同一锁组。开始实现前先看本计划、执行日志和当前 `git status`。

## 执行顺序
0. 审计与基线冻结
1. Runtime 职责拆分
2. 调度与文件观察收敛
3. 权威状态机落地
4. 交互协调与错误处理降阻塞
5. Settings 模块化拆分
6. 解码韧性、fingerprint 与测试补强
7. 验证、文档收尾与 push 通道评估

## 步骤详情

### Step 0: 审计与基线冻结
状态: done

目标:
- 冻结当前 GUI 的结构债，而不是重复做上一轮已经完成的契约补齐。
- 明确本轮哪些问题已经被旧计划覆盖，哪些仍需要架构性修正。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-architecture-optimization-plan.md`
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-architecture-optimization-log.md`

执行内容:
1. 审计 `MenuBarManager`、`MenuBarController`、`SettingsView`、`Models`、`ConfigManager`。
2. 对照上一轮 GUI 收尾文档，标记“已修复”与“仍未解决”的边界。
3. 运行 `swift build`、`swift test`、`tests/test_gui_cli_support.py`、`git status --short` 作为基线。
4. 用事实记录主要结构问题与推荐执行顺序。

完成 gate:
- 新的 plan + log 已创建
- 已修复项与未修复项已分开
- 基线命令结果已登记

回滚:
- 只删除本轮新增文档

### Step 1: Runtime 职责拆分
状态: done
前置依赖: Step 0

目标:
- 把 `MenuBarManager` 从单一上帝类拆成“状态容器 + 协调器 + service”。
- 保持菜单栏用户可见行为不变，为后续状态机和调度器改造腾出边界。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarController.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/CLIWrapper.swift`
- 新增 runtime 文件建议目录:
  - `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/`

必须完成:
- 给 runtime 定出至少这几类对象边界:
  - `MenuBarStore` 或等价状态存储对象
  - `StatusService` / `RepairService` / `ApprovalService` 之类 IO 层
  - `MenuBuilder` 或等价菜单拼装层
  - `WindowCoordinator` / `ApprovalCoordinator` 之类展示协调层
- `MenuBarController` 只负责 AppKit 生命周期和 action 转发，不再持有大段业务逻辑。
- `MenuBarManager` 如果继续存在，职责必须缩成 façade，不允许继续增长。

建议实现顺序:
1. 先抽离纯函数和展示拼装逻辑。
2. 再抽离 CLI/file IO。
3. 最后收敛状态发布入口。

完成 gate:
- `MenuBarManager.swift` 明显降体积，且不再同时承担菜单拼装、文件读取、弹窗和通知投递。
- 运行态主入口可以通过依赖注入替换 service，方便后续测试。

回滚:
- 恢复 runtime core 新增文件和相关引用

### Step 2: 调度与文件观察收敛
状态: done
前置依赖: Step 1

目标:
- 去掉 4 个彼此独立的裸 `Timer`，统一调度和文件观察入口。
- 把高频文件轮询替换为事件驱动或更低成本的策略。

允许修改:
- `gui-runtime-core` 锁组文件
- `gui-runtime-io` 锁组文件

必须完成:
- 为状态检查、健康检查、审批文件、修复进度建立统一 scheduler API。
- `repair_progress.json`、`ai_approval.active.json`、`ai_approval.decision.json`、`repair_result.json` 优先改为文件事件观察。
- 失败重试要支持至少一个简单退避策略，不能所有失败都原频率硬打。
- 明确 app 启动、窗口关闭、应用退出时调度器和 observer 的生命周期。

建议方案:
- 首选 `DispatchSourceFileSystemObject` 或等价文件系统事件源。
- 若目录级监听在当前状态目录结构下不可行，再评估 FSEvents。
- 只有在“文件事件 + 低频健康检查”仍不足以消除延迟时，才进入 Step 7 的 push 通道评估。

完成 gate:
- GUI 不再依赖 1 秒和 2 秒的持续文件轮询。
- 调度器具备显式 `start / stop / refreshNow` 入口。
- 应用退出时不存在悬挂 timer / observer。

回滚:
- 恢复统一调度层和原有 timer 接线

### Step 3: 权威状态机落地
状态: done
前置依赖: Step 1

目标:
- 用单一权威状态取代 `state + effectiveState + currentRepairStage + pendingAiRequest` 的松散组合。
- 让图标、tooltip、菜单、通知、弹窗消费同一状态图。

允许修改:
- `gui-runtime-core` 锁组文件
- `gui-contract` 锁组文件

必须完成:
- 定义明确的 GUI runtime 状态模型，例如:
  - `uninitialized`
  - `unknown`
  - `healthy`
  - `unhealthy(reason:)`
  - `repairing(stage:)`
  - `awaitingApproval(request:)`
- 状态转换必须通过受控入口完成，不能继续由多个字段散落改变。
- 菜单构建与通知摘要从权威状态衍生，而不是各自再做一遍 if-else 优先级。
- 至少补一组状态机测试，覆盖“修复中优先于健康态”“审批与修复互斥展示”“修复结束后的收敛”。

注意:
- 本步骤不强制引入第三方状态机库。先实现可读、可测的本地状态 reducer。

完成 gate:
- `effectiveState` 被删除或退化成单行转发，不再承载业务优先级。
- 同一用户可见状态不会在不同 UI 位置显示出不一致文案。

完成说明 (2026-03-09):
- `MenuBarManager` 已通过 `configLoaded`、`healthCheckStarted`、`healthCheckCompleted`、`healthCheckFailed`、`monitoringToggled` 等事件接入 reducer，不再直接写 `store.state`。
- `StatusPayload.enabled` 已接回权威状态流；首次健康检查、手动检查和监控开关切换都能收敛到正确的 `healthy` / `unhealthy` / `paused*` 状态。
- reducer 已补强优先级保护，避免异步健康检查或 repair progress 覆盖 `repairing` / `awaitingApproval`。
- Step 4 相关 coordinator 草稿继续保留在工作树，但本次未扩大其行为范围。

回滚:
- 恢复原 runtime 状态字段与菜单衍生逻辑

### Step 4: 交互协调与错误处理降阻塞
状态: done
前置依赖: Step 1

目标:
- 把审批、错误、确认和设置窗口的展示管理从业务逻辑里抽离出来。
- 去掉主线程阻塞式 `runModal()` 作为默认交互方式。

允许修改:
- `gui-runtime-core` 锁组文件
- `gui-settings` 锁组文件
- 当前已登记的 step4 runtime 文件:
  - `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/WindowCoordinator.swift`
  - `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/ApprovalCoordinator.swift`
  - `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/AlertPresenter.swift`

必须完成:
- 为错误、审批、确认窗口建立统一 presenter/coordinator。
- `MenuBarController` 不再直接构造多个 `NSAlert`。
- 设置窗口生命周期集中管理；窗口关闭后可以安全复用或重建，不保留悬挂强引用。
- 错误至少分成:
  - CLI/IO 错误
  - 配置错误
  - 用户操作确认
  - 后台状态提示

建议实现:
- 优先使用非阻塞 sheet 或独立窗口。
- 无法在本轮彻底去掉 AppKit alert 时，至少把 `runModal()` 收敛到 presenter 层，不再散落在 controller/manager。

完成 gate:
- `MenuBarController.swift` 不再同时承担 action、窗口创建和 alert 呈现细节。
- 错误处理可以按类型降级，而不是所有问题都弹同一种阻塞警告。

完成说明 (2026-03-09):
- `WindowCoordinator` / `ApprovalCoordinator` 已统一切到 `AlertPresenter`，默认交互不再使用阻塞式 `runModal()`，而是走非阻塞 sheet 队列。
- `RuntimeAlertCategory` 已区分 CLI/IO、配置错误和后台状态提示；用户确认交互通过单独的 confirmation 流程处理。
- 设置窗口生命周期继续集中在 `WindowCoordinator`，窗口关闭后会清理引用并允许安全重建。
- 本步骤未触碰 step5 的 settings 拆分范围；`SettingsView.swift` 保持原状。

回滚:
- 恢复原有 alert 和窗口接线

### Step 5: Settings 模块化拆分
状态: done
前置依赖: Step 0

目标:
- 把 `SettingsView.swift` 从单文件巨型视图拆成按 tab 或域组织的模块。
- 保持当前字段覆盖范围和保存逻辑不回退。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/SettingsView.swift`
- 新增目录建议:
  - `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/Settings/`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/ConfigManager.swift`

必须完成:
- 至少按以下粒度拆分:
  - 根设置页容器
  - `MonitorSettingsView`
  - `RepairSettingsView`
  - `AISettingsView`
  - `IDSettingsView`
  - `AdvancedSettingsView`
  - 通用表单控件
- `ConfigBindable` 和表单 binding helper 如继续保留，要移动到单独文件。
- preview、表单组件、业务 tab 不允许继续塞在同一个 1000+ 行文件。

完成 gate:
- `SettingsView.swift` 只保留容器层和最小公共定义。
- tab 级别的维护可以独立进行，不需要在单一大文件里来回跳转。

回滚:
- 恢复旧 settings 文件布局

### Step 6: 解码韧性、fingerprint 与测试补强
状态: done
前置依赖: Step 1, Step 3, Step 5

目标:
- 补齐 field-level decode 韧性、路径脱敏和架构级测试。
- 为本轮重构后的对象边界建立回归保护。

允许修改:
- `gui-runtime-core` 锁组文件
- `gui-settings` 锁组文件
- `gui-contract` 锁组文件

必须完成:
- 为高价值 config section 提供字段级容错，不再只靠顶层 section fallback。
- 修复结果去重要去掉完整路径拼接，改为 hash、basename 或结构化 identity。
- 新增测试至少覆盖:
  - section 内字段缺失时的 decode 行为
  - runtime 状态转换
  - scheduler / observer 触发路径
  - settings 保存不会吃掉未触碰字段

完成 gate:
- `PayloadDecodingTests` 不再是唯一 GUI 级保障。
- repair fingerprint 不再暴露完整 `attempt_dir`。
- 缺字段配置不会因为单个 section key 缺失直接 decode 失败。

完成说明 (2026-03-09):
- `MonitorConfig`、`OpenClawConfig`、`RepairConfig`、`AnomalyGuardConfig`、`NotifyConfig`、`AiConfig`、`AgentRolesConfig` 已补字段级 `decodeIfPresent` fallback，section 内缺字段会回退默认值。
- `RepairResult.identityKey` 已改为 `basename + stable hash`，不再直接拼接完整 `attempt_dir`。
- `ConfigManager` 已暴露可复用的 merge helper，并补充 settings merge 保存回归测试。
- GUI 测试已扩展到 38 个，通过新增 decode 韧性、settings merge、scheduler refresh 和目录 observer 触发路径验证。

回滚:
- 恢复新增 decode fallback、fingerprint 规则和相关测试

### Step 7: 验证、文档收尾与 push 通道评估
状态: done
前置依赖: Step 2, Step 3, Step 4, Step 5, Step 6

目标:
- 用真实构建和测试收尾本轮前端架构优化。
- 决定是否还需要后端推送通道。

允许修改:
- `docs` 锁组文件
- 如需只读型后端通知桥接评估，再单独登记后允许触碰 Python 侧

必须完成:
- 运行并记录:
  - `swift build`
  - `swift test`
  - `python -m pytest tests/test_gui_cli_support.py -q`
- 更新执行日志中的每一步 gate、风险和遗留项。
- 对“文件观察 + 低频健康检查”是否足够给出结论。
- 只有在文件观察仍无法满足延迟或可靠性要求时，才登记下一轮 `DistributedNotificationCenter` / XPC 方案。

完成 gate:
- 本轮所有步骤状态与验证结果已记录
- 已明确“是否还需要 push 通道”的结论

完成说明 (2026-03-09):
- `swift build`、`swift test`、`python -m pytest tests/test_gui_cli_support.py -q` 已完成并全部通过。
- 本轮 7 个步骤的 gate、变更范围和验证结果已在执行日志登记完成。
- 当前 runtime 已具备目录级文件事件观察、`refreshNow()` 主动刷新入口，以及 30 秒状态刷新 / 300 秒健康检查的低频回退与退避机制。
- 结论是当前不需要进入 `DistributedNotificationCenter` / XPC push 通道评估；只有在后续实测发现文件事件漏报、睡眠恢复异常或不可接受的状态收敛延迟时，才需要登记下一轮方案。

回滚:
- 只回滚文档，不回滚已通过验证的代码
