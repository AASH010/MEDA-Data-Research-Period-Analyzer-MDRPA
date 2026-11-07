
"""Tests for the read-only Quality Dashboard."""

from __future__ import annotations

import csv
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pyqtgraph as pg
import pytest

from PySide6.QtWidgets import QApplication

from gui.dashboard.quality_dashboard import QualityDashboard


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def dashboard(qapp):
    view = QualityDashboard()
    yield view
    view.close()


@pytest.fixture
def quality_summary():
    return {
        "analyzer": "MEDA Quality Analyzer",
        "report_row_count": 12,
        "analysed_field_reports": 8,
        "quality_field_reports": 2,
        "quality_field_candidate_reports": 2,
        "operational_context_flag_candidate_reports": 1,
        "measurement_uncertainty_reports": 2,
        "range_check_reports": 3,
        "file_status_reports": 4,
        "analysis_status_counts": {
            "analysed": 8,
            "metadata_not_found": 2,
            "no_target_fields": 2,
        },
        "column_mapping_status_counts": {
            "header_exact_match": 8,
        },
        "total_rows_examined_by_field": 1200,
        "total_missing_values_by_field": 35,
        "total_values_below_declared_minimum": 4,
        "total_values_above_declared_maximum": 7,
        "limitations": [
            "Values outside documented limits are flagged for review."
        ],
    }


@pytest.fixture
def report_rows():
    return [
        {
            "sol_number": "100",
            "product_code": "ATS",
            "csv_file": "sample.csv",
            "field_name": "Temperature",
            "field_type": "range_check",
            "analysis_status": "analysed",
            "total_rows": "100",
            "missing_count": "3",
            "below_valid_minimum": "2",
            "above_valid_maximum": "4",
        },
        {
            "sol_number": "101",
            "product_code": "PS",
            "csv_file": "other.csv",
            "field_name": "Quality Flag",
            "field_type": "quality_field_candidate",
            "analysis_status": "analysed",
            "total_rows": "50",
            "missing_count": "1",
            "below_valid_minimum": "0",
            "above_valid_maximum": "0",
        },
    ]


def write_report(path, rows):
    columns = QualityDashboard.REPORT_SOURCE_COLUMNS

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def test_quality_dashboard_starts_unavailable(dashboard):
    assert dashboard.summary is None
    assert dashboard.report_table.rowCount() == 0
    assert "not available" in dashboard.status_label.text().lower()


def test_set_summary_displays_overview_metrics(
    dashboard,
    quality_summary,
):
    assert dashboard.set_summary(quality_summary) is True

    assert dashboard.summary is quality_summary
    assert dashboard.report_rows_label.text() == "Report Rows: 12"
    assert dashboard.analysed_fields_label.text() == (
        "Analysed Field Reports: 8"
    )
    assert dashboard.quality_candidates_label.text() == (
        "Quality Candidates: 2"
    )
    assert dashboard.range_checks_label.text() == "Range Checks: 3"
    assert dashboard.below_minimum_label.text() == "Below Minimum: 4"
    assert dashboard.above_maximum_label.text() == "Above Maximum: 7"


def test_set_summary_creates_category_chart(
    dashboard,
    quality_summary,
):
    dashboard.set_summary(quality_summary)

    plot_item = dashboard.category_chart.getPlotItem()
    bars = [
        item
        for item in plot_item.items
        if isinstance(item, pg.BarGraphItem)
    ]

    assert len(bars) == 1
    assert "Persisted Reports by Category" in plot_item.titleLabel.text


def test_set_summary_creates_status_chart(
    dashboard,
    quality_summary,
):
    dashboard.set_summary(quality_summary)

    plot_item = dashboard.status_chart.getPlotItem()
    bars = [
        item
        for item in plot_item.items
        if isinstance(item, pg.BarGraphItem)
    ]

    assert len(bars) == 1
    assert "Persisted Analysis Status Counts" in plot_item.titleLabel.text


def test_set_summary_handles_missing_category_counts(dashboard):
    summary = {
        "analyzer": "MEDA Quality Analyzer",
        "report_row_count": 0,
    }

    assert dashboard.set_summary(summary) is True

    assert "not available" in (
        dashboard.category_chart.getPlotItem().titleLabel.text.lower()
    )
    assert dashboard.quality_candidates_label.text() == (
        "Quality Candidates: Not available"
    )


def test_set_summary_handles_missing_status_counts(dashboard):
    summary = {
        "analyzer": "MEDA Quality Analyzer",
        "report_row_count": 0,
    }

    assert dashboard.set_summary(summary) is True

    assert "not available" in (
        dashboard.status_chart.getPlotItem().titleLabel.text.lower()
    )


def test_set_summary_does_not_convert_missing_counts_to_zero(dashboard):
    summary = {
        "analyzer": "MEDA Quality Analyzer",
        "report_row_count": 5,
    }

    assert dashboard.set_summary(summary) is True

    assert dashboard.analysed_fields_label.text() == (
        "Analysed Field Reports: Not available"
    )
    assert dashboard.below_minimum_label.text() == (
        "Below Minimum: Not available"
    )


