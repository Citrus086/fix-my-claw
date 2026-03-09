# Fix-My-Claw GUI 前端架构优化执行日志

## 使用说明
- 每个新窗口开始前，先读计划文档，再读本日志。
- 任意时刻只允许一个步骤处于 `in_progress`。
- 如果需要偏离计划，先在“变更建议记录”登记，再更新计划文档，不要直接实施。
- 本日志记录事实，不记录臆测。

配套计划文档:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-architecture-optimization-plan.md`

## 当前状态总览

| Step | 名称 | 状态 | 执行人 | 开始时间 | 结束时间 | Gate |
|------|------|------|--------|----------|----------|------|
| 0 | 审计与基线冻结 | done | Codex | 2026-03-09 | 2026-03-09 | passed |
| 1 | Runtime 职责拆分 | done | Codex | 2026-03-09 | 2026-03-09 | passed |
| 2 | 调度与文件观察收敛 | done | Codex | 2026-03-09 | 2026-03-09 | passed |
| 3 | 权威状态机落地 | done | Codex | 2026-03-09 | 2026-03-09 | passed |
| 4 | 交互协调与错误处理降阻塞 | done | Codex | 2026-03-09 | 2026-03-09 | passed |
| 5 | Settings 模块化拆分 | done | Codex | 2026-03-09 | 2026-03-09 | passed |
| 6 | 解码韧性、fingerprint 与测试补强 | done | Codex | 2026-03-09 | 2026-03-09 | passed |
| 7 | 验证、文档收尾与 push 通道评估 | done | Codex | 2026-03-09 | 2026-03-09 | passed |

状态约定:
- `pending`: 未开始
- `in_progress`: 正在执行
- `blocked`: 有阻塞，禁止进入下一步
- `done`: gate 已通过
- `rolled_back`: 已回滚

## 锁组占用

| 锁组 | 涉及文件 | 当前持有者 | 备注 |
|------|----------|------------|------|
| gui-runtime-core | `MenuBarManager.swift`、`MenuBarController.swift`、`Models.swift` | - | Step 6 已完成；当前未占用 |
| gui-runtime-io | `CLIWrapper.swift`、未来 runtime service / observer / scheduler 文件 | - | Step 1/2 已完成；当前未占用 |
| gui-settings | `Views/SettingsView.swift`、未来 `Views/Settings/` 目录、`ConfigManager.swift` | - | Step 6 已完成；当前未占用 |
| gui-contract | `gui/Tests/`、`tests/test_gui_cli_support.py`、`gui/Package.swift` | - | Step 6 已完成；已补齐 decode / runtime / settings 回归测试 |
| docs | `docs/refactors/` | - | 本轮文档收尾已完成；当前未占用 |

## 执行记录

### Step 0: 审计与基线冻结
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-architecture-optimization-plan.md` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-architecture-optimization-log.md` (新建)

执行内容:
- [x] 审计 GUI runtime / settings / model / controller 当前结构
- [x] 对照上轮 `gui-post-refactor` 文档，区分“已修复”和“未修复”的问题
- [x] 运行构建与测试基线命令
- [x] 输出本轮架构优化计划和执行日志

命令记录:
```bash
wc -l gui/Sources/FixMyClawGUI/MenuBarManager.swift \
      gui/Sources/FixMyClawGUI/Views/SettingsView.swift \
      gui/Sources/FixMyClawGUI/Models.swift \
      gui/Sources/FixMyClawGUI/ConfigManager.swift
swift build
swift test
python -m pytest tests/test_gui_cli_support.py -q
git status --short
swift -e 'import Foundation; struct Foo: Codable { var x:Int = 1 }; do { let foo = try JSONDecoder().decode(Foo.self, from: Data("{}".utf8)); print(foo) } catch { print(error) }'
```

结果摘要:
```text
wc -l:
- MenuBarManager.swift: 1020
- SettingsView.swift: 1359
- Models.swift: 746
- ConfigManager.swift: 210

swift build:
- Build complete! (0.22s)

swift test:
- 9 GUI tests passed in 0.008s

tests/test_gui_cli_support.py:
- 15 passed in 0.06s

git status --short:
- 审计开始前工作树干净

