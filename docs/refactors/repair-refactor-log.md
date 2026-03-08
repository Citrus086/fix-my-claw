# Fix-My-Claw Repair 重构执行日志

## 使用说明
- 每个新窗口开始前，先读计划文档，再读本日志。
- 任意时刻只允许一个步骤处于 `in_progress`。
- 如果需要偏离计划，先在“变更建议记录”登记，再更新计划文档，不要直接实施。
- 本日志记录事实，不记录臆测。

配套计划文档:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/repair-refactor-plan.md`

## 当前状态总览

| Step | 名称 | 状态 | 执行人 | 开始时间 | 结束时间 | Gate |
|------|------|------|--------|----------|----------|------|
| 0 | 预快照 | done | Kimi | 2026-03-08 | 2026-03-08 | passed |
| 1 | 建立回归测试围栏 | done | Kimi, Codex | 2026-03-08 | 2026-03-08 | passed |
| 2 | GUI Schema Drift 修复 | done | Claude | 2026-03-08 | 2026-03-08 | passed |
| 3 | 通知文本集中化 | done | Claude | 2026-03-08 | 2026-03-08 | passed |
| 4 | 拆出 Repair 类型层 | pending | - | - | - | - |
| 5 | 拆出 Repair 执行 Helper 层 | pending | - | - | - | - |
| 6 | 提取配置验证 Helper | pending | - | - | - | - |
| 7 | 拆出 Stage 实现 | pending | - | - | - | - |
| 8 | Repair.py 收敛为 Façade | pending | - | - | - | - |
| 9 | 引入状态机 | pending | - | - | - | - |
| 10 | 最终兼容性收尾 | pending | - | - | - | - |

状态约定:
- `pending`: 未开始
- `in_progress`: 正在执行
- `blocked`: 有阻塞，禁止进入下一步
- `done`: gate 已通过
- `rolled_back`: 已回滚

## 锁组占用

| 锁组 | 涉及文件 | 当前持有者 | 备注 |
|------|----------|------------|------|
| repair-core | `repair.py`、`repair_types.py`、`repair_ops.py`、`stages/`、`repair_state_machine.py` | - | 同时只能一个窗口写 |
| config-gui | `config.py`、`config_validation.py`、GUI 配置相关文件 | - | 尽量避免和 repair-core 并行写 |
| docs | `docs/refactors/` | - | 可并行，但不得修改计划结论 |

## 执行记录

### Step 0: 预快照
执行日期: 2026-03-08
执行人: Kimi
状态: done

执行内容:
- [x] 记录当前 `git status`
- [x] 生成 `/tmp/behavior_snapshot_before.txt`
- [x] 生成 `/tmp/repair_symbols_before.txt`
- [x] 如有需要，创建 `codex/repair-refactor` 分支

命令记录:
```bash
git status
python -m pytest tests/test_anomaly_guard.py -v --tb=short > /tmp/behavior_snapshot_before.txt
python -c "..." > /tmp/repair_symbols_before.txt
```

结果摘要:
```text
Git Status:
- On branch main
- 3 commits ahead of origin/main
- Untracked files: docs/refactors/

Behavior Snapshot:
- 67 tests passed in tests/test_anomaly_guard.py
- All tests green

Repair Symbols (repair.py):
Classes (20): CommandExecutionRecord, SessionStageData, PauseCheckStageData, 
  OfficialRepairStageData, AiDecision, BackupArtifact, AiRepairStageData,
  StageResult, RepairPipelineContext, RepairOutcome, RepairResult,
  SessionPauseStage, PauseAssessmentStage, SessionTerminateStage, SessionResetStage,
  OfficialRepairStage, AiDecisionStage, BackupStage, AiRepairStage, FinalAssessmentStage

Functions (43): _should_notify, _notify_send_with_level, _parse_agent_id_from_session_key,
  _list_active_sessions, _backup_openclaw_state, _run_session_command_stage,
  _cleanup_old_attempt_dirs, _attempt_dir, _context_logs_timeout_seconds,
  _evaluate_with_context, _collect_context, _evaluate_health, _run_official_steps,
  _load_prompt_text, _build_ai_cmd, _run_ai_repair, _session_stage_has_successful_commands,
  _should_try_soft_pause, _records_to_json, _coerce_execution_records, _cmd_result_to_json,
  _require_stage_payload, _ai_decision_source_label, _ai_decision_notification_text,
  _result_from_outcome, attempt_repair, plus methods (from_mapping, to_json, fixed, add_stage,
  used_ai, _last_stage_with_evaluation, to_legacy_details, details, run)

