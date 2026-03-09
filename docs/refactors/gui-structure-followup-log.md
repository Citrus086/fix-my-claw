# Fix-My-Claw GUI 结构收尾执行日志

## 使用说明
- 每个新窗口开始前，先读计划文档，再读本日志。
- 任意时刻只允许一个步骤处于 `in_progress`。
- 如果需要偏离计划，先在"变更建议记录"登记，再更新计划文档，不要直接实施。
- 本日志记录事实，不记录臆测。

配套计划文档:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-structure-followup-plan.md`

## 当前状态总览

| Step | 名称 | 状态 | 执行人 | 开始时间 | 结束时间 | Gate |
|------|------|------|--------|----------|----------|------|
| 0 | 范围冻结与基线记录 | done | Codex | 2026-03-09 | 2026-03-09 | passed |
| 1 | `Models.swift` 按领域拆分 | done | Codex | 2026-03-09 | 2026-03-09 | passed |
| 2 | runtime interaction / lifecycle 测试补强 | done | Codex | 2026-03-09 | 2026-03-09 | passed |
| 3 | `MenuBarManager` 复评与可选 extraction | done | Codex | 2026-03-09 | 2026-03-09 | passed |
| 4 | 验证、文档收尾 | done | Codex | 2026-03-09 | 2026-03-09 | passed |

状态约定:
- `pending`: 未开始
- `in_progress`: 正在执行
- `blocked`: 有阻塞，禁止进入下一步
- `done`: gate 已通过
- `rolled_back`: 已回滚

## 锁组占用

| 锁组 | 涉及文件 | 当前持有者 | 备注 |
|------|----------|------------|------|
| gui-models | `Models.swift`、未来 `Models/` 目录 | - | Step 1 已完成 |
| gui-runtime-core | `MenuBarManager.swift`、`MenuBarController.swift`、`Runtime/` | - | Step 2 已完成；Step 3 如开始可触碰 |
| gui-settings | `ConfigManager.swift`、`Views/SettingsView.swift`、`Views/Settings/` | - | 默认不在本轮前两步触碰 |
| gui-contract | `gui/Tests/`、`tests/test_gui_cli_support.py`、`gui/Package.swift` | - | Step 2 已完成；当前测试覆盖已扩展到 presenter/scheduler 行为 |
| docs | `docs/refactors/` | - | Step 4 已完成 |

## 执行记录

### Step 0: 范围冻结与基线记录
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-structure-followup-plan.md` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-structure-followup-log.md` (新建)

执行内容:
- [x] 复核上一轮架构优化完成结果，确认 follow-up 范围只聚焦模型拆分、测试边界和 `MenuBarManager` 复评
- [x] 记录 `Models.swift`、`MenuBarManager.swift` 和当前测试集规模
- [x] 复跑当前 baseline 命令，确认 follow-up 起点仍是稳定状态
- [x] 产出新的 plan + log，并将 Step 1 锁定为当前活动步骤

命令记录:
```bash
git status --short --branch
wc -l gui/Sources/FixMyClawGUI/Models.swift \
      gui/Sources/FixMyClawGUI/MenuBarManager.swift \
      gui/Tests/FixMyClawGUITests/*.swift
swift build
swift test
python -m pytest tests/test_gui_cli_support.py -q
```

结果摘要:
```text
git status --short --branch:
- ## main...origin/main [ahead 17]
- 工作树包含上一轮 Step 1-7 的未提交改动和新增文件

wc -l:
- Models.swift: 904
- MenuBarManager.swift: 676
- AppStateMachineTests.swift: 322
- PayloadDecodingTests.swift: 259
- ConfigResilienceTests.swift: 119
- RuntimeSchedulerTests.swift: 57

swift build:
- Build complete! (0.25s)

swift test:
- 38 GUI tests passed

tests/test_gui_cli_support.py:
- 15 passed in 0.09s
```

结论:
- `Models.swift` 是当前最明确的文件组织债务，应优先处理。
- `MenuBarManager` 仍偏大，但当前证据显示它更像 orchestration façade，不应先验继续拆。
- 测试覆盖已有基础，但 coordinator / lifecycle / AppKit 边界仍明显不足。

下一步建议:
- 进入 Step 1 时只动 `gui-models` 和必要的 `gui-contract` 文件，不要提前触碰 runtime core。

gate:
- passed

### Step 1: `Models.swift` 按领域拆分
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift` (重写为兼容壳层，从 904 行缩减至 17 行)
- 新增 `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models/CLIPayloads.swift` (121 行)
- 新增 `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models/ConfigModels.swift` (418 行)
- 新增 `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models/LegacyServiceState.swift` (57 行)
- 新增 `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models/RepairModels.swift` (299 行)
- 新增 `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models/CLIError.swift` (23 行)

执行内容:
- [x] 按领域拆分 `Models.swift` 为五个独立文件
  - `CLIPayloads.swift`: CLI 输出模型 (StatusPayload, CheckPayload, ProbeResult, LogsSummary, AnomalyGuardResult, AnomalyMetrics, AnomalySignals)
  - `ConfigModels.swift`: 配置模型 (AppConfig, AgentRolesConfig, MonitorConfig, OpenClawConfig, RepairConfig, AnomalyGuardConfig, NotifyConfig, AiConfig, ServiceStatus) 及所有解码扩展
  - `LegacyServiceState.swift`: 旧 ServiceState 兼容层，明确标记为 legacy
  - `RepairModels.swift`: 修复相关模型 (RepairResultSource, RepairPresentation, CheckHistoryItem, RepairRecord) 及 RepairResult 扩展
  - `CLIError.swift`: CLI 错误类型
- [x] 保留 `Models.swift` 作为小型兼容壳层，仅包含迁移说明文档
- [x] 所有类型名、字段名、外部可见行为保持不变
- [x] 未触碰 `gui-runtime-core` 锁组文件

命令记录:
```bash
swift build
swift test
python -m pytest tests/test_gui_cli_support.py -q
```

结果摘要:
```text
swift build:
- Build complete! (3.76s)

swift test:
- 38 GUI tests passed

python -m pytest tests/test_gui_cli_support.py:
- 15 passed in 0.06s
```

行数变化:
- Models.swift: 904 → 17 行 (缩减 98%)
- 新增 Models/ 目录总代码行数: 918 行
- 按领域清晰分离，无代码重复

结论:
- `Models.swift` 已成功按领域拆分，不再同时承载 CLI payload、配置模型、repair 展示/历史、错误类型四类职责。
- `ServiceState` 兼容层已独立到 `LegacyServiceState.swift`，并明确标记为 legacy。
- 所有测试通过，行为冻结要求得到满足。
- `Models.swift` 现在只是小型文档壳层，可以安全删除（但保留作为迁移标记）。

gate:
- passed

下一步建议:
- 进入 Step 2: runtime interaction / lifecycle 测试补强
- 注意：Step 2 允许触碰 `gui-runtime-core` 和 `gui-contract` 锁组文件

### Step 2: runtime interaction / lifecycle 测试补强
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/AlertPresenter.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Tests/FixMyClawGUITests/AlertPresenterTests.swift` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Tests/FixMyClawGUITests/RuntimeSchedulerTests.swift`

执行内容:
- [x] 为 `AlertPresenter` 增加最小测试注入点，不改生产默认展示路径
- [x] 新增 `AlertPresenterTests`，覆盖 alert 串行排队语义
- [x] 补强 `RuntimeSchedulerTests`，覆盖 `refreshStateObservation` 切换观察目录后的恢复路径
- [x] 保持测试改动局限在 pure logic / lifecycle 边界，不启动完整 AppKit UI

命令记录:
```bash
swift test
swift build
python -m pytest tests/test_gui_cli_support.py -q
git status --short
```

结果摘要:
```text
swift test:
- 40 GUI tests passed
- 新增 AlertPresenterTests: 1
- RuntimeSchedulerTests: 3（新增目录切换用例后）

swift build:
- Build complete! (0.25s)

python -m pytest tests/test_gui_cli_support.py -q:
- 15 passed in 0.07s

git status --short:
- 本步骤新增/修改文件位于 `Runtime/AlertPresenter.swift`、`gui/Tests/`
- 工作树仍保留 Step 1 的 model 拆分结果
```

完成情况:
- runtime 测试不再只覆盖 reducer / decode / 基础 observer 写入路径
- `AlertPresenter` 的队列语义现在可在无 UI 环境下回归保护
- scheduler 已增加目录切换后的 observer 恢复验证，覆盖比 `start/stop/refreshNow` 更接近真实生命周期的边界
- 本步骤没有扩大到 AppKit 集成测试，也没有借测试名义重写 runtime core

下一步建议:
- 进入 Step 3 时先做 `MenuBarManager` 剩余职责复评，除非出现单一高价值边界，否则不要为了缩行数继续硬拆

gate:
- passed

### Step 3: `MenuBarManager` 复评与可选 extraction
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-structure-followup-plan.md`
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-structure-followup-log.md`

执行内容:
- [x] 复读 `MenuBarManager.swift` 与现有 runtime 协作者，按职责重新分类剩余方法与复杂度来源
- [x] 对照 `MenuBarStore`、`RuntimeServices`、`RuntimeScheduler`、`MenuBuilder`、`ApprovalCoordinator`、`WindowCoordinator`，确认主要可拆职责已在前序步骤落位
- [x] 评估 plan 中列出的三个候选边界
  - repair result/presentation: 逻辑集中但体量较小，且已主要是 presentation + notification 编排
  - approval polling / decision claim: 是当前最像独立子流程的部分，但同时依赖 scheduler 触发、store 门控、services 竞态复查和现有 `ApprovalCoordinator`；单独抽出会增加依赖透传层
  - service command orchestration: 现状多为薄包装 action，不形成独立领域对象
- [x] 结论定为“不继续拆”并把证据写回计划文档，而不是为了缩行数继续做机械 extraction

复评结论:
- `MenuBarManager` 当前剩余职责可归为 6 类:
  - 生命周期与启动编排
  - 状态刷新与健康检查
  - 用户动作与服务命令转发
  - 调度与状态目录观察
  - repair result / progress 同步
  - approval polling / dialog 协调
- 当前复杂度主要来自单一 AppKit 入口需要串联多个已拆出的 runtime 组件，而不是某个新领域仍被错误混放。
- approval 流程虽然是最大候选边界，但它并没有形成低耦合子系统；现在拆只会把相同依赖搬进新的 façade，收益不足以覆盖额外抽象成本和命名复杂度。
- 因此 Step 3 选择“保留 `MenuBarManager` 作为 orchestration façade”，等待未来出现单一高价值边界或真实回归压力时再评估。

命令记录:
```bash
git status --short
swift build
swift test
python -m pytest tests/test_gui_cli_support.py -q
```

结果摘要:
```text
git status --short:
- 工作树仍包含 Step 1/Step 2 的既有改动
- 本步骤新增改动仅位于 `docs/refactors/`；未触碰 `gui-runtime-core` 或 `gui-contract` 代码文件

swift build:
- Build complete! (0.28s)

swift test:
- 40 GUI tests passed

python -m pytest tests/test_gui_cli_support.py -q:
- 15 passed in 0.28s
```

完成情况:
- 已记录 `MenuBarManager` 的剩余职责类别和真实复杂度来源
- 已完成“不继续拆”的证据化结论，避免为缩行数继续硬拆
- 本步骤未偏离计划，且未触碰超出允许范围的文件

下一步建议:
- 进入 Step 4，只做验证与文档收尾
- 复跑并记录最终 gate 命令时，保持 `MenuBarManager` 结论稳定，不要重新打开 Step 3

gate:
- passed

### Step 4: 验证、文档收尾
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-structure-followup-plan.md`
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-structure-followup-log.md`

执行内容:
- [x] 按计划复跑最终 gate 命令，并记录实际输出
- [x] 收口 `Models.swift` 拆分和 `MenuBarManager` 复评的最终结论，避免留存“半拆不拆”描述
- [x] 记录本轮残余风险，并明确是否需要下一轮结构性重构

命令记录:
```bash
git status --short
swift build
swift test
python -m pytest tests/test_gui_cli_support.py -q
```

结果摘要:
```text
git status --short:
- 工作树仍是本轮既有未提交改动集合
- Step 4 未新增任何非文档代码改动

swift build:
- Build complete! (0.19s)

swift test:
- 40 GUI tests passed

python -m pytest tests/test_gui_cli_support.py -q:
- 15 passed in 0.07s
```

最终结论:
- `Models.swift` 拆分已完成并稳定落地；模型边界现在按 CLI payload、配置、repair、legacy state、error 分类收口。
- `MenuBarManager` 已完成复评并明确保留为 orchestration façade；当前没有足够证据支持继续按体积拆分。
- 本轮 follow-up 计划的目标已完成，不建议立即启动下一轮结构性重构。

残余风险:
- 当前 GUI 测试仍以 pure logic / runtime 生命周期边界为主，未覆盖真实 AppKit 集成流。
- `MenuBarManager.swift` 文件体积仍偏大，但现阶段属于可接受的编排成本，不构成独立重构触发条件。
- 工作树仍处于未提交状态；后续若继续推进功能开发，需注意与本轮结构改动叠加时的 review 粒度。

下一步建议:
- 如果后续要继续工作，优先转入功能开发或缺陷修复，不再以“继续拆 GUI 结构”为默认目标。
- 只有在出现新的高价值单一边界、明确测试回归痛点，或多人协作导致 `MenuBarManager` review 成本显著上升时，再开启下一轮结构评估。

gate:
- passed

## 变更建议记录
- 暂无
