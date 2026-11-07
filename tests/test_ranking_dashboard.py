
"""Tests for the read-only MEDA Ranking Dashboard."""

from __future__ import annotations

import csv
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pyqtgraph as pg
import pytest

from PySide6.QtWidgets import QApplication

from gui.dashboard.ranking_dashboard import RankingDashboard


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def dashboard(qapp):
    view = RankingDashboard()
    yield view
    view.close()


@pytest.fixture
def ranking_summary():
    return {
        "analyzer": "MEDA Period Ranker",
        "ranking_type": "exploratory_comparative",
        "sol_range": {
            "start": 100,
            "end": 129,
        },
        "window_size": 10,
        "total_candidate_windows": 3,
        "rankable_windows": 2,
        "unrankable_windows": 1,
        "comparison_group_count": 2,
        "ranking_weights": {
            "file_availability": 0.2,
            "data_integrity": 0.45,
            "quality_indicators": 0.15,
            "synchronization": 0.2,
        },
        "required_products": ["ATS", "PS"],
        "required_products_source": "default_configuration",
        "required_products_explicitly_configured": False,
        "optional_products": ["ENG"],
        "min_sol_fraction": 0.8,
        "min_metrics": 2,
        "best_ranked_window": None,
        "best_ranked_windows_by_comparison_group": {
            "file_availability,data_integrity": {
                "rank": 1,
                "comparison_group": "file_availability,data_integrity",
                "window_start_sol": 100,
                "window_end_sol": 109,
                "window_label": "Sol 100-109",
                "ranking_status": "rankable",
                "exploratory_score": 90.5,
            },
            "data_integrity,synchronization": {
                "rank": 1,
                "comparison_group": "data_integrity,synchronization",
                "window_start_sol": 110,
                "window_end_sol": 119,
                "window_label": "Sol 110-119",
                "ranking_status": "rankable",
                "exploratory_score": 80.25,
            },
        },
        "important_limitations": [
            "Scores are exploratory indicators, not scientific validation.",
            "Ranks from different comparison groups are not directly comparable.",
        ],
    }


@pytest.fixture
def ranking_rows():
    return [
        {
            "rank": "1",
            "comparison_group": "file_availability,data_integrity",
            "window_start_sol": "100",
            "window_end_sol": "109",
            "window_label": "Sol 100-109",
            "ranking_status": "rankable",
            "is_partial_window": "False",
            "exploratory_score": "90.5",
            "available_metrics": "2",
            "metrics_used": "file_availability,data_integrity",
            "total_sols": "10",
            "file_availability_score": "100",
            "data_integrity_score": "81",
            "quality_indicators_score": "",
            "synchronization_score": "",
            "file_availability_sols": "10",
            "data_integrity_sols": "10",
            "quality_indicators_sols": "0",
            "synchronization_sols": "0",
            "reasons": "Two metrics available.",
        },
        {
            "rank": "1",
            "comparison_group": "data_integrity,synchronization",
            "window_start_sol": "110",
            "window_end_sol": "119",
            "window_label": "Sol 110-119",
            "ranking_status": "rankable",
            "is_partial_window": "False",
            "exploratory_score": "80.25",
            "available_metrics": "2",
            "metrics_used": "data_integrity,synchronization",
            "total_sols": "10",
            "file_availability_score": "",
            "data_integrity_score": "85",
            "quality_indicators_score": "",
            "synchronization_score": "75.5",
            "file_availability_sols": "0",
            "data_integrity_sols": "10",
            "quality_indicators_sols": "0",
            "synchronization_sols": "10",
            "reasons": "Different comparison group.",
        },
        {
            "rank": "",
            "comparison_group": "no_available_metrics",
            "window_start_sol": "120",
            "window_end_sol": "129",
            "window_label": "Sol 120-129",
            "ranking_status": "insufficient_data",
            "is_partial_window": "False",
            "exploratory_score": "",
            "available_metrics": "0",
            "metrics_used": "",
            "total_sols": "10",
            "file_availability_score": "",
            "data_integrity_score": "",
            "quality_indicators_score": "",
            "synchronization_score": "",
            "file_availability_sols": "0",
            "data_integrity_sols": "0",
            "quality_indicators_sols": "0",
            "synchronization_sols": "0",
            "reasons": "Insufficient data.",
        },
    ]


