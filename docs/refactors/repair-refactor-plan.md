# Fix-My-Claw Repair 模块重构计划

## 版本信息
- 创建日期: 2026-03-08
- 计划版本: v1.2
- 当前状态: step6
- 目标周期: 10-14 天
- 风险等级: 中高

## 文档用途
这是这次重构的唯一计划文档。所有窗口在开始执行前都必须先读完本文件，再读执行日志。

配套日志文件:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/repair-refactor-log.md`

如果计划需要变更，先在日志里登记变更建议，再回到本文件修改。不要在实现过程中默默改顺序、改范围或改兼容约束。

## 重构目标
将 `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair.py` 从“全量实现文件”逐步收敛为“公共入口 + 少量组装逻辑”，并把类型、执行 helper、stage 实现和状态机分别落到独立模块中。

最终目标结构:
- `repair.py`: 公共入口与兼容 re-export
- `repair_types.py`: 结果模型、payload、legacy details 转换
- `repair_ops.py`: 执行 helper
- `stages/`: 具体 stage
- `repair_state_machine.py`: 状态机
- `messages.py`: 通知文案

## 核心原则：行为冻结
以下行为绝对不允许改变，除非本计划明确更新:
- CLI JSON 输出格式，包括 `repair --json`、`config show --json`、`config set --json`
- TOML 配置结构、字段名和默认值
- `state.json` 与 `repair_progress.json` 的格式
- `attempts/` 目录结构和文件命名
- 所有用户可见通知文案
- `RepairResult.details` 的 legacy key
- stage 名称
- stage 执行顺序
- `mark_repair_attempt()` 与 `mark_ai_attempt()` 的调用时机
- `clear_repair_progress()` 的所有早退时机

## 协作规则
- 任意时刻只允许一个步骤处于 `in_progress`。
- `repair.py`、`repair_types.py`、`repair_ops.py`、`stages/`、`repair_state_machine.py` 属于同一个锁组，同一时间只允许一个窗口写这个锁组。
- 新窗口开始前必须先看计划文档和日志文档，再看当前 `git status`。
- 如果发现需要跳步，先停下，在日志里登记变更建议，再更新本计划。
- 如果需要新建分支，分支名前缀必须使用 `codex/`。

## 执行顺序
0. 预快照
1. 建立回归测试围栏
2. GUI Schema Drift 修复
3. 通知文本集中化
4. 拆出 Repair 类型层
5. 拆出 Repair 执行 Helper 层
6. 提取配置验证 Helper
7. 拆出 Stage 实现
8. Repair.py 收敛为 Façade
9. 引入状态机
10. 最终兼容性收尾

## 步骤详情

### Step 0: 预快照
状态: done
目标: 记录当前行为，作为全程对比基线。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/repair-refactor-log.md`

执行内容:
1. 记录当前 `git status`
2. 生成行为快照:
   - `python -m pytest tests/test_anomaly_guard.py -v --tb=short > /tmp/behavior_snapshot_before.txt`
3. 记录 `repair.py` 顶层符号清单:
   - `python - <<'PY' ...` 或等价命令输出到 `/tmp/repair_symbols_before.txt`
4. 如果需要新建分支，使用 `codex/repair-refactor`

完成 gate:
- 行为快照和符号清单都已生成
- 日志已记录执行人、时间和基线文件位置

回滚:
- 无需代码回滚，只需保留快照记录

### Step 1: 建立回归测试围栏
状态: done
前置依赖: Step 0
目标: 冻结当前 repair 分支行为，后续所有结构改动都靠这些测试兜底。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/tests/test_anomaly_guard.py`
- `/Users/mima0000/.openclaw/fix-my-claw/tests/test_gui_cli_support.py`
- 如确有必要，可新建 `/Users/mima0000/.openclaw/fix-my-claw/tests/test_repair_flow.py`

禁止修改:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair.py`

必须覆盖:
- already healthy
- repair disabled
- cooldown
- soft pause 恢复
- skip soft pause
- official 恢复
- AI disabled
- AI rate limited
- no approval
- backup error
- AI config success
- AI code success
- 最终失败

每个分支都必须断言:
- `attempted` / `fixed` / `used_ai`
- `RepairResult.details` 的关键 legacy key
- stage 顺序
- 最终通知内容
- `repair_progress` 状态流

完成 gate:
- 关键 repair 分支回归测试全部通过
- 日志中记录新增或扩展了哪些测试

回滚:
- 删除新增测试或恢复到基线

### Step 2: GUI Schema Drift 修复
状态: done
前置依赖: Step 1
目标: 修复 Swift 配置模型与 Python 配置模型不一致的问题。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/SettingsView.swift`
- `/Users/mima0000/.openclaw/fix-my-claw/tests/test_gui_cli_support.py`

必须完成:
- `NotifyConfig` 增加 `level`
- `SettingsView` 增加通知级别 Picker
- 修正 Swift `notify.target` 默认值漂移

完成 gate:
- `swift build` 通过
- GUI 保存现有配置时不会把 `notify.level` 静默回退
- `config show --json` / `config set --json` 兼容性不变

回滚:
- 恢复 Swift 文件到基线

### Step 3: 通知文本集中化
状态: done
前置依赖: Step 2
目标: 将所有用户可见通知文案集中到单独模块。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/messages.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/notify.py`
- `/Users/mima0000/.openclaw/fix-my-claw/tests/test_messages.py`

约束:
- 只搬文案，不改变文案内容
- 优先使用模块常量和小型格式化函数，不使用 dataclass 消息容器