swift -e decode probe:
- synthesized Decodable with default property still throws keyNotFound on missing key
```

### 审计发现

#### 发现 1: `MenuBarManager` 仍然是运行态 God object
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:43`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:58`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:421`

事实:
- 文件当前约 1020 行。
- 对象同时持有 9 个 `@Published` 状态、4 个 `Timer`、CLI wrapper、状态文件路径、审批对话框去重、通知投递和菜单拼装。
- 同一个类里既有 `refreshHealthSnapshot()` 这类 IO 逻辑，也有 `buildMenu()`、`showAiRepairDialog()` 这类展示逻辑。

影响:
- 任意一个职责改动都会牵连整类重编译和联调。
- 很难给 scheduler、状态机或菜单拼装单独加测试。

结论:
- 这是本轮 Step 1 的 P1 问题。

#### 发现 2: 调度策略仍是 4 个固定频率 `Timer`
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:423`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:428`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:432`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:436`

事实:
- 服务状态 30 秒轮询，健康检查 300 秒轮询，repair progress 1 秒轮询，审批文件 2 秒轮询。
- 当前没有统一调度器、失败退避、timer invalidation 或 app lifecycle hook。
- 文件状态变化仍靠轮询读取 JSON 文件，而不是文件系统事件。

影响:
- 高频轮询在 idle 场景下也会持续唤醒。
- 失败时会以原频率继续打 CLI 或文件系统。
- 睡眠恢复、退出、未来多窗口场景都缺乏明确生命周期。

结论:
- 这是 Step 2 的 P1 问题。

#### 发现 3: `state` 与 `effectiveState` 仍是并行状态源
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:46`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:52`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:77`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarController.swift:46`

事实:
- 展示层已经不直接使用旧的乐观健康推断，但仍要依赖 `effectiveState` 对 `state` 进行二次覆盖。
- `currentRepairStage` 和 `pendingAiRequest` 仍然散落在 store 外部，没有统一 reducer 或显式转换规则。
- 图标、tooltip、菜单项虽然现在大体一致，但正确性依赖调用方都记得用“派生态”而不是“原始态”。

影响:
- 一旦后续引入更多瞬时态，例如“加载配置”“文件观察降级”“通知失败”，状态优先级会继续散落。
- 测试只能验证最终 UI 文案，很难验证状态流本身。

结论:
- 这是 Step 3 的 P1 问题。

#### 发现 4: 弹窗和窗口管理仍然阻塞且分散
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarController.swift:51`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarController.swift:87`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarController.swift:116`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarController.swift:134`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:651`

事实:
- 错误、卸载确认、状态详情、AI 审批都通过 `NSAlert.runModal()` 展示。
- 设置窗口仍由 controller 自己构造 `NSHostingController` 和 `NSWindow`，并用 `settingsWindow` 强持有。
- 当前没有统一 presenter/coordinator 对这些交互做归档和分类。

影响:
- 阻塞式 modal 容易卡住主线程上的后续交互。
- 错误展示、确认弹窗和审批弹窗彼此之间没有统一优先级和重入控制。
- 窗口生命周期管理无法独立测试。

结论:
- 这是 Step 4 的 P1 问题。

#### 发现 5: `SettingsView.swift` 仍是超大单文件
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/SettingsView.swift:3`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/SettingsView.swift:172`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/SettingsView.swift:281`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/SettingsView.swift:428`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/SettingsView.swift:539`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/SettingsView.swift:614`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/SettingsView.swift:1083`

事实:
- 文件当前 1359 行，包含根容器、5 个 tab、binding helper、表单控件和 preview。
- 逻辑上虽然已经按 tab 分段，但物理文件边界仍然没有拆开。

影响:
- 任意 tab 微调都会触碰整个文件。
- review 和后续冲突处理成本都会继续升高。

结论:
- 这是 Step 5 的 P1 问题。

