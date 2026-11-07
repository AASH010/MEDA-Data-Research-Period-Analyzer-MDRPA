
"""Tests for the read-only Synchronization Dashboard."""

from __future__ import annotations

import csv
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pyqtgraph as pg
import pytest

from PySide6.QtWidgets import QApplication

from gui.dashboard.synchronization_dashboard import (
    SynchronizationDashboard,
)


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def dashboard(qapp):
    view = SynchronizationDashboard()
    yield view
    view.close()


@pytest.fixture
def synchronization_summary():
    return {
        "analyzer": "MEDA Synchronization Analyzer",
        "generated_at_utc": "2026-10-01T12:00:00+00:00",
        "tolerance": 1.0,
        "tolerance_interpretation": (
            "Applied to the selected time coordinate."
        ),
        "total_files": 10,
        "analysed_files": 8,
        "unanalysed_files": 2,
        "file_status_counts": {
            "analysed": 8,
            "metadata_not_found": 2,
        },
        "mapping_status_counts": {
            "header_exact_match": 8,
        },
        "total_product_pairs": 4,
        "analysed_pairs": 3,
        "pair_status_counts": {
            "analysed": 3,
            "incompatible_time_axes": 1,
        },
        "pairs_with_matches": 2,
        "matching_method": "Sorted two-pointer one-to-one matching.",
        "important_limitations": [
            "A timestamp match does not prove scientific equivalence."
        ],
    }


@pytest.fixture
def file_rows():
    return [
        {
            "sol_number": "100",
            "product_code": "ATS",
            "csv_file": "sample_ATS.csv",
            "selected_time_field": "LMST",
            "time_kind": "lmst",
            "analysis_status": "analysed",
            "total_rows": "100",
            "parsed_timestamps": "98",
            "missing_timestamps": "1",
            "invalid_timestamps": "1",
            "duplicate_timestamps": "2",
            "out_of_order_timestamps": "0",
        },
        {
            "sol_number": "100",
            "product_code": "PS",
            "csv_file": "sample_PS.csv",
            "selected_time_field": "LMST",
            "time_kind": "lmst",
            "analysis_status": "analysed",
            "total_rows": "100",
            "parsed_timestamps": "100",
            "missing_timestamps": "0",
            "invalid_timestamps": "0",
            "duplicate_timestamps": "0",
            "out_of_order_timestamps": "0",
        },
    ]


@pytest.fixture
def pair_rows():
    return [
        {
            "sol_number": "100",
            "product_1": "ATS",
            "file_1": "sample_ATS.csv",
            "product_2": "PS",
            "file_2": "sample_PS.csv",
            "comparison_status": "analysed",
            "time_kind": "lmst",
            "tolerance": "1.0",
            "overlap_start": "100.0",
            "overlap_end": "200.0",
            "overlap_duration": "100.0",
            "first_count": "100",
            "second_count": "100",
            "matched_timestamps": "95",
            "first_unmatched": "5",
            "second_unmatched": "5",
            "match_rate_first_percent": "95.0",
            "match_rate_second_percent": "95.0",
            "match_rate_sparser_percent": "95.0",
            "mean_match_difference": "0.1",
            "max_match_difference": "0.5",
            "notes": "",
        },
        {
            "sol_number": "101",
            "product_1": "ATS",
            "file_1": "second_ATS.csv",
            "product_2": "PS",
            "file_2": "second_PS.csv",
            "comparison_status": "analysed",
            "time_kind": "sclk",
            "tolerance": "1.0",
            "overlap_start": "300.0",
            "overlap_end": "400.0",
            "overlap_duration": "100.0",
            "first_count": "80",
            "second_count": "100",
            "matched_timestamps": "72",
            "first_unmatched": "8",
            "second_unmatched": "28",
            "match_rate_first_percent": "90.0",
            "match_rate_second_percent": "72.0",
            "match_rate_sparser_percent": "90.0",
            "mean_match_difference": "0.2",
            "max_match_difference": "0.8",
            "notes": "",
        },
    ]


