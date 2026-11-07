
"""First-launch tutorial dialog for the MDRPA desktop application."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from application.version import APP_NAME


__all__ = ["TutorialDialog"]


class TutorialDialog(QDialog):
    """Guide users through the main application sections."""

    completed = Signal()
    skipped = Signal()

    STEPS = (
        (
            "Welcome to MDRPA",
            "MEDA Data Research & Period Analyzer helps organize "
            "MEDA datasets, configure analysis periods, execute "
            "analysis runs, and review their available results.\n\n"
            "This short tour introduces the main application workflow.",
        ),
        (
            "1. Overview",
            "Overview is the starting page. It summarizes available "
            "analysis runs, displays recent activity, and provides "
            "shortcuts to the main application sections.",
        ),
        (
            "2. Input Data",
            "Use Input Data to select and validate the source dataset. "
            "Review the selected directory and resolve validation "
            "issues before proceeding.",
        ),
        (
            "3. Analysis",
            "Use Analysis to configure the analysis period and available "
            "settings. Review the configuration before starting an "
            "execution. The application reports execution progress "
            "and its final status.",
        ),
        (
            "4. Dashboard",
            "Dashboard provides an overview of stored analysis runs "
            "and the result summaries available for the selected run. "
            "The available information depends on the outputs produced "
            "by that run.",
        ),
        (
            "5. Reports & Export",
            "Reports lists the report artifacts available for a selected "
            "run. You can inspect available files and export selected "
            "artifacts to another destination.\n\n"
            "Not every report is necessarily available for every run.",
        ),
        (
            "You're ready to begin",
            "A typical workflow is:\n\n"
            "1. Select and validate an input dataset.\n"
            "2. Configure the analysis period and settings.\n"
            "3. Start the analysis and monitor its progress.\n"
            "4. Review the run in Dashboard.\n"
            "5. Inspect and export available reports.\n\n"
            "Each run is stored separately. Interpret scientific results "
            "in the context of the original MEDA data and its "
            "documentation.",
        ),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._current_step = 0

        self.setObjectName("tutorial_dialog")
        self.setWindowTitle(f"{APP_NAME} - First-Launch Tutorial")
        self.setMinimumSize(580, 390)
        self.setModal(True)

        self._build_ui()
        self._render_step()

    @property
    def current_step(self) -> int:
        """Return the zero-based index of the displayed step."""
        return self._current_step

    @property
    def step_count(self) -> int:
        """Return the number of tutorial steps."""
        return len(self.STEPS)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(16)

        self.application_label = QLabel(APP_NAME, self)
        self.application_label.setObjectName("tutorial_application_name")
        self.application_label.setWordWrap(True)

        self.step_label = QLabel(self)
        self.step_label.setObjectName("tutorial_step_title")
        self.step_label.setWordWrap(True)

        self.content_label = QLabel(self)
        self.content_label.setObjectName("tutorial_step_content")
        self.content_label.setWordWrap(True)
        self.content_label.setMinimumHeight(170)
        self.content_label.setAlignment(
            self.content_label.alignment()
        )

        self.progress_label = QLabel(self)
        self.progress_label.setObjectName("tutorial_progress")

        layout.addWidget(self.application_label)
        layout.addWidget(self.step_label)
        layout.addWidget(self.content_label, 1)
        layout.addWidget(self.progress_label)

        navigation = QHBoxLayout()

        self.skip_button = QPushButton("Skip", self)
        self.skip_button.setObjectName("tutorial_skip_button")
        self.skip_button.clicked.connect(self._skip)

        self.back_button = QPushButton("Back", self)
        self.back_button.setObjectName("tutorial_back_button")
        self.back_button.clicked.connect(self._go_back)

        self.next_button = QPushButton("Next", self)
        self.next_button.setObjectName("tutorial_next_button")
        self.next_button.clicked.connect(self._go_next)

        self.finish_button = QPushButton("Finish", self)
        self.finish_button.setObjectName("tutorial_finish_button")
        self.finish_button.clicked.connect(self._finish)

        navigation.addWidget(self.skip_button)
        navigation.addStretch(1)
        navigation.addWidget(self.back_button)
        navigation.addWidget(self.next_button)
        navigation.addWidget(self.finish_button)

        layout.addLayout(navigation)

    def _render_step(self) -> None:
        title, content = self.STEPS[self._current_step]

        self.step_label.setText(title)
        self.content_label.setText(content)
        self.progress_label.setText(
            f"Step {self._current_step + 1} of {self.step_count}"
        )

        self.back_button.setEnabled(self._current_step > 0)

        is_last_step = self._current_step == self.step_count - 1
        self.next_button.setVisible(not is_last_step)
        self.finish_button.setVisible(is_last_step)

    def _go_back(self) -> None:
        if self._current_step > 0:
            self._current_step -= 1
            self._render_step()

    def _go_next(self) -> None:
        if self._current_step < self.step_count - 1:
            self._current_step += 1
            self._render_step()

    def _finish(self) -> None:
        self.completed.emit()
        self.accept()

    def _skip(self) -> None:
        self.skipped.emit()
        self.accept()
