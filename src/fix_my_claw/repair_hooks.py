"""Hook assembly for the repair state machine.

This module contains the hook assembly logic that wires together
runtime dependencies, message constants, and stage classes for
the RepairStateMachine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import AppConfig

from . import repair_ops
from .messages import (
    REPAIR_AI_CODE_SUCCESS,
    REPAIR_AI_CONFIG_SUCCESS,
    REPAIR_AI_DISABLED,
    REPAIR_AI_RATE_LIMITED,
    REPAIR_FINAL_STILL_UNHEALTHY,
    REPAIR_NO_YES_RECEIVED,
    REPAIR_RECOVERED_AFTER_PAUSE,
    REPAIR_RECOVERED_AFTER_STOP,
    REPAIR_RECOVERED_BY_OFFICIAL,
    REPAIR_STARTING,
    REPAIR_STARTING_MANUAL,
    repair_backup_failed,
)
from .repair_state_machine import (
    RepairMessageHooks,
    RepairRuntimeHooks,
    RepairStageHooks,
    RepairStateMachineHooks,
)

# Notification level constants shared by repair hooks.
NOTIFY_LEVEL_ALL = repair_ops.NOTIFY_LEVEL_ALL
NOTIFY_LEVEL_IMPORTANT = repair_ops.NOTIFY_LEVEL_IMPORTANT
NOTIFY_LEVEL_CRITICAL = repair_ops.NOTIFY_LEVEL_CRITICAL


def _should_notify(cfg: "AppConfig", level: str) -> bool:
    """Check if notification should be sent based on configured level."""
    configured_level = cfg.notify.level.strip().lower()
    if configured_level == NOTIFY_LEVEL_ALL:
        return True
    if configured_level == NOTIFY_LEVEL_IMPORTANT:
        return level in {NOTIFY_LEVEL_IMPORTANT, NOTIFY_LEVEL_CRITICAL}
    if configured_level == NOTIFY_LEVEL_CRITICAL:
        return level == NOTIFY_LEVEL_CRITICAL
    return True


def build_repair_state_machine_hooks(
    *,
    # Runtime hooks
    ai_decision_notification_text_fn,
    ask_user_enable_ai_fn,
    attempt_dir_fn,
    backup_openclaw_state_fn,
    clear_repair_progress_fn,
    collect_context_fn,
    context_logs_timeout_seconds_fn,
    evaluate_health_fn,
    evaluate_with_context_fn,
    dispatch_notification_fn,
    now_ts_fn,
    require_stage_payload_fn,
    result_from_outcome_fn,
    run_ai_repair_fn,
    run_official_steps_fn,
    run_session_command_stage_fn,
    session_stage_has_successful_commands_fn,
    should_try_soft_pause_fn,
    write_repair_progress_fn,
    # Stage classes
    session_pause_stage_cls,
    pause_assessment_stage_cls,
    session_terminate_stage_cls,
    terminate_assessment_stage_cls,
    session_reset_stage_cls,
    official_repair_stage_cls,
    ai_decision_stage_cls,
    backup_stage_cls,
    ai_repair_stage_cls,
    final_assessment_stage_cls,
) -> RepairStateMachineHooks:
    """Build the hooks container for RepairStateMachine.

    This function assembles all runtime dependencies, message constants,
    and stage classes into a single hooks container that the state machine
    uses to execute repair operations.
    """
    return RepairStateMachineHooks(
        runtime=RepairRuntimeHooks(
            ai_decision_notification_text_fn=ai_decision_notification_text_fn,
            ask_user_enable_ai_fn=ask_user_enable_ai_fn,
            attempt_dir_fn=attempt_dir_fn,
            backup_openclaw_state_fn=backup_openclaw_state_fn,
            clear_repair_progress_fn=clear_repair_progress_fn,
            collect_context_fn=collect_context_fn,
            context_logs_timeout_seconds_fn=context_logs_timeout_seconds_fn,
            evaluate_health_fn=evaluate_health_fn,
            evaluate_with_context_fn=evaluate_with_context_fn,
            dispatch_notification_fn=dispatch_notification_fn,
            now_ts_fn=now_ts_fn,
            require_stage_payload_fn=require_stage_payload_fn,
            result_from_outcome_fn=result_from_outcome_fn,
            run_ai_repair_fn=run_ai_repair_fn,
            run_official_steps_fn=run_official_steps_fn,
            run_session_command_stage_fn=run_session_command_stage_fn,
            session_stage_has_successful_commands_fn=session_stage_has_successful_commands_fn,
            should_try_soft_pause_fn=should_try_soft_pause_fn,
            write_repair_progress_fn=write_repair_progress_fn,
        ),
        messages=RepairMessageHooks(
            repair_starting_message=REPAIR_STARTING,
            repair_starting_manual_message=REPAIR_STARTING_MANUAL,
            recovered_after_pause_message=REPAIR_RECOVERED_AFTER_PAUSE,
            recovered_after_stop_message=REPAIR_RECOVERED_AFTER_STOP,
            recovered_by_official_message=REPAIR_RECOVERED_BY_OFFICIAL,
            ai_disabled_message=REPAIR_AI_DISABLED,
            ai_rate_limited_message=REPAIR_AI_RATE_LIMITED,
            no_yes_received_message=REPAIR_NO_YES_RECEIVED,
            ai_config_success_message=REPAIR_AI_CONFIG_SUCCESS,
            ai_code_success_message=REPAIR_AI_CODE_SUCCESS,
            final_still_unhealthy_message=REPAIR_FINAL_STILL_UNHEALTHY,
            repair_backup_failed_fn=repair_backup_failed,
            notify_level_all=NOTIFY_LEVEL_ALL,
            notify_level_important=NOTIFY_LEVEL_IMPORTANT,
            notify_level_critical=NOTIFY_LEVEL_CRITICAL,
        ),
        stages=RepairStageHooks(
            session_pause_stage_cls=session_pause_stage_cls,
            pause_assessment_stage_cls=pause_assessment_stage_cls,
            session_terminate_stage_cls=session_terminate_stage_cls,
            terminate_assessment_stage_cls=terminate_assessment_stage_cls,
            session_reset_stage_cls=session_reset_stage_cls,
            official_repair_stage_cls=official_repair_stage_cls,
            ai_decision_stage_cls=ai_decision_stage_cls,
            backup_stage_cls=backup_stage_cls,
            ai_repair_stage_cls=ai_repair_stage_cls,
            final_assessment_stage_cls=final_assessment_stage_cls,
        ),
    )