def write_csv(path, columns, rows):
    """Write required columns plus any additional persisted source fields."""
    fieldnames = list(columns)

    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_dashboard_starts_unavailable(dashboard):
    assert dashboard.summary is None
    assert dashboard.file_table.rowCount() == 0
    assert dashboard.pair_table.rowCount() == 0
    assert "not available" in dashboard.status_label.text().lower()


def test_set_summary_displays_overview_metrics(
    dashboard,
    synchronization_summary,
):
    assert dashboard.set_summary(synchronization_summary) is True

    assert dashboard.summary is synchronization_summary
    assert dashboard.total_files_label.text() == "Total Files: 10"
    assert dashboard.analysed_files_label.text() == "Analysed Files: 8"
    assert dashboard.unanalysed_files_label.text() == (
        "Unanalysed Files: 2"
    )
    assert dashboard.total_pairs_label.text() == "Product Pairs: 4"
    assert dashboard.analysed_pairs_label.text() == "Analysed Pairs: 3"
    assert dashboard.pairs_with_matches_label.text() == (
        "Pairs With Matches: 2"
    )
    assert dashboard.tolerance_label.text() == "Tolerance: 1.0"


def test_set_summary_populates_file_status_chart(
    dashboard,
    synchronization_summary,
):
    dashboard.set_summary(synchronization_summary)

    plot_item = dashboard.file_status_chart.getPlotItem()
    bars = [
        item
        for item in plot_item.items
        if isinstance(item, pg.BarGraphItem)
    ]

    assert len(bars) == 1
    assert "File Analysis Status" in plot_item.titleLabel.text


def test_set_summary_populates_pair_status_chart(
    dashboard,
    synchronization_summary,
):
    dashboard.set_summary(synchronization_summary)

    plot_item = dashboard.pair_status_chart.getPlotItem()
    bars = [
        item
        for item in plot_item.items
        if isinstance(item, pg.BarGraphItem)
    ]

    assert len(bars) == 1
    assert "Product Pair Comparison Status" in plot_item.titleLabel.text


def test_set_summary_handles_missing_status_counts(dashboard):
    summary = {
        "analyzer": "MEDA Synchronization Analyzer",
        "total_files": 0,
        "analysed_files": 0,
        "unanalysed_files": 0,
        "file_status_counts": {},
        "mapping_status_counts": {},
        "total_product_pairs": 0,
        "analysed_pairs": 0,
        "pair_status_counts": {},
        "pairs_with_matches": 0,
        "tolerance": 0.0,
    }

    assert dashboard.set_summary(summary) is True

    assert "not available" in (
        dashboard.file_status_chart.getPlotItem()
        .titleLabel.text.lower()
    )
    assert "not available" in (
        dashboard.pair_status_chart.getPlotItem()
        .titleLabel.text.lower()
    )


def test_set_summary_does_not_convert_missing_values_to_zero(dashboard):
    summary = {
        "analyzer": "MEDA Synchronization Analyzer",
        "total_files": 0,
        "analysed_files": 0,
        "unanalysed_files": 0,
        "file_status_counts": {},
        "mapping_status_counts": {},
        "total_product_pairs": 0,
        "analysed_pairs": 0,
        "pair_status_counts": {},
        "pairs_with_matches": 0,
        "tolerance": 0.0,
    }

    assert dashboard.set_summary(summary) is True
    assert dashboard.tolerance_label.text() == "Tolerance: 0.0"


@pytest.mark.parametrize(
    "summary",
    [
        None,
        [],
        "invalid",
        {},
        {
            "analyzer": "Wrong Analyzer",
            "total_files": 0,
        },
        {
            "analyzer": "MEDA Synchronization Analyzer",
            "total_files": -1,
        },
        {
            "analyzer": "MEDA Synchronization Analyzer",
            "total_files": True,
        },
        {
            "analyzer": "MEDA Synchronization Analyzer",
            "total_files": 0,
            "analysed_files": 0,
            "unanalysed_files": 0,
            "file_status_counts": [],
        },
        {
            "analyzer": "MEDA Synchronization Analyzer",
            "total_files": 0,
            "analysed_files": 0,
            "unanalysed_files": 0,
            "file_status_counts": {},
            "mapping_status_counts": {},
            "total_product_pairs": 0,
            "analysed_pairs": 0,
            "pair_status_counts": {},
            "pairs_with_matches": 0,
            "tolerance": -1,
        },
    ],
)
def test_set_summary_rejects_invalid_structures(dashboard, summary):
    assert dashboard.set_summary(summary) is False
    assert dashboard.summary is None


