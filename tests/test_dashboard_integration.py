
"""Integration tests for Dashboard and application composition."""

from __future__ import annotations

import csv
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication, QTabWidget

from application.analysis_controller import AnalysisController
from application.app_config import AppConfig
from application.app_paths import AppPaths
from backend.pipeline.analysis_pipeline import AnalysisPipeline
from backend.run_manager.run_manager import RunManager
from gui.dashboard.dashboard_view import DashboardView
from gui.main_window.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def application_paths(tmp_path):
    return AppPaths.from_root(
        tmp_path / "application-data"
    )


@pytest.fixture
def main_window(qapp, application_paths):
    window = MainWindow(
        AppConfig(application_paths)
    )

    run_manager = RunManager(
        application_paths.runs_dir
    )
    pipeline = AnalysisPipeline(run_manager)

    controller = AnalysisController(
        pipeline,
        parent=window,
    )

    window.attach_analysis_controller(controller)

    yield window

    window.close()


def create_completed_run(
    manager: RunManager,
    run_id: str,
    start_sol: int = 100,
    end_sol: int = 110,
):
    record = manager.create_run(
        run_id=run_id,
        start_sol=start_sol,
        end_sol=end_sol,
    )
    manager.start_run(record.run_id)
    return manager.complete_run(record.run_id)


def write_json(path, payload):
    path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def write_empty_csv(path, columns):
    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.writer(file)
        writer.writerow(columns)


