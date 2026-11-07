
"""Read-only visualization of persisted MEDA quality summaries and reports."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pyqtgraph as pg
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


__all__ = ["QualityDashboard"]


class QualityDashboard(QWidget):
    """Display persisted quality artifacts without rerunning analysis."""

    CATEGORY_LABELS = {
        "quality_field_candidate_reports": "Quality field candidates",
        "operational_context_flag_candidate_reports": (
            "Operational/context candidates"
        ),
        "measurement_uncertainty_reports": "Measurement uncertainty",
        "range_check_reports": "Range checks",
        "file_status_reports": "File status reports",
    }

    CATEGORY_ORDER = tuple(CATEGORY_LABELS)

    REPORT_COLUMNS = (
        "SOL",
        "Product",
        "File",
        "Field",
        "Category",
        "Status",
        "Rows",
        "Missing",
        "Below Minimum",
        "Above Maximum",
    )

    REPORT_SOURCE_COLUMNS = (
        "sol_number",
        "product_code",
        "csv_file",
        "field_name",
        "field_type",
        "analysis_status",
        "total_rows",
        "missing_count",
        "below_valid_minimum",
        "above_valid_maximum",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setObjectName("quality_dashboard")

        self._summary: dict[str, Any] | None = None
        self._summary_path: Path | None = None
        self._report_path: Path | None = None
        self._report_rows: list[dict[str, str]] = []

        self._build_ui()
        self._show_unavailable("Quality summary is not available.")

    @property
    def summary(self) -> dict[str, Any] | None:
        """Return the currently displayed summary."""
        return self._summary

    @property
    def summary_path(self) -> Path | None:
        """Return the latest summary file path."""
        return self._summary_path

    @property
    def report_path(self) -> Path | None:
        """Return the latest field report file path."""
        return self._report_path

    @property
    def report_rows(self) -> list[dict[str, str]]:
        """Return a copy of the loaded field report rows."""
        return list(self._report_rows)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.status_label = QLabel(self)
        self.status_label.setObjectName("quality_status")
        self.status_label.setWordWrap(True)

        metrics_group = QGroupBox("Quality Overview", self)
        metrics_group.setObjectName("quality_metrics_group")
        metrics_layout = QGridLayout(metrics_group)

        self.report_rows_label = self._make_metric_label(
            "Report Rows: Not available",
            "quality_report_rows",
        )
        self.analysed_fields_label = self._make_metric_label(
            "Analysed Field Reports: Not available",
            "quality_analysed_fields",
        )
        self.quality_candidates_label = self._make_metric_label(
            "Quality Candidates: Not available",
            "quality_candidates",
        )
        self.range_checks_label = self._make_metric_label(
            "Range Checks: Not available",
            "quality_range_checks",
        )
        self.below_minimum_label = self._make_metric_label(
            "Below Minimum: Not available",
            "quality_below_minimum",
        )
        self.above_maximum_label = self._make_metric_label(
            "Above Maximum: Not available",
            "quality_above_maximum",
        )

        metrics = (
            self.report_rows_label,
            self.analysed_fields_label,
            self.quality_candidates_label,
            self.range_checks_label,
            self.below_minimum_label,
            self.above_maximum_label,
        )

        for index, label in enumerate(metrics):
            metrics_layout.addWidget(label, index // 3, index % 3)

        charts_layout = QHBoxLayout()

        category_group = QGroupBox("Persisted Report Categories", self)
        category_group.setObjectName("quality_category_group")
        category_layout = QVBoxLayout(category_group)

        self.category_chart = pg.PlotWidget(category_group)
        self.category_chart.setObjectName("quality_category_chart")
        self.category_chart.setBackground(None)
        self.category_chart.setLabel("left", "Report Count")
        self.category_chart.setLabel("bottom", "Category")
        self.category_chart.showGrid(x=True, y=True, alpha=0.2)
        self.category_chart.setMinimumHeight(230)

        category_layout.addWidget(self.category_chart)

        status_group = QGroupBox("Persisted Analysis Statuses", self)
        status_group.setObjectName("quality_status_group")
        status_layout = QVBoxLayout(status_group)

        self.status_chart = pg.PlotWidget(status_group)
        self.status_chart.setObjectName("quality_status_chart")
        self.status_chart.setBackground(None)
        self.status_chart.setLabel("left", "Report Count")
        self.status_chart.setLabel("bottom", "Analysis Status")
        self.status_chart.showGrid(x=True, y=True, alpha=0.2)
        self.status_chart.setMinimumHeight(230)

        status_layout.addWidget(self.status_chart)

        charts_layout.addWidget(category_group)
        charts_layout.addWidget(status_group)

        details_group = QGroupBox("Persisted Field Report Details", self)
        details_group.setObjectName("quality_details_group")
        details_layout = QVBoxLayout(details_group)

        self.report_status_label = QLabel(
            "Field report is not available.",
            details_group,
        )
        self.report_status_label.setObjectName("quality_report_status")
        self.report_status_label.setWordWrap(True)

        self.report_table = QTableWidget(
            0,
            len(self.REPORT_COLUMNS),
            details_group,
        )
        self.report_table.setObjectName("quality_report_table")
        self.report_table.setHorizontalHeaderLabels(
            self.REPORT_COLUMNS
        )
        self.report_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.report_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.report_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.report_table.setAlternatingRowColors(True)
        self.report_table.setWordWrap(False)
        self.report_table.horizontalHeader().setStretchLastSection(True)

        details_layout.addWidget(self.report_status_label)
        details_layout.addWidget(self.report_table)

        layout.addWidget(self.status_label)
        layout.addWidget(metrics_group)
        layout.addLayout(charts_layout)
        layout.addWidget(details_group, 1)

    @staticmethod
    def _make_metric_label(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        label.setWordWrap(True)
        return label

    @staticmethod
    def _is_non_negative_integer(value: Any) -> bool:
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        )

    @classmethod
    def _format_count(cls, value: Any) -> str:
        if not cls._is_non_negative_integer(value):
            return "Not available"

        return f"{value:,}"

    @classmethod
    def _validate_summary(cls, summary: Any) -> tuple[bool, str]:
        if not isinstance(summary, dict):
            return False, "Quality summary must be a JSON object."

        if not isinstance(summary.get("analyzer"), str):
            return False, "Quality summary has no valid analyzer identifier."

        if not cls._is_non_negative_integer(
            summary.get("report_row_count")
        ):
            return False, "Quality summary has an invalid report row count."

        for key in (
            "analysis_status_counts",
            "column_mapping_status_counts",
        ):
            value = summary.get(key)
            if value is not None and not isinstance(value, dict):
                return False, f"Quality summary has an invalid {key} object."

        for key in cls.CATEGORY_ORDER:
            value = summary.get(key)
            if value is not None and not cls._is_non_negative_integer(value):
                return False, f"Quality summary has an invalid {key} value."

        for key in (
            "analysed_field_reports",
            "quality_field_reports",
            "total_values_below_declared_minimum",
            "total_values_above_declared_maximum",
            "total_rows_examined_by_field",
            "total_missing_values_by_field",
        ):
            value = summary.get(key)
            if value is not None and not cls._is_non_negative_integer(value):
                return False, f"Quality summary has an invalid {key} value."

        return True, ""

    def set_summary(self, summary: dict[str, Any] | None) -> bool:
        """Display a previously generated quality summary."""
        if summary is None:
            self._summary = None
            self._clear_summary_display()
            self._show_unavailable("Quality summary is not available.")
            return False

        valid, error_message = self._validate_summary(summary)

        if not valid:
            self._summary = None
            self._clear_summary_display()
            self._show_unavailable(error_message)
            return False

        self._summary = summary
        self._display_summary(summary)
        return True

    def reset(self) -> None:
        """Clear all Run-specific data and restore unavailable states."""
        self._summary = None
        self._summary_path = None
        self._report_path = None
        self._report_rows = []

        self._clear_summary_display()
        self._populate_report_table()

        self.report_status_label.setText(
            "Field report is not available."
        )
        self._show_unavailable("Quality summary is not available.")

    def load_summary_file(self, path: str | Path) -> bool:
        """Load a persisted quality summary JSON file."""
        summary_path = Path(path)
        self._summary_path = summary_path

        if not summary_path.is_file():
            self.set_summary(None)
            self._show_unavailable(
                f"Quality summary is not available: {summary_path}"
            )
            return False

        try:
            with summary_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self.set_summary(None)
            self._show_unavailable(
                "Unable to read quality summary: "
                f"{type(exc).__name__}: {exc}"
            )
            return False

        return self.set_summary(payload)

    def load_report_file(self, path: str | Path) -> bool:
        """Load the persisted quality field report CSV."""
        report_path = Path(path)
        self._report_path = report_path

        if not report_path.is_file():
            self._report_rows = []
            self._populate_report_table()
            self.report_status_label.setText(
                f"Field report is not available: {report_path}"
            )
            return False

        try:
            with report_path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as file:
                reader = csv.DictReader(file)
                fieldnames = reader.fieldnames or []

                missing_columns = [
                    column
                    for column in self.REPORT_SOURCE_COLUMNS
                    if column not in fieldnames
                ]

                if missing_columns:
                    self._report_rows = []
                    self._populate_report_table()
                    self.report_status_label.setText(
                        "Field report has an incompatible schema. "
                        "Missing columns: "
                        + ", ".join(missing_columns)
                    )
                    return False

                rows = list(reader)

        except (OSError, UnicodeError, csv.Error) as exc:
            self._report_rows = []
            self._populate_report_table()
            self.report_status_label.setText(
                "Unable to read field report: "
                f"{type(exc).__name__}: {exc}"
            )
            return False

        self._report_rows = rows
        self._populate_report_table()
        self.report_status_label.setText(
            f"{len(rows):,} persisted field report row(s) loaded."
        )
        return True

    def load_artifacts(
        self,
        summary_path: str | Path,
        report_path: str | Path | None = None,
    ) -> bool:
        """Load the JSON summary and optional CSV field report."""
        summary_loaded = self.load_summary_file(summary_path)

        if report_path is not None:
            self.load_report_file(report_path)
        else:
            self._report_rows = []
            self._populate_report_table()
            self.report_status_label.setText(
                "Field report is not available."
            )

        return summary_loaded

    def _display_summary(self, summary: dict[str, Any]) -> None:
        self.report_rows_label.setText(
            "Report Rows: "
            + self._format_count(summary.get("report_row_count"))
        )
        self.analysed_fields_label.setText(
            "Analysed Field Reports: "
            + self._format_count(summary.get("analysed_field_reports"))
        )
        self.quality_candidates_label.setText(
            "Quality Candidates: "
            + self._format_count(
                summary.get("quality_field_candidate_reports")
                if "quality_field_candidate_reports" in summary
                else summary.get("quality_field_reports")
            )
        )
        self.range_checks_label.setText(
            "Range Checks: "
            + self._format_count(summary.get("range_check_reports"))
        )
        self.below_minimum_label.setText(
            "Below Minimum: "
            + self._format_count(
                summary.get("total_values_below_declared_minimum")
            )
        )
        self.above_maximum_label.setText(
            "Above Maximum: "
            + self._format_count(
                summary.get("total_values_above_declared_maximum")
            )
        )

        self._populate_category_chart(summary)
        self._populate_status_chart(summary)

        self.status_label.setText(
            "Quality summary loaded. Values are displayed from "
            "persisted analyzer output; no analysis was rerun."
        )

    def _populate_category_chart(self, summary: dict[str, Any]) -> None:
        plot_item = self.category_chart.getPlotItem()
        plot_item.clear()

        available = [
            (self.CATEGORY_LABELS[key], summary[key])
            for key in self.CATEGORY_ORDER
            if key in summary
            and self._is_non_negative_integer(summary[key])
        ]

        if not available:
            plot_item.setTitle("Category counts are not available")
            plot_item.getAxis("bottom").setTicks([[]])
            return

        bars = pg.BarGraphItem(
            x=list(range(len(available))),
            height=[value for _, value in available],
            width=0.6,
            brush=(70, 125, 170),
        )
        plot_item.addItem(bars)
        plot_item.getAxis("bottom").setTicks(
            [[(index, label) for index, (label, _) in enumerate(available)]]
        )
        plot_item.setTitle("Persisted Reports by Category")
        plot_item.setXRange(-0.6, len(available) - 0.4, padding=0)

    def _populate_status_chart(self, summary: dict[str, Any]) -> None:
        plot_item = self.status_chart.getPlotItem()
        plot_item.clear()

        statuses = summary.get("analysis_status_counts")

        if not isinstance(statuses, dict) or not statuses:
            plot_item.setTitle("Analysis status counts are not available")
            plot_item.getAxis("bottom").setTicks([[]])
            return

        available = [
            (name, value)
            for name, value in sorted(statuses.items())
            if (
                isinstance(name, str)
                and name.strip()
                and self._is_non_negative_integer(value)
            )
        ]

        if not available:
            plot_item.setTitle("Analysis status counts are not available")
            plot_item.getAxis("bottom").setTicks([[]])
            return

        bars = pg.BarGraphItem(
            x=list(range(len(available))),
            height=[value for _, value in available],
            width=0.6,
            brush=(170, 125, 75),
        )
        plot_item.addItem(bars)
        plot_item.getAxis("bottom").setTicks(
            [[(index, name) for index, (name, _) in enumerate(available)]]
        )
        plot_item.setTitle("Persisted Analysis Status Counts")
        plot_item.setXRange(-0.6, len(available) - 0.4, padding=0)

    def _populate_report_table(self) -> None:
        self.report_table.setRowCount(len(self._report_rows))

        for row_index, report in enumerate(self._report_rows):
            values = (
                report.get("sol_number", "") or "Not available",
                report.get("product_code", "") or "Not available",
                report.get("csv_file", "") or "Not available",
                report.get("field_name", "") or "Not available",
                report.get("field_type", "") or "Not available",
                report.get("analysis_status", "") or "Not available",
                self._format_report_value(report.get("total_rows")),
                self._format_report_value(report.get("missing_count")),
                self._format_report_value(
                    report.get("below_valid_minimum")
                ),
                self._format_report_value(
                    report.get("above_valid_maximum")
                ),
            )

            for column_index, value in enumerate(values):
                self.report_table.setItem(
                    row_index,
                    column_index,
                    QTableWidgetItem(value),
                )

        self.report_table.resizeColumnsToContents()

    @staticmethod
    def _format_report_value(value: Any) -> str:
        if value is None or str(value).strip() == "":
            return "Not available"

        try:
            number = int(str(value))
        except (TypeError, ValueError, OverflowError):
            return "Not available"

        if number < 0:
            return "Not available"

        return f"{number:,}"

    def _clear_summary_display(self) -> None:
        self.report_rows_label.setText("Report Rows: Not available")
        self.analysed_fields_label.setText(
            "Analysed Field Reports: Not available"
        )
        self.quality_candidates_label.setText(
            "Quality Candidates: Not available"
        )
        self.range_checks_label.setText("Range Checks: Not available")
        self.below_minimum_label.setText("Below Minimum: Not available")
        self.above_maximum_label.setText("Above Maximum: Not available")

        self.category_chart.getPlotItem().clear()
        self.status_chart.getPlotItem().clear()

    def _show_unavailable(self, message: str) -> None:
        self.status_label.setText(message)
