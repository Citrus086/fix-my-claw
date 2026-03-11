# Fix-My-Claw Backend Hotspots 定向瘦身执行日志

## 使用说明
- 每个新窗口开始前，先读计划文档，再读本日志。
- 任意时刻只允许一个步骤处于 `in_progress`。
- 如果需要偏离计划，先在“变更建议记录”登记，再更新计划文档，不要直接实施。
- 本日志记录事实，不记录臆测。

配套计划文档:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/backend-hotspots-refactor-plan.md`

## 当前状态总览

| Step | 名称 | 状态 | 执行人 | 开始时间 | 结束时间 | Gate |
|------|------|------|--------|----------|----------|------|
| 0 | 范围冻结与基线记录 | done | Codex | 2026-03-11 | 2026-03-11 | passed |
| 1 | `cli.py` 拆分为 facade + 子模块 | done | Kimi, Codex | 2026-03-11 | 2026-03-11 | passed |
| 2 | `config.py` 拆分为 facade + 子模块 | done | Kimi | 2026-03-11 | 2026-03-11 | passed |
| 3 | `anomaly_guard.py` 拆分为 facade + 分层实现 | done | Claude | 2026-03-12 | 2026-03-12 | passed |
| 4 | `repair.py` compat / hook 收敛 | done | Claude | 2026-03-12 | 2026-03-12 | passed |
| 5 | 验证、收尾与交接 | done | Claude | 2026-03-12 | 2026-03-12 | passed |

状态约定:
- `pending`: 未开始
- `in_progress`: 正在执行
- `blocked`: 有阻塞，禁止进入下一步
- `done`: gate 已通过
- `rolled_back`: 已回滚

## 锁组占用

| 锁组 | 涉及文件 | 当前持有者 | 备注 |
|------|----------|------------|------|
| backend-cli | `cli.py`、未来 `cli_commands/` | - | Step 1 已完成，锁已释放 |
| backend-config | `config.py`、`config_validation.py`、`config_parts/` | - | Step 2 已完成，锁已释放 |
| backend-anomaly | `anomaly_guard.py`、`anomaly_guard/` | - | Step 3 已完成，锁已释放 |
| backend-repair-compat | `repair.py`、`repair_hooks.py` | - | Step 4 已完成，锁已释放 |
| contracts-gui | `protocol.py`、`contracts/fixtures/`、`tests/test_contracts.py`、`tests/test_gui_cli_support.py`、`gui/` | - | 默认不触碰；若要触碰需先登记变更建议 |
| docs | `docs/refactors/` | - | 当前可自由写入 |

## 执行记录

### Step 0: 范围冻结与基线记录
执行日期: 2026-03-11
执行人: Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/backend-hotspots-refactor-plan.md` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/backend-hotspots-refactor-log.md` (新建)

执行内容:
- [x] 复核当前结构判断，确认本轮只治理 `cli.py`、`config.py`、`anomaly_guard.py`
- [x] 记录当前热点文件行数
- [x] 记录 baseline 测试状态
- [x] 明确“前端最小改动”边界与锁组

命令记录:
```bash
git status --short
wc -l src/fix_my_claw/cli.py \
      src/fix_my_claw/config.py \
      src/fix_my_claw/anomaly_guard.py \
      src/fix_my_claw/repair.py \
      src/fix_my_claw/repair_state_machine.py \
      src/fix_my_claw/monitor.py
python -m pytest tests/test_contracts.py tests/test_gui_cli_support.py tests/test_anomaly_guard.py -q
cd gui && swift test
```

结果摘要:
```text
git status --short:
- 当前工作树不是干净状态，存在大量已修改和未跟踪文件
- 后续 agent 不得回滚与本轮无关的现有改动

wc -l:
- cli.py: 838
- config.py: 733
- anomaly_guard.py: 1350
- repair.py: 435
- repair_state_machine.py: 652
- monitor.py: 183

python -m pytest tests/test_contracts.py tests/test_gui_cli_support.py tests/test_anomaly_guard.py -q:
- 151 passed in 31.55s

swift test:
- 59 tests passed
```

结论:
- `monitor.py` 和 `repair.py` 当前不是最优先的治理对象。
- `cli.py`、`config.py`、`anomaly_guard.py` 是本轮最明确的热点文件。
- 当前 baseline 证明“外壳稳定”，因此本轮必须以“不拖前端下水”为首要边界。

下一步建议:
- Step 1 先拆 `cli.py`
- 默认不动 `protocol.py`、`contracts/fixtures/`、`gui/` 生产代码

gate:
- passed

### Step 1: `cli.py` 拆分为 facade + 子模块
执行日期: 2026-03-11
执行人: Kimi, Codex
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/cli.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/cli_commands/service.py`
- 已承接并保留既有拆分骨架:
  - `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/cli_commands/core.py`
  - `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/cli_commands/config_cmd.py`
  - `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/cli_commands/parser.py`
  - `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/cli_commands/_helpers.py`
  - `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/cli_commands/_config_helpers.py`