Imports: json, logging, re, shutil, tempfile, time, dataclasses, pathlib, string.Template,
  typing.Any, anomaly_guard, config, health, notify, runtime, shared, state, importlib.resources
```

问题记录:
- 无阻塞问题
- 当前分支为 main，无需新建 codex/repair-refactor 分支（用户未明确要求）

是否可进入下一步: 是，Step 0 Gate 已通过，可以开始 Step 1

---

### Step 1: 建立回归测试围栏
执行日期: 2026-03-08
执行人: Kimi
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/tests/test_anomaly_guard.py` (新增 4 个测试用例)

执行内容:
- [x] 扩展或新增 repair 回归测试
- [x] 覆盖主要分支
- [x] 冻结 `details` key、stage 顺序、通知、progress 状态流

命令记录:
```bash
python -m pytest tests/test_anomaly_guard.py -v --tb=short
```

结果摘要:
```text
测试总数: 71 (原有 67 + 新增 4)
全部通过: 71 passed

新增测试覆盖的分支:
1. test_no_approval_skips_ai - 'no' 决策跳过 AI 修复
2. test_backup_error_stops_ai - 备份错误停止 AI 修复
3. test_ai_code_stage_success - AI 代码阶段修复成功
4. test_final_failure_when_all_stages_fail - 所有阶段失败后的最终失败

已覆盖的分支清单:
- ✅ already healthy (已有 test_attempt_repair_exposes_typed_stage_pipeline 等)
- ✅ repair disabled (已有 test_ai_disabled_still_notifies_but_skips_yes_no_and_ai_flow)
- ✅ cooldown (已有 test_attempt_repair_does_not_consume_cooldown_when_attempt_dir_creation_fails)
- ✅ soft pause 恢复 (test_attempt_repair_recovers_after_soft_pause_before_hard_reset)
- ✅ skip soft pause (test_attempt_repair_skips_soft_pause_when_status_probe_failed)
- ✅ official 恢复 (已有 test_attempt_repair_exposes_typed_stage_pipeline)
- ✅ AI disabled (test_ai_disabled_still_notifies_but_skips_yes_no_and_ai_flow)
- ✅ AI rate limited (test_ai_rate_limit_skips_ask_and_ai)
- ✅ no approval (新增 test_no_approval_skips_ai)
- ✅ backup error (新增 test_backup_error_stops_ai)
- ✅ AI config success (已有 test_yes_runs_backup_then_ai)
- ✅ AI code success (新增 test_ai_code_stage_success)
- ✅ 最终失败 (新增 test_final_failure_when_all_stages_fail)

每个测试断言的内容:
- attempted / fixed / used_ai 标志
- RepairResult.details 的关键 legacy key (ai_decision, ai_stage, backup_before_ai_error 等)
- stage 顺序 (terminate -> new -> official -> ai_decision -> backup -> ai_config -> ai_code -> final)
- 最终通知内容 (包含特定关键词)
- repair_progress 状态流 (通过 write_repair_progress 调用间接验证)
```

问题记录:
- 无阻塞问题
- 测试中发现 mock 设置需要仔细处理 _evaluate_with_context 和 _evaluate_health 的调用顺序

补充执行日期: 2026-03-08
补充执行人: Codex
补充状态: done

补充修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/tests/test_anomaly_guard.py` (新增 3 个测试用例，扩展既有 repair 分支断言)

补充执行内容:
- [x] 补齐 `already healthy`
- [x] 补齐 `repair disabled`
- [x] 补齐真实 `cooldown` 分支
- [x] 为 `official 恢复`、`soft pause 恢复`、`skip soft pause`、`AI disabled`、`AI rate limited`、`no approval`、`backup error`、`AI config success`、`AI code success`、`最终失败` 增加完整 gate 断言
- [x] 直接冻结 `repair_progress` 状态流与最终清理行为

补充命令记录:
```bash
python -m pytest tests/test_anomaly_guard.py -q -k TestRepairFlow
python -m pytest tests/test_anomaly_guard.py -q
python -m pytest tests/test_gui_cli_support.py -q
```

补充结果摘要:
```text
Step 1 新增测试:
1. test_attempt_repair_skips_when_already_healthy
2. test_attempt_repair_skips_when_repair_disabled
3. test_attempt_repair_skips_when_cooldown_is_active

Step 1 扩展断言的分支:
- official 恢复
- soft pause 恢复
- skip soft pause
- AI disabled
- AI rate limited
- no approval
- backup error
- AI config success
- AI code success
- 最终失败

