
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
    )

    for widget in widgets:
        original_reset = widget.reset

        def tracked_reset(
            original=original_reset,
            name=type(widget).__name__,
        ):
            reset_calls.append(name)
            original()

        monkeypatch.setattr(widget, "reset", tracked_reset)

    dashboard._clear_analysis_dashboards()

    assert reset_calls == [
        "CoverageDashboard",
        "QualityDashboard",
        "SynchronizationDashboard",
        "RankingDashboard",
    ]

    assert dashboard.coverage_dashboard.summary_path is None
    assert dashboard.quality_dashboard.summary_path is None
    assert dashboard.synchronization_dashboard.summary_path is None
    assert dashboard.ranking_dashboard.summary_path is None

    assert dashboard.coverage_dashboard.summary is None
    assert dashboard.quality_dashboard.summary is None
    assert dashboard.synchronization_dashboard.summary is None
    assert dashboard.ranking_dashboard.summary is None
