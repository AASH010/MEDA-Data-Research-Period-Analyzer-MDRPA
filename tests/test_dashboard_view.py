
"""Tests for the read-only Dashboard view."""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication

from backend.run_manager.run_manager import RunManager
from gui.dashboard.dashboard_view import DashboardView


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def run_manager(tmp_path):
    return RunManager(tmp_path / "runs")


@pytest.fixture
def dashboard(qapp):
    view = DashboardView()
    yield view
    view.close()


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


def write_range_summaries(
    record,
    full_start: int = 100,
    full_end: int = 110,
    selected_start: int = 103,
    selected_end: int = 107,
) -> None:
    output_dir = record.paths.output_dir

    (output_dir / "coverage_summary.json").write_text(
        json.dumps({
            "start_sol": full_start,
            "end_sol": full_end,
        }),
        encoding="utf-8",
    )

    (output_dir / "coverage_range_summary.json").write_text(
        json.dumps({
            "start_sol": selected_start,
            "end_sol": selected_end,
        }),
        encoding="utf-8",
    )


def select_run(dashboard, run_id: str) -> None:
    for row in range(dashboard.run_table.rowCount()):
        item = dashboard.run_table.item(row, 0)

        if item.data(256) == run_id:
            dashboard.run_table.selectRow(row)
            return

    raise AssertionError(f"Run not found: {run_id}")


def test_dashboard_starts_without_run_manager(dashboard):
    assert dashboard.run_manager is None
    assert dashboard.run_table.rowCount() == 0
    assert "not connected" in dashboard.status_label.text().lower()


def test_set_run_manager_loads_existing_runs(
    dashboard,
    run_manager,
):
    create_completed_run(
        run_manager,
        "dashboard-run-001",
    )

    dashboard.set_run_manager(run_manager)

    assert dashboard.run_manager is run_manager
    assert dashboard.run_table.rowCount() == 1
    assert dashboard.run_table.item(0, 0).text() == (
        "dashboard-run-001"
    )
    assert dashboard.run_table.item(0, 1).text() == "COMPLETED"
    assert dashboard.run_table.item(0, 2).text() == "100 – 110"


def test_dashboard_displays_single_sol_range(
    dashboard,
    run_manager,
):
    create_completed_run(
        run_manager,
        "dashboard-run-single-sol",
        start_sol=250,
        end_sol=250,
    )

    dashboard.set_run_manager(run_manager)

    assert dashboard.run_table.item(0, 2).text() == "250"


def test_dashboard_selects_run_and_reads_json_summaries(
    dashboard,
    run_manager,
):
    record = create_completed_run(
        run_manager,
        "dashboard-run-summary",
    )

    coverage_summary = {
        "products": {
            "ATS": {
                "coverage": 0.95,
            },
        },
    }

    summary_path = (
        record.paths.output_dir / "coverage_summary.json"
    )
    summary_path.write_text(
        json.dumps(coverage_summary),
        encoding="utf-8",
    )

    dashboard.set_run_manager(run_manager)

    assert dashboard.selected_run_id == record.run_id
    assert record.run_id in dashboard.run_details_label.text()

    displayed = dashboard.summary_text.toPlainText()

    assert "Coverage Summary" in displayed
    assert "coverage_summary.json" in displayed
    assert '"ATS"' in displayed
    assert "0.95" in displayed


def test_dashboard_handles_missing_summary_artifacts(
    dashboard,
    run_manager,
):
    create_completed_run(
        run_manager,
        "dashboard-run-no-artifacts",
    )

    dashboard.set_run_manager(run_manager)

    displayed = dashboard.summary_text.toPlainText()

    assert "Coverage Summary" in displayed
    assert "Not generated or not available" in displayed


def test_dashboard_handles_invalid_json_artifact(
    dashboard,
    run_manager,
):
    record = create_completed_run(
        run_manager,
        "dashboard-run-invalid-json",
    )

    summary_path = (
        record.paths.output_dir / "coverage_summary.json"
    )
    summary_path.write_text(
        "{invalid json",
        encoding="utf-8",
    )

    dashboard.set_run_manager(run_manager)

    displayed = dashboard.summary_text.toPlainText()

    assert "Unable to read this artifact" in displayed
    assert "JSONDecodeError" in displayed


