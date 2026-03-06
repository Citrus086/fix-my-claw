from __future__ import annotations

import os
import time

from . import anomaly_guard as _anomaly_guard_module
from . import cli as _cli_module
from . import config as _config_module
from . import health as _health_module
from . import monitor as _monitor_module
from . import notify as _notify_module
from . import repair as _repair_module
from . import runtime as _runtime_module
from . import shared as _shared_module
from . import state as _state_module

# Compatibility re-export layer for legacy `fix_my_claw.core` imports and patch points.

# config.py
DEFAULT_CONFIG_PATH = _config_module.DEFAULT_CONFIG_PATH
DEFAULT_CONFIG_TOML = _config_module.DEFAULT_CONFIG_TOML
MonitorConfig = _config_module.MonitorConfig
OpenClawConfig = _config_module.OpenClawConfig
RepairConfig = _config_module.RepairConfig
AnomalyGuardConfig = _config_module.AnomalyGuardConfig
NotifyConfig = _config_module.NotifyConfig
AiConfig = _config_module.AiConfig
AppConfig = _config_module.AppConfig
_get = _config_module._get
_parse_monitor = _config_module._parse_monitor
_parse_openclaw = _config_module._parse_openclaw
_parse_repair = _config_module._parse_repair
_parse_anomaly_guard = _config_module._parse_anomaly_guard
_parse_notify = _config_module._parse_notify
_parse_ai = _config_module._parse_ai
load_config = _config_module.load_config
write_default_config = _config_module.write_default_config

# shared.py
_expand_path = _shared_module._expand_path
_as_path = _shared_module._as_path
ensure_dir = _shared_module.ensure_dir
truncate_for_log = _shared_module.truncate_for_log
redact_text = _shared_module.redact_text
SecureRotatingFileHandler = _shared_module.SecureRotatingFileHandler
setup_logging = _shared_module.setup_logging

# runtime.py
CmdResult = _runtime_module.CmdResult
run_cmd = _runtime_module.run_cmd

# health.py
_parse_json_maybe = _health_module._parse_json_maybe
Probe = _health_module.Probe
HealthEvaluation = _health_module.HealthEvaluation
probe_health = _health_module.probe_health
probe_status = _health_module.probe_status
probe_logs = _health_module.probe_logs

# anomaly_guard.py
ROLE_ALIASES = _anomaly_guard_module.ROLE_ALIASES
AGENT_ROLES = _anomaly_guard_module.AGENT_ROLES
Event = _anomaly_guard_module.Event
CycleMatch = _anomaly_guard_module.CycleMatch
StagnationMatch = _anomaly_guard_module.StagnationMatch
DetectorFinding = _anomaly_guard_module.DetectorFinding
_analyze_anomaly_guard = _anomaly_guard_module._analyze_anomaly_guard

# state.py
LOCK_INITIALIZING_GRACE_SECONDS = _state_module.LOCK_INITIALIZING_GRACE_SECONDS
FileLock = _state_module.FileLock
State = _state_module.State
StateStore = _state_module.StateStore
_now_ts = _state_module._now_ts
_today_ymd = _state_module._today_ymd

# notify.py
_normalize_name_key = _notify_module._normalize_name_key
_max_message_id = _notify_module._max_message_id
_normalize_ai_reply_token = _notify_module._normalize_ai_reply_token
_message_mentions_notify_account = _notify_module._message_mentions_notify_account
_resolve_sent_message_author_id = _notify_module._resolve_sent_message_author_id
_is_ai_reply_candidate = _notify_module._is_ai_reply_candidate
_extract_ai_decision = _notify_module._extract_ai_decision
_notify_send = _notify_module._notify_send
_notify_read_messages = _notify_module._notify_read_messages
_ask_user_enable_ai = _notify_module._ask_user_enable_ai

# repair.py
_parse_agent_id_from_session_key = _repair_module._parse_agent_id_from_session_key
_list_active_sessions = _repair_module._list_active_sessions
_backup_openclaw_state = _repair_module._backup_openclaw_state
_run_session_command_stage = _repair_module._run_session_command_stage
_attempt_dir = _repair_module._attempt_dir
_write_attempt_file = _repair_module._write_attempt_file
_context_logs_timeout_seconds = _repair_module._context_logs_timeout_seconds
_evaluate_with_context = _repair_module._evaluate_with_context
_collect_context = _repair_module._collect_context
_evaluate_health = _repair_module._evaluate_health
_run_official_steps = _repair_module._run_official_steps
_load_prompt_text = _repair_module._load_prompt_text
_build_ai_cmd = _repair_module._build_ai_cmd
_run_ai_repair = _repair_module._run_ai_repair
CommandExecutionRecord = _repair_module.CommandExecutionRecord
SessionStageData = _repair_module.SessionStageData
OfficialRepairStageData = _repair_module.OfficialRepairStageData
AiDecision = _repair_module.AiDecision
BackupArtifact = _repair_module.BackupArtifact
AiRepairStageData = _repair_module.AiRepairStageData
StagePayload = _repair_module.StagePayload
StageResult = _repair_module.StageResult
RepairPipelineContext = _repair_module.RepairPipelineContext
RepairOutcome = _repair_module.RepairOutcome
RepairResult = _repair_module.RepairResult
SessionTerminateStage = _repair_module.SessionTerminateStage
SessionResetStage = _repair_module.SessionResetStage
OfficialRepairStage = _repair_module.OfficialRepairStage
AiDecisionStage = _repair_module.AiDecisionStage
BackupStage = _repair_module.BackupStage
AiRepairStage = _repair_module.AiRepairStage
FinalAssessmentStage = _repair_module.FinalAssessmentStage
attempt_repair = _repair_module.attempt_repair

# monitor.py
run_check = _monitor_module.run_check
monitor_loop = _monitor_module.monitor_loop

# cli.py
_add_config_arg = _cli_module._add_config_arg
_load_or_init_config = _cli_module._load_or_init_config
cmd_init = _cli_module.cmd_init
cmd_check = _cli_module.cmd_check
cmd_repair = _cli_module.cmd_repair
cmd_monitor = _cli_module.cmd_monitor
cmd_up = _cli_module.cmd_up
build_parser = _cli_module.build_parser
main = _cli_module.main