#### 发现 6: GUI 测试仍然只覆盖“能 decode”，没有覆盖运行态结构
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Tests/FixMyClawGUITests/PayloadDecodingTests.swift:4`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Tests/FixMyClawGUITests/PayloadDecodingTests.swift:11`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Tests/FixMyClawGUITests/PayloadDecodingTests.swift:145`

事实:
- 当前 9 个 Swift 测试主要覆盖 payload 解码、路径解析和通知开关条件。
- 没有 runtime 状态机测试、scheduler/observer 测试、菜单构建测试或 settings 保存测试。

影响:
- 架构重排时，开发者缺少“行为没变”的保护网。
- 调度与状态层越复杂，未来越容易出现回归。

结论:
- 这是 Step 6 的 P1 问题。

#### 发现 7: repair fingerprint 仍然直接包含本地路径
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift:513`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:487`

事实:
- `RepairResult.identityKey` 优先把 `attempt_dir` 整个路径拼进 identity。
- `MenuBarManager` 再用这个字符串做去重。

影响:
- 本地目录结构被直接带入 GUI 内部识别键。
- 后续如果把 identity 打进日志、调试输出或 crash 诊断，会暴露更多路径信息。

结论:
- 这是 Step 6 的 P1 问题。

#### 发现 8: 配置 decode 的韧性仍然只在顶层 section
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift:125`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift:145`

事实:
- `AppConfig` 只对顶层 section 使用 `decodeIfPresent(... ) ?? DefaultSection()`。
- `MonitorConfig`、`RepairConfig`、`NotifyConfig` 等 section 仍依赖 synthesized `Decodable`。
- 基线命令中用 `swift -e` 验证过，带默认值的 synthesized `Decodable` 在 key 缺失时仍会抛 `keyNotFound`。

影响:
- 只要 CLI 某个 section 以部分字段形式返回，或未来字段兼容策略发生变化，GUI 仍可能 decode 失败。
- 这类问题当前测试没有覆盖。

结论:
- 这是 Step 6 的 P1 问题。

#### 发现 9: 用户提到的部分问题已经在上一轮修复，不应重复开工
证据:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift:109`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/SettingsView.swift:620`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config.py:537`

事实:
- GUI 冷启动真实健康检查已经存在。
- `notify.manual_repair_keywords`、`notify.ai_approve_keywords`、`notify.ai_reject_keywords` 已接回 Python parser 和 Swift 模型。
- OpenClaw、notify、anomaly guard 的大量高价值字段已经进了设置页。

影响:
- 这轮如果继续按“字段补齐”展开，会重复上轮工作，且无法触达真正的架构债。

结论:
- 本轮应优先做 runtime、调度、状态机、窗口协调和测试，不再把时间花在重复字段对齐上。

### Step 1: Runtime 职责拆分
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarController.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/MenuBarStore.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/MenuBuilder.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/RuntimeServices.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/WindowCoordinator.swift` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/ApprovalCoordinator.swift` (新建)

执行内容:
- [x] 复核工作树中已存在的 runtime 拆分草稿，确认 `MenuBarStore`、`RuntimeServices`、`MenuBuilder` 已经落地
- [x] 给 `MenuBarManager` 增加 façade 级依赖转发与 `store.objectWillChange -> manager.objectWillChange` 桥接
- [x] 把 controller 中的窗口与通用弹窗管理抽到 `WindowCoordinator`
- [x] 把 AI 审批弹窗抽到 `ApprovalCoordinator`
- [x] 收缩 `MenuBarController` 到 AppKit 生命周期 + action 转发

命令记录:
```bash
wc -l gui/Sources/FixMyClawGUI/MenuBarManager.swift \
      gui/Sources/FixMyClawGUI/MenuBarController.swift \
      gui/Sources/FixMyClawGUI/Runtime/*.swift
swift build
swift test
python -m pytest tests/test_gui_cli_support.py -q
```

结果摘要:
```text
wc -l:
- MenuBarManager.swift: 659
- MenuBarController.swift: 122
- Runtime/ApprovalCoordinator.swift: 34
- Runtime/MenuBarStore.swift: 187
- Runtime/MenuBuilder.swift: 313
- Runtime/RuntimeServices.swift: 292
- Runtime/WindowCoordinator.swift: 130

swift build:
- Build complete! (3.79s)

swift test:
- 9 GUI tests passed

tests/test_gui_cli_support.py:
- 15 passed in 0.07s
```

