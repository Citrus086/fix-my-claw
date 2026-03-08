"""
Tests for message text consistency in fix_my_claw.messages module.

These tests ensure that all notification messages are properly centralized
and maintain the expected format.
"""

import pytest

from fix_my_claw.messages import (
    REPAIR_AI_CODE_SUCCESS,
    REPAIR_AI_CONFIG_SUCCESS,
    REPAIR_AI_DISABLED,
    REPAIR_AI_RATE_LIMITED,
    REPAIR_FINAL_STILL_UNHEALTHY,
    REPAIR_NO_YES_RECEIVED,
    REPAIR_RECOVERED_AFTER_PAUSE,
    REPAIR_RECOVERED_BY_OFFICIAL,
    REPAIR_STARTING,
    ai_decision_no,
    ai_decision_yes,
    ask_enable_ai_prompt,
    ask_invalid_reply,
    backup_completed,
    repair_backup_failed,
)


class TestMessagePrefix:
    """All messages should start with 'fix-my-claw:' prefix."""

    def test_ai_decision_yes_has_prefix(self):
        assert ai_decision_yes("用户").startswith("fix-my-claw:")

    def test_ai_decision_no_has_prefix(self):
        assert ai_decision_no("用户").startswith("fix-my-claw:")

    def test_backup_completed_has_prefix(self):
        assert backup_completed("/path/to/backup.tar.gz").startswith("fix-my-claw:")

    def test_repair_starting_has_prefix(self):
        assert REPAIR_STARTING.startswith("fix-my-claw:")

    def test_repair_recovered_after_pause_has_prefix(self):
        assert REPAIR_RECOVERED_AFTER_PAUSE.startswith("fix-my-claw:")

    def test_repair_recovered_by_official_has_prefix(self):
        assert REPAIR_RECOVERED_BY_OFFICIAL.startswith("fix-my-claw:")

    def test_repair_ai_disabled_has_prefix(self):
        assert REPAIR_AI_DISABLED.startswith("fix-my-claw:")

    def test_repair_ai_rate_limited_has_prefix(self):
        assert REPAIR_AI_RATE_LIMITED.startswith("fix-my-claw:")

    def test_repair_no_yes_received_has_prefix(self):
        assert REPAIR_NO_YES_RECEIVED.startswith("fix-my-claw:")

    def test_repair_backup_failed_has_prefix(self):
        assert repair_backup_failed("some error").startswith("fix-my-claw:")

    def test_repair_ai_config_success_has_prefix(self):
        assert REPAIR_AI_CONFIG_SUCCESS.startswith("fix-my-claw:")

    def test_repair_ai_code_success_has_prefix(self):
        assert REPAIR_AI_CODE_SUCCESS.startswith("fix-my-claw:")

    def test_repair_final_still_unhealthy_has_prefix(self):
        assert REPAIR_FINAL_STILL_UNHEALTHY.startswith("fix-my-claw:")

    def test_ask_enable_ai_prompt_has_prefix(self):
        assert ask_enable_ai_prompt("TestBot").startswith("fix-my-claw:")

    def test_ask_invalid_reply_has_prefix(self):
        assert ask_invalid_reply(2).startswith("fix-my-claw:")


class TestMessageContent:
    """Test message content matches expected values."""

    def test_ai_decision_yes_content(self):
        msg = ai_decision_yes("GUI")
        assert "GUI" in msg
        assert "yes" in msg
        assert "备份" in msg
        assert "Codex" in msg

    def test_ai_decision_no_content(self):
        msg = ai_decision_no("Discord")
        assert "Discord" in msg
        assert "no" in msg
        assert "不会启用" in msg

    def test_backup_completed_includes_path(self):
        path = "/tmp/backup.tar.gz"
        msg = backup_completed(path)
        assert path in msg

    def test_ask_enable_ai_prompt_includes_account(self):
        account = "MyBot"
        msg = ask_enable_ai_prompt(account)
        assert f"@{account}" in msg

    def test_ask_invalid_reply_includes_remaining(self):
        msg = ask_invalid_reply(3)
        assert "3" in msg
        assert "剩余" in msg

    def test_repair_backup_failed_includes_error(self):
        error = "disk full"
        msg = repair_backup_failed(error)
        assert error in msg


class TestNoHardcodedMessagesInRepair:
    """Verify repair.py has no hardcoded fix-my-claw: messages."""

    def test_no_hardcoded_messages_in_repair(self):
        """Check that repair.py does not contain hardcoded notification messages."""
        import fix_my_claw.repair as repair_module

        source_file = repair_module.__file__
        with open(source_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Find all string literals that start with "fix-my-claw:"
        import re
        # Match string literals with fix-my-claw: prefix
        # This pattern catches f-strings and regular strings
        hardcoded = re.findall(r'["\']fix-my-claw:', content)

        # Should be empty - all messages should come from messages.py
        assert len(hardcoded) == 0, (
            f"Found {len(hardcoded)} hardcoded 'fix-my-claw:' messages in repair.py. "
            "All messages should be imported from messages.py"
        )


class TestNoHardcodedMessagesInNotify:
    """Verify notify.py has no hardcoded fix-my-claw: messages."""

    def test_no_hardcoded_messages_in_notify(self):
        """Check that notify.py does not contain hardcoded notification messages."""
        import fix_my_claw.notify as notify_module

        source_file = notify_module.__file__
        with open(source_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Find all string literals that start with "fix-my-claw:"
        import re
        hardcoded = re.findall(r'["\']fix-my-claw:', content)

        # Should be empty - all messages should come from messages.py
        assert len(hardcoded) == 0, (
            f"Found {len(hardcoded)} hardcoded 'fix-my-claw:' messages in notify.py. "
            "All messages should be imported from messages.py"
        )
