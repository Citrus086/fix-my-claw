# Fix-My-Claw Backend Hotspots 定向瘦身计划

## 版本信息
- 创建日期: 2026-03-11
- 计划版本: v1.0
- 当前状态: completed
- 目标周期: 5-8 天
- 实际周期: 2 天 (2026-03-11 ~ 2026-03-12)
- 风险等级: 中

## 文档用途
这是本轮后端结构治理的唯一计划文档。所有执行窗口开始前都必须先读完本文件，再读执行日志。

配套日志文件:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/backend-hotspots-refactor-log.md`

前序文档:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/repair-refactor-plan.md`
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/repair-refactor-log.md`

如果计划需要变更，先在日志里登记变更建议，再回到本文件修改。不要在实现过程中默默改顺序、改范围、改兼容约束，也不要把这一轮扩大成新的“全仓重构”。

## 当前判断
系统级结构仍然健康，但已经进入“热点文件明显偏胖，需要定向瘦身”的阶段。

当前基线事实:
- `monitor.py` 当前 183 行，仍是薄协调层。
- `repair.py` 当前 435 行，已基本是 facade + hook 装配层。
- `repair_state_machine.py` 当前 652 行，当前作为骨架保留，不列为本轮默认拆分对象。
- `cli.py` 当前 838 行，已同时承载命令解析、协议输出、service/launchd 管理。
- `config.py` 当前 733 行，仍同时承载 defaults、schema、parse、serialize、TOML I/O。
- `anomaly_guard.py` 当前 1350 行，已是单文件子系统。

2026-03-11 已确认的 baseline:
- `python -m pytest tests/test_contracts.py tests/test_gui_cli_support.py tests/test_anomaly_guard.py -q` -> `151 passed`
- `swift test` -> `59 tests passed`

## 目标
将后端从“宏观结构稳定但局部拥挤”的状态，推进到“热点模块边界清晰、对前端零或极小影响、后续 agent 可持续推进”的状态。

本轮目标结构:
- `cli.py`: 保留公共入口与兼容导出，具体实现迁移到 `cli_commands/`
- `config.py`: 保留公共入口与兼容导出，解析/序列化/默认值拆到独立模块
- `anomaly_guard.py`: 保留兼容入口，内部按模型、抽取、聚类、detector、汇总分层
- `repair.py`: 仅允许做最小 compat/hook 收敛，不重写主流程

## 核心原则
1. 这一轮优先做物理文件边界整理，不默认引入新的架构层、框架或运行时机制。
2. 外部契约优先于内部整洁。只要会迫使 GUI、fixtures 或协议升级，就默认不做。
3. 过渡期允许保留 facade/compat 层，禁止为“彻底干净”而一次性移除旧入口。
4. 每一步都必须能独立回滚，不做跨三个热点文件的大合并提交。
5. 当前工作树不是干净状态；后续窗口不得回滚不属于本轮的已有改动。

## 非目标
以下内容不属于本轮默认范围，除非日志先登记并更新计划:
- 重写 `repair_state_machine.py`
- 调整 repair stage 顺序、语义或通知文案
- 修改 GUI 交互、Settings UI 或菜单行为
- 修改 CLI 命令名、参数名、退出码语义
- 修改 JSON payload 结构、字段名、`api_version`
- 修改 TOML schema、字段名、默认值
- 修改 `state.json`、`repair_progress.json`、`repair_result.json`、`attempts/` 目录结构
- 重做 anomaly detector 策略，只允许结构性搬迁，不允许默认改变启发式语义

## 行为冻结
以下行为绝对不允许改变，除非本计划明确更新:
- `fix-my-claw status/check/repair/service/config` 的 CLI 子命令名、参数名、退出码语义
- `config show --json`、`config set --json` 的结构与字段名
- `status --json`、`check --json`、`repair --json`、`service status --json`、`service reconcile --json` 的结构与字段名
- `contracts/fixtures/` 的现有结构与语义
- GUI 现有 CLI 调用方式和 decode 预期
- TOML 配置结构、字段名、默认值，以及 `anomaly_guard` / `loop_guard` 兼容关系
- `RepairResult.details` 的 legacy key
- 所有用户可见通知文案

## 前端最小改动约束
默认目标是“不让前端为这轮重构付出任何代码改动”。

硬约束:
- 非阻塞情况下，不得修改 `gui/` 下任何生产代码。
- 非阻塞情况下，不得修改 `protocol.py` 和 `contracts/fixtures/`。
- 如果某一步发现必须修改 GUI、fixtures 或协议，先停止实现，在日志的“变更建议记录”登记，再更新计划；不能边改边说。
- `swift test` 在每一步都必须继续通过，用来证明这轮确实没有把前端拖下水。

## 锁组
- `backend-cli`: `src/fix_my_claw/cli.py`、未来 `src/fix_my_claw/cli_commands/`
- `backend-config`: `src/fix_my_claw/config.py`、`src/fix_my_claw/config_validation.py`、未来配置子模块
- `backend-anomaly`: `src/fix_my_claw/anomaly_guard.py`、未来 `src/fix_my_claw/anomaly_guard/`
- `backend-repair-compat`: `src/fix_my_claw/repair.py`、未来 `src/fix_my_claw/repair_hooks.py`
- `contracts-gui`: `src/fix_my_claw/protocol.py`、`contracts/fixtures/`、`tests/test_contracts.py`、`tests/test_gui_cli_support.py`、`gui/`
- `docs`: `docs/refactors/`

同一时间只允许一个窗口写同一锁组。开始实现前先看本计划、执行日志和当前 `git status`。

## 执行顺序
0. 范围冻结与基线记录
1. `cli.py` 拆分为 facade + 子模块
2. `config.py` 拆分为 facade + 子模块
3. `anomaly_guard.py` 拆分为 facade + 分层实现
4. `repair.py` compat / hook 收敛
5. 验证、收尾与交接

## 步骤详情

### Step 0: 范围冻结与基线记录
状态: done

目标:
- 冻结本轮范围，明确只治理 `cli.py`、`config.py`、`anomaly_guard.py` 三个热点。
- 记录当前文件尺寸、测试状态和工作树状态，作为后续所有窗口的共同基线。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/backend-hotspots-refactor-plan.md`
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/backend-hotspots-refactor-log.md`

执行内容:
1. 复核热点文件职责与当前边界。
2. 记录当前 `git status`、文件行数、baseline 测试结果。
3. 产出本轮 plan + log。

完成 gate:
- plan + log 已创建
- 本轮范围、非目标、锁组、gate 已明确
- baseline 测试状态已记录

回滚:
- 只删除本轮新增文档

### Step 1: `cli.py` 拆分为 facade + 子模块
状态: done
前置依赖: Step 0

目标:
- 将 `cli.py` 从单文件“大杂烩”收敛为稳定入口层。
- 在不改变 CLI 对外行为的前提下，把命令实现拆到单独目录。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/cli.py`
- 新增目录建议:
  - `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/cli_commands/`
