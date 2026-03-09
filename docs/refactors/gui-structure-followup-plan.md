# Fix-My-Claw GUI 结构收尾计划

## 版本信息
- 创建日期: 2026-03-09
- 计划版本: v1.4.x-followup
- 当前状态: done
- 目标周期: 2-4 天
- 风险等级: 中

## 文档用途
这是 `gui-architecture-optimization-plan` 完成后的后续维护计划，目标不再是重做 runtime 架构，而是清理仍然明显的文件组织债务、补齐剩余测试缺口，并用事实重新评估 `MenuBarManager` 是否还值得继续拆分。

配套日志文件:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-structure-followup-log.md`

前序文档:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-architecture-optimization-plan.md`
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-architecture-optimization-log.md`

如果计划需要变更，先在日志里登记变更建议，再回到本文件修改。不要把已经完成的 Step 1-7 重新打开，也不要在没有新证据的情况下继续扩大重构范围。

## 当前判断
前一轮架构优化已经完成这些高价值目标:
- runtime 状态、调度、IO、窗口/弹窗协调边界已经落地。
- 设置页已经完成模块化拆分。
- config decode 韧性、repair fingerprint 脱敏、scheduler/observer 基础测试已经补齐。
- `swift build`、`swift test`、`python -m pytest tests/test_gui_cli_support.py -q` 当前均为通过状态。

剩余问题更偏“可维护性收尾”，而不是“架构失控”:
- `Models.swift` 仍有 904 行，继续混放 CLI payload、配置模型、修复展示/历史和错误类型。
- `AppState` 已独立到 `Runtime/AppStateMachine.swift`，但旧的 `ServiceState` 兼容层还留在 `Models.swift`，容易让后续拆分时重复造状态模型。
- 测试已经覆盖状态机、decode、settings merge 和 scheduler 基础路径，但仍缺少 coordinator 行为、scheduler 生命周期边界和更真实的 runtime 交互场景。
- `MenuBarManager` 仍有 676 行，不过它现在更像 orchestration façade；是否继续拆分，必须基于新证据，而不是按体积先入为主。

## 目标
将 `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/` 从“架构已稳定但文件组织仍偏拥挤”的状态，推进到“模型边界清晰、关键交互有更完整测试、剩余大文件有明确处理结论”的状态。

最终目标:
- `Models.swift` 不再承担四类以上不同领域模型。
- `ServiceState` 兼容层要么被独立收口，要么被明确标记为 legacy，不再和配置/CLI payload 混在一起。
- runtime 测试向 coordinator / lifecycle / observer edge 扩展，不再只停留在 reducer 和基础 observer 写入路径。
- `MenuBarManager` 的下一步结论要可证伪: 要么继续拆分并给出清晰边界，要么明确记录“当前大小主要是编排成本，不值得再拆”。

## 核心原则
1. 这一轮优先做物理文件边界整理，不默认引入新的状态层、view model 层或额外框架。
2. `AppState` / `AppStateReducer` / `AppStateContext` 继续留在 runtime 目录，不要为了“模型拆分”把它们重新搬回 `Models/`。
3. 拆文件不等于改语义。类型名、字段名、CLI JSON 契约、默认配置路径、repair stage 名称和测试通过状态默认保持不变。
4. 测试改进优先补“难回归的行为边界”，不是机械追求文件数或覆盖率数字。
5. `MenuBarManager` 是否继续拆分必须以职责边界和回归价值为依据，不能仅凭“文件还大”继续切。
6. 当前工作树不是干净状态；后续窗口不得回滚前一轮未提交结果，除非用户明确要求。

## 非目标
以下内容不属于本轮默认范围，除非日志先登记并更新计划:
- 重做 runtime 状态机或重新设计 scheduler
- 引入 TCA、XPC、`DistributedNotificationCenter`、数据库或其他新基础设施
- 重做 Settings UI 或视觉层
- 修改 CLI JSON 契约、状态文件名或 Python 端行为
- 为了拆文件而引入大量 typealias / wrapper 噪音

## 行为冻结
以下行为不允许改变，除非本计划明确更新:
- `config show --json` / `config set --json` 的现有结构与字段名
- `status --json` / `check --json` / `repair --json` / `service status --json` 的现有结构与字段名
- `repair_progress.json`、`ai_approval.active.json`、`ai_approval.decision.json`、`repair_result.json` 的文件名和基础字段
- GUI 默认配置路径仍为 `~/.fix-my-claw/config.toml`
- 现有 repair stage 名称与顺序
- `swift build`、`swift test`、`tests/test_gui_cli_support.py` 通过状态

## 锁组
- `gui-models`: `Models.swift`、未来 `Models/` 目录
- `gui-runtime-core`: `MenuBarManager.swift`、`MenuBarController.swift`、`Runtime/`
- `gui-settings`: `ConfigManager.swift`、`Views/SettingsView.swift`、`Views/Settings/`
- `gui-contract`: `gui/Tests/`、`tests/test_gui_cli_support.py`、`gui/Package.swift`
- `docs`: `docs/refactors/`

同一时间只允许一个窗口写同一锁组。开始实现前先看本计划、执行日志和当前 `git status`。

## 执行顺序
0. 范围冻结与基线记录
1. `Models.swift` 按领域拆分
2. runtime interaction / lifecycle 测试补强
3. `MenuBarManager` 复评与可选 extraction
4. 验证、文档收尾

## 步骤详情

### Step 0: 范围冻结与基线记录
状态: done

目标:
- 冻结后续维护轮的范围，避免把上一轮已完成的架构计划重新打开。
- 用当前代码事实确认真正剩余的债务是“模型拆分 + 测试边界 + manager 复评”。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-structure-followup-plan.md`
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-structure-followup-log.md`

执行内容:
1. 复核 `Models.swift`、`MenuBarManager.swift`、当前测试集和上一轮完成日志。
2. 记录当前行数、测试通过状态和工作树状态。
3. 产出新的 follow-up plan + log。

完成 gate:
- follow-up plan + log 已创建
- 下一步优先级和允许改动范围已明确
- 已记录当前 baseline 事实

回滚:
- 只删除本轮新增文档

### Step 1: `Models.swift` 按领域拆分
状态: done
前置依赖: Step 0

目标:
- 让模型文件边界和实际领域保持一致，降低未来 review / merge / 查找成本。
- 在不改行为的前提下，把 legacy 兼容层和新模型边界理清。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift`
- 新增目录建议:
  - `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models/`