def write_csv(path, columns, rows):
    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def test_dashboard_starts_unavailable(dashboard):
    assert dashboard.summary is None
    assert dashboard.ranking_rows == []
    assert "not available" in dashboard.status_label.text().lower()
    assert dashboard.ranking_table.rowCount() == 0


def test_validate_summary_accepts_valid_summary(
    dashboard,
    ranking_summary,
):
    valid, message = dashboard._validate_summary(ranking_summary)

    assert valid is True
    assert message == ""


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("analyzer", "Other Analyzer"),
        ("ranking_type", "unknown"),
        ("total_candidate_windows", -1),
        ("rankable_windows", "2"),
        ("window_size", 0),
        ("comparison_group_count", -1),
        ("min_metrics", True),
        ("ranking_weights", []),
        ("important_limitations", "not a list"),
    ],
)
def test_set_summary_rejects_invalid_summary(
    dashboard,
    ranking_summary,
    field,
    value,
):
    payload = dict(ranking_summary)
    payload[field] = value

    assert dashboard.set_summary(payload) is False
    assert dashboard.summary is None


def test_set_summary_rejects_inconsistent_window_counts(
    dashboard,
    ranking_summary,
):
    payload = dict(ranking_summary)
    payload["rankable_windows"] = 1

    assert dashboard.set_summary(payload) is False
    assert dashboard.summary is None


def test_set_summary_populates_overview_and_limitations(
    dashboard,
    ranking_summary,
):
    assert dashboard.set_summary(ranking_summary) is True

    assert dashboard.summary is ranking_summary
    assert dashboard.total_windows_label.text() == "Candidate Windows: 3"
    assert dashboard.rankable_windows_label.text() == "Rankable Windows: 2"
    assert dashboard.unrankable_windows_label.text() == "Unrankable Windows: 1"
    assert dashboard.comparison_groups_label.text() == "Comparison Groups: 2"
    assert dashboard.sol_range_label.text() == "SOL Range: 100 – 129"
    assert dashboard.window_size_label.text() == "Window Size: 10 SOLs"

    details = dashboard.summary_text.toPlainText()

    assert "Ranking Weights:" in details
    assert "Best Ranked Window by Comparison Group:" in details
    assert "Sol 100-109" in details
    assert "Ranks from different comparison groups" in details


def test_load_summary_file_reads_json(
    dashboard,
    ranking_summary,
    tmp_path,
):
    path = tmp_path / "period_ranking_summary.json"
    path.write_text(
        json.dumps(ranking_summary),
        encoding="utf-8",
    )

    assert dashboard.load_summary_file(path) is True
    assert dashboard.summary_path == path
    assert dashboard.summary["total_candidate_windows"] == 3


def test_load_summary_file_handles_missing_file(dashboard, tmp_path):
    path = tmp_path / "missing_summary.json"

    assert dashboard.load_summary_file(path) is False
    assert dashboard.summary is None
    assert "not available" in dashboard.status_label.text().lower()


def test_load_summary_file_handles_invalid_json(dashboard, tmp_path):
    path = tmp_path / "period_ranking_summary.json"
    path.write_text("{invalid", encoding="utf-8")

    assert dashboard.load_summary_file(path) is False
    assert dashboard.summary is None
    assert "JSONDecodeError" in dashboard.status_label.text()


def test_load_ranking_report_populates_table_and_charts(
    dashboard,
    ranking_rows,
    tmp_path,
):
    path = tmp_path / "period_ranking.csv"
    write_csv(
        path,
        dashboard.RANKING_SOURCE_COLUMNS,
        ranking_rows,
    )

    assert dashboard.load_ranking_report(path) is True
    assert dashboard.ranking_report_path == path
    assert dashboard.ranking_table.rowCount() == 3

    assert dashboard.ranking_table.item(0, 0).text() == "1"
    assert dashboard.ranking_table.item(0, 1).text() == (
        "file_availability,data_integrity"
    )
    assert dashboard.ranking_table.item(0, 2).text() == "Sol 100-109"
    assert dashboard.ranking_table.item(0, 3).text() == "rankable"
    assert dashboard.ranking_table.item(0, 4).text() == "90.500"

    assert dashboard.ranking_table.item(1, 0).text() == "1"
    assert dashboard.ranking_table.item(2, 0).text() == "Not ranked"
    assert dashboard.ranking_table.item(2, 4).text() == "Not available"

    score_bars = [
        item
        for item in dashboard.score_chart.getPlotItem().items
        if isinstance(item, pg.BarGraphItem)
    ]
    status_bars = [
        item
        for item in dashboard.status_chart.getPlotItem().items
        if isinstance(item, pg.BarGraphItem)
    ]

    assert len(score_bars) == 1
    assert len(status_bars) == 1


