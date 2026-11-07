
"""Tests for the application-level AnalysisController."""

from __future__ import annotations

from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from PySide6.QtCore import (
    QCoreApplication,
    QEventLoop,
    QTimer,
)

from backend.pipeline.analysis_pipeline import (
    AnalysisPipeline,
    PipelineRunResult,
)
from backend.pipeline.pipeline_validator import PipelineConfig
from backend.run_manager.run_status import RunStatus
from application.analysis_controller import AnalysisController


@pytest.fixture(scope="module")
def qt_app():
    """Create a Qt application for controller lifecycle tests."""
    app = QCoreApplication.instance()

    if app is None:
        app = QCoreApplication([])

    return app


def make_pipeline() -> AnalysisPipeline:
    """Create an AnalysisPipeline instance without a RunManager."""
    return object.__new__(AnalysisPipeline)


def make_config(tmp_path: Path) -> PipelineConfig:
    """Create a minimal valid pipeline configuration."""
    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True)

    return PipelineConfig(input_dir=input_dir)


def make_result(
    *,
    status: RunStatus = RunStatus.COMPLETED,
    error: str | None = None,
) -> PipelineRunResult:
    """Create a lightweight pipeline run result."""
    record = SimpleNamespace(
        run_id="controller-test-run",
        status=status,
    )

    return PipelineRunResult(
        record=record,
        execution=None,
        error=error,
    )


def wait_for_thread_finished(
    controller: AnalysisController,
    qt_app: QCoreApplication,
    timeout_ms: int = 5000,
) -> None:
    """Process Qt events until the controller reports thread cleanup."""
    if not controller.is_active:
        qt_app.processEvents()
        return

    loop = QEventLoop()

    def handle_finished() -> None:
        loop.quit()

    controller.thread_finished.connect(
        handle_finished
    )

    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(
        loop.quit
    )
    timeout.start(timeout_ms)

    try:
        loop.exec()

    finally:
        timeout.stop()

        try:
            controller.thread_finished.disconnect(
                handle_finished
            )
        except (RuntimeError, TypeError):
            pass

    assert not controller.is_active, (
        "Controller still owns a thread after waiting."
    )

    assert not controller.is_running, (
        "Controller thread is still running after waiting."
    )

    qt_app.processEvents()


def test_controller_rejects_invalid_pipeline():
    with pytest.raises(TypeError, match="pipeline"):
        AnalysisController(object())


def test_controller_starts_worker_and_forwards_result(
    tmp_path,
    qt_app,
):
    pipeline = make_pipeline()
    expected_result = make_result()

    def fake_execute(config, **kwargs):
        return expected_result

    pipeline.execute = fake_execute

    controller = AnalysisController(pipeline)

    received = {
        "started": [],
        "finished": [],
        "execution_ended": [],
        "thread_finished": [],
    }

    controller.started.connect(
        lambda: received["started"].append(True)
    )
    controller.finished.connect(
        received["finished"].append
    )
    controller.execution_ended.connect(
        lambda: received["execution_ended"].append(True)
    )
    controller.thread_finished.connect(
        lambda: received["thread_finished"].append(True)
    )

    controller.start(
        make_config(tmp_path),
        run_id="controller-test-run",
    )

    assert controller.is_active is True

    wait_for_thread_finished(controller, qt_app)

    assert received["started"] == [True]
    assert received["finished"] == [expected_result]
    assert received["execution_ended"] == [True]
    assert received["thread_finished"] == [True]

    assert controller.is_active is False
    assert controller.is_running is False


def test_controller_rejects_second_start_while_active(
    tmp_path,
    qt_app,
):
    pipeline = make_pipeline()
    release_execution = Event()
    execution_started = Event()

    def fake_execute(config, **kwargs):
        execution_started.set()
        release_execution.wait(timeout=5)
        return make_result()

    pipeline.execute = fake_execute

    controller = AnalysisController(pipeline)

    controller.start(make_config(tmp_path))

    assert execution_started.wait(timeout=2)

    with pytest.raises(
        RuntimeError,
        match="already active",
    ):
        controller.start(make_config(tmp_path / "second"))

    release_execution.set()

    wait_for_thread_finished(controller, qt_app)


def test_controller_forwards_cooperative_cancellation(
    tmp_path,
    qt_app,
):
    pipeline = make_pipeline()
    release_execution = Event()
    execution_started = Event()
    cancellation_observed = []

    def fake_execute(config, **kwargs):
        cancel_event = kwargs["cancel_event"]

        execution_started.set()
        release_execution.wait(timeout=5)

        cancellation_observed.append(
            cancel_event.is_set()
        )

        return make_result(
            status=RunStatus.CANCELLED,
        )

    pipeline.execute = fake_execute

    controller = AnalysisController(pipeline)

    cancelled = []

    controller.cancelled.connect(
        cancelled.append
    )

    controller.start(make_config(tmp_path))

    assert execution_started.wait(timeout=2)

    assert controller.request_cancel() is True

    release_execution.set()

    wait_for_thread_finished(controller, qt_app)

    assert cancellation_observed == [True]

    assert cancelled == [
        "Analysis cancellation completed."
    ]


def test_controller_cleans_up_after_unexpected_worker_exception(
    tmp_path,
    qt_app,
):
    pipeline = make_pipeline()

    def fake_execute(config, **kwargs):
        raise RuntimeError("Unexpected controller test error")

    pipeline.execute = fake_execute

    controller = AnalysisController(pipeline)

    errors = []
    finished = []
    execution_ended = []

    controller.error_occurred.connect(
        errors.append
    )
    controller.finished.connect(
        finished.append
    )
    controller.execution_ended.connect(
        lambda: execution_ended.append(True)
    )

    controller.start(make_config(tmp_path))

    wait_for_thread_finished(controller, qt_app)

    assert errors == [
        "RuntimeError: Unexpected controller test error"
    ]

    assert finished == []
    assert execution_ended == [True]

    assert controller.is_active is False
    assert controller.is_running is False


def test_controller_cancel_returns_false_without_active_worker():
    pipeline = make_pipeline()
    controller = AnalysisController(pipeline)

    assert controller.request_cancel() is False
    assert controller.is_active is False
    assert controller.is_running is False
