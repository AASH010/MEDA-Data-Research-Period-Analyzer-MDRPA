
"""Read-only dashboard for browsing and comparing analysis Runs."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.run_manager.run_manager import RunManager
from backend.run_manager.run_registry import RunRecord
from gui.dashboard.comparison_dashboard import ComparisonDashboard
from gui.dashboard.coverage_dashboard import CoverageDashboard
from gui.dashboard.quality_dashboard import QualityDashboard
from gui.dashboard.ranking_dashboard import RankingDashboard
from gui.dashboard.synchronization_dashboard import (
    SynchronizationDashboard,
)


__all__ = ["DashboardView"]


class DashboardView(QWidget):
    """Browse persisted Runs and their read-only analysis artifacts."""

    SUMMARY_FILES = (
        ("Coverage Summary", "coverage_summary.json"),
        ("Quality Summary", "quality_summary.json"),
        ("Synchronization Summary", "synchronization_summary.json"),
        ("Period Ranking Summary", "period_ranking_summary.json"),
    )

    QUALITY_REPORT_FILE = "quality_field_report.csv"
    SYNCHRONIZATION_FILE_REPORT = "synchronization_file_report.csv"
    SYNCHRONIZATION_PAIR_REPORT = "synchronization_pair_report.csv"
    RANKING_REPORT_FILE = "period_ranking.csv"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setObjectName("dashboard_view")

        self._run_manager: RunManager | None = None
        self._records_by_id: dict[str, RunRecord] = {}
        self._selected_run_id: str | None = None

        self._build_ui()
        self._connect_signals()
        self._show_unavailable_state()

    @property
    def run_manager(self) -> RunManager | None:
        """Return the RunManager used as the dashboard data source."""
        return self._run_manager

    @property
    def selected_run_id(self) -> str | None:
        """Return the currently displayed Run identifier."""
        return self._selected_run_id

    @property
    def comparison_dashboard(self) -> ComparisonDashboard:
        """Return the embedded multi-Run comparison page."""
        return self._comparison_dashboard

    @property
    def coverage_dashboard(self) -> CoverageDashboard:
        return self._coverage_dashboard

    @property
    def quality_dashboard(self) -> QualityDashboard:
        return self._quality_dashboard

    @property
    def synchronization_dashboard(self) -> SynchronizationDashboard:
        return self._synchronization_dashboard

    @property
    def ranking_dashboard(self) -> RankingDashboard:
        return self._ranking_dashboard

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Analysis Dashboard")
        title.setObjectName("dashboard_title")

        self.status_label = QLabel("Dashboard is not connected.")
        self.status_label.setObjectName("dashboard_status")
        self.status_label.setWordWrap(True)

        runs_group = QGroupBox("Analysis Runs", self)
        runs_group.setObjectName("dashboard_runs_group")
        runs_layout = QVBoxLayout(runs_group)

        self.run_table = QTableWidget(0, 4, runs_group)
        self.run_table.setObjectName("dashboard_runs_table")
        self.run_table.setHorizontalHeaderLabels(
            ("Run ID", "Status", "SOL Range", "Created")
        )
        self.run_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.run_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.run_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.run_table.setAlternatingRowColors(True)
        self.run_table.setWordWrap(False)
        self.run_table.horizontalHeader().setStretchLastSection(True)
        runs_layout.addWidget(self.run_table)

        details_group = QGroupBox("Selected Run Details", self)
        details_group.setObjectName("dashboard_details_group")
        details_layout = QVBoxLayout(details_group)

        self.run_details_label = QLabel("No Run selected.")
        self.run_details_label.setObjectName("dashboard_run_details")
        self.run_details_label.setWordWrap(True)

        self.summary_text = QPlainTextEdit(details_group)
        self.summary_text.setObjectName("dashboard_summary_text")
        self.summary_text.setReadOnly(True)
        self.summary_text.setPlaceholderText(
            "Select a Run to inspect its available summaries."
        )

        self._coverage_dashboard = CoverageDashboard(self)
        self._quality_dashboard = QualityDashboard(self)
        self._synchronization_dashboard = SynchronizationDashboard(self)
        self._ranking_dashboard = RankingDashboard(self)

        self.analysis_tabs = QTabWidget(details_group)
        self.analysis_tabs.setObjectName("dashboard_analysis_tabs")
        self.analysis_tabs.addTab(self.summary_text, "Run Summary")
        self.analysis_tabs.addTab(self._coverage_dashboard, "Coverage")
        self.analysis_tabs.addTab(self._quality_dashboard, "Quality")
        self.analysis_tabs.addTab(
            self._synchronization_dashboard,
            "Synchronization",
        )
        self.analysis_tabs.addTab(self._ranking_dashboard, "Ranking")

        details_layout.addWidget(self.run_details_label)
        details_layout.addWidget(self.analysis_tabs, 1)

        self._comparison_dashboard = ComparisonDashboard(self)

        self.comparison_notice = QLabel(
            "Comparison is exploratory: matching numeric JSON paths do not "
            "guarantee equivalent units, SOL ranges, configurations, or "
            "scientific meaning. Review each Run's metadata and source "
            "artifacts before interpreting differences."
        )
        self.comparison_notice.setObjectName(
            "comparison_limitations_notice"
        )
        self.comparison_notice.setWordWrap(True)

        comparison_layout = self._comparison_dashboard.layout()
        if comparison_layout is not None:
            comparison_layout.insertWidget(0, self.comparison_notice)

        self.details_tabs = QTabWidget(self)
        self.details_tabs.setObjectName("dashboard_details_tabs")
        self.details_tabs.addTab(details_group, "Run Details")
        self.details_tabs.addTab(
            self._comparison_dashboard,
            "Compare Runs",
        )

        layout.addWidget(title)
        layout.addWidget(self.status_label)
        layout.addWidget(runs_group, 2)
        layout.addWidget(self.details_tabs, 3)

    def _connect_signals(self) -> None:
        self.run_table.itemSelectionChanged.connect(
            self._handle_selection_changed
        )

    def set_run_manager(self, run_manager: RunManager) -> None:
        """Attach the application's RunManager and load its Runs."""
        if not isinstance(run_manager, RunManager):
            raise TypeError("run_manager must be a RunManager instance.")

        self._run_manager = run_manager
        self.refresh_runs()

    def _show_unavailable_state(self) -> None:
        self.status_label.setText(
            "Run Manager is not connected. No Run data is available."
        )
        self.run_details_label.setText("No Run selected.")
        self.summary_text.clear()
        self._comparison_dashboard.set_runs(())
        self._clear_analysis_dashboards()

    def _clear_analysis_dashboards(self) -> None:
        """Reset all visualization widgets to their unavailable states."""
        self._coverage_dashboard.load_summary_file(
            Path("__dashboard_no_run__") / "coverage_summary.json"
        )
        self._quality_dashboard.load_artifacts(
            Path("__dashboard_no_run__") / "quality_summary.json"
        )
        self._synchronization_dashboard.load_artifacts(
            Path("__dashboard_no_run__") / "synchronization_summary.json"
        )
        self._ranking_dashboard.load_artifacts(
            Path("__dashboard_no_run__") / "period_ranking_summary.json"
        )

    @staticmethod
    def _format_sol_range(record: RunRecord) -> str:
        start_sol = record.metadata.start_sol
        end_sol = record.metadata.end_sol

        if start_sol is None or end_sol is None:
            return "Not specified"

        if start_sol == end_sol:
            return str(start_sol)

        return f"{start_sol} – {end_sol}"

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return "Not available"

        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    def refresh_runs(self) -> None:
        """Reload Runs and comparison choices without executing analysis."""
        manager = self._run_manager

        if manager is None:
            self._show_unavailable_state()
            return

        selected_run_id = self._selected_run_id

        try:
            records = list(manager.list_runs())
        except Exception as exc:
            self.status_label.setText(
                f"Unable to load Runs: {type(exc).__name__}: {exc}"
            )
            self.run_table.setRowCount(0)
            self._records_by_id.clear()
            self._selected_run_id = None
            self.run_details_label.setText("Run list could not be loaded.")
            self.summary_text.clear()
            self._comparison_dashboard.set_runs(())
            self._clear_analysis_dashboards()
            return

        records.sort(
            key=lambda record: record.metadata.created_at,
            reverse=True,
        )

        self._records_by_id = {
            record.run_id: record
            for record in records
        }

        self._comparison_dashboard.set_runs(records)

        self.run_table.blockSignals(True)
        self.run_table.setRowCount(len(records))

        selected_row: int | None = None

        for row, record in enumerate(records):
            run_id_item = QTableWidgetItem(record.run_id)
            run_id_item.setData(
                Qt.ItemDataRole.UserRole,
                record.run_id,
            )

            status_item = QTableWidgetItem(record.status.value)
            range_item = QTableWidgetItem(
                self._format_sol_range(record)
            )
            created_item = QTableWidgetItem(
                self._format_datetime(record.metadata.created_at)
            )

            self.run_table.setItem(row, 0, run_id_item)
            self.run_table.setItem(row, 1, status_item)
            self.run_table.setItem(row, 2, range_item)
            self.run_table.setItem(row, 3, created_item)

            if record.run_id == selected_run_id:
                selected_row = row

        self.run_table.blockSignals(False)

        if not records:
            self._selected_run_id = None
            self.status_label.setText("No analysis Runs are available.")
            self.run_details_label.setText("No Run selected.")
            self.summary_text.clear()
            self._clear_analysis_dashboards()
            return

        self.status_label.setText(f"{len(records)} Run(s) available.")

        if selected_row is None:
            selected_row = 0

        self.run_table.selectRow(selected_row)
        self._display_selected_run()

    def _handle_selection_changed(self) -> None:
        self._display_selected_run()

    def _display_selected_run(self) -> None:
        row = self.run_table.currentRow()

        if row < 0:
            self._selected_run_id = None
            self.run_details_label.setText("No Run selected.")
            self.summary_text.clear()
            self._clear_analysis_dashboards()
            return

        item = self.run_table.item(row, 0)

        if item is None:
            self._selected_run_id = None
            self.run_details_label.setText("No Run selected.")
            self.summary_text.clear()
            self._clear_analysis_dashboards()
            return

        run_id = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(run_id, str):
            self._selected_run_id = None
            self.run_details_label.setText("Invalid Run selection.")
            self.summary_text.clear()
            self._clear_analysis_dashboards()
            return

        record = self._records_by_id.get(run_id)

        if record is None:
            self._selected_run_id = None
            self.run_details_label.setText(
                "The selected Run is no longer available."
            )
            self.summary_text.clear()
            self._clear_analysis_dashboards()
            return

        self._selected_run_id = run_id
        self._display_run_details(record)
        self._load_analysis_dashboards(record)

    def _display_run_details(self, record: RunRecord) -> None:
        metadata = record.metadata

        details = (
            f"Run ID: {record.run_id}\n"
            f"Status: {record.status.value}\n"
            f"SOL Range: {self._format_sol_range(record)}\n"
            f"Created: {self._format_datetime(metadata.created_at)}\n"
            f"Started: {self._format_datetime(metadata.started_at)}\n"
            f"Finished: {self._format_datetime(metadata.finished_at)}\n"
            f"Application Version: "
            f"{metadata.application_version or 'Not available'}\n"
            f"Failure Reason: "
            f"{metadata.failure_reason or 'None'}"
        )

        self.run_details_label.setText(details)

        sections: list[str] = []

        for title, filename in self.SUMMARY_FILES:
            sections.append(
                self._read_summary_section(
                    record.paths.output_dir,
                    title,
                    filename,
                )
            )

        execution_summary: Any = metadata.settings.get(
            "execution_summary"
        )

        if execution_summary is not None:
            sections.append(
                "Execution Summary (metadata.json)\n"
                "---------------------------------\n"
                + json.dumps(
                    execution_summary,
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            sections.append(
                "Execution Summary (metadata.json)\n"
                "---------------------------------\n"
                "Not persisted for this Run."
            )

        self.summary_text.setPlainText("\n\n".join(sections))

    def _load_analysis_dashboards(self, record: RunRecord) -> None:
        """Load only artifacts persisted inside the selected Run directory."""
        output_dir = record.paths.output_dir

        self._coverage_dashboard.load_summary_file(
            output_dir / "coverage_summary.json"
        )

        self._quality_dashboard.load_artifacts(
            output_dir / "quality_summary.json",
            output_dir / self.QUALITY_REPORT_FILE,
        )

        self._synchronization_dashboard.load_artifacts(
            output_dir / "synchronization_summary.json",
            output_dir / self.SYNCHRONIZATION_FILE_REPORT,
            output_dir / self.SYNCHRONIZATION_PAIR_REPORT,
        )

        self._ranking_dashboard.load_artifacts(
            output_dir / "period_ranking_summary.json",
            output_dir / self.RANKING_REPORT_FILE,
        )

    @staticmethod
    def _read_summary_section(
        output_dir: Path,
        title: str,
        filename: str,
    ) -> str:
        path = output_dir / filename

        heading = (
            f"{title} ({filename})\n"
            f"{'-' * (len(title) + len(filename) + 3)}"
        )

        if not path.is_file():
            return heading + "\nNot generated or not available."

        try:
            with path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ) as exc:
            return (
                heading
                + "\nUnable to read this artifact: "
                + f"{type(exc).__name__}: {exc}"
            )

        return (
            heading
            + "\n"
            + json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