- `gui-contract` 锁组文件

必须完成:
- 至少拆出这些领域文件:
  - `CLIPayloads.swift`
  - `ConfigModels.swift`
  - `RepairModels.swift`
  - `LegacyServiceState.swift` 或等价兼容文件
  - `CLIError.swift`
- `AppState` 相关定义必须继续留在 `Runtime/AppStateMachine.swift`，不能重新搬回模型目录。
- 如果保留 `Models.swift`，它只能做极小的兼容/过渡层，不允许继续承担主模型堆放区。
- 拆分过程不得改类型名、字段名或外部可见行为。

完成 gate:
- 不再存在单一模型文件同时承载 CLI payload、配置模型、repair 展示/历史、错误类型四类职责。
- `Models.swift` 删除或显著收缩到小型兼容壳层。
- `swift build`、`swift test`、`python -m pytest tests/test_gui_cli_support.py -q` 继续通过。

回滚:
- 恢复 `Models.swift` 和本步骤新增的模型文件

### Step 2: runtime interaction / lifecycle 测试补强
状态: done
前置依赖: Step 1

目标:
- 把测试覆盖从当前 reducer / decode / 基础 observer，扩展到更接近真实运行边界的交互与生命周期。

允许修改:
- `gui-runtime-core` 锁组文件
- `gui-contract` 锁组文件

必须完成:
- 至少新增一类 coordinator / presenter 的纯逻辑测试，优先覆盖审批、确认或 alert 排队行为。
- 至少新增一类 scheduler 生命周期测试，覆盖 `start / stop / refreshNow` 以外的边界，如重复启动保护、目录变更后的恢复或可接受的限制说明。
- 如果需要为测试引入 seam，只允许做小范围可解释的可测性改造，不得借测试名义重写 runtime 架构。

完成 gate:
- 测试不再只覆盖状态机和基础 observer 写入路径。
- 至少有一条 runtime interaction 行为能在不启动完整 AppKit UI 的情况下被回归保护。

完成说明 (2026-03-09):
- `AlertPresenter` 已补最小测试 seam，可在不启动真实 sheet 的情况下验证串行排队行为。
- 新增 `AlertPresenterTests`，覆盖“第二个 alert 必须等待第一个完成后才展示”的 presenter 队列语义。
- `RuntimeSchedulerTests` 已补 `refreshStateObservation` 切换观察目录后的恢复路径，验证旧目录不再触发、新目录继续触发。
- 本步骤未扩大到完整 AppKit UI 测试，也未重写 runtime 架构。

