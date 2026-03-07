from __future__ import annotations

from . import cli as _cli_module
from . import config as _config_module
from . import health as _health_module
from . import monitor as _monitor_module
from . import repair as _repair_module
from . import runtime as _runtime_module
from . import shared as _shared_module
from . import state as _state_module

# Minimal compatibility layer for legacy `fix_my_claw.core` imports.

# Config dataclasses and file lifecycle
MonitorConfig = _config_module.MonitorConfig
OpenClawConfig = _config_module.OpenClawConfig
RepairConfig = _config_module.RepairConfig
AnomalyGuardConfig = _config_module.AnomalyGuardConfig
NotifyConfig = _config_module.NotifyConfig
AiConfig = _config_module.AiConfig
AppConfig = _config_module.AppConfig
load_config = _config_module.load_config
write_default_config = _config_module.write_default_config

# Shared runtime values
CmdResult = _runtime_module.CmdResult
Probe = _health_module.Probe
HealthEvaluation = _health_module.HealthEvaluation
State = _state_module.State
StateStore = _state_module.StateStore
RepairResult = _repair_module.RepairResult

# Stable entry points
setup_logging = _shared_module.setup_logging
run_check = _monitor_module.run_check
attempt_repair = _repair_module.attempt_repair
monitor_loop = _monitor_module.monitor_loop
main = _cli_module.main