完成情况:
- `MenuBarManager` 不再直接持有 `@Published` 运行态状态；状态集中到 `MenuBarStore`
- CLI / 文件 IO 已集中到 `RuntimeServices`
- 菜单拼装已集中到 `MenuBuilder`
- 窗口 / 通用弹窗 / AI 审批弹窗已经有明确 coordinator 边界
- `MenuBarController` 只保留生命周期、订阅和 action 转发

gate:
- passed

### Step 2: 调度与文件观察收敛
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarController.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/RuntimeScheduler.swift` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/RuntimeServices.swift`

执行内容:
- [x] 用 `RuntimeScheduler` 统一管理周期任务，替代原先分散在 manager 里的 4 个裸 `Timer`
- [x] 为状态刷新和健康检查增加简单指数退避
- [x] 用 `DispatchSourceFileSystemObject` 观察状态目录，替代 1 秒 / 2 秒的文件轮询
- [x] 在配置变更和默认配置重建后刷新状态目录观察目标
- [x] 在应用退出时显式 `stop()` scheduler，关闭 timer 和 observer
- [x] 保留 30 秒级 fallback：状态刷新时顺带同步 repair/approval/result，避免 observer 失效时完全失明

命令记录:
```bash
swift build
swift test
python -m pytest tests/test_gui_cli_support.py -q
rg -n "statusTimer|checkTimer|approvalTimer|repairProgressTimer" gui/Sources/FixMyClawGUI
```

结果摘要:
```text
swift build:
- Build complete! (3.79s)

swift test:
- 9 GUI tests passed

tests/test_gui_cli_support.py:
- 15 passed in 0.07s

rg timer fields:
- 无结果
```

完成情况:
- `MenuBarManager` 通过 `RuntimeScheduler.start()/stop()/refreshStateObservation()` 接入统一调度
- 高频文件轮询已移除；repair / approval / result 改为目录事件触发
- 仅保留状态/健康两个低频周期任务，并带失败退避
- `applicationWillTerminate` 会调用 `manager.stop()`，不再遗留悬挂调度器

gate:
- passed

### Step 3: 权威状态机落地
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/AppStateMachine.swift` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/MenuBarStore.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/MenuBuilder.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Tests/FixMyClawGUITests/AppStateMachineTests.swift` (新建)

执行内容:
- [x] 创建 `AppState` 权威状态枚举，取代 `state + effectiveState + currentRepairStage + pendingAiRequest` 松散组合
- [x] 定义 `RepairStage` 修复阶段枚举，统一修复状态表示
- [x] 创建 `AppStateEvent` 状态事件枚举，规范状态转换输入
- [x] 实现 `AppStateReducer` 纯函数状态机 reducer
- [x] 创建 `AppStateContext` 保存不参与状态转换的辅助信息
- [x] 重构 `MenuBarStore` 使用 `AppState` 作为唯一状态源
- [x] 更新 `MenuBuilder` 消费 `AppState` 而非 `ServiceState`
- [x] 添加 21 个状态机测试，覆盖状态转换、属性、优先级

命令记录:
```bash
wc -l gui/Sources/FixMyClawGUI/Runtime/AppStateMachine.swift \
      gui/Sources/FixMyClawGUI/Runtime/MenuBarStore.swift \
      gui/Tests/FixMyClawGUITests/AppStateMachineTests.swift
swift build
swift test
python -m pytest tests/test_gui_cli_support.py -q
```

结果摘要:
```text
wc -l:
- AppStateMachine.swift: 280
- MenuBarStore.swift: 230
- AppStateMachineTests.swift: 270

swift build:
- Build complete! (2.30s)

swift test:
- 30 GUI tests passed (21 个新状态机测试 + 9 个原有测试)

tests/test_gui_cli_support.py:
- 15 passed in 0.06s
```

完成情况:
- `effectiveState` 已删除，现在直接消费 `state`（权威状态）
- 状态转换通过 `AppStateReducer.reduce(state:event:)` 统一处理
- 修复中/审批中状态优先级由状态机保证，不再散落各处
- 菜单构建、图标显示、tooltip 都消费同一份权威状态
- 新增状态机测试覆盖：
  - 初始状态与配置加载
  - 健康检查状态转换
  - 监控切换状态转换
  - 修复状态转换（开始、进度、完成）
  - 审批状态转换（请求、响应、过期）
  - 状态优先级（修复/审批优先于健康检查）
  - 状态属性一致性