回滚:
- 恢复本步骤新增的测试和为测试服务的最小 seam

### Step 3: `MenuBarManager` 复评与可选 extraction
状态: done
前置依赖: Step 1, Step 2

目标:
- 用当前代码事实判断 `MenuBarManager` 是否还存在值得继续拆分的高价值边界。

允许修改:
- `gui-runtime-core` 锁组文件
- `gui-contract` 锁组文件
- `docs` 锁组文件

必须完成:
- 先记录 `MenuBarManager` 的剩余职责类别和真实复杂度来源。
- 只有在出现明确的单一边界时才允许 extraction，例如:
  - repair result/presentation 处理
  - approval polling / decision claim 协调
  - service command orchestration
- 如果没有清晰边界，必须在日志中明确写出“不继续拆”的证据，而不是为了缩行数硬拆。

完成 gate:
- 二选一:
  - `MenuBarManager` 完成一处高价值 extraction，职责边界更清晰
  - 或者日志明确记录“不继续拆”的证据和理由
- 无论选哪条路径，`swift build`、`swift test`、`python -m pytest tests/test_gui_cli_support.py -q` 必须通过

完成说明 (2026-03-09):
- 已按职责复评 `MenuBarManager`，剩余代码主要分为 6 类:
  - 生命周期与启动编排 (`start` / `initialSetup` / `performInitialHealthCheck`)
  - 状态刷新与健康检查 (`refreshStatus` / `refreshHealthSnapshot` / `periodicHealthCheck`)
  - 用户动作与服务命令转发 (`toggleMonitoring` / `performCheck` / service install/start/stop/uninstall)
  - 调度与状态目录观察 (`startScheduling` / `refreshStateObservation` / scheduled refresh)
  - repair result / progress 同步 (`handleRepairResult` / `syncPersistedRepairResult` / `pollRepairProgress`)
  - approval polling / dialog 协调 (`pollApprovalRequest` / `showPendingApprovalDialog` / `presentApprovalDialog`)
- 当前复杂度来源主要是“单一 AppKit 入口需要串联 Store、Services、Scheduler、Coordinator 和通知”，而不是某个独立领域仍被混放。
- 已存在的 `MenuBarStore`、`RuntimeServices`、`RuntimeScheduler`、`MenuBuilder`、`ApprovalCoordinator`、`WindowCoordinator` 已吸收主要可独立职责；继续把剩余方法再拆成新的 coordinator，只会把同一批依赖重新透传一层。
- 本轮未发现足以单独抽出的高价值边界；尤其 approval/repair 流程虽然相对集中，但都同时依赖 scheduler 回调、store 状态门控和 services 读写，硬拆会制造新的 façade，而不是显著降低耦合。
- 因此本步骤结论为: 不继续为缩行数拆分 `MenuBarManager`，保留其 orchestration façade 角色，待后续只有在出现新的单一边界或真实回归压力时再评估。

回滚:
- 恢复本步骤新增 extraction 或复评文档

### Step 4: 验证、文档收尾
状态: done
前置依赖: Step 1, Step 2, Step 3

目标:
- 收尾本轮“结构维护”计划，确认剩余遗留项是否足以留给后续按需处理。

允许修改:
- `docs` 锁组文件
- 如需仅为验证补微小测试说明，可触碰 `gui-contract` 锁组文件

必须完成:
- 运行并记录:
  - `swift build`
  - `swift test`
  - `python -m pytest tests/test_gui_cli_support.py -q`
- 更新执行日志中的每一步 gate、残余风险和明确结论。
- 对 `Models.swift` 拆分和 `MenuBarManager` 复评给出最终状态，不留“半拆不拆”的模糊描述。

完成 gate:
- 本轮所有步骤状态与验证结果已记录
- 已明确是否还需要下一轮结构性重构

完成说明 (2026-03-09):
- 已复跑并记录最终验证:
  - `swift build`
  - `swift test`
  - `python -m pytest tests/test_gui_cli_support.py -q`
- `Models.swift` 拆分结论已定稿: 主模型已按领域迁出，`Models.swift` 只保留为小型兼容/迁移壳层。
- `MenuBarManager` 复评结论已定稿: 当前主要承担 orchestration façade 角色，不再基于文件体积继续拆分。
- 本轮结论为“结构维护收尾完成”，当前没有足够证据支持立即开启下一轮结构性重构；后续仅在出现新的单一高价值边界、真实回归压力或协作摩擦时再评估。

回滚:
- 只回滚文档，不回滚已通过验证的代码