def test_set_summary_clears_previous_values(
    dashboard,
    synchronization_summary,
):
    assert dashboard.set_summary(synchronization_summary) is True
    assert dashboard.total_files_label.text() == "Total Files: 10"

    assert dashboard.set_summary(None) is False

    assert dashboard.summary is None
    assert dashboard.total_files_label.text() == (
        "Total Files: Not available"
    )


def test_load_summary_file_reads_json(
    dashboard,
    synchronization_summary,
    tmp_path,
):
    path = tmp_path / "synchronization_summary.json"
    path.write_text(
        json.dumps(synchronization_summary),
        encoding="utf-8",
    )

    assert dashboard.load_summary_file(path) is True
    assert dashboard.summary_path == path
    assert dashboard.summary["total_files"] == 10


def test_load_summary_file_handles_missing_file(dashboard, tmp_path):
    path = tmp_path / "missing_synchronization_summary.json"

    assert dashboard.load_summary_file(path) is False
    assert dashboard.summary is None
    assert "not available" in dashboard.status_label.text().lower()


def test_load_summary_file_handles_invalid_json(dashboard, tmp_path):
    path = tmp_path / "synchronization_summary.json"
    path.write_text("{invalid", encoding="utf-8")

    assert dashboard.load_summary_file(path) is False
    assert dashboard.summary is None
    assert "JSONDecodeError" in dashboard.status_label.text()


def test_load_file_report_populates_table(
    dashboard,
    file_rows,
    tmp_path,
):
    path = tmp_path / "synchronization_file_report.csv"
    write_csv(
        path,
        dashboard.FILE_SOURCE_COLUMNS,
        file_rows,
    )

    assert dashboard.load_file_report(path) is True
    assert dashboard.file_report_path == path
    assert dashboard.file_table.rowCount() == 2

    assert dashboard.file_table.item(0, 0).text() == "100"
    assert dashboard.file_table.item(0, 1).text() == "ATS"
    assert dashboard.file_table.item(0, 5).text() == "analysed"
    assert dashboard.file_table.item(0, 8).text() == "1"
    assert dashboard.file_table.item(0, 10).text() == "2"


def test_load_file_report_handles_missing_file(dashboard, tmp_path):
    path = tmp_path / "missing_file_report.csv"

    assert dashboard.load_file_report(path) is False
    assert dashboard.file_table.rowCount() == 0
    assert "not available" in (
        dashboard.file_report_status_label.text().lower()
    )


def test_load_file_report_rejects_incompatible_schema(
    dashboard,
    tmp_path,
):
    path = tmp_path / "synchronization_file_report.csv"
    path.write_text(
        "sol_number,product_code\n100,ATS\n",
        encoding="utf-8",
    )

    assert dashboard.load_file_report(path) is False
    assert dashboard.file_table.rowCount() == 0
    assert "incompatible schema" in (
        dashboard.file_report_status_label.text().lower()
    )


def test_load_pair_report_populates_table_and_chart(
    dashboard,
    pair_rows,
    tmp_path,
):
    path = tmp_path / "synchronization_pair_report.csv"
    write_csv(
        path,
        dashboard.PAIR_SOURCE_COLUMNS,
        pair_rows,
    )

    assert dashboard.load_pair_report(path) is True
    assert dashboard.pair_report_path == path
    assert dashboard.pair_table.rowCount() == 2

    assert dashboard.pair_table.item(0, 0).text() == "100"
    assert dashboard.pair_table.item(0, 1).text() == "ATS"
    assert dashboard.pair_table.item(0, 5).text() == "analysed"
    assert dashboard.pair_table.item(0, 7).text() == "95"
    assert dashboard.pair_table.item(0, 8).text() == "95.00%"
    assert dashboard.pair_table.item(1, 9).text() == "72.00%"

    bars = [
        item
        for item in dashboard.match_rate_chart.getPlotItem().items
        if isinstance(item, pg.BarGraphItem)
    ]

    assert len(bars) == 3