复核记录 (2026-03-09，修复前):

命令记录:
```bash
git status --short --branch
swift build
swift test
python -m pytest tests/test_gui_cli_support.py -q
rg -n "healthCheckCompleted|healthCheckStarted|configLoaded|monitoringToggled|repairStarted|repairCompleted|approvalRequested|approvalExpired|approvalResponded" gui/Sources/FixMyClawGUI
rg -n "store\\.state\\s*=" gui/Sources/FixMyClawGUI/MenuBarManager.swift gui/Sources/FixMyClawGUI/Runtime/MenuBarStore.swift
```

结果摘要:
```text
git status --short --branch:
- ## main...origin/main [ahead 17]
-  M gui/Sources/FixMyClawGUI/MenuBarController.swift
-  M gui/Sources/FixMyClawGUI/MenuBarManager.swift
- ?? gui/Sources/FixMyClawGUI/Runtime/
- ?? gui/Tests/FixMyClawGUITests/AppStateMachineTests.swift

swift build:
- Build complete! (0.18s)

swift test:
- 30 GUI tests passed

tests/test_gui_cli_support.py:
- 15 passed in 0.06s

rg reducer wiring:
- 运行时代码里只定义了 `AppStateEvent` / `AppStateReducer`
- `healthCheckCompleted`、`configLoaded`、`monitoringToggled` 等关键事件没有接入生产路径

rg direct state writes:
- `MenuBarManager.swift:87` / `121` / `211` 仍直接写 `store.state`
```

复核结论:
- 当前通过的是 reducer 单测，不是完整的 runtime 接线验收。
- `refreshHealthSnapshot()` 只更新 `lastCheckResult`，没有派发 `healthCheckCompleted`；`initialSetup()` 和 `toggleMonitoring()` 也没有把配置加载、监控切换事件送进状态机，所以 GUI 运行时不能稳定收敛到 `healthy` / `unhealthy` / `paused*`。
- `MenuBarStore.state` 仍是公开可写，`MenuBarManager` 仍在多个入口直接赋值，Step 3 的“受控状态转换入口” gate 未满足。
- 当前工作树已混入 `WindowCoordinator` / `ApprovalCoordinator` 与 controller alert 抽离，这属于 Step 4 范围；在 Step 3 仍 blocked 的情况下不能继续往 Step 4 推进。

下一步建议:
- 先只在 `gui-runtime-core` / `gui-contract` 范围内收口 Step 3，把生产代码统一改为经由 `store.send(...)` 或等价受控 API 驱动状态转换。
- 增补一组接线级测试，至少覆盖“真实健康检查后 state 从 `checking` 收敛到 `healthy`/`unhealthy`”和“toggleMonitoring 后 paused/active 状态切换”。
- Step 3 gate 通过前，不再扩大 `WindowCoordinator` / `ApprovalCoordinator` 的行为改动；Step 4 保持 `pending`。

修复记录 (2026-03-09):

执行内容:
- [x] 把 `healthCheckCompleted` 事件改为显式携带 `monitoringEnabled`，消除“首次健康检查默认走 paused 分支”的状态丢失
- [x] 在 `MenuBarStore.updateStatusPayload()` 中接入 `configLoaded` + `monitoringToggled`，让 `status --json` 真正驱动权威状态
- [x] 用 `beginHealthCheck()` / `failHealthCheck()` / `updateHealthCheck(..., monitoringEnabled:)` 收口运行时状态入口
- [x] 移除 `MenuBarManager` 中剩余的直接 `store.state` 赋值
- [x] 补强 reducer 优先级，防止异步健康检查或 repair progress 覆盖 `repairing` / `awaitingApproval`
- [x] 重写状态机测试，去掉测试里的直接状态赋值，并新增接线级断言

命令记录:
```bash
rg -n "store\\.state\\s*=|\\.state\\s*=" gui/Sources/FixMyClawGUI/MenuBarManager.swift gui/Sources/FixMyClawGUI/Runtime/MenuBarStore.swift gui/Tests/FixMyClawGUITests/AppStateMachineTests.swift
swift build
swift test
python -m pytest tests/test_gui_cli_support.py -q
```

