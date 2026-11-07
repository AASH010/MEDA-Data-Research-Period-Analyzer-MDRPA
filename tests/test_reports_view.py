
"""Tests for the read-only ReportsView browser and exporter."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QPlainTextEdit, QTableWidget

from backend.run_manager.run_manager import RunManager
from gui.reports.reports_view import ReportsView


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    """Create one QApplication for the test session."""
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def run_manager(tmp_path):
    """Create an isolated RunManager for each test."""
    return RunManager(tmp_path / "runs")


@pytest.fixture
def reports_view(qapp):
    """Create a ReportsView without an attached RunManager."""
    view = ReportsView()
    yield view
    view.close()
    view.deleteLater()
    qapp.processEvents()


def create_completed_run(
    manager: RunManager,
    run_id: str,
    start_sol: int = 100,
    end_sol: int = 110,
):
    """Create and complete a Run for report-view tests."""
    record = manager.create_run(
        run_id=run_id,
        start_sol=start_sol,
        end_sol=end_sol,
    )

    manager.start_run(record.run_id)

    return manager.complete_run(record.run_id)


def get_run_selector(view: ReportsView) -> QComboBox:
    """Return the Run selector."""
    selector = view.findChild(
        QComboBox,
        "reports_run_selector",
    )
    assert selector is not None
    return selector


def get_report_table(view: ReportsView) -> QTableWidget:
    """Return the report artifact table."""
    table = view.findChild(
        QTableWidget,
        "reports_table",
    )
    assert table is not None
    return table


def get_preview_widget(view: ReportsView) -> QPlainTextEdit:
    """Return the report preview text widget."""
    preview = view.findChild(
        QPlainTextEdit,
        "reports_preview_text",
    )
    assert preview is not None
    return preview


def select_run(
    view: ReportsView,
    run_id: str,
) -> None:
    """Select a Run by its stored identifier."""
    selector = get_run_selector(view)
    index = selector.findData(run_id)

    assert index >= 0, f"Run was not listed: {run_id}"

    selector.setCurrentIndex(index)
    QApplication.processEvents()


def find_report_row(
    view: ReportsView,
    filename: str,
) -> int:
    """Find a report row by its filename."""
    table = get_report_table(view)

    for row in range(table.rowCount()):
        item = table.item(row, 1)

        if item is not None and item.text() == filename:
            return row

    raise AssertionError(f"Report was not listed: {filename}")


def select_report(
    view: ReportsView,
    filename: str,
) -> None:
    """Select a report row by filename."""
    table = get_report_table(view)
    row = find_report_row(view, filename)

    table.selectRow(row)
    QApplication.processEvents()


def write_report(
    record,
    filename: str,
    content: str,
) -> Path:
    """Write a test artifact into one Run's output directory."""
    output_dir = record.paths.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    path = output_dir / filename
    path.write_text(content, encoding="utf-8")

    return path


def report_status(
    view: ReportsView,
    filename: str,
) -> str:
    """Return the displayed availability status for an artifact."""
    table = get_report_table(view)
    row = find_report_row(view, filename)
    item = table.item(row, 2)

    assert item is not None
    return item.text()


def test_reports_view_initializes_without_run_manager(
    reports_view,
):
    assert reports_view.run_manager is None
    assert reports_view.selected_run_id is None
    assert get_report_table(reports_view).rowCount() == 0
    assert not reports_view.export_button.isEnabled()


def test_reports_view_shows_empty_state(
    reports_view,
    run_manager,
):
    reports_view.set_run_manager(run_manager)

    assert get_run_selector(reports_view).count() == 0
    assert get_report_table(reports_view).rowCount() == 0
    assert "no analysis runs" in reports_view.status_label.text().lower()


def test_reports_view_loads_runs_from_run_manager(
    reports_view,
    run_manager,
):
    first = create_completed_run(
        run_manager,
        "reports-first-run",
    )
    second = create_completed_run(
        run_manager,
        "reports-second-run",
        200,
        210,
    )

    reports_view.set_run_manager(run_manager)

    selector = get_run_selector(reports_view)
    listed_runs = [
        selector.itemText(index)
        for index in range(selector.count())
    ]

    assert any(
        item.startswith(first.run_id)
        for item in listed_runs
    )
    assert any(
        item.startswith(second.run_id)
        for item in listed_runs
    )

    assert selector.count() == 2


def test_reports_view_lists_artifact_availability(
    reports_view,
    run_manager,
):
    record = create_completed_run(
        run_manager,
        "reports-availability-run",
    )

    write_report(
        record,
        "coverage_summary.json",
        '{"coverage": 95}',
    )

    write_report(
        record,
        "coverage_report.csv",
        "sol,coverage\n100,95\n",
    )

    reports_view.set_run_manager(run_manager)
    select_run(reports_view, record.run_id)

    assert report_status(
        reports_view,
        "coverage_summary.json",
    ) == "Available"

    assert report_status(
        reports_view,
        "coverage_report.csv",
    ) == "Available"

    assert report_status(
        reports_view,
        "quality_summary.json",
    ) == "Not generated"