@pytest.mark.parametrize(
    "summary",
    [
        None,
        [],
        "invalid",
        {},
        {
            "analyzer": "MEDA Quality Analyzer",
            "report_row_count": -1,
        },
        {
            "analyzer": "MEDA Quality Analyzer",
            "report_row_count": True,
        },
        {
            "analyzer": "MEDA Quality Analyzer",
            "report_row_count": 1,
            "analysis_status_counts": [],
        },
        {
            "analyzer": "MEDA Quality Analyzer",
            "report_row_count": 1,
            "range_check_reports": -1,
        },
    ],
)
def test_set_summary_rejects_invalid_structures(
    dashboard,
    summary,
):
    assert dashboard.set_summary(summary) is False
    assert dashboard.summary is None


def test_set_summary_clears_previous_data(
    dashboard,
    quality_summary,
):
    assert dashboard.set_summary(quality_summary) is True
    assert dashboard.report_rows_label.text() == "Report Rows: 12"

    assert dashboard.set_summary({}) is False

    assert dashboard.summary is None
    assert dashboard.report_rows_label.text() == (
        "Report Rows: Not available"
    )


def test_load_summary_file_reads_json(
    dashboard,
    quality_summary,
    tmp_path,
):
    path = tmp_path / "quality_summary.json"
    path.write_text(
        json.dumps(quality_summary),
        encoding="utf-8",
    )

    assert dashboard.load_summary_file(path) is True
    assert dashboard.summary_path == path
    assert dashboard.summary["report_row_count"] == 12


def test_load_summary_file_handles_missing_file(dashboard, tmp_path):
    path = tmp_path / "missing_quality_summary.json"

    assert dashboard.load_summary_file(path) is False
    assert dashboard.summary is None
    assert "not available" in dashboard.status_label.text().lower()


def test_load_summary_file_handles_invalid_json(dashboard, tmp_path):
    path = tmp_path / "quality_summary.json"
    path.write_text("{invalid", encoding="utf-8")

    assert dashboard.load_summary_file(path) is False
    assert dashboard.summary is None
    assert "JSONDecodeError" in dashboard.status_label.text()


def test_load_report_file_populates_table(
    dashboard,
    report_rows,
    tmp_path,
):
    path = tmp_path / "quality_field_report.csv"
    write_report(path, report_rows)

    assert dashboard.load_report_file(path) is True
    assert dashboard.report_path == path
    assert dashboard.report_table.rowCount() == 2

    assert dashboard.report_table.item(0, 0).text() == "100"
    assert dashboard.report_table.item(0, 1).text() == "ATS"
    assert dashboard.report_table.item(0, 4).text() == "range_check"
    assert dashboard.report_table.item(0, 8).text() == "2"
    assert dashboard.report_table.item(0, 9).text() == "4"


def test_load_report_file_handles_missing_file(dashboard, tmp_path):
    path = tmp_path / "missing_quality_field_report.csv"

    assert dashboard.load_report_file(path) is False
    assert dashboard.report_table.rowCount() == 0
    assert "not available" in dashboard.report_status_label.text().lower()


def test_load_report_file_rejects_incompatible_schema(
    dashboard,
    tmp_path,
):
    path = tmp_path / "quality_field_report.csv"
    path.write_text(
        "sol_number,product_code\n100,ATS\n",
        encoding="utf-8",
    )

    assert dashboard.load_report_file(path) is False
    assert dashboard.report_table.rowCount() == 0
    assert "incompatible schema" in (
        dashboard.report_status_label.text().lower()
    )


def test_load_report_file_handles_empty_numeric_values(
    dashboard,
    tmp_path,
):
    row = {
        "sol_number": "100",
        "product_code": "ATS",
        "csv_file": "sample.csv",
        "field_name": "Temperature",
        "field_type": "range_check",
        "analysis_status": "analysed",
        "total_rows": "",
        "missing_count": "",
        "below_valid_minimum": "",
        "above_valid_maximum": "",
    }

    path = tmp_path / "quality_field_report.csv"
    write_report(path, [row])

    assert dashboard.load_report_file(path) is True
    assert dashboard.report_table.item(0, 6).text() == "Not available"
    assert dashboard.report_table.item(0, 7).text() == "Not available"


def test_load_artifacts_loads_summary_and_report(
    dashboard,
    quality_summary,
    report_rows,
    tmp_path,
):
    summary_path = tmp_path / "quality_summary.json"
    summary_path.write_text(
        json.dumps(quality_summary),
        encoding="utf-8",
    )

    report_path = tmp_path / "quality_field_report.csv"
    write_report(report_path, report_rows)

    assert dashboard.load_artifacts(summary_path, report_path) is True
    assert dashboard.summary is not None
    assert dashboard.report_table.rowCount() == 2


def test_load_artifacts_without_report_keeps_report_unavailable(
    dashboard,
    quality_summary,
    tmp_path,
):
    summary_path = tmp_path / "quality_summary.json"
    summary_path.write_text(
        json.dumps(quality_summary),
        encoding="utf-8",
    )

    assert dashboard.load_artifacts(summary_path) is True
    assert dashboard.summary is not None
    assert dashboard.report_table.rowCount() == 0
    assert "not available" in (
        dashboard.report_status_label.text().lower()
    )


def test_loaded_report_is_not_modified(
    dashboard,
    report_rows,
    tmp_path,
):
    path = tmp_path / "quality_field_report.csv"
    write_report(path, report_rows)
    original = path.read_bytes()

    assert dashboard.load_report_file(path) is True
    assert path.read_bytes() == original
