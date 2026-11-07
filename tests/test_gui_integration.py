
"""Tests for analysis controller and main-window GUI integration."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication

from application.analysis_controller import AnalysisController
from application.app_config import AppConfig
from application.app_paths import AppPaths
from backend.pipeline.analysis_pipeline import AnalysisPipeline
from gui.main_window.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    """Provide a QApplication for GUI integration tests."""
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    return application


@pytest.fixture
def main_window(qapp, tmp_path):
    """Create a main window with an attached controller."""
    paths = AppPaths.from_root(tmp_path / "application-data")
    config = AppConfig(paths)

    window = MainWindow(config)

    pipeline = object.__new__(AnalysisPipeline)
    controller = AnalysisController(
        pipeline,
        parent=window,
    )

    window.attach_analysis_controller(controller)

    yield window

    window.close()


def test_controller_started_resets_and_shows_progress(main_window):
    status_bar = main_window.application_status_bar

    status_bar.progress_bar.setValue(65)
    status_bar.progress_bar.hide()

    main_window.analysis_controller.started.emit()

    assert not status_bar.progress_bar.isHidden()
    assert status_bar.progress_bar.value() == 0
    assert status_bar.currentMessage() == "Starting analysis..."


def test_progress_signal_updates_status_bar(main_window):
    status_bar = main_window.application_status_bar

    main_window.analysis_controller.progress_updated.emit(
        42,
        "Quality: completed",
    )

    assert status_bar.progress_bar.value() == 42
    assert not status_bar.progress_bar.isHidden()
    assert status_bar.currentMessage() == "Quality: completed"


def test_progress_value_is_clamped(main_window):
    status_bar = main_window.application_status_bar

    status_bar.update_progress(150, "Over range")
    assert status_bar.progress_bar.value() == 100

    status_bar.update_progress(-10, "Under range")
    assert status_bar.progress_bar.value() == 0


def test_stage_started_updates_status_message(main_window):
    main_window.analysis_controller.stage_started.emit(
        "File Discovery"
    )

    assert (
        main_window.application_status_bar.currentMessage()
        == "Running: File Discovery"
    )


def test_stage_completed_updates_status_message(main_window):
    stage_result = SimpleNamespace(
        stage_name="Quality Analyzer",
        status="completed",
    )

    main_window.analysis_controller.stage_completed.emit(
        stage_result
    )

    assert (
        main_window.application_status_bar.currentMessage()
        == "Quality Analyzer: completed"
    )


def test_warning_signal_is_displayed(main_window):
    main_window.analysis_controller.warning_occurred.emit(
        "Some metadata records were skipped."
    )

    assert (
        main_window.application_status_bar.currentMessage()
        == "Warning: Some metadata records were skipped."
    )


def test_error_signal_is_displayed(main_window):
    main_window.analysis_controller.error_occurred.emit(
        "Input directory is invalid."
    )

    assert (
        main_window.application_status_bar.currentMessage()
        == "Error: Input directory is invalid."
    )


def test_successful_result_updates_status(main_window):
    result = SimpleNamespace(
        successful=True,
        cancelled=False,
    )

    main_window.analysis_controller.finished.emit(result)

    assert (
        main_window.application_status_bar.currentMessage()
        == "Analysis completed successfully."
    )
    assert main_window.application_status_bar.progress_bar.value() == 100


def test_failed_result_updates_status(main_window):
    result = SimpleNamespace(
        successful=False,
        cancelled=False,
    )

    main_window.analysis_controller.finished.emit(result)

    assert (
        main_window.application_status_bar.currentMessage()
        == "Analysis failed."
    )


def test_cancelled_result_updates_status(main_window):
    result = SimpleNamespace(
        successful=False,
        cancelled=True,
    )

    main_window.analysis_controller.finished.emit(result)

    assert (
        main_window.application_status_bar.currentMessage()
        == "Analysis cancelled."
    )


def test_cancelled_signal_updates_status(main_window):
    main_window.analysis_controller.cancelled.emit(
        "Analysis cancellation completed."
    )

    assert (
        main_window.application_status_bar.currentMessage()
        == "Analysis cancellation completed."
    )
