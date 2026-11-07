
"""Application-level controller for background MEDA analysis execution.

The controller owns the QThread lifecycle and coordinates one
AnalysisWorker at a time.

It does not implement GUI widgets, scientific analysis, pipeline
execution, or Run lifecycle management.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QObject, QThread, Qt, Signal

from backend.pipeline.analysis_pipeline import AnalysisPipeline
from backend.pipeline.pipeline_validator import PipelineConfig
from backend.workers.analysis_worker import AnalysisWorker


__all__ = ["AnalysisController"]


class AnalysisController(QObject):
    """Manage background execution of one AnalysisPipeline at a time.

    Public API:
        start(config, run_id=None):
            Create and start a worker thread.

        request_cancel():
            Request cooperative cancellation of the active worker.

        is_active:
            Whether a worker thread is still owned by the controller.

        is_running:
            Whether the owned QThread is currently running.

    The controller forwards worker signals and emits thread_finished
    after the QThread has actually stopped and its references have
    been cleared.
    """

    started = Signal()

    stage_started = Signal(str)
    stage_completed = Signal(object)

    progress_updated = Signal(int, str)

    warning_occurred = Signal(str)
    error_occurred = Signal(str)

    finished = Signal(object)
    cancelled = Signal(str)
    execution_ended = Signal()

    thread_finished = Signal()

    def __init__(
        self,
        pipeline: AnalysisPipeline,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)

        if not isinstance(pipeline, AnalysisPipeline):
            raise TypeError(
                "pipeline must be an AnalysisPipeline instance."
            )

        self.pipeline = pipeline

        self._thread: QThread | None = None
        self._worker: AnalysisWorker | None = None

    @property
    def is_active(self) -> bool:
        """Whether the controller currently owns an execution thread."""
        return self._thread is not None

    @property
    def is_running(self) -> bool:
        """Whether the owned QThread is currently running."""
        return (
            self._thread is not None
            and self._thread.isRunning()
        )

    def start(
        self,
        config: PipelineConfig | Mapping[str, Any],
        *,
        run_id: str | None = None,
    ) -> None:
        """Create and start one background analysis execution.

        Raises:
            RuntimeError: If a previous thread has not fully finished.

        Configuration validation and Run lifecycle management remain
        responsibilities of AnalysisWorker and AnalysisPipeline.
        """
        if self._thread is not None:
            raise RuntimeError(
                "An analysis execution is already active."
            )

        worker = AnalysisWorker(
            self.pipeline,
            config,
            run_id=run_id,
        )

        thread = QThread(self)
        worker.moveToThread(thread)

        self._worker = worker
        self._thread = thread

        worker.signals.started.connect(
            self.started
        )

        worker.signals.stage_started.connect(
            self.stage_started
        )
        worker.signals.stage_completed.connect(
            self.stage_completed
        )

        worker.signals.progress_updated.connect(
            self.progress_updated
        )

        worker.signals.warning_occurred.connect(
            self.warning_occurred
        )
        worker.signals.error_occurred.connect(
            self.error_occurred
        )

        worker.signals.finished.connect(
            self.finished
        )
        worker.signals.cancelled.connect(
            self.cancelled
        )
        worker.signals.execution_ended.connect(
            self.execution_ended
        )

        thread.started.connect(
            worker.run
        )

        # Schedule worker deletion in its own thread. The deferred
        # deletion is processed as the thread finishes.
        worker.signals.execution_ended.connect(
            worker.deleteLater,
            Qt.ConnectionType.DirectConnection,
        )

        # QThread.quit() is thread-safe. A direct connection avoids
        # depending on the controller's event loop to deliver the
        # shutdown request.
        worker.signals.execution_ended.connect(
            thread.quit,
            Qt.ConnectionType.DirectConnection,
        )

        # Let Qt schedule deletion of the stopped QThread object.
        # The controller only clears its Python references.
        thread.finished.connect(
            thread.deleteLater
        )

        thread.finished.connect(
            self._handle_thread_finished
        )

        thread.start()

    def request_cancel(self) -> bool:
        """Request cooperative cancellation of the active worker.

        Returns:
            True if a cancellation request was forwarded.
            False if there is no active worker thread.

        The controller never terminates a thread forcefully.
        """
        if self._thread is None or self._worker is None:
            return False

        if not self._thread.isRunning():
            return False

        self._worker.request_cancel()
        return True

    def _handle_thread_finished(self) -> None:
        """Clear controller references after the QThread has stopped."""
        self._worker = None
        self._thread = None

        self.thread_finished.emit()
