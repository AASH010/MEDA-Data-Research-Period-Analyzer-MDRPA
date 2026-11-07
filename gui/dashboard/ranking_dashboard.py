
"""Read-only visualization of persisted MEDA candidate period rankings."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

import pyqtgraph as pg
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


__all__ = ["RankingDashboard"]


class RankingDashboard(QWidget):
    """Display persisted candidate-period rankings without recalculation."""

    RANKING_SOURCE_COLUMNS = (
        "rank",
        "comparison_group",
        "window_start_sol",
        "window_end_sol",
        "window_label",
        "ranking_status",
        "is_partial_window",
        "exploratory_score",
        "available_metrics",
        "metrics_used",
        "total_sols",
        "file_availability_score",
        "data_integrity_score",
        "quality_indicators_score",
        "synchronization_score",
        "file_availability_sols",
        "data_integrity_sols",
        "quality_indicators_sols",
        "synchronization_sols",
        "reasons",
    )

    TABLE_COLUMNS = (
        "Rank",
        "Comparison Group",
        "Candidate Window",
        "Status",
        "Exploratory Score",
        "Available Metrics",
        "Metrics Used",
        "Total SOLs",
        "File Availability",
        "Data Integrity",
        "Quality Indicators",
        "Synchronization",
    )

    METRIC_FIELDS = (
        ("file_availability_score", "File Availability"),
        ("data_integrity_score", "Data Integrity"),
        ("quality_indicators_score", "Quality Indicators"),
        ("synchronization_score", "Synchronization"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setObjectName("ranking_dashboard")

        self._summary: dict[str, Any] | None = None
        self._summary_path: Path | None = None
        self._ranking_report_path: Path | None = None
        self._ranking_rows: list[dict[str, str]] = []

        self._build_ui()
        self._show_unavailable(
            "Period ranking summary is not available."
        )

    @property
    def summary(self) -> dict[str, Any] | None:
        """Return the currently displayed ranking summary."""
        return self._summary

    @property
    def summary_path(self) -> Path | None:
        return self._summary_path

    @property
    def ranking_report_path(self) -> Path | None:
        return self._ranking_report_path

    @property
    def ranking_rows(self) -> list[dict[str, str]]:
        """Return a copy of the loaded ranking report rows."""
        return list(self._ranking_rows)

    def reset(self) -> None:
        """Clear all Run-specific data and restore unavailable states."""
        self._summary_path = None
        self._ranking_report_path = None
        self._ranking_rows = []

        self._show_unavailable(
            "Period ranking summary is not available."
        )

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.status_label = QLabel(self)
        self.status_label.setObjectName("ranking_status")
        self.status_label.setWordWrap(True)

        metrics_group = QGroupBox("Candidate Ranking Overview", self)
        metrics_group.setObjectName("ranking_metrics_group")
        metrics_layout = QGridLayout(metrics_group)

        self.total_windows_label = self._make_metric(
            "Candidate Windows: Not available",
            "ranking_total_windows",
        )
        self.rankable_windows_label = self._make_metric(
            "Rankable Windows: Not available",
            "ranking_rankable_windows",
        )
        self.unrankable_windows_label = self._make_metric(
            "Unrankable Windows: Not available",
            "ranking_unrankable_windows",
        )
        self.comparison_groups_label = self._make_metric(
            "Comparison Groups: Not available",
            "ranking_comparison_groups",
        )
        self.sol_range_label = self._make_metric(
            "SOL Range: Not available",
            "ranking_sol_range",
        )
        self.window_size_label = self._make_metric(
            "Window Size: Not available",
            "ranking_window_size",
        )

        metrics = (
            self.total_windows_label,
            self.rankable_windows_label,
            self.unrankable_windows_label,
            self.comparison_groups_label,
            self.sol_range_label,
            self.window_size_label,
        )

        for index, label in enumerate(metrics):
            metrics_layout.addWidget(label, index // 3, index % 3)

        score_group = QGroupBox(
            "Exploratory Scores — Within Comparison Groups",
            self,
        )
        score_group.setObjectName("ranking_score_group")
        score_layout = QVBoxLayout(score_group)

        self.score_chart = pg.PlotWidget(score_group)
        self.score_chart.setObjectName("ranking_score_chart")
        self.score_chart.setBackground(None)
        self.score_chart.setLabel("left", "Exploratory Score", units="/100")
        self.score_chart.setLabel("bottom", "Comparison Group / Window")
        self.score_chart.setYRange(0, 100, padding=0)
        self.score_chart.showGrid(x=True, y=True, alpha=0.2)
        self.score_chart.setMinimumHeight(260)

        score_layout.addWidget(self.score_chart)

        status_group = QGroupBox("Candidate Window Statuses", self)
        status_group.setObjectName("ranking_status_group")
        status_layout = QVBoxLayout(status_group)

        self.status_chart = pg.PlotWidget(status_group)
        self.status_chart.setObjectName("ranking_status_chart")
        self.status_chart.setBackground(None)
        self.status_chart.setLabel("left", "Window Count")
        self.status_chart.setLabel("bottom", "Ranking Status")
        self.status_chart.showGrid(x=True, y=True, alpha=0.2)
        self.status_chart.setMinimumHeight(220)

        status_layout.addWidget(self.status_chart)

        details_group = QGroupBox(
            "Persisted Candidate Ranking Details",
            self,
        )
        details_group.setObjectName("ranking_details_group")
        details_layout = QVBoxLayout(details_group)

        self.report_status_label = QLabel(
            "Period ranking report is not available.",
            details_group,
        )
        self.report_status_label.setObjectName(
            "ranking_report_status"
        )
        self.report_status_label.setWordWrap(True)

        self.ranking_table = self._make_table(
            len(self.TABLE_COLUMNS),
            self.TABLE_COLUMNS,
            "ranking_report_table",
            details_group,
        )

        details_layout.addWidget(self.report_status_label)
        details_layout.addWidget(self.ranking_table)

        summary_group = QGroupBox(
            "Ranking Configuration and Limitations",
            self,
        )
        summary_group.setObjectName("ranking_summary_group")
        summary_layout = QVBoxLayout(summary_group)

        self.summary_text = QPlainTextEdit(summary_group)
        self.summary_text.setObjectName("ranking_summary_text")
        self.summary_text.setReadOnly(True)
        self.summary_text.setPlaceholderText(
            "Load a ranking summary to inspect its configuration."
        )

        summary_layout.addWidget(self.summary_text)

        layout.addWidget(self.status_label)
        layout.addWidget(metrics_group)
        layout.addWidget(score_group)
        layout.addWidget(status_group)
        layout.addWidget(details_group, 2)
        layout.addWidget(summary_group, 1)

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
    def _validate_summary(cls, summary: Any) -> tuple[bool, str]:
        if not isinstance(summary, dict):
            return False, "Period ranking summary must be a JSON object."

        if summary.get("analyzer") != "MEDA Period Ranker":
            return False, "Period ranking summary has an invalid analyzer identifier."

        if summary.get("ranking_type") != "exploratory_comparative":
            return False, "Period ranking summary has an unsupported ranking type."

        required_counts = (
            "total_candidate_windows",
            "rankable_windows",
            "unrankable_windows",
            "comparison_group_count",
            "window_size",
            "min_metrics",
        )

        for key in required_counts:
            value = summary.get(key)

            if not cls._is_non_negative_integer(value):
                return False, f"Period ranking summary has an invalid {key} value."

        if summary["window_size"] < 1:
            return False, "Period ranking summary has an invalid window_size value."

        if (
            summary["rankable_windows"]
            + summary["unrankable_windows"]
            != summary["total_candidate_windows"]
        ):
            return False, "Period ranking summary has inconsistent window counts."

        sol_range = summary.get("sol_range")

        if not isinstance(sol_range, dict):
            return False, "Period ranking summary has an invalid SOL range."

        start = sol_range.get("start")
        end = sol_range.get("end")

        if (
            not cls._is_non_negative_integer(start)
            or not cls._is_non_negative_integer(end)
            or start > end
        ):
            return False, "Period ranking summary has an invalid SOL range."

        weights = summary.get("ranking_weights")

        if not isinstance(weights, dict):
            return False, "Period ranking summary has invalid ranking weights."

        for name, value in weights.items():
            if (
                not isinstance(name, str)
                or isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                return False, "Period ranking summary has invalid ranking weights."

        limitations = summary.get("important_limitations")

        if not isinstance(limitations, list) or not all(
            isinstance(item, str) for item in limitations
        ):
            return False, "Period ranking summary has invalid limitations."

        return True, ""

    @staticmethod
    def _parse_number(value: Any) -> float | None:
        if value is None or str(value).strip() == "":
            return None

        try:
            number = float(str(value).strip())
        except (TypeError, ValueError, OverflowError):
            return None

        if not math.isfinite(number):
            return None

        return number

    @classmethod
    def _parse_score(cls, value: Any) -> float | None:
        number = cls._parse_number(value)

        if number is None or not 0 <= number <= 100:
            return None

        return number

    @classmethod
    def _parse_count(cls, value: Any) -> int | None:
        number = cls._parse_number(value)

        if number is None or number < 0 or not number.is_integer():
            return None

        return int(number)

    @classmethod
    def _format_count(cls, value: Any) -> str:
        if not cls._is_non_negative_integer(value):
            return "Not available"

        return f"{value:,}"

    @classmethod
    def _format_score(cls, value: Any) -> str:
        number = cls._parse_score(value)

        if number is None:
            return "Not available"

        return f"{number:.3f}"

    @staticmethod
    def _format_text(value: Any) -> str:
        text = str(value or "").strip()
        return text if text else "Not available"

    def _show_unavailable(self, message: str) -> None:
        self.status_label.setText(message)
        self._clear_summary_display()
        self._ranking_rows = []
        self._populate_ranking_table()
        self._populate_score_chart()
        self._populate_status_chart()
        self.report_status_label.setText(
            "Period ranking report is not available."
        )

    def _clear_summary_display(self) -> None:
        self._summary = None

        labels = (
            (self.total_windows_label, "Candidate Windows"),
            (self.rankable_windows_label, "Rankable Windows"),
            (self.unrankable_windows_label, "Unrankable Windows"),
            (self.comparison_groups_label, "Comparison Groups"),
            (self.sol_range_label, "SOL Range"),
            (self.window_size_label, "Window Size"),
        )

        for label, title in labels:
            label.setText(f"{title}: Not available")

        self.summary_text.clear()

    def set_summary(self, summary: dict[str, Any] | None) -> bool:
        """Display a previously persisted ranking summary."""
        if summary is None:
            self._clear_summary_display()
            self._show_unavailable(
                "Period ranking summary is not available."
            )
            return False

        valid, message = self._validate_summary(summary)

        if not valid:
            self._clear_summary_display()
            self._show_unavailable(message)
            return False

        self._summary = summary
        self._display_summary(summary)
        return True

    def load_summary_file(self, path: str | Path) -> bool:
        """Load the persisted period ranking JSON."""
        summary_path = Path(path)
        self._summary_path = summary_path

        if not summary_path.is_file():
            self.set_summary(None)
            self._show_unavailable(
                f"Period ranking summary is not available: {summary_path}"
            )
            return False

        try:
            with summary_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self.set_summary(None)
            self._show_unavailable(
                "Unable to read period ranking summary: "
                f"{type(exc).__name__}: {exc}"
            )
            return False

        return self.set_summary(payload)

    def _display_summary(self, summary: dict[str, Any]) -> None:
        sol_range = summary["sol_range"]

        self.total_windows_label.setText(
            "Candidate Windows: "
            + self._format_count(summary["total_candidate_windows"])
        )
        self.rankable_windows_label.setText(
            "Rankable Windows: "
            + self._format_count(summary["rankable_windows"])
        )
        self.unrankable_windows_label.setText(
            "Unrankable Windows: "
            + self._format_count(summary["unrankable_windows"])
        )
        self.comparison_groups_label.setText(
            "Comparison Groups: "
            + self._format_count(summary["comparison_group_count"])
        )
        self.sol_range_label.setText(
            f"SOL Range: {sol_range['start']} – {sol_range['end']}"
        )
        self.window_size_label.setText(
            f"Window Size: {summary['window_size']} SOLs"
        )

        details = [
            "Ranking Type: Exploratory comparative ranking",
            (
                "SOL Range: "
                f"{sol_range['start']} – {sol_range['end']}"
            ),
            f"Window Size: {summary['window_size']}",
            f"Minimum Metrics: {summary['min_metrics']}",
            "",
            "Ranking Weights:",
        ]

        weights = summary.get("ranking_weights", {})

        for name, value in weights.items():
            details.append(f"- {name}: {value}")

        details.extend(("", "Best Ranked Window by Comparison Group:"))

        best_by_group = summary.get(
            "best_ranked_windows_by_comparison_group",
            {},
        )

        if isinstance(best_by_group, dict) and best_by_group:
            for group_name, row in best_by_group.items():
                if not isinstance(row, dict):
                    details.append(f"- {group_name}: Not available")
                    continue

                details.append(
                    "- "
                    f"{group_name}: "
                    f"{self._format_text(row.get('window_label'))}; "
                    f"score {self._format_score(row.get('exploratory_score'))}"
                )
        else:
            details.append("- No best-ranked candidate is available.")

        details.extend(("", "Important Limitations:"))

        for limitation in summary.get("important_limitations", []):
            details.append(f"- {limitation}")

        self.summary_text.setPlainText("\n".join(details))

        self.status_label.setText(
            "Persisted ranking summary loaded. "
            "Scores and ranks are displayed as generated by the analyzer."
        )

    def load_ranking_report(self, path: str | Path) -> bool:
        """Load the persisted candidate-period ranking CSV."""
        report_path = Path(path)
        self._ranking_report_path = report_path

        rows, error = self._read_csv_report(
            report_path,
            self.RANKING_SOURCE_COLUMNS,
        )

        if error:
            self._ranking_rows = []
            self._populate_ranking_table()
            self._populate_score_chart()
            self._populate_status_chart()
            self.report_status_label.setText(error)
            return False

        self._ranking_rows = rows
        self._populate_ranking_table()
        self._populate_score_chart()
        self._populate_status_chart()

        self.report_status_label.setText(
            f"{len(rows):,} persisted candidate window row(s) loaded."
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
        ranking_report_path: str | Path | None = None,
    ) -> bool:
        """Load the summary and optional persisted ranking CSV."""
        summary_loaded = self.load_summary_file(summary_path)

        if ranking_report_path is None:
            self._ranking_rows = []
            self._populate_ranking_table()
            self._populate_score_chart()
            self._populate_status_chart()
            self.report_status_label.setText(
                "Period ranking report path was not supplied."
            )
            return summary_loaded

        report_loaded = self.load_ranking_report(ranking_report_path)
        return summary_loaded and report_loaded

    def _populate_ranking_table(self) -> None:
        self.ranking_table.setRowCount(len(self._ranking_rows))

        for row_index, row in enumerate(self._ranking_rows):
            start = self._parse_count(row.get("window_start_sol"))
            end = self._parse_count(row.get("window_end_sol"))

            window_label = self._format_text(row.get("window_label"))

            if window_label == "Not available" and start is not None and end is not None:
                window_label = f"Sol {start}-{end}"

            rank = self._parse_count(row.get("rank"))
            available_metrics = self._parse_count(
                row.get("available_metrics")
            )
            total_sols = self._parse_count(row.get("total_sols"))

            values = (
                str(rank) if rank is not None else "Not ranked",
                self._format_text(row.get("comparison_group")),
                window_label,
                self._format_text(row.get("ranking_status")),
                self._format_score(row.get("exploratory_score")),
                (
                    str(available_metrics)
                    if available_metrics is not None
                    else "Not available"
                ),
                self._format_text(row.get("metrics_used")),
                (
                    str(total_sols)
                    if total_sols is not None
                    else "Not available"
                ),
                self._format_score(row.get("file_availability_score")),
                self._format_score(row.get("data_integrity_score")),
                self._format_score(row.get("quality_indicators_score")),
                self._format_score(row.get("synchronization_score")),
            )

            for column, value in enumerate(values):
                self.ranking_table.setItem(
                    row_index,
                    column,
                    QTableWidgetItem(value),
                )

    def _populate_score_chart(self) -> None:
        plot = self.score_chart.getPlotItem()
        plot.clear()

        rankable_rows = []

        for row in self._ranking_rows:
            if row.get("ranking_status") != "rankable":
                continue

            score = self._parse_score(row.get("exploratory_score"))

            if score is None:
                continue

            group = self._format_text(row.get("comparison_group"))
            window = self._format_text(row.get("window_label"))

            rankable_rows.append((group, window, score))

        if not rankable_rows:
            plot.setTitle("No rankable persisted scores are available")
            plot.getAxis("bottom").setTicks([[]])
            return

        labels = [
            f"{group} | {window}"
            for group, window, _score in rankable_rows
        ]
        scores = [score for _group, _window, score in rankable_rows]

        plot.setTitle(
            "Persisted Scores — Different Comparison Groups Are Not Comparable"
        )
        plot.getAxis("bottom").setTicks(
            [list(enumerate(labels))]
        )

        plot.addItem(
            pg.BarGraphItem(
                x=list(range(len(scores))),
                height=scores,
                width=0.65,
            )
        )

    def _populate_status_chart(self) -> None:
        plot = self.status_chart.getPlotItem()
        plot.clear()

        counts: dict[str, int] = {}

        for row in self._ranking_rows:
            status = self._format_text(row.get("ranking_status"))
            counts[status] = counts.get(status, 0) + 1

        if not counts:
            plot.setTitle("Ranking status data is not available")
            plot.getAxis("bottom").setTicks([[]])
            return

        labels = list(counts)
        values = [counts[label] for label in labels]

        plot.setTitle("Persisted Candidate Window Status Counts")
        plot.getAxis("bottom").setTicks(
            [list(enumerate(labels))]
        )
        plot.addItem(
            pg.BarGraphItem(
                x=list(range(len(values))),
                height=values,
                width=0.65,
            )
        )
