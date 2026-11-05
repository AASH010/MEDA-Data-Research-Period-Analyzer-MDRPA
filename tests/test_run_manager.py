"""Tests for run lifecycle status definitions and transition rules."""

import pytest

from backend.run_manager.run_status import (
    TERMINAL_STATUSES,
    RunStatus,
    can_transition,
    validate_transition,
)


def test_run_status_contains_all_supported_states():
    assert {status.value for status in RunStatus} == {
        "PENDING",
        "RUNNING",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }


def test_terminal_statuses_are_correct():
    assert TERMINAL_STATUSES == {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }

    assert RunStatus.PENDING.is_terminal is False
    assert RunStatus.RUNNING.is_terminal is False

    for status in TERMINAL_STATUSES:
        assert status.is_terminal is True


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunStatus.PENDING, RunStatus.RUNNING),
        (RunStatus.PENDING, RunStatus.CANCELLED),
        (RunStatus.RUNNING, RunStatus.COMPLETED),
        (RunStatus.RUNNING, RunStatus.FAILED),
        (RunStatus.RUNNING, RunStatus.CANCELLED),
        ("pending", "running"),
        ("running", "completed"),
    ],
)
def test_allowed_transitions(current, target):
    assert can_transition(current, target) is True


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunStatus.PENDING, RunStatus.COMPLETED),
        (RunStatus.PENDING, RunStatus.FAILED),
        (RunStatus.RUNNING, RunStatus.PENDING),
        (RunStatus.COMPLETED, RunStatus.RUNNING),
        (RunStatus.FAILED, RunStatus.RUNNING),
        (RunStatus.CANCELLED, RunStatus.RUNNING),
        (RunStatus.COMPLETED, RunStatus.FAILED),
    ],
)
def test_disallowed_transitions(current, target):
    assert can_transition(current, target) is False


def test_validate_transition_returns_target_enum():
    result = validate_transition("pending", "running")

    assert result is RunStatus.RUNNING


def test_validate_transition_rejects_disallowed_transition():
    with pytest.raises(ValueError, match="Invalid run status transition"):
        validate_transition(
            RunStatus.COMPLETED,
            RunStatus.RUNNING,
        )


def test_unknown_status_is_rejected():
    with pytest.raises(ValueError, match="Unknown run status"):
        can_transition("UNKNOWN", "RUNNING")


def test_non_string_status_is_rejected():
    with pytest.raises(TypeError, match="status must be"):
        can_transition(123, RunStatus.RUNNING)