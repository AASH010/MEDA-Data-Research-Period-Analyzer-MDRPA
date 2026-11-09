"""Read-only visualization of persisted MEDA synchronization reports."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any
from gui.styles.classic_theme import apply_dashboard_theme
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


__all__ = ["SynchronizationDashboard"]


class SynchronizationDashboard(QWidget):
    """Display persisted synchronization artifacts without rerunning analysis."""

    FILE_COLUMNS = (
        "SOL",
        "Product",
        "CSV File",
        "Time Field",
        "Time Axis",
        "Analysis Status",
        "Rows",
        "Parsed",
        "Missing",
        "Invalid",
        "Duplicates",
        "Out of Order",
    )

    FILE_SOURCE_COLUMNS = (
        "sol_number",
        "product_code",
        "csv_file",
        "selected_time_field",
        "time_kind",
        "analysis_status",
        "total_rows",
        "parsed_timestamps",
        "missing_timestamps",
        "invalid_timestamps",
        "duplicate_timestamps",
        "out_of_order_timestamps",
    )

    PAIR_COLUMNS = (
        "SOL",
        "Product 1",
        "File 1",
        "Product 2",
        "File 2",
        "Comparison Status",
        "Time Axis",
        "Matched",
        "First Match %",
        "Second Match %",
        "Sparser Match %",
    )

    PAIR_SOURCE_COLUMNS = (
        "sol_number",
        "product_1",
        "file_1",
        "product_2",
        "file_2",
        "comparison_status",
        "time_kind",
        "matched_timestamps",
        "match_rate_first_percent",
        "match_rate_second_percent",
        "match_rate_sparser_percent",
    )

    FILE_STATUS_LABELS = {
        "analysed": "Analysed",
        "file_not_found_or_ambiguous": "File unavailable/ambiguous",
        "missing_inventory_filename": "Missing filename",
        "metadata_not_found": "Metadata not found",
        "ambiguous_metadata_path": "Ambiguous metadata",
        "empty_file": "Empty file",
        "file_stat_error": "File access error",
    }

    PAIR_STATUS_LABELS = {
        "analysed": "Analysed",
        "incompatible_time_axes": "Incompatible time axes",
        "no_temporal_overlap": "No temporal overlap",
        "empty_series": "Empty series",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setObjectName("synchronization_dashboard")

        self._summary: dict[str, Any] | None = None
        self._summary_path: Path | None = None
        self._file_report_path: Path | None = None
        self._pair_report_path: Path | None = None
        self._file_rows: list[dict[str, str]] = []
        self._pair_rows: list[dict[str, str]] = []

        self._build_ui()
        apply_dashboard_theme(self)
        self._show_unavailable(
            "Synchronization summary is not available."
        )

    @property
    def summary(self) -> dict[str, Any] | None:
        return self._summary

    @property
    def summary_path(self) -> Path | None:
        return self._summary_path

    @property
    def file_report_path(self) -> Path | None:
        return self._file_report_path

    @property
    def pair_report_path(self) -> Path | None:
        return self._pair_report_path

    @property
    def file_rows(self) -> list[dict[str, str]]:
        return list(self._file_rows)

    @property
    def pair_rows(self) -> list[dict[str, str]]:
        return list(self._pair_rows)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.status_label = QLabel(self)
        self.status_label.setObjectName("synchronization_status")
        self.status_label.setWordWrap(True)

        metrics_group = QGroupBox("Synchronization Overview", self)
        metrics_group.setObjectName("synchronization_metrics_group")
        metrics_layout = QGridLayout(metrics_group)

        self.total_files_label = self._make_metric(
            "Total Files: Not available",
            "synchronization_total_files",
        )
        self.analysed_files_label = self._make_metric(
            "Analysed Files: Not available",
            "synchronization_analysed_files",
        )
        self.unanalysed_files_label = self._make_metric(
            "Unanalysed Files: Not available",
            "synchronization_unanalysed_files",
        )
        self.total_pairs_label = self._make_metric(
            "Product Pairs: Not available",
            "synchronization_total_pairs",
        )
        self.analysed_pairs_label = self._make_metric(
            "Analysed Pairs: Not available",
            "synchronization_analysed_pairs",
        )
        self.pairs_with_matches_label = self._make_metric(
            "Pairs With Matches: Not available",
            "synchronization_pairs_with_matches",
        )
        self.tolerance_label = self._make_metric(
            "Tolerance: Not available",
            "synchronization_tolerance",
        )

        metrics = (
            self.total_files_label,
            self.analysed_files_label,
            self.unanalysed_files_label,
            self.total_pairs_label,
            self.analysed_pairs_label,
            self.pairs_with_matches_label,
            self.tolerance_label,
        )

        for index, label in enumerate(metrics):
            metrics_layout.addWidget(label, index // 3, index % 3)

        charts_layout = QVBoxLayout()

        file_group = QGroupBox("File Analysis Statuses", self)
        file_group.setObjectName("synchronization_file_chart_group")
        file_layout = QVBoxLayout(file_group)

        self.file_status_chart = pg.PlotWidget(file_group)
        self.file_status_chart.setObjectName(
            "synchronization_file_status_chart"
        )
        self.file_status_chart.setBackground(None)
        self.file_status_chart.setLabel("left", "File Count")
        self.file_status_chart.setLabel("bottom", "Analysis Status")
        self.file_status_chart.showGrid(x=True, y=True, alpha=0.2)
        self.file_status_chart.setMinimumHeight(360)
        file_layout.addWidget(self.file_status_chart)

        pair_group = QGroupBox("Product Comparison Statuses", self)
        pair_group.setObjectName("synchronization_pair_chart_group")
        pair_layout = QVBoxLayout(pair_group)

        self.pair_status_chart = pg.PlotWidget(pair_group)
        self.pair_status_chart.setObjectName(
            "synchronization_pair_status_chart"
        )
        self.pair_status_chart.setBackground(None)
        self.pair_status_chart.setLabel("left", "Pair Count")
        self.pair_status_chart.setLabel("bottom", "Comparison Status")
        self.pair_status_chart.showGrid(x=True, y=True, alpha=0.2)
        self.pair_status_chart.setMinimumHeight(360)
        pair_layout.addWidget(self.pair_status_chart)

        charts_layout.addWidget(file_group)
        charts_layout.addWidget(pair_group)

        rates_group = QGroupBox("Persisted Product Match Rates", self)
        rates_group.setObjectName("synchronization_match_rates_group")
        rates_layout = QVBoxLayout(rates_group)

        self.match_rate_chart = pg.PlotWidget(rates_group)
        self.match_rate_chart.setObjectName(
            "synchronization_match_rate_chart"
        )
        self.match_rate_chart.setBackground(None)
        self.match_rate_chart.setLabel("left", "Match Rate", units="%")
        self.match_rate_chart.setLabel("bottom", "Product Pair")
        self.match_rate_chart.setYRange(0, 100, padding=0)
        self.match_rate_chart.showGrid(x=True, y=True, alpha=0.2)
        self.match_rate_chart.setMinimumHeight(360)
        rates_layout.addWidget(self.match_rate_chart)

        file_table_group = QGroupBox("File Analysis Details", self)
        file_table_group.setObjectName(
            "synchronization_file_details_group"
        )
        file_table_layout = QVBoxLayout(file_table_group)

        self.file_report_status_label = QLabel(
            "File report is not available.",
            file_table_group,
        )
        self.file_report_status_label.setObjectName(
            "synchronization_file_report_status"
        )
        self.file_report_status_label.setWordWrap(True)

        self.file_table = self._make_table(
            len(self.FILE_COLUMNS),
            self.FILE_COLUMNS,
            "synchronization_file_table",
            file_table_group,
        )

        file_table_layout.addWidget(self.file_report_status_label)
        file_table_layout.addWidget(self.file_table)

        pair_table_group = QGroupBox("Product Pair Details", self)
        pair_table_group.setObjectName(
            "synchronization_pair_details_group"
        )
        pair_table_layout = QVBoxLayout(pair_table_group)

        self.pair_report_status_label = QLabel(
            "Pair report is not available.",
            pair_table_group,
        )
        self.pair_report_status_label.setObjectName(
            "synchronization_pair_report_status"
        )
        self.pair_report_status_label.setWordWrap(True)

        self.pair_table = self._make_table(
            len(self.PAIR_COLUMNS),
            self.PAIR_COLUMNS,
            "synchronization_pair_table",
            pair_table_group,
        )

        pair_table_layout.addWidget(self.pair_report_status_label)
        pair_table_layout.addWidget(self.pair_table)

        layout.addWidget(self.status_label)
        layout.addWidget(metrics_group)
        layout.addLayout(charts_layout)
        layout.addWidget(rates_group)
        layout.addWidget(file_table_group, 1)
        layout.addWidget(pair_table_group, 1)

    @staticmethod
    def _make_metric(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        label.setWordWrap(True)
        return label

    @staticmethod
    def _make_table(
        columns: int,
        headers: tuple[str, ...],
        object_name: str,
        parent: QWidget,
    ) -> QTableWidget:
        table = QTableWidget(0, columns, parent)
        table.setObjectName(object_name)
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    @staticmethod
    def _is_non_negative_integer(value: Any) -> bool:
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        )

    @classmethod
    def _validate_count_mapping(
        cls,
        value: Any,
        field_name: str,
    ) -> tuple[bool, str]:
        if not isinstance(value, dict):
            return False, f"Synchronization summary has an invalid {field_name}."

        for key, count in value.items():
            if not isinstance(key, str) or not key.strip():
                return False, f"Synchronization summary has an invalid {field_name} key."

            if not cls._is_non_negative_integer(count):
                return False, f"Synchronization summary has an invalid {field_name} count."

        return True, ""

    @classmethod
    def _validate_summary(cls, summary: Any) -> tuple[bool, str]:
        if not isinstance(summary, dict):
            return False, "Synchronization summary must be a JSON object."

        if summary.get("analyzer") != "MEDA Synchronization Analyzer":
            return False, "Synchronization summary has an invalid analyzer identifier."

        required_counts = (
            "total_files",
            "analysed_files",
            "unanalysed_files",
            "total_product_pairs",
            "analysed_pairs",
            "pairs_with_matches",
        )

        for key in required_counts:
            if not cls._is_non_negative_integer(summary.get(key)):
                return False, f"Synchronization summary has an invalid {key} value."

        for key in (
            "file_status_counts",
            "mapping_status_counts",
            "pair_status_counts",
        ):
            valid, message = cls._validate_count_mapping(
                summary.get(key),
                key,
            )
            if not valid:
                return False, message

        tolerance = summary.get("tolerance")
        if (
            isinstance(tolerance, bool)
            or not isinstance(tolerance, (int, float))
            or not math.isfinite(tolerance)
            or tolerance < 0
        ):
            return False, "Synchronization summary has an invalid tolerance."

        return True, ""

    @staticmethod
    def _format_count(value: Any) -> str:
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        ):
            return f"{value:,}"

        return "Not available"

    @staticmethod
    def _format_tolerance(value: Any) -> str:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            return "Not available"

        return str(value)

    @staticmethod
    def _parse_csv_number(value: Any) -> int | None:
        if value is None or str(value).strip() == "":
            return None

        try:
            number = int(str(value).strip())
        except (TypeError, ValueError, OverflowError):
            return None

        return number if number >= 0 else None

    @staticmethod
    def _parse_percentage(value: Any) -> float | None:
        if value is None or str(value).strip() == "":
            return None

        try:
            number = float(str(value).strip())
        except (TypeError, ValueError, OverflowError):
            return None

        if not math.isfinite(number) or not 0 <= number <= 100:
            return None

        return number

    @staticmethod
    def _format_percentage(value: Any) -> str:
        number = SynchronizationDashboard._parse_percentage(value)

        if number is None:
            return "Not available"

        return f"{number:.2f}%"

    @staticmethod
    def _format_text(value: Any) -> str:
        text = str(value or "").strip()
        return text if text else "Not available"

    def reset(self) -> None:
        """Clear all Run-specific data and restore unavailable states."""
        self._summary = None
        self._summary_path = None
        self._file_report_path = None
        self._pair_report_path = None
        self._file_rows = []
        self._pair_rows = []

        self._clear_summary_display()
        self._populate_file_table()
        self._populate_pair_table()
        self._populate_match_rate_chart()

        self.file_report_status_label.setText(
            "File report is not available."
        )
        self.pair_report_status_label.setText(
            "Pair report is not available."
        )

        self.file_status_chart.setTitle(
            "File status counts are not available"
        )
        self.pair_status_chart.setTitle(
            "Pair status counts are not available"
        )
        self.match_rate_chart.setTitle(
            "Persisted match rates are not available"
        )

        self._show_unavailable(
            "Synchronization summary is not available."
        )

    def set_summary(self, summary: dict[str, Any] | None) -> bool:
        """Display a persisted synchronization summary."""
        if summary is None:
            self._summary = None
            self._clear_summary_display()
            self._show_unavailable(
                "Synchronization summary is not available."
            )
            return False

        valid, message = self._validate_summary(summary)

        if not valid:
            self._summary = None
            self._clear_summary_display()
            self._show_unavailable(message)
            return False

        self._summary = summary
        self._display_summary(summary)
        return True

    def load_summary_file(self, path: str | Path) -> bool:
        """Load the persisted synchronization summary JSON."""
        summary_path = Path(path)
        self._summary_path = summary_path

        if not summary_path.is_file():
            self.set_summary(None)
            self._show_unavailable(
                f"Synchronization summary is not available: {summary_path}"
            )
            return False

        try:
            with summary_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self.set_summary(None)
            self._show_unavailable(
                "Unable to read synchronization summary: "
                f"{type(exc).__name__}: {exc}"
            )
            return False

        return self.set_summary(payload)

    def load_file_report(self, path: str | Path) -> bool:
        """Load the persisted per-file synchronization CSV."""
        report_path = Path(path)
        self._file_report_path = report_path

        rows, error = self._read_csv_report(
            report_path,
            self.FILE_SOURCE_COLUMNS,
        )

        if error:
            self._file_rows = []
            self._populate_file_table()
            self.file_report_status_label.setText(error)
            return False

        self._file_rows = rows
        self._populate_file_table()
        self.file_report_status_label.setText(
            f"{len(rows):,} persisted file report row(s) loaded."
        )
        return True

    def load_pair_report(self, path: str | Path) -> bool:
        """Load the persisted product-pair synchronization CSV."""
        report_path = Path(path)
        self._pair_report_path = report_path

        rows, error = self._read_csv_report(
            report_path,
            self.PAIR_SOURCE_COLUMNS,
        )

        if error:
            self._pair_rows = []
            self._populate_pair_table()
            self._populate_match_rate_chart()
            self.pair_report_status_label.setText(error)
            return False

        self._pair_rows = rows
        self._populate_pair_table()
        self._populate_match_rate_chart()
        self.pair_report_status_label.setText(
            f"{len(rows):,} persisted product-pair row(s) loaded."
        )
        return True

    @staticmethod
    def _read_csv_report(
        path: Path,
        required_columns: tuple[str, ...],
    ) -> tuple[list[dict[str, str]], str | None]:
        if not path.is_file():
            return [], f"Report is not available: {path}"

        try:
            with path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as file:
                reader = csv.DictReader(file)
                fieldnames = reader.fieldnames or []

                missing = [
                    column
                    for column in required_columns
                    if column not in fieldnames
                ]

                if missing:
                    return (
                        [],
                        "Report has an incompatible schema. Missing columns: "
                        + ", ".join(missing),
                    )

                return list(reader), None

        except (OSError, UnicodeError, csv.Error) as exc:
            return (
                [],
                "Unable to read report: "
                f"{type(exc).__name__}: {exc}",
            )

    def load_artifacts(
        self,
        summary_path: str | Path,
        file_report_path: str | Path | None = None,
        pair_report_path: str | Path | None = None,
    ) -> bool:
        """Load the summary and optional persisted CSV reports."""
        summary_loaded = self.load_summary_file(summary_path)

        if file_report_path is None:
            self._file_rows = []
            self._populate_file_table()
            self.file_report_status_label.setText(
                "File report is not available."
            )
        else:
            self.load_file_report(file_report_path)

        if pair_report_path is None:
            self._pair_rows = []
            self._populate_pair_table()
            self._populate_match_rate_chart()
            self.pair_report_status_label.setText(
                "Pair report is not available."
            )
        else:
            self.load_pair_report(pair_report_path)

        return summary_loaded

    def _display_summary(self, summary: dict[str, Any]) -> None:
        self.total_files_label.setText(
            "Total Files: " + self._format_count(summary.get("total_files"))
        )
        self.analysed_files_label.setText(
            "Analysed Files: " + self._format_count(summary.get("analysed_files"))
        )
        self.unanalysed_files_label.setText(
            "Unanalysed Files: " + self._format_count(summary.get("unanalysed_files"))
        )
        self.total_pairs_label.setText(
            "Product Pairs: " + self._format_count(summary.get("total_product_pairs"))
        )
        self.analysed_pairs_label.setText(
            "Analysed Pairs: " + self._format_count(summary.get("analysed_pairs"))
        )
        self.pairs_with_matches_label.setText(
            "Pairs With Matches: " + self._format_count(summary.get("pairs_with_matches"))
        )
        self.tolerance_label.setText(
            "Tolerance: " + self._format_tolerance(summary.get("tolerance"))
        )

        self._populate_status_chart(
            self.file_status_chart,
            summary.get("file_status_counts"),
            "Persisted File Analysis Status Counts",
            self.FILE_STATUS_LABELS,
        )
        self._populate_status_chart(
            self.pair_status_chart,
            summary.get("pair_status_counts"),
            "Persisted Product Pair Comparison Status Counts",
            self.PAIR_STATUS_LABELS,
        )

        self.status_label.setText(
            "Synchronization summary loaded from persisted analyzer output. "
            "No analysis or matching was rerun."
        )

    @staticmethod
    def _populate_status_chart(
        chart: pg.PlotWidget,
        counts: Any,
        title: str,
        labels: dict[str, str],
    ) -> None:
        plot_item = chart.getPlotItem()
        plot_item.clear()

        if not isinstance(counts, dict) or not counts:
            plot_item.setTitle("Status counts are not available")
            plot_item.getAxis("bottom").setTicks([[]])
            return

        available = [
            (labels.get(name, name), count)
            for name, count in sorted(counts.items())
            if (
                isinstance(name, str)
                and name.strip()
                and isinstance(count, int)
                and not isinstance(count, bool)
                and count >= 0
            )
        ]

        if not available:
            plot_item.setTitle("Status counts are not available")
            plot_item.getAxis("bottom").setTicks([[]])
            return

        bars = pg.BarGraphItem(
            x=list(range(len(available))),
            height=[count for _, count in available],
            width=0.6,
            brush=(70, 125, 170),
        )
        plot_item.addItem(bars)
        plot_item.getAxis("bottom").setTicks(
            [[(index, label) for index, (label, _) in enumerate(available)]]
        )
        plot_item.setTitle(title)
        plot_item.setXRange(-0.6, len(available) - 0.4, padding=0)

    def _populate_file_table(self) -> None:
        self.file_table.setRowCount(len(self._file_rows))

        for row_index, report in enumerate(self._file_rows):
            values = (
                self._format_text(report.get("sol_number")),
                self._format_text(report.get("product_code")),
                self._format_text(report.get("csv_file")),
                self._format_text(report.get("selected_time_field")),
                self._format_text(report.get("time_kind")),
                self._format_text(report.get("analysis_status")),
                self._format_csv_count(report.get("total_rows")),
                self._format_csv_count(report.get("parsed_timestamps")),
                self._format_csv_count(report.get("missing_timestamps")),
                self._format_csv_count(report.get("invalid_timestamps")),
                self._format_csv_count(report.get("duplicate_timestamps")),
                self._format_csv_count(report.get("out_of_order_timestamps")),
            )

            self._set_table_row(self.file_table, row_index, values)

        self.file_table.resizeColumnsToContents()

    def _populate_pair_table(self) -> None:
        self.pair_table.setRowCount(len(self._pair_rows))

        for row_index, report in enumerate(self._pair_rows):
            values = (
                self._format_text(report.get("sol_number")),
                self._format_text(report.get("product_1")),
                self._format_text(report.get("file_1")),
                self._format_text(report.get("product_2")),
                self._format_text(report.get("file_2")),
                self._format_text(report.get("comparison_status")),
                self._format_text(report.get("time_kind")),
                self._format_csv_count(report.get("matched_timestamps")),
                self._format_percentage(
                    report.get("match_rate_first_percent")
                ),
                self._format_percentage(
                    report.get("match_rate_second_percent")
                ),
                self._format_percentage(
                    report.get("match_rate_sparser_percent")
                ),
            )

            self._set_table_row(self.pair_table, row_index, values)

        self.pair_table.resizeColumnsToContents()

    @staticmethod
    def _set_table_row(
        table: QTableWidget,
        row_index: int,
        values: tuple[str, ...],
    ) -> None:
        for column_index, value in enumerate(values):
            table.setItem(
                row_index,
                column_index,
                QTableWidgetItem(value),
            )

    @classmethod
    def _format_csv_count(cls, value: Any) -> str:
        number = cls._parse_csv_number(value)

        if number is None:
            return "Not available"

        return f"{number:,}"

    def _populate_match_rate_chart(self) -> None:
        plot_item = self.match_rate_chart.getPlotItem()
        plot_item.clear()

        available: list[tuple[str, float, float, float]] = []

        for report in self._pair_rows:
            first = self._parse_percentage(
                report.get("match_rate_first_percent")
            )
            second = self._parse_percentage(
                report.get("match_rate_second_percent")
            )
            sparser = self._parse_percentage(
                report.get("match_rate_sparser_percent")
            )

            if first is None and second is None and sparser is None:
                continue

            pair_name = (
                f"{self._format_text(report.get('product_1'))} / "
                f"{self._format_text(report.get('product_2'))}"
            )

            available.append((
                pair_name,
                first if first is not None else math.nan,
                second if second is not None else math.nan,
                sparser if sparser is not None else math.nan,
            ))

        if not available:
            plot_item.setTitle("Persisted match rates are not available")
            plot_item.getAxis("bottom").setTicks([[]])
            return

        x_values = list(range(len(available)))
        width = 0.22

        for offset, key, brush in (
            (-width, 1, (70, 125, 170)),
            (0, 2, (170, 125, 75)),
            (width, 3, (90, 150, 105)),
        ):
            heights = [row[key] for row in available]
            valid_positions = [
                (x + offset, height)
                for x, height in zip(x_values, heights)
                if math.isfinite(height)
            ]

            if valid_positions:
                plot_item.addItem(
                    pg.BarGraphItem(
                        x=[position for position, _ in valid_positions],
                        height=[height for _, height in valid_positions],
                        width=width,
                        brush=brush,
                    )
                )

        plot_item.getAxis("bottom").setTicks(
            [[(index, row[0]) for index, row in enumerate(available)]]
        )
        plot_item.setYRange(0, 100, padding=0)
        plot_item.setTitle(
            "Persisted Match Rates: Product 1, Product 2, Sparser Side"
        )
        plot_item.setXRange(-0.6, len(available) - 0.4, padding=0)

    def _clear_summary_display(self) -> None:
        self.total_files_label.setText("Total Files: Not available")
        self.analysed_files_label.setText("Analysed Files: Not available")
        self.unanalysed_files_label.setText("Unanalysed Files: Not available")
        self.total_pairs_label.setText("Product Pairs: Not available")
        self.analysed_pairs_label.setText("Analysed Pairs: Not available")
        self.pairs_with_matches_label.setText(
            "Pairs With Matches: Not available"
        )
        self.tolerance_label.setText("Tolerance: Not available")

        for chart in (
            self.file_status_chart,
            self.pair_status_chart,
            self.match_rate_chart,
        ):
            chart.getPlotItem().clear()

    def _show_unavailable(self, message: str) -> None:
        self.status_label.setText(message)