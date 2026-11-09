
"""Read-only visualization of persisted MEDA coverage summaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from gui.styles.classic_theme import apply_dashboard_theme

import pyqtgraph as pg
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


__all__ = ["CoverageDashboard"]


class CoverageDashboard(QWidget):
    """Display persisted coverage summary data without recomputing analysis."""

    TABLE_COLUMNS = (
        "Product",
        "CSV Files",
        "SOLs With Rows",
        "SOLs Without Rows",
        "Total Rows",
        "Numeric Values",
        "Parsed Timestamps",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setObjectName("coverage_dashboard")

        self._summary: dict[str, Any] | None = None
        self._summary_path: Path | None = None

        self._build_ui()
        apply_dashboard_theme(self)
        self._show_unavailable("Coverage summary is not available.")

    @property
    def summary(self) -> dict[str, Any] | None:
        """Return the currently displayed summary."""
        return self._summary

    @property
    def summary_path(self) -> Path | None:
        """Return the path used by the latest file-loading attempt."""
        return self._summary_path

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.status_label = QLabel(self)
        self.status_label.setObjectName("coverage_status")
        self.status_label.setWordWrap(True)

        metrics_layout = QHBoxLayout()

        self.sol_range_label = QLabel("SOL Range: Not available", self)
        self.sol_range_label.setObjectName("coverage_sol_range")

        self.report_count_label = QLabel(
            "Coverage Reports: Not available",
            self,
        )
        self.report_count_label.setObjectName("coverage_report_count")

        self.product_count_label = QLabel("Products: 0", self)
        self.product_count_label.setObjectName("coverage_product_count")

        metrics_layout.addWidget(self.sol_range_label)
        metrics_layout.addWidget(self.report_count_label)
        metrics_layout.addWidget(self.product_count_label)
        metrics_layout.addStretch(1)

        products_group = QGroupBox("Product Coverage Details", self)
        products_group.setObjectName("coverage_products_group")
        products_layout = QVBoxLayout(products_group)

        self.product_table = QTableWidget(
            0,
            len(self.TABLE_COLUMNS),
            products_group,
        )
        self.product_table.setObjectName("coverage_product_table")
        self.product_table.setHorizontalHeaderLabels(self.TABLE_COLUMNS)
        self.product_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.product_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.product_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.product_table.setAlternatingRowColors(True)
        self.product_table.setWordWrap(False)
        self.product_table.horizontalHeader().setStretchLastSection(True)

        products_layout.addWidget(self.product_table)

        chart_group = QGroupBox("SOL Availability by Product", self)
        chart_group.setObjectName("coverage_chart_group")
        chart_layout = QVBoxLayout(chart_group)

        self.chart = pg.PlotWidget(chart_group)
        self.chart.setObjectName("coverage_product_chart")
        self.chart.setBackground(None)
        self.chart.setLabel("left", "SOL Count")
        self.chart.setLabel("bottom", "Product")
        self.chart.showGrid(x=True, y=True, alpha=0.2)
        self.chart.setMinimumHeight(240)

        chart_layout.addWidget(self.chart)

        layout.addWidget(self.status_label)
        layout.addLayout(metrics_layout)
        layout.addWidget(products_group, 2)
        layout.addWidget(chart_group, 2)

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
    def _validate_summary(
        cls,
        summary: Any,
    ) -> tuple[bool, str]:
        if not isinstance(summary, dict):
            return False, "Coverage summary must be a JSON object."

        products = summary.get("products")

        if not isinstance(products, dict):
            return False, "Coverage summary has no valid products object."

        start_sol = summary.get("start_sol")
        end_sol = summary.get("end_sol")

        if (
            not cls._is_non_negative_integer(start_sol)
            or not cls._is_non_negative_integer(end_sol)
            or start_sol > end_sol
        ):
            return False, "Coverage summary has an invalid SOL range."

        report_count = summary.get("report_count")

        if not cls._is_non_negative_integer(report_count):
            return False, "Coverage summary has an invalid report count."

        for product_name, product_data in products.items():
            if not isinstance(product_name, str) or not product_name.strip():
                return False, "Coverage summary contains an invalid product name."

            if not isinstance(product_data, dict):
                return False, (
                    f"Coverage data for {product_name} must be an object."
                )

        return True, ""

    def set_summary(self, summary: dict[str, Any] | None) -> bool:
        """Display a previously generated coverage summary."""
        if summary is None:
            self._summary = None
            self._clear_display()
            self._show_unavailable("Coverage summary is not available.")
            return False

        valid, error_message = self._validate_summary(summary)

        if not valid:
            self._summary = None
            self._clear_display()
            self._show_unavailable(error_message)
            return False

        self._summary = summary
        self._display_summary(summary)
        return True

    def reset(self) -> None:
        """Clear all Run-specific data and restore the unavailable state."""
        self._summary_path = None
        self._summary = None
        self._clear_display()
        self._show_unavailable("Coverage summary is not available.")

    def load_summary_file(self, path: str | Path) -> bool:
        """Load a persisted coverage summary JSON file."""
        summary_path = Path(path)
        self._summary_path = summary_path

        if not summary_path.is_file():
            self._summary = None
            self._clear_display()
            self._show_unavailable(
                f"Coverage summary is not available: {summary_path}"
            )
            return False

        try:
            with summary_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ) as exc:
            self._summary = None
            self._clear_display()
            self._show_unavailable(
                "Unable to read coverage summary: "
                f"{type(exc).__name__}: {exc}"
            )
            return False

        return self.set_summary(payload)

    def _display_summary(self, summary: dict[str, Any]) -> None:
        start_sol = summary["start_sol"]
        end_sol = summary["end_sol"]
        products = summary["products"]

        self.sol_range_label.setText(
            f"SOL Range: {start_sol} – {end_sol}"
        )
        self.report_count_label.setText(
            "Coverage Reports: "
            f"{self._format_count(summary['report_count'])}"
        )
        self.product_count_label.setText(
            f"Products: {len(products):,}"
        )

        self._populate_product_table(products)
        self._populate_chart(products)

        self.status_label.setText(
            "Coverage summary loaded. Values are displayed from "
            "the persisted analyzer output."
        )

    def _populate_product_table(
        self,
        products: dict[str, Any],
    ) -> None:
        self.product_table.setRowCount(len(products))

        for row, (product_name, data) in enumerate(
            sorted(products.items())
        ):
            values = (
                product_name,
                self._format_count(data.get("csv_file_count")),
                self._format_count(data.get("sols_with_rows")),
                self._format_count(data.get("sols_without_rows")),
                self._format_count(data.get("total_rows")),
                self._format_count(data.get("total_numeric_values")),
                self._format_count(data.get("total_parsed_timestamps")),
            )

            for column, value in enumerate(values):
                self.product_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )

        self.product_table.resizeColumnsToContents()

    def _populate_chart(
        self,
        products: dict[str, Any],
    ) -> None:
        plot_item = self.chart.getPlotItem()
        plot_item.clear()

        if not products:
            plot_item.setTitle("No product coverage data")
            plot_item.getAxis("bottom").setTicks([[]])
            return

        chart_products = [
            (name, data)
            for name, data in sorted(products.items())
            if (
                self._is_non_negative_integer(
                    data.get("sols_with_rows")
                )
                and self._is_non_negative_integer(
                    data.get("sols_without_rows")
                )
            )
        ]

        if not chart_products:
            plot_item.setTitle(
                "Chart unavailable: no valid persisted SOL counts"
            )
            plot_item.getAxis("bottom").setTicks([[]])
            return

        positions = list(range(len(chart_products)))
        present_values = [
            data["sols_with_rows"]
            for _, data in chart_products
        ]
        missing_values = [
            data["sols_without_rows"]
            for _, data in chart_products
        ]

        bar_width = 0.36

        present_bars = pg.BarGraphItem(
            x=[position - bar_width / 2 for position in positions],
            height=present_values,
            width=bar_width,
            brush=(70, 145, 100),
        )
        missing_bars = pg.BarGraphItem(
            x=[position + bar_width / 2 for position in positions],
            height=missing_values,
            width=bar_width,
            brush=(190, 110, 75),
        )

        plot_item.addItem(present_bars)
        plot_item.addItem(missing_bars)

        legend = plot_item.addLegend()
        legend.addItem(present_bars, "SOLs with rows")
        legend.addItem(missing_bars, "SOLs without rows")

        plot_item.getAxis("bottom").setTicks(
            [[
                (position, product_name)
                for position, (product_name, _) in enumerate(
                    chart_products
                )
            ]]
        )

        title = "Persisted SOL Counts by Product"

        if len(chart_products) != len(products):
            title += " (available counts only)"

        plot_item.setTitle(title)
        plot_item.setXRange(
            -0.75,
            len(chart_products) - 0.25,
            padding=0,
        )

    def _clear_display(self) -> None:
        self.sol_range_label.setText("SOL Range: Not available")
        self.report_count_label.setText(
            "Coverage Reports: Not available"
        )
        self.product_count_label.setText("Products: 0")
        self.product_table.setRowCount(0)
        self.chart.getPlotItem().clear()

    def _show_unavailable(self, message: str) -> None:
        self.status_label.setText(message)
