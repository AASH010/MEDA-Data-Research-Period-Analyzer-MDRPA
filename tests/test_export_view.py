
"""Tests for the dedicated report ExportView."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from backend.run_manager.run_manager import RunManager
from gui.reports.export_view import ExportView


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


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
def completed_run(run_manager):
    record = run_manager.create_run(
        run_id="export-view-test-run",
        start_sol=100,
        end_sol=110,
    )
    run_manager.start_run(record.run_id)
    return run_manager.complete_run(record.run_id)


@pytest.fixture
def report_source(completed_run):
    output_dir = completed_run.paths.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    source = output_dir / "coverage_summary.json"
    source.write_text(
        '{"coverage": 95, "run": "export-view-test-run"}',
        encoding="utf-8",
    )
    return source


@pytest.fixture
def export_view(qapp, completed_run, report_source):
    view = ExportView(
        source_path=report_source,
        output_dir=completed_run.paths.output_dir,
        run_id=completed_run.run_id,
    )
    yield view
    view.close()
    view.deleteLater()
    qapp.processEvents()


def test_export_view_initializes(export_view):
    assert export_view.run_id == "export-view-test-run"
    assert export_view.source_path.name == "coverage_summary.json"
    assert not export_view.export_button.isEnabled()


def test_export_button_requires_destination(export_view):
    assert not export_view.export_button.isEnabled()

    export_view.destination_input.setText("")

    assert not export_view.export_button.isEnabled()

    export_view.destination_input.setText("report-copy.json")

    assert export_view.export_button.isEnabled()


def test_export_view_copies_report(export_view, tmp_path, report_source):
    destination = (
        tmp_path / "exports" / "coverage_summary.json"
    )

    exported = export_view.export_to(destination)

    assert exported == destination.resolve()
    assert exported.is_file()
    assert exported.read_bytes() == report_source.read_bytes()


def test_export_view_creates_destination_directory(
    export_view,
    tmp_path,
):
    destination = (
        tmp_path
        / "new"
        / "nested"
        / "directory"
        / "report.json"
    )

    exported = export_view.export_to(destination)

    assert exported.is_file()
    assert exported.parent.is_dir()


def test_export_view_rejects_source_as_destination(
    export_view,
    report_source,
):
    with pytest.raises(ValueError, match="must differ"):
        export_view.export_to(report_source)


def test_export_view_rejects_directory_destination(
    export_view,
    tmp_path,
):
    destination = tmp_path / "existing-directory"
    destination.mkdir()

    with pytest.raises(IsADirectoryError):
        export_view.export_to(destination)


def test_export_view_rejects_missing_source(
    qapp,
    completed_run,
    tmp_path,
):
    missing_source = (
        completed_run.paths.output_dir / "missing_report.json"
    )

    view = ExportView(
        source_path=missing_source,
        output_dir=completed_run.paths.output_dir,
        run_id=completed_run.run_id,
    )

    try:
        with pytest.raises(FileNotFoundError):
            view.export_to(tmp_path / "export.json")
    finally:
        view.close()
        view.deleteLater()
        qapp.processEvents()


def test_export_view_rejects_source_outside_run_output(
    qapp,
    completed_run,
    tmp_path,
):
    outside_source = tmp_path / "outside.json"
    outside_source.write_text('{"outside": true}', encoding="utf-8")

    view = ExportView(
        source_path=outside_source,
        output_dir=completed_run.paths.output_dir,
        run_id=completed_run.run_id,
    )

    try:
        with pytest.raises(ValueError, match="inside the selected Run"):
            view.export_to(tmp_path / "export.json")
    finally:
        view.close()
        view.deleteLater()
        qapp.processEvents()


def test_export_view_rejects_empty_destination(export_view):
    with pytest.raises(ValueError, match="required"):
        export_view.export_to("   ")


def test_export_view_rejects_invalid_run_id(
    report_source,
    completed_run,
):
    with pytest.raises(ValueError, match="run_id"):
        ExportView(
            source_path=report_source,
            output_dir=completed_run.paths.output_dir,
            run_id="",
        )
def test_export_view_rejects_existing_destination(
    export_view,
    tmp_path,
):
    destination = tmp_path / "existing-report.json"
    original_content = "keep this content"
    destination.write_text(original_content, encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        export_view.export_to(destination)

    assert destination.read_text(encoding="utf-8") == original_content