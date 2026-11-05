"""Status definitions and transition rules for MEDA analysis runs.

This module defines run lifecycle states only. It does not execute runs,
persist status changes, manage directories, or perform scientific analysis.
"""

from __future__ import annotations

from enum import Enum


__all__ = [
    "RunStatus",
    "TERMINAL_STATUSES",
    "can_transition",
    "validate_transition",
]


class RunStatus(str, Enum):
    """Supported lifecycle states for one analysis run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        """Return whether this status represents a finished run."""
        return self in TERMINAL_STATUSES


TERMINAL_STATUSES = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }
)


_ALLOWED_TRANSITIONS = {
    RunStatus.PENDING: frozenset(
        {
            RunStatus.RUNNING,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.RUNNING: TERMINAL_STATUSES,
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


def _coerce_status(status: RunStatus | str) -> RunStatus:
    """Convert a supported status value into RunStatus."""
    if isinstance(status, RunStatus):
        return status

    if not isinstance(status, str):
        raise TypeError("status must be a RunStatus or string.")

    try:
        return RunStatus(status.strip().upper())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in RunStatus)
        raise ValueError(
            f"Unknown run status {status!r}. Expected one of: {allowed}."
        ) from exc


def can_transition(
    current: RunStatus | str,
    target: RunStatus | str,
) -> bool:
    """Return whether a transition between two run statuses is allowed.

    Invalid status values raise an exception rather than being treated as
    an ordinary disallowed transition.
    """
    current_status = _coerce_status(current)
    target_status = _coerce_status(target)

    return target_status in _ALLOWED_TRANSITIONS[current_status]


def validate_transition(
    current: RunStatus | str,
    target: RunStatus | str,
) -> RunStatus:
    """Validate a status transition and return the target RunStatus.

    Raises:
        TypeError: If either value has an unsupported type.
        ValueError: If a status is unknown or the transition is disallowed.
    """
    current_status = _coerce_status(current)
    target_status = _coerce_status(target)

    if target_status not in _ALLOWED_TRANSITIONS[current_status]:
        raise ValueError(
            "Invalid run status transition: "
            f"{current_status.value} -> {target_status.value}."
        )

    return target_status