
"""Analysis execution controls and status display."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

__all__ = ["AnalysisCenterView"]


class AnalysisCenterView(QWidget):
    """Display analysis execution controls and the current run state."""

    start_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setObjectName("analysis_center_view")

        self._configuration_available = False
        self._execution_active = False
        self._worker_started = False
        self._cancellation_requested = False
        self._result_received = False
        self._last_error: str | None = None

        self._build_ui()
        self._connect_signals()
        self._refresh_controls()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        group = QGroupBox("Analysis Execution", self)
        group.setObjectName("analysis_execution_group")

        group_layout = QVBoxLayout(group)

        self.status_label = QLabel("Waiting for a validated configuration.")
        self.status_label.setObjectName("analysis_execution_status")
        self.status_label.setWordWrap(True)

        self.run_id_label = QLabel("—")
        self.run_id_label.setObjectName("analysis_run_id")

        self.stage_label = QLabel("Current stage: —")
        self.stage_label.setObjectName("analysis_current_stage")
        self.stage_label.setWordWrap(True)

        self.result_label = QLabel("Result: —")
        self.result_label.setObjectName("analysis_execution_result")
        self.result_label.setWordWrap(True)

        buttons = QHBoxLayout()

        self.start_button = QPushButton("Start Analysis", group)
        self.start_button.setObjectName("start_analysis_button")

        self.cancel_button = QPushButton("Cancel Analysis", group)
        self.cancel_button.setObjectName("cancel_analysis_button")

        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)

        group_layout.addWidget(self.status_label)
        group_layout.addWidget(self.run_id_label)
        group_layout.addWidget(self.stage_label)
        group_layout.addWidget(self.result_label)
        group_layout.addLayout(buttons)

        layout.addWidget(group)

    def _connect_signals(self) -> None:
        self.start_button.clicked.connect(self.start_requested.emit)
        self.cancel_button.clicked.connect(self.cancel_requested.emit)

    def _refresh_controls(self) -> None:
        can_start = (
            self._configuration_available
            and not self._execution_active
        )
        can_cancel = (
            self._execution_active
            and self._worker_started
            and not self._cancellation_requested
        )

        self.start_button.setEnabled(can_start)
        self.cancel_button.setEnabled(can_cancel)

    @property
    def configuration_available(self) -> bool:
        """Whether a validated analysis configuration is available."""
        return self._configuration_available

    @property
    def execution_active(self) -> bool:
        """Whether the UI currently represents an active execution."""
        return self._execution_active

    def set_configuration_available(self, available: bool) -> None:
        """Enable Start only when a valid configuration is available."""
        self._configuration_available = bool(available)

        if not self._execution_active:
            if self._configuration_available:
                self.status_label.setText("Ready to start analysis.")
            else:
                self.status_label.setText(
                    "Waiting for a validated configuration."
                )

        self._refresh_controls()

    def set_execution_starting(self) -> None:
        """Lock execution controls while the controller starts the worker."""
        self._execution_active = True
        self._worker_started = False
        self._cancellation_requested = False
        self._result_received = False
        self._last_error = None

        self.status_label.setText("Starting analysis...")
        self.run_id_label.setText("Pending")
        self.stage_label.setText("Current stage: waiting to start")
        self.result_label.setText("Result: running")

        self._refresh_controls()

    def set_execution_started(self) -> None:
        """Record that the worker has begun execution."""
        if not self._execution_active:
            return

        self._worker_started = True
        self.status_label.setText("Analysis is running.")
        self._refresh_controls()

    def set_stage_started(self, stage_name: str) -> None:
        """Display the stage currently being executed."""
        self._worker_started = True
        self.stage_label.setText(f"Current stage: {stage_name}")
        self.status_label.setText(f"Running: {stage_name}")
        self._refresh_controls()

    def set_stage_completed(self, stage_result: object) -> None:
        """Display the most recent stage outcome."""
        stage_name = getattr(stage_result, "stage_name", "Pipeline stage")
        status = getattr(stage_result, "status", "completed")

        self.stage_label.setText(
            f"Current stage: {stage_name} — {status}"
        )

    def set_progress(self, percentage: int, message: str) -> None:
        """Display a progress message received from the controller."""
        bounded = max(0, min(100, int(percentage)))
        self.status_label.setText(f"{bounded}% — {message}")

    def show_warning(self, message: str) -> None:
        """Display a non-fatal execution warning."""
        self.status_label.setText(f"Warning: {message}")

    def show_error(self, message: str) -> None:
        """Display an execution error without releasing the thread lock."""
        self._last_error = str(message)
        self.status_label.setText(f"Error: {message}")

    def set_cancellation_requested(self) -> None:
        """Reflect a cooperative cancellation request."""
        if not self._execution_active:
            return

        self._cancellation_requested = True
        self.status_label.setText(
            "Cancellation requested. Waiting for the current stage to finish..."
        )
        self._refresh_controls()

    def set_cancellation_completed(self, message: str) -> None:
        """Display the cancellation completion message."""
        self.status_label.setText(str(message))

    def set_execution_result(self, result: object) -> None:
        """Display the final Run result emitted by the controller."""
        self._result_received = True

        run_id = getattr(result, "run_id", None)
        status = getattr(result, "status", None)
        successful = bool(getattr(result, "successful", False))
        cancelled = bool(getattr(result, "cancelled", False))
        error = getattr(result, "error", None)

        if run_id:
            self.run_id_label.setText(str(run_id))

        if cancelled:
            message = "Analysis cancelled."
        elif successful:
            message = "Analysis completed successfully."
        elif error:
            message = f"Analysis failed: {error}"
        else:
            message = f"Analysis finished with status: {status or 'unknown'}."

        self.result_label.setText(f"Result: {message}")
        self.status_label.setText(message)

    def set_start_error(self, message: str) -> None:
        """Report an error raised while starting the controller."""
        self._last_error = str(message)
        self.status_label.setText(f"Unable to start analysis: {message}")
        self.result_label.setText("Result: not started")

    def set_execution_ended(self) -> None:
        """Release the UI lock after the QThread has actually finished."""
        self._execution_active = False
        self._worker_started = False
        self._cancellation_requested = False

        if not self._result_received and self._last_error is None:
            self.status_label.setText("Execution ended.")
            self.result_label.setText("Result: execution ended")

        self._refresh_controls()