def test_load_ranking_report_handles_missing_file(dashboard, tmp_path):
    path = tmp_path / "missing_period_ranking.csv"

    assert dashboard.load_ranking_report(path) is False
    assert dashboard.ranking_rows == []
    assert dashboard.ranking_table.rowCount() == 0
    assert "not available" in (
        dashboard.report_status_label.text().lower()
    )


def test_load_ranking_report_rejects_incompatible_schema(
    dashboard,
    tmp_path,
):
    path = tmp_path / "period_ranking.csv"
    path.write_text(
        "rank,window_label\n1,Sol 100-109\n",
        encoding="utf-8",
    )

    assert dashboard.load_ranking_report(path) is False
    assert dashboard.ranking_table.rowCount() == 0
    assert "incompatible schema" in (
        dashboard.report_status_label.text().lower()
    )


def test_load_artifacts_loads_summary_and_csv(
    dashboard,
    ranking_summary,
    ranking_rows,
    tmp_path,
):
    summary_path = tmp_path / "period_ranking_summary.json"
    report_path = tmp_path / "period_ranking.csv"

    summary_path.write_text(
        json.dumps(ranking_summary),
        encoding="utf-8",
    )
    write_csv(
        report_path,
        dashboard.RANKING_SOURCE_COLUMNS,
        ranking_rows,
    )

    assert dashboard.load_artifacts(summary_path, report_path) is True
    assert dashboard.summary is not None
    assert len(dashboard.ranking_rows) == 3
    assert dashboard.ranking_table.rowCount() == 3


def test_load_artifacts_without_report_path_keeps_summary(
    dashboard,
    ranking_summary,
    tmp_path,
):
    summary_path = tmp_path / "period_ranking_summary.json"
    summary_path.write_text(
        json.dumps(ranking_summary),
        encoding="utf-8",
    )

    assert dashboard.load_artifacts(summary_path) is True
    assert dashboard.summary is not None
    assert dashboard.ranking_table.rowCount() == 0
    assert "not supplied" in dashboard.report_status_label.text().lower()


def test_missing_scores_are_not_displayed_as_zero(
    dashboard,
    ranking_rows,
    tmp_path,
):
    path = tmp_path / "period_ranking.csv"
    write_csv(
        path,
        dashboard.RANKING_SOURCE_COLUMNS,
        ranking_rows,
    )

    assert dashboard.load_ranking_report(path) is True

    # Missing component scores remain unavailable, not zero.
    assert dashboard.ranking_table.item(0, 10).text() == "Not available"
    assert dashboard.ranking_table.item(0, 11).text() == "Not available"

    # The unrankable candidate has no exploratory score.
    assert dashboard.ranking_table.item(2, 4).text() == "Not available"


def test_non_rankable_rows_are_excluded_from_score_chart(
    dashboard,
    ranking_rows,
    tmp_path,
):
    path = tmp_path / "period_ranking.csv"
    write_csv(
        path,
        dashboard.RANKING_SOURCE_COLUMNS,
        ranking_rows,
    )

    assert dashboard.load_ranking_report(path) is True

    plot = dashboard.score_chart.getPlotItem()
    bars = [
        item
        for item in plot.items
        if isinstance(item, pg.BarGraphItem)
    ]

    assert len(bars) == 1
    assert "Different Comparison Groups Are Not Comparable" in (
        plot.titleLabel.text
    )


def test_invalid_score_is_not_plotted(
    dashboard,
    ranking_rows,
    tmp_path,
):
    rows = [dict(row) for row in ranking_rows]
    rows[0]["exploratory_score"] = "nan"

    path = tmp_path / "period_ranking.csv"
    write_csv(
        path,
        dashboard.RANKING_SOURCE_COLUMNS,
        rows,
    )

    assert dashboard.load_ranking_report(path) is True

    bars = [
        item
        for item in dashboard.score_chart.getPlotItem().items
        if isinstance(item, pg.BarGraphItem)
    ]

    # Only the second valid rankable score is plotted.
    assert len(bars) == 1


