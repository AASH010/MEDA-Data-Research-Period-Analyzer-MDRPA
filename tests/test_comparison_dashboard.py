
"""Tests for the read-only MEDA multi-Run comparison dashboard."""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication

from backend.run_manager.run_manager import RunManager
from gui.dashboard.comparison_dashboard import ComparisonDashboard
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
def comparison_dashboard(qapp):
    view = ComparisonDashboard()
    yield view
    view.close()


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


def write_summary(record, filename: str, payload: dict) -> None:
    path = record.paths.output_dir / filename
    path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def select_runs(view: ComparisonDashboard, run_ids: list[str]) -> None:
    selected = set(run_ids)

    for index in range(view.run_selector.count()):
        item = view.run_selector.item(index)
        run_id = item.data(256)  # Qt.ItemDataRole.UserRole
        item.setSelected(run_id in selected)


def find_row(
    view: ComparisonDashboard,
    artifact: str,
    metric: str,
) -> dict:
    for row in view.comparison_rows:
        if row["artifact"] == artifact and row["metric"] == metric:
            return row

    raise AssertionError(
        f"Comparison row not found: {artifact} / {metric}"
    )


def test_comparison_dashboard_starts_without_runs(
    comparison_dashboard,
):
    assert comparison_dashboard.available_run_ids == ()
    assert comparison_dashboard.selected_run_ids == ()
    assert comparison_dashboard.comparison_table.rowCount() == 0
    assert comparison_dashboard.compare_button.isEnabled() is False


def test_set_runs_populates_selector_and_preserves_valid_selection(
    comparison_dashboard,
    run_manager,
):
    first = create_completed_run(run_manager, "comparison-first")
    second = create_completed_run(run_manager, "comparison-second")

    comparison_dashboard.set_runs((first, second))
    select_runs(
        comparison_dashboard,
        [first.run_id, second.run_id],
    )

    third = create_completed_run(run_manager, "comparison-third")
    comparison_dashboard.set_runs((first, second, third))

    assert comparison_dashboard.available_run_ids == (
        first.run_id,
        second.run_id,
        third.run_id,
    )
    assert set(comparison_dashboard.selected_run_ids) == {
        first.run_id,
        second.run_id,
    }
    assert comparison_dashboard.compare_button.isEnabled() is True


def test_set_runs_rejects_non_run_records(comparison_dashboard):
    with pytest.raises(TypeError, match="RunRecord"):
        comparison_dashboard.set_runs([object()])


def test_compare_requires_at_least_two_runs(
    comparison_dashboard,
    run_manager,
):
    first = create_completed_run(run_manager, "comparison-only-one")
    comparison_dashboard.set_runs((first,))
    select_runs(comparison_dashboard, [first.run_id])

    assert comparison_dashboard.compare_selected_runs() is False
    assert comparison_dashboard.comparison_table.rowCount() == 0
    assert "at least two" in (
        comparison_dashboard.status_label.text().lower()
    )


def test_compare_reads_shared_persisted_numeric_metrics(
    comparison_dashboard,
    run_manager,
):
    first = create_completed_run(run_manager, "comparison-shared-1")
    second = create_completed_run(run_manager, "comparison-shared-2")

    write_summary(
        first,
        "quality_summary.json",
        {
            "analyzer": "MEDA Quality Analyzer",
            "report_row_count": 12,
            "analysed_field_reports": 10,
            "range_checks": {
                "below_minimum": 2,
                "above_maximum": 1,
            },
        },
    )
    write_summary(
        second,
        "quality_summary.json",
        {
            "analyzer": "MEDA Quality Analyzer",
            "report_row_count": 20,
            "analysed_field_reports": 18,
            "range_checks": {
                "below_minimum": 3,
                "above_maximum": 0,
            },
        },
    )

    comparison_dashboard.set_runs((first, second))
    select_runs(
        comparison_dashboard,
        [first.run_id, second.run_id],
    )

    assert comparison_dashboard.compare_selected_runs() is True

    row = find_row(
        comparison_dashboard,
        "Quality",
        "range_checks.below_minimum",
    )

    assert row["values"][first.run_id] == 2
    assert row["values"][second.run_id] == 3
    assert row["status"] == "Comparable"

    assert comparison_dashboard.comparison_table.rowCount() > 0
    assert "Comparable metrics:" in (
        comparison_dashboard.status_label.text()
    )


