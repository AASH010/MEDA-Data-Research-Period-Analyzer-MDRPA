
"""Background worker for executing one MEDA analysis pipeline.

The worker is a QObject intended to be moved to a QThread owned by
the application or controller.

It does not create, start, stop, or terminate threads.
Cancellation is cooperative and is delegated to AnalysisPipeline.
Pipeline lifecycle events are forwarded through WorkerSignals.
"""

from __future__ import annotations

from collections.abc import Mapping
from threading import Event, Lock
from typing import Any

from PySide6.QtCore import QObject, Slot

from backend.pipeline.analysis_pipeline import (
    AnalysisPipeline,
    PipelineRunResult,
)
from backend.pipeline.pipeline_executor import PipelineStageResult
from backend.pipeline.pipeline_validator import PipelineConfig
from backend.workers.worker_signals import WorkerSignals


__all__ = ["AnalysisWorker"]


class AnalysisWorker(QObject):
    """Execute one analysis pipeline in a controller-owned thread.

    The worker is designed for a single execution.

    Signals are exposed through the ``signals`` attribute.

    The worker does not own thread lifecycle. The controller is
    responsible for creating and managing the QThread.

    Pipeline stage events are forwarded as they occur. Warning and
    error messages are emitted when their corresponding stage result
    is received, rather than being replayed after execution finishes.
    """

    def __init__(
        self,
        pipeline: AnalysisPipeline,
        config: PipelineConfig | Mapping[str, Any],
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__()

        if not isinstance(pipeline, AnalysisPipeline):
            raise TypeError(
                "pipeline must be an AnalysisPipeline instance."
            )

        if not isinstance(config, (PipelineConfig, Mapping)):
            raise TypeError(
                "config must be a PipelineConfig instance or mapping."
            )

        if run_id is not None:
            if not isinstance(run_id, str) or not run_id.strip():
                raise ValueError(
                    "run_id must be a non-empty string or None."
                )

        self.pipeline = pipeline
        self.config = config
        self.run_id = run_id

        self.signals = WorkerSignals(self)

        self._cancel_event = Event()
        self._execution_lock = Lock()
        self._has_started = False

    @property
    def cancellation_requested(self) -> bool:
        """Whether cooperative cancellation has been requested."""
        return self._cancel_event.is_set()

    def request_cancel(self) -> None:
        """Request cancellation at the next safe pipeline boundary.

        An analyzer that is already running is allowed to finish.
        No thread or process is forcefully terminated.
        """
        self._cancel_event.set()

    def _handle_stage_started(
        self,
        stage_name: str,
    ) -> None:
        """Forward a pipeline stage-start event."""
        self.signals.stage_started.emit(stage_name)

    def _handle_stage_completed(
        self,
        stage_result: PipelineStageResult,
    ) -> None:
        """Forward a completed stage and its warnings or errors."""
        self.signals.stage_completed.emit(stage_result)

        for warning in stage_result.warnings:
            self.signals.warning_occurred.emit(warning)

        for error in stage_result.errors:
            self.signals.error_occurred.emit(error)

    def _handle_progress_updated(
        self,
        percentage: int,
        message: str,
    ) -> None:
        """Forward pipeline progress."""
        self.signals.progress_updated.emit(
            percentage,
            message,
        )

    @Slot()
    def run(self) -> None:
        """Execute the configured pipeline and emit its final result.

        This slot is intended to be connected to QThread.started.

        The worker can only run once. Unexpected exceptions are
        reported through error_occurred.

        execution_ended is emitted in the finally block so the
        controller can reliably finish the owning QThread.
        """
        with self._execution_lock:
            if self._has_started:
                self.signals.error_occurred.emit(
                    "AnalysisWorker can only be executed once."
                )
                return

            self._has_started = True

        try:
            self.signals.started.emit()

            result = self.pipeline.execute(
                self.config,
                run_id=self.run_id,
                cancel_event=self._cancel_event,
                on_stage_started=self._handle_stage_started,
                on_stage_completed=self._handle_stage_completed,
                on_progress_updated=self._handle_progress_updated,
            )

            if not isinstance(result, PipelineRunResult):
                raise TypeError(
                    "AnalysisPipeline.execute() must return "
                    "a PipelineRunResult instance."
                )

            if result.error:
                self.signals.error_occurred.emit(result.error)

            if result.cancelled:
                self.signals.cancelled.emit(
                    "Analysis cancellation completed."
                )

            self.signals.finished.emit(result)

        except Exception as exc:
            self.signals.error_occurred.emit(
                f"{type(exc).__name__}: {exc}"
            )

        finally:
            self.signals.execution_ended.emit()
