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
| 1 | 运行态状态感知修复 | pending | - | - | - | - |
| 2 | 修复结果与进度展示对齐 | pending | - | - | - | - |
| 3 | 设置页 schema 覆盖补齐 | pending | - | - | - | - |
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
| gui-runtime | `CLIWrapper.swift`、`MenuBarManager.swift`、`MenuBarController.swift` | - | 仅完成审计，未开始代码修改 |
| gui-settings | `Models.swift`、`SettingsView.swift`、`ConfigManager.swift` | - | 仅完成审计，未开始代码修改 |
| gui-contract | `tests/test_gui_cli_support.py`、`gui/Package.swift`、未来 `gui/Tests/` | - | 当前只有基线验证 |
| docs | `docs/refactors/` | Codex | 本次新增 GUI plan/log 文档 |

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
- 当前没有代码实现阻塞，本轮阻塞主要是“范围确认”和“跨 GUI/CLI 的 notify 配置依赖”。
- 尚未开始 Step 1-6 的代码修改。

下一步建议:
- 从 Step 1 开始，先把 GUI 的运行态状态判断修正，否则后续所有“结果展示”都会建立在错误状态之上。
- Step 2 与 Step 3 可以并行设计，但不要同时写同一锁组。

是否可进入下一步: 是，Step 0 Gate 已通过，可以开始 Step 1

## 变更建议记录
- 暂无