def test_load_pair_report_handles_missing_file(dashboard, tmp_path):
    path = tmp_path / "missing_pair_report.csv"

    assert dashboard.load_pair_report(path) is False
    assert dashboard.pair_table.rowCount() == 0
    assert "not available" in (
        dashboard.pair_report_status_label.text().lower()
    )
    assert "not available" in (
        dashboard.match_rate_chart.getPlotItem()
        .titleLabel.text.lower()
    )


def test_load_pair_report_rejects_incompatible_schema(
    dashboard,
    tmp_path,
):
    path = tmp_path / "synchronization_pair_report.csv"
    path.write_text(
        "sol_number,product_1\n100,ATS\n",
        encoding="utf-8",
    )

    assert dashboard.load_pair_report(path) is False
    assert dashboard.pair_table.rowCount() == 0
    assert "incompatible schema" in (
        dashboard.pair_report_status_label.text().lower()
    )


def test_pair_report_does_not_convert_missing_rates_to_zero(
    dashboard,
    tmp_path,
):
    row = {
        "sol_number": "100",
        "product_1": "ATS",
        "file_1": "first.csv",
        "product_2": "PS",
        "file_2": "second.csv",
        "comparison_status": "analysed",
        "time_kind": "lmst",
        "matched_timestamps": "10",
        "match_rate_first_percent": "",
        "match_rate_second_percent": "90.0",
        "match_rate_sparser_percent": "",
    }

    path = tmp_path / "synchronization_pair_report.csv"
    write_csv(path, dashboard.PAIR_SOURCE_COLUMNS, [row])

    assert dashboard.load_pair_report(path) is True

    assert dashboard.pair_table.item(0, 8).text() == "Not available"
    assert dashboard.pair_table.item(0, 9).text() == "90.00%"
    assert dashboard.pair_table.item(0, 10).text() == "Not available"


def test_load_artifacts_loads_all_reports(
    dashboard,
    synchronization_summary,
    file_rows,
    pair_rows,
    tmp_path,
):
    summary_path = tmp_path / "synchronization_summary.json"
    summary_path.write_text(
        json.dumps(synchronization_summary),
        encoding="utf-8",
    )

    file_path = tmp_path / "synchronization_file_report.csv"
    write_csv(file_path, dashboard.FILE_SOURCE_COLUMNS, file_rows)

    pair_path = tmp_path / "synchronization_pair_report.csv"
    write_csv(pair_path, dashboard.PAIR_SOURCE_COLUMNS, pair_rows)

    assert dashboard.load_artifacts(
        summary_path,
        file_path,
        pair_path,
    ) is True

    assert dashboard.summary is not None
    assert dashboard.file_table.rowCount() == 2
    assert dashboard.pair_table.rowCount() == 2


def test_load_artifacts_without_optional_reports(
    dashboard,
    synchronization_summary,
    tmp_path,
):
    summary_path = tmp_path / "synchronization_summary.json"
    summary_path.write_text(
        json.dumps(synchronization_summary),
        encoding="utf-8",
    )

    assert dashboard.load_artifacts(summary_path) is True

    assert dashboard.summary is not None
    assert dashboard.file_table.rowCount() == 0
    assert dashboard.pair_table.rowCount() == 0
    assert "not available" in (
        dashboard.file_report_status_label.text().lower()
    )
    assert "not available" in (
        dashboard.pair_report_status_label.text().lower()
    )


def test_loaded_reports_are_not_modified(
    dashboard,
    file_rows,
    pair_rows,
    tmp_path,
):
    file_path = tmp_path / "synchronization_file_report.csv"
    pair_path = tmp_path / "synchronization_pair_report.csv"

    write_csv(file_path, dashboard.FILE_SOURCE_COLUMNS, file_rows)
    write_csv(pair_path, dashboard.PAIR_SOURCE_COLUMNS, pair_rows)

    original_file = file_path.read_bytes()
    original_pair = pair_path.read_bytes()

    assert dashboard.load_file_report(file_path) is True
    assert dashboard.load_pair_report(pair_path) is True

    assert file_path.read_bytes() == original_file
    assert pair_path.read_bytes() == original_pair