执行内容:
- [x] 承接已有 `cli_commands/` 拆分骨架，不回退已拆分模块
- [x] 重建 `cli.py` façade，使其继续暴露旧测试依赖的本地 patch 点
- [x] 保留 `build_parser()` 下沉到 `cli_commands/parser.py`
- [x] 保留 launchd/service 重 helper 下沉到 `cli_commands/service.py`
- [x] 修复 façade 与子模块之间的 patchability 断层
- [x] 对齐 `service status` 路径规范化，恢复 `_as_path()` 语义

命令记录:
```bash
python -m pytest tests/test_gui_cli_support.py -q
python -m pytest tests/test_contracts.py -q
python -m pytest tests/test_gui_cli_support.py tests/test_contracts.py -q
cd /Users/mima0000/.openclaw/fix-my-claw/gui && swift test
wc -l src/fix_my_claw/cli.py \
      src/fix_my_claw/cli_commands/core.py \
      src/fix_my_claw/cli_commands/config_cmd.py \
      src/fix_my_claw/cli_commands/service.py \
      src/fix_my_claw/cli_commands/parser.py
```

结果摘要:
```text
初始 gate 失败:
- tests/test_gui_cli_support.py: 10 failed, 15 passed
- 失败原因集中在 cli façade 未保住旧 patch surface，测试在 `fix_my_claw.cli` 上打补丁时无法穿透到底层实现

修复后 gate:
- python -m pytest tests/test_gui_cli_support.py tests/test_contracts.py -q
  50 passed in 0.15s
- swift test
  59 tests passed

当前文件行数:
- cli.py: 632
- cli_commands/core.py: 285
- cli_commands/config_cmd.py: 71
- cli_commands/service.py: 531
- cli_commands/parser.py: 148
```

关键结论:
- `cli.py` 已不再承担 parser 装配和大段 launchd helper 实现，但为了保持 GUI/测试零改动，仍保留了命令入口和兼容 re-export。
- Step 1 的真正收口点不是“把所有命令逻辑完全搬空”，而是“在保住外部 patch surface 的前提下完成物理拆分”。
- 本轮未修改 `protocol.py`、`contracts/fixtures/` 或任何 `gui/` 生产代码。

下一步建议:
- 进入 Step 2，开始拆 `config.py`
- 优先保持 `config.py` 的兼容导出层，不要重复 Step 1 遇到的 patchability 断层

gate:
- passed

### Step 2: `config.py` 拆分为 facade + 子模块
执行日期: 2026-03-11
执行人: Kimi
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config.py` (重构为 facade)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config_parts/__init__.py` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config_parts/defaults.py` (新建 - 常量和默认 TOML)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config_parts/models.py` (新建 - dataclass schema)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config_parts/parse.py` (新建 - 解析函数)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config_parts/serialize.py` (新建 - 序列化函数)

执行内容:
- [x] 创建 `config_parts/` 目录结构
- [x] 将常量/默认值迁移到 `defaults.py`
- [x] 将数据模型迁移到 `models.py`
- [x] 将解析函数迁移到 `parse.py`
- [x] 将序列化函数迁移到 `serialize.py`
- [x] 重建 `config.py` 作为 facade，保留所有公共导出
- [x] 保持 `anomaly_guard` / `loop_guard` 兼容处理
- [x] 保持 `official_steps` 白名单过滤逻辑
- [x] 保持 `min_ping_pong_turns` 到 `min_cycle_repeated_turns` 的 legacy 兼容

命令记录:
```bash
python -m pytest tests/test_gui_cli_support.py tests/test_contracts.py -q
python -m pytest tests/test_anomaly_guard.py -q
cd /Users/mima0000/.openclaw/fix-my-claw/gui && swift test
wc -l src/fix_my_claw/config.py src/fix_my_claw/config_parts/*.py
```

结果摘要:
```text
python -m pytest tests/test_gui_cli_support.py tests/test_contracts.py -q:
- 50 passed in 0.13s

python -m pytest tests/test_anomaly_guard.py -q:
- 101 passed in 34.78s

swift test:
- 59 tests passed

当前文件行数:
- config.py: 85 (从 733 行缩减)
- config_parts/__init__.py: 5
- config_parts/defaults.py: 162
- config_parts/models.py: 240
- config_parts/parse.py: 265
- config_parts/serialize.py: 111
- 总计: 868 行
```