- `/Users/mima0000/.openclaw/fix-my-claw/tests/test_gui_cli_support.py`

禁止修改:
- `gui/` 下任何生产代码
- `protocol.py`
- `contracts/fixtures/`

建议拆分边界:
- `cli_commands/core.py`: `init/check/status/start/stop/repair/auto-repair/monitor/up`
- `cli_commands/config.py`: `config show/set`
- `cli_commands/service.py`: launchd/service 相关 helper 与命令
- `cli_commands/parser.py`: parser 装配

必须完成:
- `cli.py` 保留 `main()`、`build_parser()` 入口和兼容导出
- service helper 从主文件物理迁出
- parser 装配逻辑从主文件物理迁出
- 不改变命令名、参数名、帮助语义和返回码

完成 gate:
- `cli.py` 只保留薄入口/兼容壳层
- `python -m pytest tests/test_gui_cli_support.py -q` 通过
- `python -m pytest tests/test_contracts.py -q` 通过
- `swift test` 通过

回滚:
- 删除 `cli_commands/`，把实现移回 `cli.py`

完成说明 (2026-03-11):
- `cli_commands/` 目录已建立，按 `core.py`、`config_cmd.py`、`service.py`、`parser.py` 分离实现与辅助逻辑。
- `cli.py` 已从单文件实现收敛为兼容 façade，保留旧测试依赖的本地 patch 点，如 `_load_or_init_config`、`_with_single_instance` 和 launchd helper re-export。
- 为了保持 GUI/测试零改动，命令入口仍保留在 `cli.py` 做薄包装；重 helper、parser 装配和 launchd 细节已下沉到 `cli_commands/`。
- `cli_commands/service.py` 的路径规范化已对齐 `_as_path()`，避免 `service status` 的 `config_path` 输出漂移。