def test_loaded_reports_are_not_modified(
    dashboard,
    ranking_summary,
    ranking_rows,
    tmp_path,
):
    summary_path = tmp_path / "period_ranking_summary.json"
    report_path = tmp_path / "period_ranking.csv"

    summary_content = json.dumps(ranking_summary, indent=2)
    summary_path.write_text(summary_content, encoding="utf-8")

    write_csv(
        report_path,
        dashboard.RANKING_SOURCE_COLUMNS,
        ranking_rows,
    )

    original_summary = summary_path.read_bytes()
    original_report = report_path.read_bytes()

    assert dashboard.load_artifacts(summary_path, report_path) is True

    assert summary_path.read_bytes() == original_summary
    assert report_path.read_bytes() == original_report


def test_set_summary_none_clears_previous_summary(
    dashboard,
    ranking_summary,
):
    assert dashboard.set_summary(ranking_summary) is True

    assert dashboard.set_summary(None) is False
    assert dashboard.summary is None
    assert dashboard.total_windows_label.text() == (
        "Candidate Windows: Not available"
    )


def test_summary_rejects_invalid_sol_range(
    dashboard,
    ranking_summary,
):
    payload = dict(ranking_summary)
    payload["sol_range"] = {
        "start": 130,
        "end": 100,
    }

    assert dashboard.set_summary(payload) is False
    assert dashboard.summary is None


def test_reset_clears_all_run_specific_state(
    dashboard,
    ranking_summary,
    ranking_rows,
    tmp_path,
):
    summary_path = tmp_path / "period_ranking_summary.json"
    report_path = tmp_path / "period_ranking.csv"

    summary_path.write_text(
        json.dumps(ranking_summary),
        encoding="utf-8",
    )
    write_csv(
        report_path,
        dashboard.RANKING_SOURCE_COLUMNS,
        ranking_rows,
    )

    assert dashboard.load_artifacts(summary_path, report_path) is True

    assert dashboard.summary is not None
    assert dashboard.summary_path == summary_path
    assert dashboard.ranking_report_path == report_path
    assert len(dashboard.ranking_rows) == 3
    assert dashboard.ranking_table.rowCount() == 3
    assert dashboard.summary_text.toPlainText()

    score_bars_before = [
        item
        for item in dashboard.score_chart.getPlotItem().items
        if isinstance(item, pg.BarGraphItem)
    ]
    status_bars_before = [
        item
        for item in dashboard.status_chart.getPlotItem().items
        if isinstance(item, pg.BarGraphItem)
    ]

    assert len(score_bars_before) == 1
    assert len(status_bars_before) == 1

    dashboard.reset()

    assert dashboard.summary is None
    assert dashboard.summary_path is None
    assert dashboard.ranking_report_path is None
    assert dashboard.ranking_rows == []

    assert dashboard.ranking_table.rowCount() == 0
    assert dashboard.total_windows_label.text() == (
        "Candidate Windows: Not available"
    )
    assert dashboard.rankable_windows_label.text() == (
        "Rankable Windows: Not available"
    )
    assert dashboard.unrankable_windows_label.text() == (
        "Unrankable Windows: Not available"
    )
    assert dashboard.comparison_groups_label.text() == (
        "Comparison Groups: Not available"
    )
    assert dashboard.sol_range_label.text() == (
        "SOL Range: Not available"
    )
    assert dashboard.window_size_label.text() == (
        "Window Size: Not available"
    )

    assert dashboard.summary_text.toPlainText() == ""
    assert "not available" in dashboard.status_label.text().lower()
    assert "not available" in (
        dashboard.report_status_label.text().lower()
    )

    score_bars_after = [
        item
        for item in dashboard.score_chart.getPlotItem().items
        if isinstance(item, pg.BarGraphItem)
    ]
    status_bars_after = [
        item
        for item in dashboard.status_chart.getPlotItem().items
        if isinstance(item, pg.BarGraphItem)
    ]

    assert score_bars_after == []
    assert status_bars_after == []
