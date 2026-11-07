
"""Tests for the read-only Coverage Dashboard."""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pyqtgraph as pg
import pytest

from PySide6.QtWidgets import QApplication

from gui.dashboard.coverage_dashboard import CoverageDashboard


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def dashboard(qapp):
    view = CoverageDashboard()
    yield view
    view.close()


@pytest.fixture
def coverage_summary():
    return {
        "start_sol": 100,
        "end_sol": 110,
        "report_count": 8,
        "products": {
            "ATS": {
                "csv_file_count": 4,
                "sols_with_rows": 7,
                "sols_without_rows": 4,
                "present_sols": [100, 101, 102, 104, 106, 108, 110],
                "missing_sols": [103, 105, 107, 109],
                "longest_consecutive_sol_range": [100, 102],
                "total_rows": 1200,
                "total_numeric_values": 8400,
                "total_parsed_timestamps": 1190,
                "files_with_available_timestamp_analysis": 4,
            },
            "PS": {
                "csv_file_count": 3,
                "sols_with_rows": 5,
                "sols_without_rows": 6,
                "present_sols": [100, 101, 104, 108, 110],
                "missing_sols": [102, 103, 105, 106, 107, 109],
                "longest_consecutive_sol_range": [100, 101],
                "total_rows": 750,
                "total_numeric_values": 5250,
                "total_parsed_timestamps": 740,
                "files_with_available_timestamp_analysis": 3,
            },
        },
    }


def test_coverage_dashboard_starts_unavailable(dashboard):
    assert dashboard.summary is None
    assert dashboard.product_table.rowCount() == 0
    assert "not available" in dashboard.status_label.text().lower()


def test_set_summary_displays_range_and_counts(
    dashboard,
    coverage_summary,
):
    result = dashboard.set_summary(coverage_summary)

    assert result is True
    assert dashboard.summary is coverage_summary
    assert dashboard.sol_range_label.text() == "SOL Range: 100 – 110"
    assert dashboard.report_count_label.text() == "Coverage Reports: 8"
    assert dashboard.product_count_label.text() == "Products: 2"


def test_set_summary_populates_product_table(
    dashboard,
    coverage_summary,
):
    dashboard.set_summary(coverage_summary)

    assert dashboard.product_table.rowCount() == 2

    ats_row = next(
        row
        for row in range(dashboard.product_table.rowCount())
        if dashboard.product_table.item(row, 0).text() == "ATS"
    )

    assert dashboard.product_table.item(ats_row, 1).text() == "4"
    assert dashboard.product_table.item(ats_row, 2).text() == "7"
    assert dashboard.product_table.item(ats_row, 3).text() == "4"
    assert dashboard.product_table.item(ats_row, 4).text() == "1,200"
    assert dashboard.product_table.item(ats_row, 5).text() == "8,400"
    assert dashboard.product_table.item(ats_row, 6).text() == "1,190"


def test_set_summary_creates_product_chart(
    dashboard,
    coverage_summary,
):
    dashboard.set_summary(coverage_summary)

    plot_item = dashboard.chart.getPlotItem()
    bar_items = [
        item
        for item in plot_item.items
        if isinstance(item, pg.BarGraphItem)
    ]

    assert len(bar_items) == 2
    assert "Persisted SOL Counts by Product" in (
        plot_item.titleLabel.text
    )


def test_set_summary_rejects_non_dictionary(dashboard):
    assert dashboard.set_summary(None) is False
    assert dashboard.summary is None
    assert dashboard.product_table.rowCount() == 0


@pytest.mark.parametrize(
    "summary",
    [
        {},
        {
            "start_sol": 100,
            "end_sol": 110,
            "report_count": 1,
            "products": [],
        },
        {
            "start_sol": 110,
            "end_sol": 100,
            "report_count": 1,
            "products": {},
        },
        {
            "start_sol": True,
            "end_sol": 110,
            "report_count": 1,
            "products": {},
        },
        {
            "start_sol": 100,
            "end_sol": 110,
            "report_count": -1,
            "products": {},
        },
        {
            "start_sol": 100,
            "end_sol": 110,
            "report_count": 1,
            "products": {"ATS": []},
        },
    ],
)
def test_set_summary_rejects_invalid_structure(
    dashboard,
    summary,
):
    assert dashboard.set_summary(summary) is False
    assert dashboard.summary is None
    assert dashboard.product_table.rowCount() == 0
    assert dashboard.status_label.text()


def test_set_summary_handles_empty_products(
    dashboard,
):
    summary = {
        "start_sol": 100,
        "end_sol": 100,
        "report_count": 0,
        "products": {},
    }

    assert dashboard.set_summary(summary) is True
    assert dashboard.product_table.rowCount() == 0
    assert dashboard.product_count_label.text() == "Products: 0"
    assert "No product coverage data" in (
        dashboard.chart.getPlotItem().titleLabel.text
    )


def test_set_summary_marks_missing_product_counts_unavailable(
    dashboard,
):
    summary = {
        "start_sol": 100,
        "end_sol": 101,
        "report_count": 1,
        "products": {
            "ATS": {
                "csv_file_count": 1,
            },
        },
    }

    assert dashboard.set_summary(summary) is True
    assert dashboard.product_table.item(0, 1).text() == "1"
    assert dashboard.product_table.item(0, 2).text() == "Not available"
    assert dashboard.product_table.item(0, 3).text() == "Not available"


def test_load_summary_file_reads_json(
    dashboard,
    coverage_summary,
    tmp_path,
):
    summary_path = tmp_path / "coverage_summary.json"
    summary_path.write_text(
        json.dumps(coverage_summary),
        encoding="utf-8",
    )

    assert dashboard.load_summary_file(summary_path) is True
    assert dashboard.summary_path == summary_path
    assert dashboard.summary["start_sol"] == 100
    assert dashboard.product_table.rowCount() == 2


def test_load_summary_file_does_not_modify_source(
    dashboard,
    coverage_summary,
    tmp_path,
):
    summary_path = tmp_path / "coverage_summary.json"
    original_content = json.dumps(
        coverage_summary,
        indent=2,
    )
    summary_path.write_text(
        original_content,
        encoding="utf-8",
    )

    assert dashboard.load_summary_file(summary_path) is True
    assert summary_path.read_text(encoding="utf-8") == original_content


def test_load_summary_file_handles_missing_file(
    dashboard,
    tmp_path,
):
    missing_path = tmp_path / "missing_coverage_summary.json"

    assert dashboard.load_summary_file(missing_path) is False
    assert dashboard.summary is None
    assert "not available" in dashboard.status_label.text().lower()


def test_load_summary_file_handles_invalid_json(
    dashboard,
    tmp_path,
):
    summary_path = tmp_path / "coverage_summary.json"
    summary_path.write_text(
        "{invalid json",
        encoding="utf-8",
    )

    assert dashboard.load_summary_file(summary_path) is False
    assert dashboard.summary is None
    assert "JSONDecodeError" in dashboard.status_label.text()


def test_invalid_summary_clears_previous_data(
    dashboard,
    coverage_summary,
):
    assert dashboard.set_summary(coverage_summary) is True
    assert dashboard.product_table.rowCount() == 2

    assert dashboard.set_summary({}) is False

    assert dashboard.summary is None
    assert dashboard.product_table.rowCount() == 0
    assert dashboard.sol_range_label.text() == (
        "SOL Range: Not available"
    )
