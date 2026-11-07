
"""Read-only report browser and exporter for isolated analysis Runs."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.run_manager.run_manager import RunManager
from backend.run_manager.run_registry import RunRecord
from gui.reports.export_view import ExportView


__all__ = ["ReportsView"]


class ReportsView(QWidget):
    """Browse and export report artifacts belonging to one selected Run."""

    REPORT_FILES = (
        ("File Inventory", "file_inventory.csv"),
        ("Metadata Inventory", "metadata_inventory.json"),
        ("Coverage Report", "coverage_report.csv"),
        ("Coverage Summary", "coverage_summary.json"),
        ("Coverage Range Summary", "coverage_range_summary.json"),
        ("Quality Field Report", "quality_field_report.csv"),
        ("Quality Summary", "quality_summary.json"),
        ("Quality Range Summary", "quality_range_summary.json"),
        ("Synchronization File Report", "synchronization_file_report.csv"),
        ("Synchronization Pair Report", "synchronization_pair_report.csv"),
        ("Synchronization Summary", "synchronization_summary.json"),
        (
            "Synchronization Range Summary",
            "synchronization_range_summary.json",
        ),
        ("Period Ranking", "period_ranking.csv"),
        ("Period Ranking Full", "period_ranking_full.csv"),
        ("Period Ranking Summary", "period_ranking_summary.json"),
        (
            "Period Ranking Full Summary",
            "period_ranking_full_summary.json",
        ),
    )

    PREVIEW_MAX_BYTES = 256 * 1024
    CSV_PREVIEW_MAX_ROWS = 100

    USER_ROLE = 32

    def __init__(
        self,
        run_manager: RunManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        if run_manager is not None and not isinstance(
            run_manager,
            RunManager,
        ):
            raise TypeError("run_manager must be a RunManager or None.")

        self._run_manager = run_manager
        self._records_by_id: dict[str, RunRecord] = {}
        self._selected_report_path: Path | None = None

        self.setObjectName("reports_view")
        self._build_ui()
        self._connect_signals()
        self.refresh_runs()

    @property
    def run_manager(self) -> RunManager | None:
        """Return the RunManager used as the reports data source."""
        return self._run_manager

    @property
    def selected_run_id(self) -> str | None:
        """Return the currently selected Run identifier."""
        value = self.run_selector.currentData()
        return value if isinstance(value, str) else None

    @property
    def selected_report_path(self) -> Path | None:
        """Return the currently selected available report path."""
        return self._selected_report_path

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Reports & Export", self)
        title.setObjectName("reports_title")

        description = QLabel(
            "Browse generated artifacts for an individual analysis Run. "
            "Reports are read from that Run's isolated output directory.",
            self,
        )
        description.setObjectName("reports_description")
        description.setWordWrap(True)

        run_group = QGroupBox("Selected Analysis Run", self)
        run_layout = QHBoxLayout(run_group)

        self.run_selector = QComboBox(run_group)
        self.run_selector.setObjectName("reports_run_selector")

        self.refresh_button = QPushButton("Refresh Runs", run_group)
        self.refresh_button.setObjectName("reports_refresh_button")

        run_layout.addWidget(QLabel("Run:", run_group))
        run_layout.addWidget(self.run_selector, 1)
        run_layout.addWidget(self.refresh_button)

        self.status_label = QLabel(
            "Connect a RunManager to browse reports.",
            self,
        )
        self.status_label.setObjectName("reports_status")
        self.status_label.setWordWrap(True)

        reports_group = QGroupBox("Report Artifacts", self)
        reports_layout = QVBoxLayout(reports_group)

        self.report_table = QTableWidget(
            0,
            4,
            reports_group,
        )
        self.report_table.setObjectName("reports_table")
        self.report_table.setHorizontalHeaderLabels(
            ("Report", "File", "Status", "Size")
        )
        self.report_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.report_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.report_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.report_table.setAlternatingRowColors(True)
        self.report_table.horizontalHeader().setStretchLastSection(True)
        reports_layout.addWidget(self.report_table)

        preview_group = QGroupBox("Report Preview", self)
        preview_layout = QVBoxLayout(preview_group)

        self.preview_label = QLabel(
            "Select an available report to preview its contents.",
            preview_group,
        )
        self.preview_label.setObjectName("reports_preview_label")
        self.preview_label.setWordWrap(True)

        self.preview_text = QPlainTextEdit(preview_group)
        self.preview_text.setObjectName("reports_preview_text")
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText(
            "The selected report preview will appear here."
        )

        self.export_button = QPushButton(
            "Export Selected Report…",
            preview_group,
        )
        self.export_button.setObjectName("reports_export_button")
        self.export_button.setEnabled(False)

        preview_layout.addWidget(self.preview_label)
        preview_layout.addWidget(self.preview_text, 1)
        preview_layout.addWidget(self.export_button)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(run_group)
        layout.addWidget(self.status_label)
        layout.addWidget(reports_group, 2)
        layout.addWidget(preview_group, 3)

    def _connect_signals(self) -> None:
        self.refresh_button.clicked.connect(self.refresh_runs)
        self.run_selector.currentIndexChanged.connect(
            self._handle_run_changed
        )
        self.report_table.itemSelectionChanged.connect(
            self._handle_report_selection
        )
        self.export_button.clicked.connect(
            self._choose_export_destination
        )

    def set_run_manager(
        self,
        run_manager: RunManager | None,
    ) -> None:
        """Replace the data source and refresh the displayed Runs."""
        if run_manager is not None and not isinstance(
            run_manager,
            RunManager,
        ):
            raise TypeError("run_manager must be a RunManager or None.")

        self._run_manager = run_manager
        self.refresh_runs()

    def refresh_runs(self) -> None:
        """Reload Runs while preserving the selected Run when possible."""
        previous_run_id = self.selected_run_id

        self._records_by_id.clear()
        self.run_selector.blockSignals(True)
        self.run_selector.clear()

        if self._run_manager is None:
            self.run_selector.blockSignals(False)
            self._clear_reports(
                "Reports are unavailable because no RunManager is connected."
            )
            return

        try:
            records = self._run_manager.list_runs()
        except Exception as exc:
            self.run_selector.blockSignals(False)
            self._clear_reports(
                f"Unable to load Runs: {type(exc).__name__}: {exc}"
            )
            return

        for record in records:
            self._records_by_id[record.run_id] = record
            self.run_selector.addItem(
                f"{record.run_id} — {record.status.value}",
                record.run_id,
            )

        if previous_run_id in self._records_by_id:
            index = self.run_selector.findData(previous_run_id)
            self.run_selector.setCurrentIndex(index)
        elif self.run_selector.count():
            self.run_selector.setCurrentIndex(0)

        self.run_selector.blockSignals(False)

        if self.run_selector.count():
            self._load_selected_run()
        else:
            self._clear_reports("No analysis Runs are available yet.")

    def _clear_reports(self, message: str) -> None:
        self._selected_report_path = None
        self.report_table.setRowCount(0)
        self.preview_text.clear()
        self.preview_label.setText(
            "Select an available report to preview its contents."
        )
        self.export_button.setEnabled(False)
        self.status_label.setText(message)

    def _handle_run_changed(self, _index: int) -> None:
        self._load_selected_run()

    def _load_selected_run(self) -> None:
        run_id = self.selected_run_id

        if run_id is None:
            self._clear_reports("No analysis Run is selected.")
            return

        record = self._records_by_id.get(run_id)

        if record is None:
            self._clear_reports("The selected Run is no longer available.")
            return

        output_dir = record.paths.output_dir

        self._selected_report_path = None
        self.preview_text.clear()
        self.preview_label.setText(
            "Select an available report to preview its contents."
        )
        self.export_button.setEnabled(False)
        self.report_table.setRowCount(0)

        for report_title, filename in self.REPORT_FILES:
            path = output_dir / filename
            available = self._is_report_available(path, output_dir)

            row = self.report_table.rowCount()
            self.report_table.insertRow(row)

            if available:
                try:
                    size_text = self._format_size(path.stat().st_size)
                except OSError:
                    available = False
                    size_text = "—"
            else:
                size_text = "—"

            values = (
                report_title,
                filename,
                "Available" if available else "Not generated",
                size_text,
            )

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(
                    self.USER_ROLE,
                    str(path) if available else None,
                )
                self.report_table.setItem(row, column, item)

        metadata = record.metadata
        self.status_label.setText(
            f"Run: {record.run_id} | "
            f"Status: {record.status.value} | "
            f"SOL range: {self._format_sol_range(metadata.start_sol, metadata.end_sol)}"
        )

    @staticmethod
    def _is_report_available(
        path: Path,
        output_dir: Path,
    ) -> bool:
        """Accept only regular files directly contained in this Run output."""
        try:
            resolved_output = output_dir.resolve()
            resolved_path = path.resolve(strict=True)

            return (
                resolved_path.parent == resolved_output
                and resolved_path.is_file()
            )
        except (OSError, RuntimeError, ValueError):
            return False

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"

    @staticmethod
    def _format_sol_range(
        start_sol: int | None,
        end_sol: int | None,
    ) -> str:
        if start_sol is None or end_sol is None:
            return "Not specified"
        return f"{start_sol}–{end_sol}"

    def _handle_report_selection(self) -> None:
        selected_items = self.report_table.selectedItems()

        if not selected_items:
            self._selected_report_path = None
            self.preview_label.setText(
                "Select an available report to preview its contents."
            )
            self.preview_text.clear()
            self.export_button.setEnabled(False)
            return

        row = selected_items[0].row()
        path_item = self.report_table.item(row, 0)

        if path_item is None:
            self._selected_report_path = None
            self.preview_label.setText("Report unavailable")
            self.preview_text.setPlainText(
                "The selected report information is unavailable."
            )
            self.export_button.setEnabled(False)
            return

        stored_path = path_item.data(self.USER_ROLE)

        if not isinstance(stored_path, str):
            self._selected_report_path = None
            self.preview_label.setText("Report unavailable")
            self.preview_text.setPlainText(
                "This report is not available for the selected Run.\n"
                "It may not have been generated during this analysis."
            )
            self.export_button.setEnabled(False)
            return

        path = Path(stored_path)
        record = self._records_by_id.get(self.selected_run_id or "")

        if record is None or not self._is_report_available(
            path,
            record.paths.output_dir,
        ):
            self._selected_report_path = None
            self.preview_label.setText("Report unavailable")
            self.preview_text.setPlainText(
                "The report is no longer available.\n"
                "It may have been removed or changed since the report list "
                "was loaded."
            )
            self.export_button.setEnabled(False)
            return

        self._selected_report_path = path
        self.export_button.setEnabled(True)
        self._preview_report(path)

    def _preview_report(self, path: Path) -> None:
        self.preview_text.clear()
        self.preview_label.setText(path.name)

        try:
            size = path.stat().st_size

            if size > self.PREVIEW_MAX_BYTES:
                self.preview_text.setPlainText(
                    "Preview omitted because this report exceeds "
                    f"{self._format_size(self.PREVIEW_MAX_BYTES)}. "
                    "You can still export the original file."
                )
                return

            if path.suffix.lower() == ".json":
                with path.open("r", encoding="utf-8") as file:
                    payload = json.load(file)

                preview = json.dumps(
                    payload,
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                )

            elif path.suffix.lower() == ".csv":
                with path.open(
                    "r",
                    encoding="utf-8-sig",
                    newline="",
                ) as file:
                    reader = csv.reader(file)
                    lines = []

                    for index, row in enumerate(reader):
                        if index >= self.CSV_PREVIEW_MAX_ROWS:
                            lines.append(
                                "... preview truncated; export the file "
                                "to inspect all rows."
                            )
                            break

                        lines.append(" | ".join(row))

                preview = "\n".join(lines)

            else:
                preview = (
                    "Preview is not supported for this file type. "
                    "You can still export the original file."
                )

            self.preview_text.setPlainText(
                preview or "The selected report is empty."
            )

        except (
            OSError,
            UnicodeError,
            csv.Error,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            self.preview_text.setPlainText(
                f"Unable to preview report: {type(exc).__name__}: {exc}"
            )

    def export_selected_to(
        self,
        destination: str | Path,
    ) -> Path:
        """Export the selected report through the dedicated ExportView."""
        source = self._selected_report_path

        if source is None:
            raise RuntimeError("No available report is selected.")

        record = self._records_by_id.get(self.selected_run_id or "")

        if record is None:
            raise FileNotFoundError(
                "The selected Run is no longer available."
            )

        dialog = ExportView(
            source_path=source,
            output_dir=record.paths.output_dir,
            run_id=record.run_id,
            parent=self,
        )

        return dialog.export_to(destination)

    def _choose_export_destination(self) -> None:
        """Open the dedicated export dialog for the selected report."""
        source = self._selected_report_path

        if source is None:
            return

        record = self._records_by_id.get(self.selected_run_id or "")

        if record is None:
            return

        if not self._is_report_available(
            source,
            record.paths.output_dir,
        ):
            self._selected_report_path = None
            self.export_button.setEnabled(False)
            self.preview_label.setText("Report unavailable")
            self.preview_text.setPlainText(
                "The selected report is no longer available."
            )
            return

        dialog = ExportView(
            source_path=source,
            output_dir=record.paths.output_dir,
            run_id=record.run_id,
            parent=self,
        )
        dialog.exec()