结果摘要:
```text
rg direct state writes:
- 无结果

swift build:
- Build complete! (3.49s)

swift test:
- 33 GUI tests passed (24 个 AppStateMachineTests + 9 个 PayloadDecodingTests)

tests/test_gui_cli_support.py:
- 15 passed in 0.07s
```

修复结论:
- `MenuBarManager` 现在通过受控事件驱动状态机，不再直接写权威状态。
- `status --json` 的 `enabled` / `config_exists` 已进入权威状态流，启动后和手动切换监控后都能收敛到正确状态。
- 状态机测试不再绕过生产入口直接赋值，Step 3 gate 所需的受控入口和优先级保护已经补齐。
- 当前工作树里提前存在的 Step 4 coordinator 代码仍未继续扩大，本次修复范围保持在 `gui-runtime-core` / `gui-contract`。

下一步建议:
- Step 4 可以开始，但应只处理交互协调与非阻塞展示，不再回头改 Step 3 的状态入口。
- 进入 Step 4 前，先把现有 `WindowCoordinator` / `ApprovalCoordinator` 当作草稿重新对照计划 gate，确认哪些只是边界拆分，哪些需要改为非阻塞 sheet / window 流程。

gate:
- passed

### Step 4: 交互协调与错误处理降阻塞
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarController.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/MenuBarManager.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/AlertPresenter.swift` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/WindowCoordinator.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/ApprovalCoordinator.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/AppStateMachine.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Runtime/MenuBarStore.swift`

执行内容:
- [x] 接受用户批准的范围扩展，把 `Runtime/WindowCoordinator.swift`、`Runtime/ApprovalCoordinator.swift` 和新增 presenter 文件纳入 step4
- [x] 新建 `AlertPresenter`，统一管理非阻塞 alert sheet 的排队和展示
- [x] 将错误、确认、状态详情、欢迎提示、AI 审批从 `runModal()` 改为异步回调式 sheet
- [x] 给 runtime 错误增加 `RuntimeAlertCategory`，区分 CLI/IO、配置错误和后台状态提示
- [x] 保持设置窗口生命周期集中在 `WindowCoordinator`，不扩展到 step5 的 settings 拆分

命令记录:
```bash
rg -n "runModal\\(" gui/Sources/FixMyClawGUI
swift build
swift test
python -m pytest tests/test_gui_cli_support.py -q
```

结果摘要:
```text
rg runModal:
- 无结果

swift build:
- Build complete! (0.18s / 3.92s)

swift test:
- 33 GUI tests passed

tests/test_gui_cli_support.py:
- 15 passed in 0.07s
```

完成情况:
- `MenuBarController` 只做 action 转发，不再直接等待阻塞式确认结果。
- `WindowCoordinator` / `ApprovalCoordinator` 已统一依赖 `AlertPresenter`，交互改为非阻塞。
- runtime 错误不再只有一种 warning 弹窗；CLI/IO、配置错误、后台状态提示已分流到不同标题和 alert style。
- 设置窗口仍由单一 coordinator 管理，关闭后会释放引用并允许复用或重建。

下一步建议:
- Step 5 只处理 settings 模块化拆分，不再回头扩大 step4 的交互行为范围。
- 如果后续需要给 step4 补测试，优先补 coordinator/presenter 的纯逻辑层，而不是把 AppKit UI 测试混进当前回归集。

gate:
- passed

### Step 5: Settings 模块化拆分
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/SettingsView.swift` (重构为容器)
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/Settings/SettingsFormControls.swift` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/Settings/ConfigBindable.swift` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/Settings/MonitorSettingsView.swift` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/Settings/RepairSettingsView.swift` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/Settings/AiSettingsView.swift` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/Settings/IdSettingsView.swift` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/Settings/AdvancedSettingsView.swift` (新建)

