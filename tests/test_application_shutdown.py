
"""Tests for safe application shutdown during background analysis."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from application.analysis_controller import AnalysisController
from application.app_config import AppConfig
from application.app_paths import AppPaths
from backend.pipeline.analysis_pipeline import AnalysisPipeline
from gui.main_window.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    """Provide a QApplication for shutdown tests."""
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    return application


def make_window(
    tmp_path: Path,
) -> tuple[MainWindow, AnalysisController]:
    """Create a main window and its controller."""
    paths = AppPaths.from_root(tmp_path / "application-data")
    window = MainWindow(AppConfig(paths))

    pipeline = object.__new__(AnalysisPipeline)
    controller = AnalysisController(
        pipeline,
        parent=window,
    )

    window.attach_analysis_controller(controller)

    return window, controller


def make_config(tmp_path: Path):
    """Create a minimal valid pipeline configuration."""
    from backend.pipeline.pipeline_validator import PipelineConfig

    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True)

    return PipelineConfig(input_dir=input_dir)


def wait_for_thread_finished(
    controller: AnalysisController,
    qapp: QApplication,
    timeout_ms: int = 5000,
) -> None:
    """Wait for the controller to report completed thread cleanup."""
    if not controller.is_active:
        qapp.processEvents()
        return

    loop = QEventLoop()

    controller.thread_finished.connect(loop.quit)

    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    timeout.start(timeout_ms)

    try:
        loop.exec()
    finally:
        timeout.stop()

        try:
            controller.thread_finished.disconnect(loop.quit)
        except (RuntimeError, TypeError):
            pass

    assert not controller.is_active
    assert not controller.is_running


def test_window_closes_immediately_without_active_analysis(
    qapp,
    tmp_path,
):
    window, controller = make_window(tmp_path)

    assert controller.is_active is False

    window.show()
    qapp.processEvents()

    assert window.close() is True
    assert window.isVisible() is False


def test_window_waits_for_analysis_thread_before_closing(
    qapp,
    tmp_path,
):
    window, controller = make_window(tmp_path)

    execution_started = Event()
    release_execution = Event()
    cancellation_observed = []

    def fake_execute(config, **kwargs):
        cancel_event = kwargs["cancel_event"]

        execution_started.set()

        # Keep the worker active until the test releases it.
        release_execution.wait(timeout=5)

        cancellation_observed.append(
            cancel_event.is_set()
        )

        raise RuntimeError("Shutdown test execution finished.")

    controller.pipeline.execute = fake_execute

    window.show()
    qapp.processEvents()

    controller.start(
        make_config(tmp_path),
        run_id="shutdown-test-run",
    )

    assert execution_started.wait(timeout=2)
    assert controller.is_running

    # The first close request must be ignored while the worker is active.
    close_result = window.close()

    assert close_result is False
    assert window.isVisible()
    assert controller.is_active
    assert controller._worker.cancellation_requested

    assert (
        window.application_status_bar.currentMessage()
        == "Cancelling analysis safely before closing..."
    )

    # The running operation is allowed to finish cooperatively.
    release_execution.set()

    wait_for_thread_finished(controller, qapp)

    assert cancellation_observed == [True]
    assert controller.is_active is False
    assert window.isVisible() is False


def test_repeated_close_requests_do_not_repeat_shutdown_request(
    qapp,
    tmp_path,
):
    window, controller = make_window(tmp_path)

    execution_started = Event()
    release_execution = Event()

    def fake_execute(config, **kwargs):
        execution_started.set()
        release_execution.wait(timeout=5)
        raise RuntimeError("Repeated close test finished.")

    controller.pipeline.execute = fake_execute

    window.show()
    qapp.processEvents()

    controller.start(
        make_config(tmp_path),
        run_id="repeated-close-test-run",
    )

    assert execution_started.wait(timeout=2)

    window.close()
    assert window._shutdown_pending is True

    # A repeated close request remains ignored.
    assert window.close() is False
    assert window._shutdown_pending is True

    release_execution.set()

    wait_for_thread_finished(controller, qapp)

    assert window.isVisible() is False