### Step 2: `config.py` 拆分为 facade + 子模块
状态: done
前置依赖: Step 1

目标:
- 将配置模型、默认值、解析、序列化、TOML I/O 解耦。
- 保留 `config.py` 作为兼容导出层，避免前端和调用方改 import。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config.py`
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config_validation.py`
- 新增目录建议:
  - `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/config_parts/`
- `/Users/mima0000/.openclaw/fix-my-claw/tests/test_gui_cli_support.py`
- `/Users/mima0000/.openclaw/fix-my-claw/tests/test_contracts.py`

禁止修改:
- `gui/` 下任何生产代码
- `contracts/fixtures/`
- `protocol.py`

建议拆分边界:
- `config_parts/models.py`: dataclass schema
- `config_parts/defaults.py`: 常量和默认 TOML 模板
- `config_parts/parse.py`: `_parse_*` 与 `load_config`
- `config_parts/serialize.py`: `_config_to_dict`、`_dict_to_config`、`_write_toml`

保留在 `config.py` 的内容:
- 面向外部的稳定导出
- 兼容别名整理

必须完成:
- `config_validation.py` 继续保持为通用 helper，不与 GUI 语义耦合
- `official_steps` 白名单过滤逻辑保留
- `anomaly_guard` / `loop_guard` 兼容仍保持
- 不改变 TOML schema、默认值和 JSON round-trip 结果

完成 gate:
- `config.py` 只保留薄 facade/compat 壳层 (85 行，原 733 行)
- `python -m pytest tests/test_gui_cli_support.py -q` 通过 (50 passed)
- `python -m pytest tests/test_contracts.py -q` 通过
- `python -m pytest tests/test_anomaly_guard.py -q` 通过 (101 passed)
- `swift test` 通过 (59 tests passed)
- 未修改 `protocol.py`、`contracts/fixtures/`、`gui/` 生产代码

回滚:
- 删除 `config_parts/`，把实现移回 `config.py`

完成说明 (2026-03-11):
- `config_parts/` 目录已建立，按 `defaults.py`、`models.py`、`parse.py`、`serialize.py` 分离实现。
- `config.py` 已从单文件实现收敛为兼容 façade，保留所有公共导出。
- 保持了 `anomaly_guard` / `loop_guard` 兼容、`min_ping_pong_turns` legacy 兼容、`official_steps` 白名单过滤等原有行为。
- 未触碰 `protocol.py`、`contracts/fixtures/`、`gui/` 生产代码，前端零改动。

### Step 3: `anomaly_guard.py` 拆分为 facade + 分层实现
状态: done
前置依赖: Step 2

目标:
- 在不改变 detector 语义和输出结构的前提下，把 `anomaly_guard.py` 从单文件子系统拆为分层实现。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/anomaly_guard.py`
- 新增目录建议:
  - `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/anomaly_guard/`
- `/Users/mima0000/.openclaw/fix-my-claw/tests/test_anomaly_guard.py`

禁止修改:
- `protocol.py`
- `contracts/fixtures/`
- `gui/` 下任何生产代码

建议拆分边界:
- `anomaly_guard/models.py`: `Event`、`CycleMatch`、`StagnationMatch`、`DetectorFinding`
- `anomaly_guard/extractors.py`: transcript/log snapshot、role/cache、line/event 抽取
- `anomaly_guard/cluster.py`: similarity、cluster assign
- `anomaly_guard/detectors.py`: self-repeat/cycle/handoff/stagnation/root-cause detectors
- `anomaly_guard/service.py`: `_analyze_anomaly_guard`

必须完成:
- `anomaly_guard.py` 保留兼容入口 `_analyze_anomaly_guard`
- detector 输出结构、signals、metrics 字段名保持不变
- 不默认调整阈值、启发式或判定先后顺序

完成 gate:
- `anomaly_guard.py` 显著收缩为 facade
- `python -m pytest tests/test_anomaly_guard.py -q` 通过
- `python -m pytest tests/test_contracts.py tests/test_gui_cli_support.py -q` 通过
- `swift test` 通过

回滚:
- 删除 `anomaly_guard/` 目录，把实现移回 `anomaly_guard.py`

完成说明 (2026-03-12):
- `anomaly_guard/` 目录已建立，按 `models.py`、`role_cache.py`、`text_utils.py`、`extractors.py`、`cluster.py`、`detectors.py`、`service.py` 分离实现。
- `anomaly_guard.py` 已从 1350 行缩减为 128 行的兼容 façade，保留所有公共导出。
- 保持了 detector 输出结构、signals、metrics 字段名不变。
- 未触碰 `protocol.py`、`contracts/fixtures/`、`gui/` 生产代码，前端零改动。

### Step 4: `repair.py` compat / hook 收敛
状态: done
前置依赖: Step 3

目标:
- 只做最小规模的 compat/hook 收敛，让 `repair.py` 更清楚地扮演 facade。
- 默认不改动 `repair_state_machine.py` 主体逻辑。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair.py`
- 新增文件建议:
  - `/Users/mima0000/.openclaw/fix-my-claw/src/fix_my_claw/repair_hooks.py`
