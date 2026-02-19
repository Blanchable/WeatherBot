"""Tests for risk management components."""

import pytest
import time

from src.risk.kill_switch import KillSwitch


class TestKillSwitch:
    def test_initial_state(self):
        ks = KillSwitch(max_errors=5, window_seconds=60)
        assert not ks.is_killed
        assert ks.error_count == 0

    def test_triggers_after_max_errors(self):
        ks = KillSwitch(max_errors=3, window_seconds=60)
        ks.record_error("err1")
        ks.record_error("err2")
        assert not ks.is_killed
        ks.record_error("err3")
        assert ks.is_killed
        assert ks.kill_reason is not None

    def test_reset(self):
        ks = KillSwitch(max_errors=2, window_seconds=60)
        ks.record_error("err1")
        ks.record_error("err2")
        assert ks.is_killed
        ks.reset()
        assert not ks.is_killed
        assert ks.error_count == 0

    def test_errors_expire(self):
        ks = KillSwitch(max_errors=5, window_seconds=1)
        ks.record_error("err1")
        ks.record_error("err2")
        assert ks.error_count == 2
        time.sleep(1.1)
        assert ks.error_count == 0

    def test_does_not_trigger_below_threshold(self):
        ks = KillSwitch(max_errors=10, window_seconds=60)
        for i in range(9):
            ks.record_error(f"err{i}")
        assert not ks.is_killed


class TestKillSwitchKillReason:
    def test_reason_format(self):
        ks = KillSwitch(max_errors=2, window_seconds=60)
        ks.record_error("first")
        ks.record_error("second")
        assert "2/2" in ks.kill_reason
