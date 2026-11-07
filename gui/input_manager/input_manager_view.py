"""Main Input Manager page."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from backend.analyzers.file_discovery import (
    SUPPORTED_EXTENSIONS,
    discover_files,
)
from gui.input_manager.file_import_view import FileImportView
from gui.input_manager.file_preview_view import FilePreviewView
from gui.input_manager.validation_view import ValidationView


__all__ = ["InputManagerView"]


class InputManagerView(QWidget):
    """Select, preview, and validate a MEDA dataset directory."""

    input_directory_changed = Signal(object)
    input_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setObjectName("input_manager_view")

        self._selected_input_dir: Path | None = None
        self._is_validated = False
        self._last_records: list[dict[str, Any]] = []

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        self.title_label = QLabel("Input Data Manager")
        self.title_label.setObjectName("input_manager_title")

        self.description_label = QLabel(
            "Select a MEDA dataset directory, inspect its contents, "
            "and validate its basic structure before analysis."
        )
        self.description_label.setObjectName(
            "input_manager_description"
        )
        self.description_label.setWordWrap(True)

        self.file_import_view = FileImportView(self)
        self.file_preview_view = FilePreviewView(self)
        self.validation_view = ValidationView(self)

        actions = QHBoxLayout()

        self.validate_button = QPushButton(
            "Validate Dataset",
            self,
        )
        self.validate_button.setObjectName(
            "validate_dataset_button"
        )
        self.validate_button.setEnabled(False)
        self.validate_button.clicked.connect(
            self.validate_dataset
        )

        self.clear_button = QPushButton("Clear", self)
        self.clear_button.setObjectName("clear_dataset_button")
        self.clear_button.clicked.connect(self.clear_selection)

        actions.addWidget(self.validate_button)
        actions.addWidget(self.clear_button)
        actions.addStretch(1)

        layout.addWidget(self.title_label)
        layout.addWidget(self.description_label)
        layout.addWidget(self.file_import_view)
        layout.addLayout(actions)
        layout.addWidget(self.file_preview_view, 1)
        layout.addWidget(self.validation_view)

    def _connect_signals(self) -> None:
        self.file_import_view.directory_selected.connect(
            self.set_input_directory
        )

    @property
    def selected_input_dir(self) -> Path | None:
        """Return the selected dataset directory."""
        return self._selected_input_dir

    @property
    def is_validated(self) -> bool:
        """Return whether the selected directory passed validation."""
        return self._is_validated

    @property
    def discovered_records(self) -> tuple[dict[str, Any], ...]:
        """Return the most recent discovery records."""
        return tuple(self._last_records)

    def set_input_directory(
        self,
        directory: str | Path,
    ) -> None:
        """Set the selected dataset directory and reset old results."""
        if not isinstance(directory, (str, Path)):
            raise TypeError(
                "directory must be a string or pathlib.Path."
            )

        if isinstance(directory, str) and not directory.strip():
            raise ValueError("directory must not be empty.")

        resolved = Path(directory).expanduser().resolve()

        self._selected_input_dir = resolved
        self._is_validated = False
        self._last_records = []

        self.file_import_view.set_selected_directory(resolved)
        self.file_preview_view.set_directory(resolved)
        self.validation_view.reset()

        self.validate_button.setEnabled(True)

        self.input_directory_changed.emit(resolved)

    def validate_dataset(self) -> bool:
        """Validate the selected directory using backend discovery."""
        directory = self._selected_input_dir

        if directory is None:
            self._show_validation_failure(
                "Select a dataset directory first."
            )
            return False

        if not directory.exists():
            self._show_validation_failure(
                "The selected directory does not exist."
            )
            return False

        if not directory.is_dir():
            self._show_validation_failure(
                "The selected path is not a directory."
            )
            return False

        try:
            records = discover_files(directory)
        except (OSError, ValueError, TypeError) as exc:
            self._show_validation_failure(
                f"Dataset discovery failed: {exc}"
            )
            return False

        self._last_records = records
        self.file_preview_view.set_records(records)

        sol_folders = {
            str(record.get("sol_folder", ""))
            for record in records
            if record.get("sol_folder")
        }

        supported_records = [
            record
            for record in records
            if str(record.get("extension", "")).lower()
            in SUPPORTED_EXTENSIONS
        ]

        warning_count = sum(
            1
            for record in records
            if str(record.get("issues", "")).strip()
        )

        if not sol_folders:
            self._show_validation_failure(
                "No recognized SOL directories containing files "
                "were found.",
                sol_count=0,
                file_count=len(supported_records),
                warning_count=warning_count,
            )
            return False

        if not supported_records:
            self._show_validation_failure(
                "No supported MEDA CSV or XML files were found "
                "inside the SOL directories.",
                sol_count=len(sol_folders),
                file_count=0,
                warning_count=warning_count,
            )
            return False

        self._is_validated = True

        message = (
            "The directory contains recognized SOL folders and "
            "supported MEDA files."
        )

        if warning_count:
            message += (
                " Some discovered files have warnings. "
                "Review the discovery results before analysis."
            )

        self.validation_view.show_result(
            valid=True,
            message=message,
            sol_count=len(sol_folders),
            file_count=len(supported_records),
            warning_count=warning_count,
        )

        self.input_ready.emit(directory)
        return True

    def _show_validation_failure(
        self,
        message: str,
        *,
        sol_count: int = 0,
        file_count: int = 0,
        warning_count: int = 0,
    ) -> None:
        self._is_validated = False

        self.validation_view.show_result(
            valid=False,
            message=message,
            sol_count=sol_count,
            file_count=file_count,
            warning_count=warning_count,
        )

    def clear_selection(self) -> None:
        """Clear the selected directory and all displayed results."""
        self._selected_input_dir = None
        self._is_validated = False
        self._last_records = []

        self.file_import_view.set_selected_directory(None)
        self.file_preview_view.clear()
        self.validation_view.reset()

        self.validate_button.setEnabled(False)
        self.input_directory_changed.emit(None)