执行内容:
- [x] 创建 `Views/Settings/` 目录结构
- [x] 提取通用表单控件 (`SectionHeader`, `TextFieldRow`, `PickerRow`, `IntField`, `DoubleField`, `MultilineTextField`, `LineListEditor`, `CommandListEditor`) 到 `SettingsFormControls.swift`
- [x] 提取 `ConfigBindable` 协议和 binding helpers (`binding`, `lineListBinding`, `commandListBinding`) 到 `ConfigBindable.swift`
- [x] 提取命令行解析工具函数 (`normalizedLineList`, `parseLineList`, `normalizedCommandList`, `parseCommandList`, `tokenizeCommandLine`) 到 `ConfigBindable.swift`
- [x] 创建 `MonitorSettingsView.swift` - 监控轮询、状态与日志路径、日志轮转设置
- [x] 创建 `RepairSettingsView.swift` - 自动修复开关、会话控制、会话文案、官方修复步骤
- [x] 创建 `AiSettingsView.swift` - AI 修复基础、AI 命令参数
- [x] 创建 `IdSettingsView.swift` - 会话 Agent IDs、Agent 角色别名、通知接收人
- [x] 创建 `AdvancedSettingsView.swift` - OpenClaw CLI、通知、异常检测高级字段
- [x] 重构 `SettingsView.swift` 为精简容器 (124 行)，只保留根容器、Tab 切换和底部操作栏

命令记录:
```bash
wc -l gui/Sources/FixMyClawGUI/Views/SettingsView.swift \
      gui/Sources/FixMyClawGUI/Views/Settings/*.swift
swift build
swift test
python -m pytest tests/test_gui_cli_support.py -q
```

结果摘要:
```text
wc -l:
- SettingsView.swift: 124 (原 1359 行，减少 90%)
- SettingsFormControls.swift: 196
- ConfigBindable.swift: 166
- MonitorSettingsView.swift: 110
- RepairSettingsView.swift: 148
- AiSettingsView.swift: 112
- IdSettingsView.swift: 76
- AdvancedSettingsView.swift: 456
- 总计: 1388 行 (原单文件 1359 行，拆分后结构更清晰)

swift build:
- Build complete! (3.05s)

swift test:
- 33 GUI tests passed (24 个 AppStateMachineTests + 9 个 PayloadDecodingTests)

tests/test_gui_cli_support.py:
- 15 passed in 0.06s
```

完成情况:
- `SettingsView.swift` 从 1359 行缩减到 124 行，只保留容器层和最小公共定义
- 5 个 tab 视图已拆分到独立文件，维护时可以独立修改
- 通用表单控件和 binding helpers 已提取到可复用模块
- 保持当前字段覆盖范围和保存逻辑不回退
- 所有测试通过，无行为变更

gate:
- passed

### Step 6: 解码韧性、fingerprint 与测试补强
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/ConfigManager.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Tests/FixMyClawGUITests/ConfigResilienceTests.swift` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Tests/FixMyClawGUITests/RuntimeSchedulerTests.swift` (新建)

执行内容:
- [x] 为 `MonitorConfig`、`OpenClawConfig`、`RepairConfig`、`AnomalyGuardConfig`、`NotifyConfig`、`AiConfig`、`AgentRolesConfig` 增加字段级缺省解码
- [x] 为 `AppConfig` 显式补回 `init()`，避免自定义 `init(from:)` 抑制默认构造
- [x] 将 `RepairResult.identityKey` 从完整 `attempt_dir` 改为 `basename + stable hash`
- [x] 提取 `ConfigManager.mergePayloadPreservingUnknownFields(...)`，让 settings 保存逻辑可直接测试
- [x] 新增 config 解码韧性、repair fingerprint 脱敏、settings merge 保存和 runtime scheduler/observer 测试

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
- 38 GUI tests passed
- AppStateMachineTests: 24
- PayloadDecodingTests: 9
- ConfigResilienceTests: 3 (新增)
- RuntimeSchedulerTests: 2 (新增)

swift build:
- Build complete! (0.19s)

tests/test_gui_cli_support.py:
- 15 passed in 0.07s