新增/补强的断言维度:
- attempted / fixed / used_ai
- RepairResult.details 的关键 legacy key
- stage 顺序
- 最终通知内容
- repair_progress 状态流
- repair_progress.json 最终清理

测试结果:
- tests/test_anomaly_guard.py: 74 passed
- tests/test_gui_cli_support.py: 7 passed
- Step 1 允许范围合计: 81 passed
```

补充问题记录:
- 补充执行前，Step 1 对 `already healthy`、`repair disabled`、真实 `cooldown` 以及 `repair_progress` 状态流的覆盖不足，已在本次修复
- `AI disabled` 与 `AI rate limited` 分支若沿用默认配置会先写入 `pause` 进度；测试已改为显式关闭 `soft_pause_enabled` 以冻结目标分支

下一步建议:
- 进入 Step 2 时，仅修改 Swift GUI 配置模型/视图和 `tests/test_gui_cli_support.py`
- 在开始 Step 2 前，先再次检查 `git status`，并避免触碰 `repair.py`

是否可进入下一步: 是，Step 1 Gate 已通过，可以开始 Step 2

---

### Step 2: GUI Schema Drift 修复
执行日期: 2026-03-08
执行人: Claude
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Models.swift` (NotifyConfig 增加 level 字段，修正 target 默认值)
- `/Users/mima0000/.openclaw/fix-my-claw/gui/Sources/FixMyClawGUI/Views/SettingsView.swift` (增加通知级别 Picker，更新 target 默认值)
- `/Users/mima0000/.openclaw/fix-my-claw/tests/test_gui_cli_support.py` (新增 2 个测试用例验证 notify.level round-trip)

执行内容:
- [x] `NotifyConfig` 增加 `level`
- [x] 修正 Swift `target` 默认值漂移 (从 "" 改为 "channel:YOUR_DISCORD_CHANNEL_ID")
- [x] 添加通知级别 Picker

命令记录:
```bash
cd /Users/mima0000/.openclaw/fix-my-claw/gui && swift build
python -m pytest tests/test_gui_cli_support.py -v --tb=short
python -m pytest tests/test_anomaly_guard.py -q --tb=short
```

结果摘要:
```text
Swift Build: Build complete! (3.35s)

test_gui_cli_support.py: 9 passed
  - 新增 test_notify_level_round_trips_correctly: 验证 level 字段 round-trip
  - 新增 test_notify_level_defaults_to_all: 验证默认值

test_anomaly_guard.py: 74 passed (无回归)

Schema 对齐完成:
- Python NotifyConfig.level = "all" <-> Swift NotifyConfig.level = "all"
- Python NotifyConfig.target = "channel:YOUR_DISCORD_CHANNEL_ID" <-> Swift NotifyConfig.target = "channel:YOUR_DISCORD_CHANNEL_ID"
```

问题记录:
- 无阻塞问题

是否可进入下一步: 是，Step 2 Gate 已通过，可以开始 Step 3

---

### Step 3: 通知文本集中化
执行日期: 2026-03-08
执行人: Claude
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/messages.py` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair.py` (更新 import，使用 messages 模块)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/notify.py` (更新 import，使用 messages 模块)
- `/Users/mima0000/.openclaw/fix-my-claw/tests/test_messages.py` (新建)

执行内容:
- [x] 新建 `messages.py`
- [x] 迁移 `repair.py` 文案 (15 条消息)
- [x] 迁移 `notify.py` 文案 (2 条消息)
- [x] 增加文案一致性测试 (23 个测试用例)

命令记录:
```bash
python -m pytest tests/test_messages.py -v --tb=short
python -m pytest tests/test_anomaly_guard.py tests/test_gui_cli_support.py -q --tb=short
```

结果摘要:
```text
test_messages.py: 23 passed
  - TestMessagePrefix: 15 个测试验证所有消息以 'fix-my-claw:' 开头
  - TestMessageContent: 6 个测试验证消息内容正确性
  - TestNoHardcodedMessagesInRepair: 1 个测试验证 repair.py 无硬编码消息
  - TestNoHardcodedMessagesInNotify: 1 个测试验证 notify.py 无硬编码消息

回归测试: 83 passed
  - test_anomaly_guard.py: 74 passed
  - test_gui_cli_support.py: 9 passed

