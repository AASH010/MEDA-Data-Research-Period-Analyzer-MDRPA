
"""Dedicated export dialog for reports belonging to an individual Run."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


__all__ = ["ExportView"]


class ExportView(QDialog):
    """Choose a destination and export one report from its source Run."""

    def __init__(
        self,
        *,
        source_path: str | Path,
        output_dir: str | Path,
        run_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string.")

        self._source_path = Path(source_path).expanduser()
        self._output_dir = Path(output_dir).expanduser()
        self._run_id = run_id

        self.setObjectName("export_view")
        self.setWindowTitle("Export Report")
        self.setModal(True)
        self.resize(560, 190)

        self._build_ui()
        self._connect_signals()

    @property
    def source_path(self) -> Path:
        """Return the original report path."""
        return self._source_path

    @property
    def run_id(self) -> str:
        """Return the Run identifier associated with this export."""
        return self._run_id

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Export Analysis Report", self)
        title.setObjectName("export_title")

        run_label = QLabel(f"Source Run: {self._run_id}", self)
        run_label.setObjectName("export_run_label")
        run_label.setWordWrap(True)

        report_label = QLabel(
            f"Report: {self._source_path.name}",
            self,
        )
        report_label.setObjectName("export_report_label")
        report_label.setWordWrap(True)

        destination_label = QLabel("Destination:", self)

        self.destination_input = QLineEdit(self)
        self.destination_input.setObjectName("export_destination_input")
        self.destination_input.setPlaceholderText(
            "Choose where to save the exported report..."
        )

        self.browse_button = QPushButton("Browse…", self)
        self.browse_button.setObjectName("export_browse_button")

        destination_layout = QHBoxLayout()
        destination_layout.addWidget(self.destination_input, 1)
        destination_layout.addWidget(self.browse_button)

        self.status_label = QLabel(
            "Choose a destination to enable export.",
            self,
        )
        self.status_label.setObjectName("export_status_label")
        self.status_label.setWordWrap(True)

        self.export_button = QPushButton("Export", self)
        self.export_button.setObjectName("export_confirm_button")
        self.export_button.setEnabled(False)

        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setObjectName("export_cancel_button")

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.export_button)

        layout.addWidget(title)
        layout.addWidget(run_label)
        layout.addWidget(report_label)
        layout.addWidget(destination_label)
        layout.addLayout(destination_layout)
        layout.addWidget(self.status_label)
        layout.addLayout(button_layout)

    def _connect_signals(self) -> None:
        self.destination_input.textChanged.connect(
            self._handle_destination_changed
        )
        self.browse_button.clicked.connect(self._choose_destination)
        self.export_button.clicked.connect(self._handle_export)
        self.cancel_button.clicked.connect(self.reject)

    def _handle_destination_changed(self, value: str) -> None:
        has_destination = bool(value.strip())
        self.export_button.setEnabled(has_destination)

        if has_destination:
            self.status_label.setText("Destination selected.")
        else:
            self.status_label.setText(
                "Choose a destination to enable export."
            )

    def _choose_destination(self) -> None:
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Choose Export Destination",
            self._source_path.name,
            "All Files (*)",
        )

        if destination:
            self.destination_input.setText(destination)

    def _validate_source(self) -> Path:
        """Ensure the source is a regular file inside its own Run output."""
        try:
            output_dir = self._output_dir.resolve(strict=True)
            source = self._source_path.resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as exc:
            raise FileNotFoundError(
                "The source report or its Run output directory "
                "is no longer available."
            ) from exc

        if not output_dir.is_dir():
            raise NotADirectoryError(
                f"Run output path is not a directory: {output_dir}"
            )

        if source.parent != output_dir or not source.is_file():
            raise ValueError(
                "The source report must be a regular file directly "
                "inside the selected Run output directory."
            )

        return source

    def export_to(self, destination: str | Path) -> Path:
        """Export the original report and preserve its file metadata."""
        source = self._validate_source()

        if not isinstance(destination, (str, Path)):
            raise TypeError("destination must be a string or Path.")

        destination_text = str(destination).strip()

        if not destination_text:
            raise ValueError("An export destination is required.")

        target = Path(destination_text).expanduser().resolve()

        if target == source:
            raise ValueError(
                "The export destination must differ from the source report."
            )

        if target.exists() and target.is_dir():
            raise IsADirectoryError(
                f"Export destination is a directory: {target}"
            )
        if target.exists():
            raise FileExistsError(
                f"An export file already exists at: {target}"
                )    
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

        return target

    def _handle_export(self) -> None:
        destination = self.destination_input.text().strip()

        if not destination:
            self.status_label.setText(
                "Choose a destination before exporting."
            )
            return

        try:
            exported_path = self.export_to(destination)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            message = f"{type(exc).__name__}: {exc}"
            self.status_label.setText(
                f"Export failed: {message}"
            )
            QMessageBox.warning(
                self,
                "Export Failed",
                f"Unable to export the report:\n{message}",
            )
            return

        QMessageBox.information(
            self,
            "Export Completed",
            f"Report exported successfully:\n{exported_path}",
        )
        self.accept()