关键结论:
- `config.py` 已从 733 行缩减为 85 行的 facade，实现有效瘦身。
- 所有公共 API 保持向后兼容，通过 re-export 模式保留原有接口。
- `config_validation.py` 保持独立，不与 GUI 语义耦合。
- 未修改 `protocol.py`、`contracts/fixtures/` 或任何 `gui/` 生产代码。
- 未修改 TOML schema、字段名、默认值。

下一步建议:
- 进入 Step 3，开始拆 `anomaly_guard.py`
- 保持 anomaly detector 语义和输出结构不变

gate:
- passed

### Step 3: `anomaly_guard.py` 拆分为 facade + 分层实现
执行日期: 2026-03-12
执行人: Claude
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/anomaly_guard.py` (重构为 facade)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/anomaly_guard/__init__.py` (新建)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/anomaly_guard/models.py` (新建 - 数据模型)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/anomaly_guard/role_cache.py` (新建 - 角色缓存)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/anomaly_guard/text_utils.py` (新建 - 文本处理工具)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/anomaly_guard/extractors.py` (新建 - 事件和快照提取)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/anomaly_guard/cluster.py` (新建 - 聚类逻辑)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/anomaly_guard/detectors.py` (新建 - 检测器)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/anomaly_guard/service.py` (新建 - 主入口)

执行内容:
- [x] 删除之前不完整的 `anomaly_guard/` 目录，恢复测试通过
- [x] 验证 Step 2 完成状态
- [x] 创建 `anomaly_guard/` 目录结构
- [x] 将数据模型迁移到 `models.py`
- [x] 将角色缓存迁移到 `role_cache.py`
- [x] 将文本处理工具迁移到 `text_utils.py`
- [x] 将事件和快照提取迁移到 `extractors.py`
- [x] 将聚类逻辑迁移到 `cluster.py`
- [x] 将检测器迁移到 `detectors.py`
- [x] 将主入口 `_analyze_anomaly_guard` 迁移到 `service.py`
- [x] 重建 `anomaly_guard.py` 作为 facade，保留所有公共导出
- [x] 保持 detector 输出结构、signals、metrics 字段名不变

命令记录:
```bash
python -m pytest tests/test_contracts.py tests/test_gui_cli_support.py tests/test_anomaly_guard.py -q
cd /Users/mima0000/.openclaw/fix-my-claw/gui && swift test
wc -l src/fix_my_claw/anomaly_guard.py src/fix_my_claw/anomaly_guard/*.py
```

结果摘要:
```text
python -m pytest tests/test_contracts.py tests/test_gui_cli_support.py tests/test_anomaly_guard.py -q:
- 151 passed in 28.75s

swift test:
- 59 tests passed

当前文件行数:
- anomaly_guard.py (facade): 128 (从 1350 行缩减)
- anomaly_guard/__init__.py: 128
- anomaly_guard/cluster.py: 62
- anomaly_guard/detectors.py: 562
- anomaly_guard/extractors.py: 409
- anomaly_guard/models.py: 66
- anomaly_guard/role_cache.py: 86
- anomaly_guard/service.py: 205
- anomaly_guard/text_utils.py: 151
- 总计: 1797 行
```

关键结论:
- `anomaly_guard.py` 已从 1350 行缩减为 128 行的 facade，实现有效瘦身。
- 所有公共 API 保持向后兼容，通过 re-export 模式保留原有接口。
- detector 输出结构、signals、metrics 字段名保持不变。
- 未修改 `protocol.py`、`contracts/fixtures/` 或任何 `gui/` 生产代码。

下一步建议:
- 进入 Step 4，开始 `repair.py` 的最小 compat / hook 收敛
- 保持最小改动原则，不重写主流程

gate:
- passed

### Step 4: `repair.py` compat / hook 收敛
执行日期: 2026-03-12
执行人: Claude
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair.py` (重构为 facade)
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair_hooks.py` (新建 - hook 装配逻辑)

执行内容:
- [x] 分析 `repair.py` 当前结构，确认已是相对干净的 facade
- [x] 创建 `repair_hooks.py`，将 hook 装配逻辑迁移到独立模块
- [x] 将 `_should_notify` 函数迁移到 `repair_hooks.py`
- [x] 将 `build_repair_state_machine_hooks` 函数迁移到 `repair_hooks.py`
- [x] 收口 `repair.py` 的 compat exports，添加清晰的块注释
- [x] 添加 `_now_ts` 到 compat exports 以保持测试 patchability
- [x] 保持 `attempt_repair()` 入口与兼容 import 继续可用

命令记录:
```bash
python -m pytest tests/test_contracts.py tests/test_gui_cli_support.py tests/test_anomaly_guard.py -q
cd /Users/mima0000/.openclaw/fix-my-claw/gui && swift test
wc -l src/fix_my_claw/repair.py src/fix_my_claw/repair_hooks.py
```

结果摘要:
```text
python -m pytest tests/test_contracts.py tests/test_gui_cli_support.py tests/test_anomaly_guard.py -q:
- 151 passed in 32.01s

swift test:
- 59 tests passed

当前文件行数:
- repair.py: 448 (从 435 行略增，主要增加了块注释和兼容导出)
- repair_hooks.py: 132 (新建)
- 总计: 580 行
```

关键结论:
- `repair.py` 继续维持 facade 角色，通过依赖注入调用 `repair_ops.py`。
- `repair_hooks.py` 承担 hook 装配逻辑，结构更清晰。
- 所有公共 API 保持向后兼容，包括测试 patch surface。
- 未修改 `protocol.py`、`contracts/fixtures/` 或任何 `gui/` 生产代码。
- 未修改 `repair_state_machine.py` 或 `stages/`。

下一步建议:
- 进入 Step 5，进行验证、收尾与交接
- 汇总所有步骤的改动和残余风险

gate:
- passed

### Step 5: 验证、收尾与交接
执行日期: 2026-03-12
执行人: Claude
状态: done

修改文件:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/backend-hotspots-refactor-log.md`
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/backend-hotspots-refactor-plan.md`

执行内容:
- [x] 运行 Python 测试 gate: 151 passed
- [x] 运行 Swift 测试 gate: 59 tests passed
- [x] 统计热点文件最终行数
- [x] 验证 GUI 零改动承诺
- [x] 更新日志和计划文档状态

命令记录:
```bash
python -m pytest tests/test_contracts.py tests/test_gui_cli_support.py tests/test_anomaly_guard.py -q
cd /Users/mima0000/.openclaw/fix-my-claw/gui && swift test
wc -l src/fix_my_claw/cli.py src/fix_my_claw/config.py src/fix_my_claw/anomaly_guard.py src/fix_my_claw/repair.py
wc -l src/fix_my_claw/cli_commands/*.py
wc -l src/fix_my_claw/config_parts/*.py
wc -l src/fix_my_claw/anomaly_guard/*.py
wc -l src/fix_my_claw/repair_hooks.py
git status gui/Sources/ --porcelain
git status src/fix_my_claw/protocol.py contracts/fixtures/ --porcelain
```

结果摘要:
```text
Python 测试 gate:
- 151 passed in 34.15s

Swift 测试 gate:
- 59 tests passed

热点文件行数变化 (原始 -> facade):
- cli.py: 838 -> 632 (减少 206 行，-24.6%)
- config.py: 733 -> 85 (减少 648 行，-88.4%)
- anomaly_guard.py: 1350 -> 128 (减少 1222 行，-90.5%)
- repair.py: 435 -> 448 (略增 13 行，+3.0%，主要增加块注释)

新增子模块:
- cli_commands/: 1120 行 (7 个文件)
- config_parts/: 783 行 (5 个文件)
- anomaly_guard/: 1669 行 (8 个文件)
- repair_hooks.py: 132 行

GUI 零改动验证:
- gui/Sources/ 无工作目录改动
- protocol.py 无工作目录改动
- contracts/fixtures/ 无工作目录改动
- 本轮确实做到了 GUI 零改动
```

关键结论:
- 本轮重构成功达成"内部瘦身，外壳不变"目标
- 所有测试通过，外部契约完全保持
- GUI 零改动承诺兑现
- protocol.py、contracts/fixtures/ 未触碰
- 后续 agent 可基于此结构继续推进

## 变更建议记录

暂无。

## 开放问题

暂无。

## 最终汇总

### 重构成果
| 文件 | 原始行数 | 最终行数 | 减少比例 |
|------|----------|----------|----------|
| cli.py | 838 | 632 | -24.6% |
| config.py | 733 | 85 | -88.4% |
| anomaly_guard.py | 1350 | 128 | -90.5% |
| repair.py | 435 | 448 | +3.0% |

### 新增模块
| 模块 | 文件数 | 总行数 |
|------|--------|--------|
| cli_commands/ | 7 | 1120 |
| config_parts/ | 5 | 783 |
| anomaly_guard/ | 8 | 1669 |
| repair_hooks.py | 1 | 132 |

### 承诺兑现
- [x] GUI 零改动
- [x] protocol.py 未修改
- [x] contracts/fixtures/ 未修改
- [x] CLI 子命令名、参数名、退出码语义不变
- [x] JSON payload 结构、字段名、api_version 不变
- [x] TOML schema、字段名、默认值不变
- [x] 所有测试通过 (Python 151, Swift 59)
