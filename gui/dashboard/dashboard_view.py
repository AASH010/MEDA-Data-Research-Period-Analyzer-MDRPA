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
    QScrollArea,
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
from gui.styles.classic_theme import apply_dashboard_theme


__all__ = ["DashboardView"]


class DashboardView(QWidget):
    """Browse persisted Runs and their read-only analysis artifacts."""

    SUMMARY_FILES = (
        ("Coverage Summary — Full Dataset", "coverage_summary.json"),
        (
            "Coverage Summary — Selected Range",
            "coverage_range_summary.json",
        ),
        ("Quality Summary — Full Dataset", "quality_summary.json"),
        (
            "Quality Summary — Selected Range",
            "quality_range_summary.json",
        ),
        (
            "Synchronization Summary — Full Dataset",
            "synchronization_summary.json",
        ),
        (
            "Synchronization Summary — Selected Range",
            "synchronization_range_summary.json",
        ),
        (
            "Period Ranking Summary — Full Dataset",
            "period_ranking_full_summary.json",
        ),
        (
            "Period Ranking Summary — Selected Range",
            "period_ranking_summary.json",
        ),
    )

    QUALITY_REPORT_FILE = "quality_field_report.csv"
    SYNCHRONIZATION_FILE_REPORT = "synchronization_file_report.csv"
    SYNCHRONIZATION_PAIR_REPORT = "synchronization_pair_report.csv"

    RANKING_REPORT_FILE = "period_ranking.csv"
    FULL_RANKING_REPORT_FILE = "period_ranking_full.csv"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setObjectName("dashboard_view")

        self._run_manager: RunManager | None = None
        self._records_by_id: dict[str, RunRecord] = {}
        self._selected_run_id: str | None = None

        self._build_ui()
        apply_dashboard_theme(self)
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
        """Return the Full Dataset coverage dashboard."""
        return self._coverage_dashboard

    @property
    def quality_dashboard(self) -> QualityDashboard:
        """Return the Full Dataset quality dashboard."""
        return self._quality_dashboard

    @property
    def synchronization_dashboard(self) -> SynchronizationDashboard:
        """Return the Full Dataset synchronization dashboard."""
        return self._synchronization_dashboard

    @property
    def ranking_dashboard(self) -> RankingDashboard:
        """Return the Full Dataset ranking dashboard."""
        return self._ranking_dashboard

    @staticmethod
    def _make_scrollable_tab(
        dashboard: QWidget,
        parent: QWidget,
        title: str,
        tabs: QTabWidget,
    ) -> None:
        """Place a dashboard inside a resizable scroll area."""
        scroll = QScrollArea(parent)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll.setWidget(dashboard)

        tabs.addTab(scroll, title)

    def _create_analysis_page(
        self,
        parent: QWidget,
    ) -> tuple[
        QWidget,
        CoverageDashboard,
        QualityDashboard,
        SynchronizationDashboard,
        RankingDashboard,
    ]:
        """Create one range-specific page containing all analyzer views."""
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        tabs = QTabWidget(page)
        tabs.setObjectName("dashboard_analyzer_tabs")

        coverage = CoverageDashboard()
        quality = QualityDashboard()
        synchronization = SynchronizationDashboard()
        ranking = RankingDashboard()

        self._make_scrollable_tab(
            coverage,
            page,
            "Coverage",
            tabs,
        )
        self._make_scrollable_tab(
            quality,
            page,
            "Quality",
            tabs,
        )
        self._make_scrollable_tab(
            synchronization,
            page,
            "Synchronization",
            tabs,
        )
        self._make_scrollable_tab(
            ranking,
            page,
            "Ranking",
            tabs,
        )

        layout.addWidget(tabs)

        return (
            page,
            coverage,
            quality,
            synchronization,
            ranking,
        )

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
        runs_group.setMaximumHeight(220)

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

        (
            full_page,
            self._coverage_dashboard,
            self._quality_dashboard,
            self._synchronization_dashboard,
            self._ranking_dashboard,
        ) = self._create_analysis_page(details_group)

        (
            selected_page,
            self._coverage_range_dashboard,
            self._quality_range_dashboard,
            self._synchronization_range_dashboard,
            self._ranking_range_dashboard,
        ) = self._create_analysis_page(details_group)

        self._selected_range_page = selected_page

        self.analysis_tabs = QTabWidget(details_group)
        self.analysis_tabs.setObjectName("dashboard_analysis_tabs")
        self.analysis_tabs.addTab(self.summary_text, "Run Summary")
        self.analysis_tabs.addTab(full_page, "Full Dataset")
        self.analysis_tabs.addTab(selected_page, "Selected Range")

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
        layout.addWidget(runs_group, 0)
        layout.addWidget(self.details_tabs, 1)

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
        self._set_selected_range_tab_visible(False)

    def _clear_analysis_dashboards(self) -> None:
        """Reset all Full Dataset and Selected Range dashboard widgets."""
        dashboards = (
            self._coverage_dashboard,
            self._quality_dashboard,
            self._synchronization_dashboard,
            self._ranking_dashboard,
            self._coverage_range_dashboard,
            self._quality_range_dashboard,
            self._synchronization_range_dashboard,
            self._ranking_range_dashboard,
        )

        for dashboard in dashboards:
            dashboard.reset()

    def _set_selected_range_tab_visible(self, visible: bool) -> None:
        """Show Selected Range only when it represents a partial range."""
        selected_page = self._selected_range_page
        selected_index = self.analysis_tabs.indexOf(selected_page)

        if visible:
            if selected_index < 0:
                self.analysis_tabs.addTab(
                    selected_page,
                    "Selected Range",
                )
        elif selected_index >= 0:
            self.analysis_tabs.removeTab(selected_index)

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
            self._set_selected_range_tab_visible(False)
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
            self._set_selected_range_tab_visible(False)
            return

        self.status_label.setText(f"{len(records)} Run(s) available.")

        if selected_row is None:
            selected_row = 0

        self.run_table.blockSignals(True)
        self.run_table.selectRow(selected_row)
        self.run_table.blockSignals(False)

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
            self._set_selected_range_tab_visible(False)
            return

        item = self.run_table.item(row, 0)

        if item is None:
            self._selected_run_id = None
            self.run_details_label.setText("No Run selected.")
            self.summary_text.clear()
            self._clear_analysis_dashboards()
            self._set_selected_range_tab_visible(False)
            return

        run_id = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(run_id, str):
            self._selected_run_id = None
            self.run_details_label.setText("Invalid Run selection.")
            self.summary_text.clear()
            self._clear_analysis_dashboards()
            self._set_selected_range_tab_visible(False)
            return

        record = self._records_by_id.get(run_id)

        if record is None:
            self._selected_run_id = None
            self.run_details_label.setText(
                "The selected Run is no longer available."
            )
            self.summary_text.clear()
            self._clear_analysis_dashboards()
            self._set_selected_range_tab_visible(False)
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

    @staticmethod
    def _read_json_object(path: Path) -> dict[str, Any] | None:
        """Read a JSON object without raising file or decoding errors."""
        if not path.is_file():
            return None

        try:
            with path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            return None

        return payload if isinstance(payload, dict) else None

    @classmethod
    def _has_partial_selected_range(
        cls,
        output_dir: Path,
    ) -> bool:
        """Return whether the persisted selected range differs from full data."""
        full_summary = cls._read_json_object(
            output_dir / "coverage_summary.json"
        )
        selected_summary = cls._read_json_object(
            output_dir / "coverage_range_summary.json"
        )

        if full_summary is None or selected_summary is None:
            return False

        full_start = full_summary.get("start_sol")
        full_end = full_summary.get("end_sol")
        selected_start = selected_summary.get("start_sol")
        selected_end = selected_summary.get("end_sol")

        bounds = (
            full_start,
            full_end,
            selected_start,
            selected_end,
        )

        if any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in bounds
        ):
            return False

        return (
            selected_start != full_start
            or selected_end != full_end
        )

    def _load_analysis_dashboards(self, record: RunRecord) -> None:
        """Load Full Dataset and Selected Range artifacts for one Run."""
        output_dir = record.paths.output_dir

        # Full Dataset dashboards.
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
            output_dir / "period_ranking_full_summary.json",
            output_dir / self.FULL_RANKING_REPORT_FILE,
        )

        # Selected Range dashboards.
        self._coverage_range_dashboard.load_summary_file(
            output_dir / "coverage_range_summary.json"
        )

        self._quality_range_dashboard.load_artifacts(
            output_dir / "quality_range_summary.json",
            output_dir / self.QUALITY_REPORT_FILE,
        )

        self._synchronization_range_dashboard.load_artifacts(
            output_dir / "synchronization_range_summary.json",
            output_dir / self.SYNCHRONIZATION_FILE_REPORT,
            output_dir / self.SYNCHRONIZATION_PAIR_REPORT,
        )

        self._ranking_range_dashboard.load_artifacts(
            output_dir / "period_ranking_summary.json",
            output_dir / self.RANKING_REPORT_FILE,
        )

        self._set_selected_range_tab_visible(
            self._has_partial_selected_range(output_dir)
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
