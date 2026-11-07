
"""Main application status bar and analysis progress display."""

from __future__ import annotations

from PySide6.QtWidgets import QProgressBar, QStatusBar


__all__ = ["MainStatusBar"]


class MainStatusBar(QStatusBar):
    """Display application status and background analysis progress."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setObjectName("main_status_bar")
        self.showMessage("Ready")

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setObjectName("analysis_progress_bar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setMaximumWidth(180)
        self.progress_bar.hide()

        self.addPermanentWidget(self.progress_bar)

    def analysis_started(self) -> None:
        """Reset progress when a new analysis begins."""
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.showMessage("Starting analysis...")

    def update_progress(
        self,
        percentage: int,
        message: str,
    ) -> None:
        """Display pipeline progress and its current message."""
        self.progress_bar.setValue(
            max(0, min(100, percentage))
        )
        self.progress_bar.show()
        self.showMessage(message)

    def stage_started(self, stage_name: str) -> None:
        """Display the name of the currently executing stage."""
        self.showMessage(f"Running: {stage_name}")

    def stage_completed(self, stage_result: object) -> None:
        """Display the outcome of a completed or skipped stage."""
        stage_name = getattr(
            stage_result,
            "stage_name",
            "Pipeline stage",
        )
        status = getattr(
            stage_result,
            "status",
            "completed",
        )

        self.showMessage(f"{stage_name}: {status}")

    def show_warning(self, message: str) -> None:
        """Display a non-fatal analysis warning."""
        self.showMessage(
            f"Warning: {message}",
            10000,
        )

    def show_error(self, message: str) -> None:
        """Display an analysis error."""
        self.showMessage(
            f"Error: {message}",
            10000,
        )

    def analysis_finished(self, result: object) -> None:
        """Display the final analysis outcome."""
        if getattr(result, "cancelled", False):
            self.showMessage("Analysis cancelled.")
            return

        if getattr(result, "successful", False):
            self.progress_bar.setValue(100)
            self.showMessage("Analysis completed successfully.")
            return

        self.showMessage("Analysis failed.")

    def analysis_cancelled(self, message: str) -> None:
        """Display completion of cooperative cancellation."""
        self.showMessage(message)

    def shutdown_pending(self) -> None:
        """Explain why the application is waiting before closing."""
        self.showMessage(
            "Cancelling analysis safely before closing..."
        )