def test_missing_artifact_is_not_treated_as_zero(
    comparison_dashboard,
    run_manager,
):
    first = create_completed_run(run_manager, "comparison-missing-1")
    second = create_completed_run(run_manager, "comparison-missing-2")

    write_summary(
        first,
        "quality_summary.json",
        {
            "analyzer": "MEDA Quality Analyzer",
            "report_row_count": 12,
        },
    )

    comparison_dashboard.set_runs((first, second))
    select_runs(
        comparison_dashboard,
        [first.run_id, second.run_id],
    )

    assert comparison_dashboard.compare_selected_runs() is True

    row = find_row(
        comparison_dashboard,
        "Quality",
        "report_row_count",
    )

    assert row["values"][first.run_id] == 12
    assert row["values"][second.run_id] == "Artifact missing"
    assert row["status"] == "Incomplete — missing data"


def test_missing_metric_in_one_summary_is_not_zero(
    comparison_dashboard,
    run_manager,
):
    first = create_completed_run(run_manager, "comparison-partial-1")
    second = create_completed_run(run_manager, "comparison-partial-2")

    write_summary(
        first,
        "synchronization_summary.json",
        {
            "analyzer": "MEDA Synchronization Analyzer",
            "total_files": 10,
            "analysed_files": 8,
        },
    )
    write_summary(
        second,
        "synchronization_summary.json",
        {
            "analyzer": "MEDA Synchronization Analyzer",
            "total_files": 15,
        },
    )

    comparison_dashboard.set_runs((first, second))
    select_runs(
        comparison_dashboard,
        [first.run_id, second.run_id],
    )

    assert comparison_dashboard.compare_selected_runs() is True

    row = find_row(
        comparison_dashboard,
        "Synchronization",
        "analysed_files",
    )

    assert row["values"][first.run_id] == 8
    assert row["values"][second.run_id] == "Metric not available"
    assert row["status"] == "Incomplete — missing data"


def test_different_analyzer_identities_are_not_comparable(
    comparison_dashboard,
    run_manager,
):
    first = create_completed_run(run_manager, "comparison-type-1")
    second = create_completed_run(run_manager, "comparison-type-2")

    write_summary(
        first,
        "quality_summary.json",
        {
            "analyzer": "MEDA Quality Analyzer",
            "report_row_count": 10,
        },
    )
    write_summary(
        second,
        "quality_summary.json",
        {
            "analyzer": "Different Quality Analyzer",
            "report_row_count": 20,
        },
    )

    comparison_dashboard.set_runs((first, second))
    select_runs(
        comparison_dashboard,
        [first.run_id, second.run_id],
    )

    assert comparison_dashboard.compare_selected_runs() is True

    row = find_row(
        comparison_dashboard,
        "Quality",
        "report_row_count",
    )

    assert row["values"][first.run_id] == 10
    assert row["values"][second.run_id] == 20
    assert row["status"] == "Incompatible analyzer"


def test_boolean_and_non_finite_values_are_not_compared(
    comparison_dashboard,
    run_manager,
):
    first = create_completed_run(run_manager, "comparison-invalid-1")
    second = create_completed_run(run_manager, "comparison-invalid-2")

    write_summary(
        first,
        "coverage_summary.json",
        {
            "module": "Coverage Analyzer",
            "valid_count": 10,
            "boolean_flag": True,
            "invalid_number": float("nan"),
        },
    )
    write_summary(
        second,
        "coverage_summary.json",
        {
            "module": "Coverage Analyzer",
            "valid_count": 20,
            "boolean_flag": False,
            "invalid_number": float("inf"),
        },
    )

    comparison_dashboard.set_runs((first, second))
    select_runs(
        comparison_dashboard,
        [first.run_id, second.run_id],
    )

    assert comparison_dashboard.compare_selected_runs() is True

    assert any(
        row["metric"] == "valid_count"
        for row in comparison_dashboard.comparison_rows
    )
    assert not any(
        row["metric"] in {"boolean_flag", "invalid_number"}
        for row in comparison_dashboard.comparison_rows
    )


def test_invalid_json_artifact_is_reported_as_unavailable(
    comparison_dashboard,
    run_manager,
    tmp_path,
):
    first = create_completed_run(run_manager, "comparison-invalid-json-1")
    second = create_completed_run(run_manager, "comparison-invalid-json-2")

    write_summary(
        first,
        "quality_summary.json",
        {
            "analyzer": "MEDA Quality Analyzer",
            "report_row_count": 10,
        },
    )

    invalid_path = second.paths.output_dir / "quality_summary.json"
    invalid_path.write_text("{invalid", encoding="utf-8")

    comparison_dashboard.set_runs((first, second))
    select_runs(
        comparison_dashboard,
        [first.run_id, second.run_id],
    )

    assert comparison_dashboard.compare_selected_runs() is True

    row = find_row(
        comparison_dashboard,
        "Quality",
        "report_row_count",
    )

    assert row["values"][second.run_id] == "Artifact invalid"
    assert row["status"] == "Incomplete — missing data"


