
"""Qt signals shared by MEDA background workers.

This module defines worker-to-controller communication signals only.
It does not create threads, execute pipeline stages, manage Run
lifecycle state, or implement GUI behavior.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


__all__ = ["WorkerSignals"]


class WorkerSignals(QObject):
    """Signals emitted by a background analysis worker.

    Signal contract:
        started:
            Emitted when worker execution begins.

        stage_started:
            Emitted when a pipeline stage begins.
            Payload: stage name (str).

        stage_completed:
            Emitted after a pipeline stage finishes.
            Payload: PipelineStageResult (object).

        progress_updated:
            Emitted when execution progress changes.
            Payload: percentage (int), message (str).

        warning_occurred:
            Emitted when a non-fatal warning is reported.
            Payload: warning message (str).

        error_occurred:
            Emitted when an execution error is reported.
            Payload: error message (str).

        finished:
            Emitted once worker execution has ended.
            Payload: PipelineRunResult (object).

        cancelled:
            Emitted when cooperative cancellation has completed.
            Payload: cancellation message (str).
    """

    started = Signal()

    stage_started = Signal(str)
    stage_completed = Signal(object)

    progress_updated = Signal(int, str)

    warning_occurred = Signal(str)
    error_occurred = Signal(str)

    finished = Signal(object)
    cancelled = Signal(str)