def test_dashboard_refresh_preserves_selected_run(
    dashboard,
    run_manager,
):
    first = create_completed_run(
        run_manager,
        "dashboard-run-first",
    )
    create_completed_run(
        run_manager,
        "dashboard-run-second",
    )

    dashboard.set_run_manager(run_manager)

    selected_row = next(
        row
        for row in range(dashboard.run_table.rowCount())
        if dashboard.run_table.item(row, 0).text() == first.run_id
    )

    dashboard.run_table.selectRow(selected_row)

    assert dashboard.selected_run_id == first.run_id

    create_completed_run(
        run_manager,
        "dashboard-run-third",
    )

    dashboard.refresh_runs()

    assert dashboard.run_table.rowCount() == 3
    assert dashboard.selected_run_id == first.run_id


def test_dashboard_refresh_selects_first_run_when_previous_run_disappears(
    dashboard,
    run_manager,
):
    create_completed_run(
        run_manager,
        "dashboard-run-existing",
    )

    dashboard.set_run_manager(run_manager)

    assert dashboard.selected_run_id == "dashboard-run-existing"

    # A fresh manager with no Runs represents an empty current data source.
    empty_manager = RunManager(
        run_manager.runs_root.parent / "empty-runs"
    )
    dashboard.set_run_manager(empty_manager)

    assert dashboard.run_table.rowCount() == 0
    assert dashboard.selected_run_id is None
    assert "No analysis Runs" in dashboard.status_label.text()


def test_dashboard_displays_execution_summary_from_metadata(
    dashboard,
    run_manager,
):
    record = run_manager.create_run(
        run_id="dashboard-run-execution-summary",
        start_sol=100,
        end_sol=100,
    )
    run_manager.start_run(record.run_id)

    run_manager.fail_run(
        record.run_id,
        failure_reason="test failure",
        settings_updates={
            "execution_summary": {
                "status": "failed",
                "stages": [
                    {
                        "stage_name": "quality_analyzer",
                        "status": "failed",
                    },
                ],
            },
        },
    )

    dashboard.set_run_manager(run_manager)

    displayed = dashboard.summary_text.toPlainText()

    assert "Execution Summary (metadata.json)" in displayed
    assert "quality_analyzer" in displayed
    assert "test failure" in dashboard.run_details_label.text()


def test_dashboard_shows_selected_range_for_partial_range(
    dashboard,
    run_manager,
):
    record = create_completed_run(
        run_manager,
        "dashboard-partial-range",
    )
    write_range_summaries(record)

    dashboard.set_run_manager(run_manager)

    tab_names = [
        dashboard.analysis_tabs.tabText(index)
        for index in range(dashboard.analysis_tabs.count())
    ]

    assert "Full Dataset" in tab_names
    assert "Selected Range" in tab_names


def test_dashboard_hides_selected_range_for_full_range(
    dashboard,
    run_manager,
):
    record = create_completed_run(
        run_manager,
        "dashboard-full-range",
    )
    write_range_summaries(
        record,
        selected_start=100,
        selected_end=110,
    )

    dashboard.set_run_manager(run_manager)

    tab_names = [
        dashboard.analysis_tabs.tabText(index)
        for index in range(dashboard.analysis_tabs.count())
    ]

    assert "Full Dataset" in tab_names
    assert "Selected Range" not in tab_names


def test_dashboard_restores_selected_range_tab(
    dashboard,
    run_manager,
):
    partial = create_completed_run(
        run_manager,
        "dashboard-partial",
    )
    full = create_completed_run(
        run_manager,
        "dashboard-full",
    )

    write_range_summaries(partial)
    write_range_summaries(
        full,
        selected_start=100,
        selected_end=110,
    )

    dashboard.set_run_manager(run_manager)

    select_run(dashboard, full.run_id)

    assert dashboard.analysis_tabs.indexOf(
        dashboard._selected_range_page
    ) == -1

    select_run(dashboard, partial.run_id)

    assert dashboard.analysis_tabs.indexOf(
        dashboard._selected_range_page
    ) >= 0


def test_dashboard_hides_selected_range_when_range_metadata_is_invalid(
    dashboard,
    run_manager,
):
    record = create_completed_run(
        run_manager,
        "dashboard-invalid-range",
    )

    output_dir = record.paths.output_dir

    (output_dir / "coverage_summary.json").write_text(
        json.dumps({
            "start_sol": 100,
            "end_sol": 110,
        }),
        encoding="utf-8",
    )

    (output_dir / "coverage_range_summary.json").write_text(
        json.dumps({
            "start_sol": "invalid",
            "end_sol": 107,
        }),
        encoding="utf-8",
    )

    dashboard.set_run_manager(run_manager)

    assert dashboard.analysis_tabs.indexOf(
        dashboard._selected_range_page
    ) == -1