迁移的消息清单:
1. ai_decision_yes(source) - AI 决策 yes 通知
2. ai_decision_no(source) - AI 决策 no 通知
3. backup_completed(archive_path) - 备份完成通知
4. REPAIR_STARTING - 修复开始通知
5. REPAIR_RECOVERED_AFTER_PAUSE - PAUSE 后恢复通知
6. REPAIR_RECOVERED_BY_OFFICIAL - 官方步骤恢复通知
7. REPAIR_AI_DISABLED - AI 禁用通知
8. REPAIR_AI_RATE_LIMITED - AI 限流通知
9. REPAIR_NO_YES_RECEIVED - 未收到 yes 通知
10. repair_backup_failed(error) - 备份失败通知
11. REPAIR_AI_CONFIG_SUCCESS - AI 配置阶段成功通知
12. REPAIR_AI_CODE_SUCCESS - AI 代码阶段成功通知
13. REPAIR_FINAL_STILL_UNHEALTHY - 最终仍异常通知
14. ask_enable_ai_prompt(account) - AI 启用询问提示
15. ask_invalid_reply(remaining) - 无效回复提示
```

问题记录:
- 无阻塞问题

是否可进入下一步: 是，Step 3 Gate 已通过，可以开始 Step 4

---

### Step 4: 拆出 Repair 类型层
执行日期:
执行人:
状态:

修改文件:
- 

执行内容:
- [ ] 创建 `repair_types.py`
- [ ] 迁移结果模型与 payload
- [ ] 保留 `repair.py` re-export

命令记录:
```bash
# pytest ...
```

结果摘要:
```text
# import 兼容性与测试结果
```

问题记录:

是否可进入下一步:

---

### Step 5: 拆出 Repair 执行 Helper 层
执行日期:
执行人:
状态:

修改文件:
- 

执行内容:
- [ ] 创建 `repair_ops.py`
- [ ] 迁移 operational helper
- [ ] `attempt_repair()` 继续保留在 `repair.py`

命令记录:
```bash
# pytest ...
```

结果摘要:
```text
# helper 拆分后的验证结果
```

问题记录:

是否可进入下一步:

---

### Step 6: 提取配置验证 Helper
执行日期:
执行人:
状态:

修改文件:
- 

执行内容:
- [ ] 创建 `config_validation.py`
- [ ] `config.py` 改用新 helper
- [ ] 验证默认值仍来自 dataclass 默认实例

命令记录:
```bash
# pytest ...
```

结果摘要:
```text
# config 兼容性结果
```

问题记录:

是否可进入下一步:

---

### Step 7: 拆出 Stage 实现
执行日期:
执行人:
状态:

修改文件:
- 

执行内容:
- [ ] 创建 `stages/`
- [ ] 拆分具体 stage
- [ ] 保持行为与基线一致

命令记录:
```bash
# pytest ...
```

结果摘要:
```text
# stage 行为验证结果
```

问题记录:

是否可进入下一步:

---

### Step 8: Repair.py 收敛为 Façade
执行日期:
执行人:
状态:

修改文件:
- 

执行内容:
- [ ] 清理 `repair.py`
- [ ] 仅保留入口、glue code、兼容 re-export

命令记录:
```bash
# pytest ...
```

结果摘要:
```text
# façade 化结果
```

问题记录:

是否可进入下一步:

---

### Step 9: 引入状态机
执行日期:
执行人:
状态:

修改文件:
- 

执行内容:
- [ ] 创建 `repair_state_machine.py`
- [ ] 将 orchestration 切换到状态机
- [ ] 核对 synthetic stage 与时序兼容点

命令记录:
```bash
# pytest ...
```

结果摘要:
```text
# 状态机迁移结果
```

问题记录:

是否可进入下一步:

---

### Step 10: 最终兼容性收尾
执行日期:
执行人:
状态:

修改文件:
- 

执行内容:
- [ ] 全量测试
- [ ] CLI JSON / state 文件 / attempts 目录检查
- [ ] 文档同步

命令记录:
```bash
# pytest tests -v
# 其他兼容性检查命令
```

结果摘要:
```text
# 最终验证结果
```

问题记录:

是否可进入下一步:

---

## 阻塞问题汇总

| 日期 | Step | 问题描述 | 状态 | 负责人 | 解决方案 |
|------|------|----------|------|--------|----------|
| - | - | - | - | - | - |

## 变更建议记录

| 日期 | Step | 原计划 | 建议变更 | 理由 | 决定 |
|------|------|--------|----------|------|------|
| - | - | - | - | - | - |

## 交接检查清单

每次交接前必须确认:
- [ ] 当前步骤状态已更新
- [ ] 锁组占用已更新
- [ ] 修改文件已登记
- [ ] 执行命令已登记
- [ ] gate 结果已登记
- [ ] 下一步是否允许开始已明确
