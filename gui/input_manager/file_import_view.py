"""Dataset directory selection widget."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


__all__ = ["FileImportView"]


class FileImportView(QWidget):
    """Allow the user to select a MEDA dataset directory."""

    directory_selected = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setObjectName("file_import_view")
        self._selected_directory: Path | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Dataset Directory")
        title.setObjectName("file_import_title")

        row = QHBoxLayout()

        self.path_edit = QLineEdit(self)
        self.path_edit.setObjectName("dataset_directory_path")
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText(
            "Select a directory containing MEDA data..."
        )

        self.browse_button = QPushButton("Browse...", self)
        self.browse_button.setObjectName("browse_dataset_button")
        self.browse_button.clicked.connect(self.choose_directory)

        row.addWidget(self.path_edit, 1)
        row.addWidget(self.browse_button)

        layout.addWidget(title)
        layout.addLayout(row)

    @property
    def selected_directory(self) -> Path | None:
        """Return the currently selected directory."""
        return self._selected_directory

    def choose_directory(self) -> None:
        """Open a native directory selection dialog."""
        initial_directory = (
            str(self._selected_directory)
            if self._selected_directory is not None
            else ""
        )

        selected = QFileDialog.getExistingDirectory(
            self,
            "Select MEDA Dataset Directory",
            initial_directory,
        )

        if not selected:
            return

        self.set_selected_directory(Path(selected))
        self.directory_selected.emit(self._selected_directory)

    def set_selected_directory(
        self,
        directory: str | Path | None,
    ) -> None:
        """Set the selected directory without opening a dialog."""
        if directory is None:
            self._selected_directory = None
            self.path_edit.clear()
            return

        if not isinstance(directory, (str, Path)):
            raise TypeError(
                "directory must be a string, pathlib.Path, or None."
            )

        if isinstance(directory, str) and not directory.strip():
            raise ValueError("directory must not be empty.")

        resolved = Path(directory).expanduser().resolve()

        self._selected_directory = resolved
        self.path_edit.setText(str(resolved))