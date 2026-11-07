
"""Integration tests for MainWindow analysis execution."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Event
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from application.analysis_controller import AnalysisController
from application.app_config import AppConfig
from application.app_paths import AppPaths
from backend.pipeline.analysis_pipeline import (
    AnalysisPipeline,
    PipelineRunResult,
)
from backend.pipeline.pipeline_executor import (
    PipelineExecutionResult,
    PipelineStageResult,
)
from backend.run_manager.run_status import RunStatus
from gui.analysis.analysis_center_view import AnalysisCenterView
from gui.main_window.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


def make_meda_stem(
    sol: int = 100,
    product: str = "ATS",
) -> str:
    return (
        f"WE__{sol:04d}___________"
        f"CAL_{product}_________________P01"
    )


def create_valid_dataset(root: Path) -> Path:
    sol_dir = root / "SOL100"
    sol_dir.mkdir(parents=True)

    stem = make_meda_stem()

    (sol_dir / f"{stem}.CSV").write_text(
        "time,value\n1,2\n",
        encoding="utf-8",
    )

    (sol_dir / f"{stem}.XML").write_text(
        "<Product></Product>",
        encoding="utf-8",
    )

    return root


def make_result(
    *,
    status: RunStatus = RunStatus.COMPLETED,
    execution_status: str = "completed",
    error: str | None = None,
) -> PipelineRunResult:
    stage = PipelineStageResult(
        stage_name="file_discovery",
        status="completed",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
    )

    execution = PipelineExecutionResult(
        run_id="gui-execution-test",
        status=execution_status,
        stage_results=(stage,),
    )

    record = SimpleNamespace(
        run_id="gui-execution-test",
        status=status,
    )

    return PipelineRunResult(
        record=record,
        execution=execution,
        error=error,
    )


def wait_for_thread_finished(
    controller: AnalysisController,
    qapp: QApplication,
    timeout_ms: int = 5000,
) -> None:
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

    assert controller.is_active is False
    assert controller.is_running is False


def wait_until(
    condition,
    qapp: QApplication,
    timeout_ms: int = 2000,
) -> None:
    elapsed = 0

    while not condition() and elapsed < timeout_ms:
        qapp.processEvents()
        QTest.qWait(10)
        elapsed += 10

    qapp.processEvents()

    assert condition()


@pytest.fixture
def main_window(qapp, tmp_path):
    paths = AppPaths.from_root(
        tmp_path / "application-data"
    )

    window = MainWindow(
        AppConfig(paths)
    )

    pipeline = object.__new__(AnalysisPipeline)

    controller = AnalysisController(
        pipeline,
        parent=window,
    )

    window.attach_analysis_controller(controller)

    yield window

    if controller.is_active:
        controller.request_cancel()
        qapp.processEvents()

    window.close()


def prepare_valid_configuration(
    window: MainWindow,
    tmp_path: Path,
) -> Path:
    dataset = create_valid_dataset(
        tmp_path / "dataset"
    )

    input_view = window.input_manager_view

    input_view.set_input_directory(dataset)

    assert input_view.validate_dataset() is True

    configuration_view = (
        window.analysis_configuration_view
    )

    assert configuration_view.input_directory == dataset.resolve()
    assert configuration_view.validate_configuration() is True

    return dataset.resolve()


def test_analysis_page_contains_execution_view(main_window):
    assert isinstance(
        main_window.analysis_center_view,
        AnalysisCenterView,
    )

    main_window.navigate_to("analysis")

    assert main_window.current_page_key == "analysis"
    assert main_window.page_stack.currentWidget() is (
        main_window.analysis_configuration_view
    )


def test_start_is_disabled_until_configuration_is_validated(
    main_window,
    tmp_path,
):
    center = main_window.analysis_center_view

    assert center.start_button.isEnabled() is False

    dataset = create_valid_dataset(
        tmp_path / "dataset"
    )

    main_window.input_manager_view.set_input_directory(dataset)

    assert center.start_button.isEnabled() is False

    assert (
        main_window.input_manager_view.validate_dataset()
        is True
    )

    # A validated dataset alone is not enough.
    assert center.start_button.isEnabled() is False

    assert (
        main_window.analysis_configuration_view.validate_configuration()
        is True
    )

    assert center.start_button.isEnabled() is True


def test_start_executes_pipeline_in_controller_thread(
    main_window,
    tmp_path,
):
    received_configs = []
    stage = PipelineStageResult(
        stage_name="file_discovery",
        status="completed",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
    )

    def fake_execute(config, **kwargs):
        received_configs.append(config)

        kwargs["on_stage_started"]("file_discovery")
        kwargs["on_stage_completed"](stage)
        kwargs["on_progress_updated"](
            17,
            "file_discovery: completed",
        )

        return make_result()

    main_window.analysis_controller.pipeline.execute = fake_execute

    dataset = prepare_valid_configuration(
        main_window,
        tmp_path,
    )

    center = main_window.analysis_center_view

    assert center.start_button.isEnabled() is True

    center.start_button.click()

    wait_for_thread_finished(
        main_window.analysis_controller,
        QApplication.instance(),
    )

    assert len(received_configs) == 1
    assert received_configs[0].input_dir == dataset

    assert center.execution_active is False
    assert center.start_button.isEnabled() is True
    assert center.run_id_label.text() == "gui-execution-test"
    assert "successfully" in center.status_label.text().lower()

    assert (
        main_window.application_status_bar.progress_bar.value()
        == 100
    )


def test_start_uses_latest_configuration_values(
    main_window,
    tmp_path,
):
    received_configs = []

    def fake_execute(config, **kwargs):
        received_configs.append(config)
        return make_result()

    main_window.analysis_controller.pipeline.execute = fake_execute

    prepare_valid_configuration(
        main_window,
        tmp_path,
    )

    configuration_view = (
        main_window.analysis_configuration_view
    )

    # Change a value after the earlier validation.
    configuration_view.tolerance_spin.setValue(2.75)

    main_window.analysis_center_view.start_button.click()

    wait_for_thread_finished(
        main_window.analysis_controller,
        QApplication.instance(),
    )

    assert len(received_configs) == 1
    assert received_configs[0].tolerance == 2.75


def test_invalid_configuration_does_not_start_pipeline(
    main_window,
    tmp_path,
):
    calls = []

    def fake_execute(config, **kwargs):
        calls.append(config)
        return make_result()

    main_window.analysis_controller.pipeline.execute = fake_execute

    prepare_valid_configuration(
        main_window,
        tmp_path,
    )

    configuration_view = (
        main_window.analysis_configuration_view
    )

    configuration_view.start_sol_edit.setText("100")

    # Start performs fresh validation and must reject the partial SOL range.
    main_window.analysis_center_view.start_button.click()

    QApplication.instance().processEvents()

    assert calls == []
    assert main_window.analysis_controller.is_active is False
    assert main_window.analysis_center_view.start_button.isEnabled() is False
    assert "invalid" in (
        configuration_view.status_label.text().lower()
    )


def test_cancel_requests_cooperative_pipeline_cancellation(
    main_window,
    tmp_path,
):
    execution_started = Event()
    release_execution = Event()
    cancellation_observed = []

    def fake_execute(config, **kwargs):
        cancel_event = kwargs["cancel_event"]

        execution_started.set()
        release_execution.wait(timeout=5)

        cancellation_observed.append(
            cancel_event.is_set()
        )

        if cancel_event.is_set():
            return make_result(
                status=RunStatus.CANCELLED,
                execution_status="cancelled",
            )

        return make_result()

    main_window.analysis_controller.pipeline.execute = fake_execute

    prepare_valid_configuration(
        main_window,
        tmp_path,
    )

    center = main_window.analysis_center_view

    center.start_button.click()

    assert execution_started.wait(timeout=2)

    wait_until(
        lambda: center.cancel_button.isEnabled(),
        QApplication.instance(),
    )

    assert center.start_button.isEnabled() is False

    center.cancel_button.click()

    assert center.cancel_button.isEnabled() is False
    assert "cancellation requested" in (
        center.status_label.text().lower()
    )

    release_execution.set()

    wait_for_thread_finished(
        main_window.analysis_controller,
        QApplication.instance(),
    )

    assert cancellation_observed == [True]
    assert center.execution_active is False
    assert center.start_button.isEnabled() is True
    assert "cancelled" in center.status_label.text().lower()


def test_repeated_start_is_prevented_while_execution_is_active(
    main_window,
    tmp_path,
):
    execution_started = Event()
    release_execution = Event()
    calls = []

    def fake_execute(config, **kwargs):
        calls.append(config)
        execution_started.set()
        release_execution.wait(timeout=5)
        return make_result()

    main_window.analysis_controller.pipeline.execute = fake_execute

    prepare_valid_configuration(
        main_window,
        tmp_path,
    )

    center = main_window.analysis_center_view

    center.start_button.click()

    assert execution_started.wait(timeout=2)

    assert center.start_button.isEnabled() is False

    # A second click cannot trigger another execution.
    center.start_button.click()

    assert len(calls) == 1

    release_execution.set()

    wait_for_thread_finished(
        main_window.analysis_controller,
        QApplication.instance(),
    )

    assert len(calls) == 1
    assert center.start_button.isEnabled() is True


def test_changing_input_invalidates_execution_readiness(
    main_window,
    tmp_path,
):
    first = create_valid_dataset(
        tmp_path / "first"
    )
    second = create_valid_dataset(
        tmp_path / "second"
    )

    input_view = main_window.input_manager_view
    configuration_view = main_window.analysis_configuration_view
    center = main_window.analysis_center_view

    input_view.set_input_directory(first)
    assert input_view.validate_dataset() is True
    assert configuration_view.validate_configuration() is True

    assert center.start_button.isEnabled() is True

    input_view.set_input_directory(second)

    assert configuration_view.input_directory is None
    assert configuration_view.validated_config is None
    assert center.start_button.isEnabled() is False