def test_reports_view_previews_json_report(
    reports_view,
    run_manager,
):
    record = create_completed_run(
        run_manager,
        "reports-json-preview-run",
    )

    write_report(
        record,
        "coverage_summary.json",
        '{"coverage": 95, "valid": true}',
    )

    reports_view.set_run_manager(run_manager)
    select_report(
        reports_view,
        "coverage_summary.json",
    )

    preview = get_preview_widget(reports_view).toPlainText()

    assert '"coverage": 95' in preview
    assert '"valid": true' in preview
    assert reports_view.export_button.isEnabled()


def test_reports_view_previews_csv_report(
    reports_view,
    run_manager,
):
    record = create_completed_run(
        run_manager,
        "reports-csv-preview-run",
    )

    write_report(
        record,
        "coverage_report.csv",
        "sol,coverage\n100,95\n101,96\n",
    )

    reports_view.set_run_manager(run_manager)
    select_report(
        reports_view,
        "coverage_report.csv",
    )

    preview = get_preview_widget(reports_view).toPlainText()

    assert "sol | coverage" in preview
    assert "100 | 95" in preview
    assert "101 | 96" in preview


def test_reports_view_exports_selected_report(
    reports_view,
    run_manager,
    tmp_path,
):
    record = create_completed_run(
        run_manager,
        "reports-export-run",
    )

    source = write_report(
        record,
        "coverage_summary.json",
        '{"coverage": 95}',
    )

    reports_view.set_run_manager(run_manager)
    select_report(
        reports_view,
        "coverage_summary.json",
    )

    destination = tmp_path / "exports" / "coverage_summary.json"

    exported = reports_view.export_selected_to(destination)

    assert exported == destination.resolve()
    assert destination.is_file()
    assert destination.read_text(encoding="utf-8") == (
        source.read_text(encoding="utf-8")
    )


def test_reports_view_does_not_mix_artifacts_between_runs(
    reports_view,
    run_manager,
):
    first = create_completed_run(
        run_manager,
        "reports-isolation-first",
    )
    second = create_completed_run(
        run_manager,
        "reports-isolation-second",
        200,
        210,
    )

    write_report(
        first,
        "coverage_summary.json",
        '{"run": "first"}',
    )

    write_report(
        second,
        "coverage_summary.json",
        '{"run": "second"}',
    )

    reports_view.set_run_manager(run_manager)

    select_run(reports_view, first.run_id)
    select_report(reports_view, "coverage_summary.json")

    first_preview = get_preview_widget(reports_view).toPlainText()

    assert '"first"' in first_preview
    assert '"second"' not in first_preview

    select_run(reports_view, second.run_id)
    select_report(reports_view, "coverage_summary.json")

    second_preview = get_preview_widget(reports_view).toPlainText()

    assert '"second"' in second_preview
    assert '"first"' not in second_preview


def test_reports_view_refresh_preserves_selected_run(
    reports_view,
    run_manager,
):
    first = create_completed_run(
        run_manager,
        "reports-preserve-first",
    )

    reports_view.set_run_manager(run_manager)
    reports_view.refresh_runs()

    select_run(
        reports_view,
        first.run_id,
    )

    create_completed_run(
        run_manager,
        "reports-preserve-second",
        200,
        210,
    )

    reports_view.refresh_runs()

    assert (
        get_run_selector(reports_view).currentData()
        == first.run_id
    )


def test_reports_view_refreshes_after_new_run(
    reports_view,
    run_manager,
):
    first = create_completed_run(
        run_manager,
        "reports-refresh-first",
    )

    reports_view.set_run_manager(run_manager)

    second = create_completed_run(
        run_manager,
        "reports-refresh-second",
        200,
        210,
    )

    reports_view.refresh_runs()

    selector = get_run_selector(reports_view)

    assert any(
        selector.itemData(index) == first.run_id
        for index in range(selector.count())
    )

    assert any(
        selector.itemData(index) == second.run_id
        for index in range(selector.count())
    )


def test_reports_view_handles_missing_artifact_preview(
    reports_view,
    run_manager,
):
    record = create_completed_run(
        run_manager,
        "reports-missing-preview-run",
    )

    reports_view.set_run_manager(run_manager)

    select_report(
        reports_view,
        "coverage_summary.json",
    )

    preview = get_preview_widget(reports_view).toPlainText()

    assert (
        "not available" in preview.lower()
        or "not generated" in preview.lower()
        or "select" in preview.lower()
    )

    assert reports_view.selected_report_path is None
    assert not reports_view.export_button.isEnabled()