def write_dashboard_artifacts(record, marker: int) -> None:
    output = record.paths.output_dir

    write_json(
        output / "coverage_summary.json",
        {
            "start_sol": 100,
            "end_sol": 110,
            "report_count": marker,
            "products": {
                "ATS": {
                    "csv_file_count": marker,
                    "sols_with_rows": marker,
                    "sols_without_rows": 0,
                    "total_rows": marker * 10,
                    "total_numeric_values": marker * 20,
                    "total_parsed_timestamps": marker * 9,
                },
            },
        },
    )

    write_json(
        output / "quality_summary.json",
        {
            "analyzer": "MEDA Quality Analyzer",
            "report_row_count": marker,
            "analysed_field_reports": marker,
            "quality_field_reports": marker,
            "quality_field_candidate_reports": marker,
            "analysis_status_counts": {
                "analysed": marker,
            },
            "column_mapping_status_counts": {
                "header_exact_match": marker,
            },
            "range_check_reports": marker,
            "total_values_below_declared_minimum": 0,
            "total_values_above_declared_maximum": 0,
        },
    )

    write_empty_csv(
        output / "quality_field_report.csv",
        (
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
        ),
    )

    write_json(
        output / "synchronization_summary.json",
        {
            "analyzer": "MEDA Synchronization Analyzer",
            "tolerance": 1.0,
            "total_files": marker,
            "analysed_files": marker,
            "unanalysed_files": 0,
            "file_status_counts": {"analysed": marker},
            "mapping_status_counts": {"header_exact_match": marker},
            "total_product_pairs": marker,
            "analysed_pairs": marker,
            "pair_status_counts": {"analysed": marker},
            "pairs_with_matches": marker,
        },
    )

    write_empty_csv(
        output / "synchronization_file_report.csv",
        (
            "sol_number",
            "sol_folder",
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
            "median_step",
            "first_timestamp",
            "last_timestamp",
            "notes",
        ),
    )

    write_empty_csv(
        output / "synchronization_pair_report.csv",
        (
            "sol_number",
            "product_1",
            "file_1",
            "product_2",
            "file_2",
            "comparison_status",
            "time_kind",
            "tolerance",
            "overlap_start",
            "overlap_end",
            "overlap_duration",
            "first_count",
            "second_count",
            "matched_timestamps",
            "first_unmatched",
            "second_unmatched",
            "match_rate_first_percent",
            "match_rate_second_percent",
            "match_rate_sparser_percent",
            "mean_match_difference",
            "max_match_difference",
            "notes",
        ),
    )

    ranking_summary = {
        "analyzer": "MEDA Period Ranker",
        "ranking_type": "exploratory_comparative",
        "sol_range": {
            "start": 100,
            "end": 110,
        },
        "window_size": 10,
        "total_candidate_windows": 1,
        "rankable_windows": 1,
        "unrankable_windows": 0,
        "comparison_group_count": 1,
        "ranking_weights": {
            "data_integrity": 1.0,
        },
        "min_metrics": 1,
        "important_limitations": [
            "Scores are exploratory indicators.",
        ],
    }

    write_json(
        output / "period_ranking_summary.json",
        ranking_summary,
    )

    write_json(
        output / "period_ranking_full_summary.json",
        ranking_summary,
    )

    ranking_columns = (
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

    write_empty_csv(
        output / "period_ranking.csv",
        ranking_columns,
    )

    write_empty_csv(
        output / "period_ranking_full.csv",
        ranking_columns,
    )


def select_run(dashboard: DashboardView, run_id: str) -> None:
    for row in range(dashboard.run_table.rowCount()):
        item = dashboard.run_table.item(row, 0)

        if item is not None and item.text() == run_id:
            dashboard.run_table.selectRow(row)
            return

    raise AssertionError(f"Run not found in dashboard: {run_id}")


def test_dashboard_is_registered_as_dashboard_page(main_window):
    dashboard = main_window.dashboard_view

    assert isinstance(dashboard, DashboardView)
    assert main_window.page_stack.widget(
        main_window.page_stack.indexOf(dashboard)
    ) is dashboard

    assert dashboard.objectName() == "page_dashboard"


def test_dashboard_uses_application_run_manager(main_window):
    expected_manager = (
        main_window.analysis_controller.pipeline.run_manager
    )

    assert main_window.dashboard_view.run_manager is expected_manager


def test_dashboard_loads_runs_when_page_is_opened(main_window):
    manager = main_window.analysis_controller.pipeline.run_manager

    record = create_completed_run(
        manager,
        "dashboard-integration-run",
        100,
        105,
    )

    main_window.navigate_to("dashboard")

    dashboard = main_window.dashboard_view

    assert main_window.current_page_key == "dashboard"
    assert dashboard.run_table.rowCount() == 1
    assert dashboard.selected_run_id == record.run_id


def test_dashboard_refreshes_when_reopened(main_window):
    manager = main_window.analysis_controller.pipeline.run_manager

    main_window.navigate_to("dashboard")

    assert main_window.dashboard_view.run_table.rowCount() == 0

    create_completed_run(
        manager,
        "dashboard-refresh-run",
        200,
        210,
    )

    main_window.navigate_to("home")
    main_window.navigate_to("dashboard")

    assert main_window.dashboard_view.run_table.rowCount() == 1
    assert (
        main_window.dashboard_view.run_table.item(0, 0).text()
        == "dashboard-refresh-run"
    )


def test_dashboard_refreshes_after_controller_thread_finished(
    main_window,
):
    manager = main_window.analysis_controller.pipeline.run_manager
    dashboard = main_window.dashboard_view

    main_window.navigate_to("dashboard")

    assert dashboard.run_table.rowCount() == 0

    create_completed_run(
        manager,
        "dashboard-thread-finished-run",
        300,
        305,
    )

    main_window.analysis_controller.thread_finished.emit()

    assert dashboard.run_table.rowCount() == 1
    assert dashboard.run_table.item(0, 0).text() == (
        "dashboard-thread-finished-run"
    )

def test_all_run_views_refresh_when_controller_thread_finishes(
    main_window,
):
    manager = main_window.analysis_controller.pipeline.run_manager

    record = create_completed_run(
        manager,
        "all-views-refresh-run",
        400,
        410,
    )

    main_window.analysis_controller.thread_finished.emit()

    overview = main_window.overview_view
    dashboard = main_window.dashboard_view
    reports = main_window.reports_view

    assert any(
        item.run_id == record.run_id
        for item in overview.records
    )

    assert dashboard.run_table.rowCount() == 1
    assert (
        dashboard.run_table.item(0, 0).text()
        == record.run_id
    )

    assert reports.run_selector.count() == 1
    assert reports.selected_run_id == record.run_id
    
def test_dashboard_navigation_preserves_existing_pages(main_window):
    expected_pages = (
        "home",
        "input",
        "analysis",
        "dashboard",
        "reports",
    )

    assert main_window.navigation_sidebar.page_keys == expected_pages
    assert main_window.page_stack.count() == len(expected_pages)

    for page_key in expected_pages:
        main_window.navigate_to(page_key)
        assert main_window.current_page_key == page_key


def test_dashboard_does_not_start_analysis(main_window):
    controller = main_window.analysis_controller

    main_window.navigate_to("dashboard")

    assert controller.is_active is False
    assert controller.is_running is False


def test_dashboard_exposes_all_analysis_visualization_tabs(
    main_window,
):
    dashboard = main_window.dashboard_view

    assert dashboard.analysis_tabs.count() == 2
    assert dashboard.analysis_tabs.tabText(0) == "Run Summary"
    assert dashboard.analysis_tabs.tabText(1) == "Full Dataset"

    full_dataset_page = dashboard.analysis_tabs.widget(1)
    analyzer_tabs = full_dataset_page.findChild(
        QTabWidget,
        "dashboard_analyzer_tabs",
    )

    assert analyzer_tabs is not None
    assert analyzer_tabs.count() == 4
    assert analyzer_tabs.tabText(0) == "Coverage"
    assert analyzer_tabs.tabText(1) == "Quality"
    assert analyzer_tabs.tabText(2) == "Synchronization"
    assert analyzer_tabs.tabText(3) == "Ranking"

    assert analyzer_tabs.widget(0) is dashboard.coverage_dashboard
    assert analyzer_tabs.widget(1) is dashboard.quality_dashboard
    assert analyzer_tabs.widget(2) is dashboard.synchronization_dashboard
    assert analyzer_tabs.widget(3) is dashboard.ranking_dashboard


def test_dashboard_loads_selected_run_artifacts_into_all_visualizations(
    main_window,
):
    manager = main_window.analysis_controller.pipeline.run_manager

    record = create_completed_run(
        manager,
        "dashboard-artifact-integration",
    )
    write_dashboard_artifacts(record, marker=7)

    main_window.navigate_to("dashboard")
    dashboard = main_window.dashboard_view

    assert dashboard.selected_run_id == record.run_id

    assert dashboard.coverage_dashboard.summary is not None
    assert dashboard.coverage_dashboard.summary["report_count"] == 7

    assert dashboard.quality_dashboard.summary is not None
    assert dashboard.quality_dashboard.summary["report_row_count"] == 7

    assert dashboard.synchronization_dashboard.summary is not None
    assert dashboard.synchronization_dashboard.summary["total_files"] == 7

    assert dashboard.ranking_dashboard.summary is not None
    assert (
        dashboard.ranking_dashboard.summary["total_candidate_windows"]
        == 1
    )

    assert dashboard.quality_dashboard.report_table.rowCount() == 0
    assert dashboard.synchronization_dashboard.file_table.rowCount() == 0
    assert dashboard.synchronization_dashboard.pair_table.rowCount() == 0
    assert dashboard.ranking_dashboard.ranking_table.rowCount() == 0


def test_dashboard_switching_runs_reloads_visualizations(
    main_window,
):
    manager = main_window.analysis_controller.pipeline.run_manager

    first = create_completed_run(
        manager,
        "dashboard-switch-first",
    )
    second = create_completed_run(
        manager,
        "dashboard-switch-second",
    )

    write_dashboard_artifacts(first, marker=3)
    write_dashboard_artifacts(second, marker=9)

    main_window.navigate_to("dashboard")
    dashboard = main_window.dashboard_view

    select_run(dashboard, first.run_id)

    assert dashboard.selected_run_id == first.run_id
    assert dashboard.coverage_dashboard.summary["report_count"] == 3
    assert dashboard.quality_dashboard.summary["report_row_count"] == 3
    assert dashboard.synchronization_dashboard.summary["total_files"] == 3

    select_run(dashboard, second.run_id)

    assert dashboard.selected_run_id == second.run_id
    assert dashboard.coverage_dashboard.summary["report_count"] == 9
    assert dashboard.quality_dashboard.summary["report_row_count"] == 9
    assert dashboard.synchronization_dashboard.summary["total_files"] == 9


def test_dashboard_missing_artifacts_are_not_carried_from_previous_run(
    main_window,
):
    manager = main_window.analysis_controller.pipeline.run_manager

    populated = create_completed_run(
        manager,
        "dashboard-populated-run",
    )
    empty = create_completed_run(
        manager,
        "dashboard-empty-run",
    )

    write_dashboard_artifacts(populated, marker=5)

    main_window.navigate_to("dashboard")
    dashboard = main_window.dashboard_view

    select_run(dashboard, populated.run_id)
    assert dashboard.coverage_dashboard.summary is not None

    select_run(dashboard, empty.run_id)

    assert dashboard.selected_run_id == empty.run_id
    assert dashboard.coverage_dashboard.summary is None
    assert dashboard.quality_dashboard.summary is None
    assert dashboard.synchronization_dashboard.summary is None
    assert dashboard.ranking_dashboard.summary is None


def test_dashboard_comparison_displays_scope_notice(main_window):
    dashboard = main_window.dashboard_view

    assert "exploratory" in (
        dashboard.comparison_notice.text().lower()
    )
    assert "scientific meaning" in (
        dashboard.comparison_notice.text().lower()
    )


def test_dashboard_refresh_preserves_selected_run_and_visualizations(
    main_window,
):
    manager = main_window.analysis_controller.pipeline.run_manager

    first = create_completed_run(
        manager,
        "dashboard-preserve-first",
    )
    write_dashboard_artifacts(first, marker=6)

    main_window.navigate_to("dashboard")
    dashboard = main_window.dashboard_view

    assert dashboard.selected_run_id == first.run_id
    assert dashboard.coverage_dashboard.summary["report_count"] == 6

    create_completed_run(
        manager,
        "dashboard-preserve-new",
    )

    dashboard.refresh_runs()

    assert dashboard.selected_run_id == first.run_id
    assert dashboard.coverage_dashboard.summary["report_count"] == 6