- `/Users/mima0000/.openclaw/fix-my-claw/tests/test_anomaly_guard.py`

禁止修改:
- `repair_state_machine.py`，除非修复因本步骤引入的明确回归
- `stages/`，除非修复因本步骤引入的明确回归

必须完成:
- hook 装配逻辑可迁到 `repair_hooks.py`
- `repair.py` 中 compat exports 按块收口，避免继续膨胀
- `attempt_repair()` 入口与兼容 import 继续可用

完成 gate:
- `repair.py` 继续维持 facade 角色
- `python -m pytest tests/test_anomaly_guard.py -q` 通过
- `python -m pytest tests/test_contracts.py tests/test_gui_cli_support.py -q` 通过
- `swift test` 通过

回滚:
- 删除 `repair_hooks.py`，把装配逻辑移回 `repair.py`

完成说明 (2026-03-12):
- `repair_hooks.py` 已创建，包含 `_should_notify` 和 `build_repair_state_machine_hooks` 函数。
- `repair.py` 继续维持 facade 角色，通过依赖注入调用 `repair_ops.py`。
- compat exports 已按块收口，添加了清晰的块注释（Public API、Compat Type、Compat Notify、Compat Operation、Compat Dependency、Compat Stage）。
- 添加了 `_now_ts` 到 compat exports 以保持测试 patchability。
- 未修改 `protocol.py`、`contracts/fixtures/` 或任何 `gui/` 生产代码。
- 未修改 `repair_state_machine.py` 或 `stages/`。

### Step 5: 验证、收尾与交接
状态: done
前置依赖: Step 1-4

目标:
- 用测试和文档证明这轮重构是"内部瘦身，外壳不变"。
- 为后续窗口留下清晰的完成状态和剩余风险。

允许修改:
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/backend-hotspots-refactor-plan.md`
- `/Users/mima0000/.openclaw/fix-my-claw/docs/refactors/backend-hotspots-refactor-log.md`

必须完成:
- 汇总每一步改动、gate、残余风险
- 记录是否真的做到了 GUI 零改动
- 如果存在偏离，必须写清原因和影响面

最终 gate:
- `python -m pytest tests/test_contracts.py tests/test_gui_cli_support.py tests/test_anomaly_guard.py -q` 通过
- `swift test` 通过
- 日志完整记录每一步事实
- 计划状态从 `pending` 更新为 `completed` 或明确 `blocked`

回滚:
- 只更新文档状态，不回滚已稳定通过的实现

完成说明 (2026-03-12):
- 所有测试通过：Python 151 passed，Swift 59 tests passed
- GUI 零改动承诺兑现：gui/Sources/、protocol.py、contracts/fixtures/ 均无本轮改动
- 热点文件成功瘦身：config.py (-88.4%)、anomaly_guard.py (-90.5%)、cli.py (-24.6%)
- 新增子模块结构清晰：cli_commands/、config_parts/、anomaly_guard/、repair_hooks.py
- 所有外部契约保持不变：CLI、JSON payload、TOML schema、退出码语义