git status --short:
- Step 6 新增/修改文件位于 `Models.swift`、`ConfigManager.swift`、`gui/Tests/`
- 工作树仍包含前序 Step 1-5 的未提交改动和新增文件
```

完成情况:
- section 内缺字段不再触发整段配置 decode 失败，缺失值会回退到 Swift 默认值
- repair 去重 fingerprint 不再暴露完整本地路径，同时保留同 basename 不同目录的区分能力
- settings 保存路径现在有直接的 merge 回归保护，能证明未触碰字段不会被 JSON round-trip 吃掉
- runtime 测试覆盖已从状态机和 payload 解码扩展到 scheduler refresh 与目录 observer 触发路径

下一步建议:
- Step 7 只做最终验证和文档收尾，先基于当前“文件观察 + 低频健康检查”给出是否足够的结论
- 除非 Step 7 验证发现延迟或可靠性问题，否则不要提前扩到 `DistributedNotificationCenter` / XPC

gate:
- passed

### Step 7: 验证、文档收尾与 push 通道评估
执行日期: 2026-03-09
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-architecture-optimization-plan.md`
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/gui-architecture-optimization-log.md`

执行内容:
- [x] 复核当前工作树状态，确认 Step 7 只触碰 `docs` 锁组
- [x] 运行最终验证命令：`swift build`、`swift test`、`python -m pytest tests/test_gui_cli_support.py -q`
- [x] 汇总本轮 7 个步骤的 gate 与验证结果
- [x] 对“文件观察 + 低频健康检查”是否足够给出结论
- [x] 完成本轮计划与执行日志收尾

命令记录:
```bash
git status --short --branch
swift build
swift test
python -m pytest tests/test_gui_cli_support.py -q
git status --short
rg -n "DispatchSourceFileSystemObject|refreshNow\\(|statusTask = PeriodicTask|healthTask = PeriodicTask|refreshStateObservation" \
  gui/Sources/FixMyClawGUI/Runtime/RuntimeScheduler.swift
```

结果摘要:
```text
git status --short --branch:
- ## main...origin/main [ahead 17]
- 工作树包含 Step 1-6 的既有未提交改动；Step 7 只更新 docs

swift build:
- Build complete! (0.14s)

swift test:
- 38 GUI tests passed
- AppStateMachineTests: 24
- PayloadDecodingTests: 9
- ConfigResilienceTests: 3
- RuntimeSchedulerTests: 2

tests/test_gui_cli_support.py:
- 15 passed in 0.07s

RuntimeScheduler evidence:
- 使用 `DispatchSourceFileSystemObject` 观察状态目录
- 保留 `refreshNow()` 主动刷新入口
- 保留 30 秒状态刷新 / 300 秒健康检查两个低频任务，并带退避
```

结论:
- 当前“目录事件观察 + 低频状态/健康检查 + 失败退避”已经满足本轮 GUI runtime 的时效性与可靠性目标。
- 现阶段没有事实证据表明必须引入 `DistributedNotificationCenter` 或 XPC push 通道；继续引入只会扩大复杂度和耦合面。
- 因此本轮结论是 `push 通道暂不需要`。只有在后续真实使用中出现以下任一事实，才应登记下一轮评估:
  - 文件事件漏报或状态长时间不收敛
  - 应用睡眠/唤醒后 observer 失效且低频回退不能接受
  - 需要低于当前轮询/observer 组合所能提供的状态延迟

遗留风险:
- 当前测试仍然偏单元/集成层，未覆盖真实 AppKit 菜单栏交互和 sleep/wake 生命周期。
- `RuntimeSchedulerTests` 已验证目录写入触发，但尚未覆盖目录 rename/delete 后的恢复场景。
- 工作树仍有 Step 1-6 的未提交变更；本步骤只负责验证与文档收尾，不处理提交流程。

下一步建议:
- 本轮 plan 可以视为完成；如需后续动作，优先做提交整理或人工 smoke test，而不是继续扩大架构范围。

gate:
- passed

## 变更建议记录
- 2026-03-09: 当前工作树已提前混入 Step 4 范围的 `WindowCoordinator` / `ApprovalCoordinator` 和 `MenuBarController` alert 抽离改动。建议先冻结这部分行为，只把它们当作 Step 1 拆边界的遗留草稿；待 Step 3 runtime 接线补齐并重新验收后，再正式进入 Step 4。
- 2026-03-09: 用户已批准将 `Runtime/WindowCoordinator.swift`、`Runtime/ApprovalCoordinator.swift` 和新增 `Runtime/AlertPresenter.swift` 纳入 Step 4 范围，本轮已按该范围完成实现。