def test_dashboard_loads_full_and_selected_artifacts_separately(
    dashboard,
    run_manager,
    monkeypatch,
):
    record = create_completed_run(
        run_manager,
        "dashboard-separate-artifacts",
    )
    write_range_summaries(record)

    calls = {}

    def capture_coverage(path):
        calls.setdefault("coverage", []).append(path)

    def capture_quality(summary_path, report_path=None):
        calls.setdefault("quality", []).append(
            (summary_path, report_path)
        )
        return True

    def capture_synchronization(
        summary_path,
        file_report_path=None,
        pair_report_path=None,
    ):
        calls.setdefault("synchronization", []).append(
            (
                summary_path,
                file_report_path,
                pair_report_path,
            )
        )
        return True

    def capture_ranking(summary_path, ranking_report_path=None):
        calls.setdefault("ranking", []).append(
            (summary_path, ranking_report_path)
        )
        return True

    monkeypatch.setattr(
        dashboard.coverage_dashboard,
        "load_summary_file",
        capture_coverage,
    )
    monkeypatch.setattr(
        dashboard._coverage_range_dashboard,
        "load_summary_file",
        capture_coverage,
    )

    for widget in (
        dashboard.quality_dashboard,
        dashboard._quality_range_dashboard,
    ):
        monkeypatch.setattr(
            widget,
            "load_artifacts",
            capture_quality,
        )

    for widget in (
        dashboard.synchronization_dashboard,
        dashboard._synchronization_range_dashboard,
    ):
        monkeypatch.setattr(
            widget,
            "load_artifacts",
            capture_synchronization,
        )

    for widget in (
        dashboard.ranking_dashboard,
        dashboard._ranking_range_dashboard,
    ):
        monkeypatch.setattr(
            widget,
            "load_artifacts",
            capture_ranking,
        )

    dashboard.set_run_manager(run_manager)

    output_dir = record.paths.output_dir

    assert calls["coverage"] == [
        output_dir / "coverage_summary.json",
        output_dir / "coverage_range_summary.json",
    ]

    assert calls["quality"][0][0] == (
        output_dir / "quality_summary.json"
    )
    assert calls["quality"][1][0] == (
        output_dir / "quality_range_summary.json"
    )

    # Detailed quality reports remain unfiltered.
    assert calls["quality"][0][1] == (
        output_dir / "quality_field_report.csv"
    )
    assert calls["quality"][1][1] == (
        output_dir / "quality_field_report.csv"
    )

    assert calls["synchronization"][0][0] == (
        output_dir / "synchronization_summary.json"
    )
    assert calls["synchronization"][1][0] == (
        output_dir / "synchronization_range_summary.json"
    )

    # Detailed synchronization reports remain unfiltered.
    assert calls["synchronization"][0][1:] == (
        output_dir / "synchronization_file_report.csv",
        output_dir / "synchronization_pair_report.csv",
    )
    assert calls["synchronization"][1][1:] == (
        output_dir / "synchronization_file_report.csv",
        output_dir / "synchronization_pair_report.csv",
    )

    assert calls["ranking"][0] == (
        output_dir / "period_ranking_full_summary.json",
        output_dir / "period_ranking_full.csv",
    )
    assert calls["ranking"][1] == (
        output_dir / "period_ranking_summary.json",
        output_dir / "period_ranking.csv",
    )


def test_clear_analysis_dashboards_calls_explicit_resets(
    dashboard,
    monkeypatch,
):
    reset_calls = []

    widgets = (
        dashboard.coverage_dashboard,
        dashboard.quality_dashboard,
        dashboard.synchronization_dashboard,
        dashboard.ranking_dashboard,
        dashboard._coverage_range_dashboard,
        dashboard._quality_range_dashboard,
        dashboard._synchronization_range_dashboard,
        dashboard._ranking_range_dashboard,
    )

    for index, widget in enumerate(widgets):
        original_reset = widget.reset

        def tracked_reset(
            original=original_reset,
            widget_index=index,
        ):
            reset_calls.append(widget_index)
            original()

        monkeypatch.setattr(widget, "reset", tracked_reset)

    dashboard._clear_analysis_dashboards()

    assert reset_calls == list(range(8))

    for widget in widgets:
        assert widget.summary_path is None
        assert widget.summary is None