完成 gate:
- `repair.py` 和 `notify.py` 中不再保留硬编码 `fix-my-claw:` 文案
- 文案一致性测试通过

回滚:
- 删除 `messages.py`，把文案移回原文件

### Step 4: 拆出 Repair 类型层
状态: done
前置依赖: Step 3
目标: 先把结果模型和 legacy 兼容层从 `repair.py` 抽离出去。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair_types.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair.py`

迁移范围:
- `CommandExecutionRecord`
- 全部 stage payload dataclass
- `StagePayload`
- `StageResult`
- `RepairPipelineContext`
- `RepairOutcome`
- `RepairResult`
- `_require_stage_payload`
- legacy `details` 转换相关 helper

完成 gate:
- `repair.py` 通过 re-export 保持现有 import 路径可用
- 所有现有测试无需改 import 即可通过

回滚:
- 将类型定义移回 `repair.py`

### Step 5: 拆出 Repair 执行 Helper 层
状态: done
前置依赖: Step 4
目标: 将 operational helper 从 `repair.py` 抽离到单独模块。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair_ops.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair.py`

迁移范围:
- session 查询与消息下发相关 helper
- attempt 目录相关 helper
- context 收集与健康复检 helper
- official repair helper
- AI prompt、AI command、AI repair helper
- backup helper

约束:
- `attempt_repair()` 继续留在 `repair.py`
- 这一阶段只做函数迁移和 import 替换，不改变分支逻辑

完成 gate:
- `repair.py` 中 helper 明显减少
- 回归测试全部通过

回滚:
- 将 helper 函数移回 `repair.py`

### Step 6: 提取配置验证 Helper
状态: done
前置依赖: Step 5
目标: 把配置验证中的通用 clamp/normalize 抽成 helper，同时保留领域规则。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config_validation.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config.py`
- 必要时更新相关测试

保留在 `config.py` 的逻辑:
- `official_steps` 白名单过滤
- `min_ping_pong_turns` 兼容别名
- `notify.level` 枚举校验

约束:
- 所有默认值必须来自 dataclass 默认实例
- 不能引入新的 min/max 规则

完成 gate:
- `_parse_*` 重复验证逻辑减少
- 默认值和当前行为保持一致

回滚:
- 删除 `config_validation.py`，恢复原始 parse 实现

### Step 7: 拆出 Stage 实现
状态: done
前置依赖: Step 6
目标: 将 stage 类按职责拆到 `stages/`，但不做过度抽象。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/stages/__init__.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/stages/base.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/stages/pause.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/stages/session.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/stages/official.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/stages/ai.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/stages/final.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair.py`

抽象规则:
- 允许使用轻量 `RepairStage` 基类或协议
- 只为需要 `write_repair_progress()` 的 stage 提供 progress helper
- 不要求所有 stage 继承同一个大而全基类

完成 gate:
- stage 文件拆分完成
- stage 行为与基线一致

回滚:
- 将 stage 定义移回 `repair.py`

### Step 8: Repair.py 收敛为 Façade
状态: pending
前置依赖: Step 7
目标: 把 `repair.py` 收敛成入口文件，而不是以行数为目标。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair.py`

完成标准:
- `repair.py` 只保留公共入口、少量 glue code、兼容 re-export
- 不再保留大块类型定义、helper 定义或 stage 定义

禁止做法:
- 不要求 `repair.py` 必须少于某个固定行数

完成 gate:
- 结构职责清晰
- 回归测试全部通过

回滚:
- 视需要把 façade 化的搬迁内容放回 `repair.py`

### Step 9: 引入状态机
状态: pending
前置依赖: Step 8
目标: 用显式状态机重写 orchestration，而不是改 stage 行为。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair_state_machine.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair.py`
- 必要时调整 `stages/` 或 `repair_types.py`

状态机规则:
- 只有执行型状态写入 `outcome.stages`
- 纯判断状态不写入 stage
- AI rate limit 继续保留 synthetic `ai_decision` stage
- `mark_repair_attempt()`、`mark_ai_attempt()` 和 `clear_repair_progress()` 时机不变

完成 gate:
- `attempt_repair()` 的控制流改由状态机承接
- 所有兼容性约束维持不变

回滚:
- 保留旧 orchestration 的可恢复版本，必要时回切

### Step 10: 最终兼容性收尾
状态: pending
前置依赖: Step 9
目标: 做最后一轮兼容性校验和过渡代码清理。

允许修改:
- 本计划涉及的所有重构文件
- 文档

必须完成:
- 全量测试
- CLI JSON 回归检查
- `repair_progress.json` 与 `attempts/` 目录验证
- 文档同步

注意:
- 不要求删除所有 re-export；只删除确认无兼容价值的过渡代码
- 不在本步骤改 `AGENTS.md`

完成 gate:
- 全量测试通过
- 兼容性检查无差异，或差异已明确记录并批准

回滚:
- 按日志回退到最近一个稳定步骤

## 每步统一检查项
每个步骤结束时都要在日志中记录:
- 修改了哪些文件
- 跑了哪些命令
- 哪些 gate 已通过
- 是否触发阻塞
- 下一步是否可以开始

## 快速判断：当前窗口能不能继续做
只有同时满足下面条件，才能继续:
- 日志里当前步骤状态是 `in_progress`
- 你当前要改的文件在该步骤允许修改范围内
- 没有其他窗口持有相同锁组
- 上一步的 gate 已通过