def test_artifact_without_numeric_metrics_is_marked_unavailable(
    comparison_dashboard,
    run_manager,
):
    first = create_completed_run(run_manager, "comparison-empty-1")
    second = create_completed_run(run_manager, "comparison-empty-2")

    write_summary(
        first,
        "coverage_summary.json",
        {
            "module": "Coverage Analyzer",
            "description": "No numeric summary values.",
        },
    )
    write_summary(
        second,
        "coverage_summary.json",
        {
            "module": "Coverage Analyzer",
            "description": "No numeric summary values.",
        },
    )

    comparison_dashboard.set_runs((first, second))
    select_runs(
        comparison_dashboard,
        [first.run_id, second.run_id],
    )

    assert comparison_dashboard.compare_selected_runs() is True

    row = find_row(
        comparison_dashboard,
        "Coverage",
        "No persisted numeric metrics",
    )

    assert row["status"] == "Unavailable"


def test_comparison_does_not_modify_persisted_artifacts(
    comparison_dashboard,
    run_manager,
):
    first = create_completed_run(run_manager, "comparison-readonly-1")
    second = create_completed_run(run_manager, "comparison-readonly-2")

    first_payload = {
        "analyzer": "MEDA Quality Analyzer",
        "report_row_count": 10,
    }
    second_payload = {
        "analyzer": "MEDA Quality Analyzer",
        "report_row_count": 20,
    }

    write_summary(first, "quality_summary.json", first_payload)
    write_summary(second, "quality_summary.json", second_payload)

    first_path = first.paths.output_dir / "quality_summary.json"
    second_path = second.paths.output_dir / "quality_summary.json"

    original_first = first_path.read_bytes()
    original_second = second_path.read_bytes()

    comparison_dashboard.set_runs((first, second))
    select_runs(
        comparison_dashboard,
        [first.run_id, second.run_id],
    )

    assert comparison_dashboard.compare_selected_runs() is True

    assert first_path.read_bytes() == original_first
    assert second_path.read_bytes() == original_second


def test_clear_selection_clears_previous_comparison(
    comparison_dashboard,
    run_manager,
):
    first = create_completed_run(run_manager, "comparison-clear-1")
    second = create_completed_run(run_manager, "comparison-clear-2")

    write_summary(
        first,
        "quality_summary.json",
        {
            "analyzer": "MEDA Quality Analyzer",
            "report_row_count": 10,
        },
    )
    write_summary(
        second,
        "quality_summary.json",
        {
            "analyzer": "MEDA Quality Analyzer",
            "report_row_count": 20,
        },
    )

    comparison_dashboard.set_runs((first, second))
    select_runs(
        comparison_dashboard,
        [first.run_id, second.run_id],
    )
    assert comparison_dashboard.compare_selected_runs() is True

    comparison_dashboard.clear_selection()

    assert comparison_dashboard.selected_run_ids == ()
    assert comparison_dashboard.comparison_rows == []
    assert comparison_dashboard.comparison_table.rowCount() == 0
    assert comparison_dashboard.compare_button.isEnabled() is False


def test_dashboard_refreshes_comparison_run_choices(
    dashboard,
    run_manager,
):
    first = create_completed_run(run_manager, "comparison-refresh-1")
    second = create_completed_run(run_manager, "comparison-refresh-2")

    dashboard.set_run_manager(run_manager)

    assert set(dashboard.comparison_dashboard.available_run_ids) == {
        first.run_id,
        second.run_id,
    }

    third = create_completed_run(run_manager, "comparison-refresh-3")
    dashboard.refresh_runs()

    assert set(dashboard.comparison_dashboard.available_run_ids) == {
        first.run_id,
        second.run_id,
        third.run_id,
    }


def test_dashboard_exposes_compare_runs_tab(
    dashboard,
    run_manager,
):
    dashboard.set_run_manager(run_manager)

    assert dashboard.details_tabs.count() == 2
    assert dashboard.details_tabs.tabText(0) == "Run Details"
    assert dashboard.details_tabs.tabText(1) == "Compare Runs"
    assert dashboard.details_tabs.widget(1) is (
        dashboard.comparison_dashboard
    )


def test_dashboard_without_run_manager_has_no_comparison_choices(
    dashboard,
):
    assert dashboard.comparison_dashboard.available_run_ids == ()
    assert dashboard.comparison_dashboard.comparison_table.rowCount() == 0
