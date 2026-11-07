"""Tests for the MEDA background analysis worker."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.pipeline.analysis_pipeline import (
    AnalysisPipeline,
    PipelineRunResult,
)
from backend.pipeline.pipeline_executor import (
    PipelineExecutionResult,
    PipelineStageResult,
)
from backend.pipeline.pipeline_validator import PipelineConfig
from backend.run_manager.run_status import RunStatus
from backend.workers.analysis_worker import AnalysisWorker


def make_pipeline() -> AnalysisPipeline:
    """Create an AnalysisPipeline instance without initializing a manager."""
    return object.__new__(AnalysisPipeline)


def make_config(tmp_path: Path) -> PipelineConfig:
    """Create a minimal pipeline configuration."""
    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True)

    return PipelineConfig(input_dir=input_dir)


def make_result(
    *,
    status: RunStatus = RunStatus.COMPLETED,
    execution: PipelineExecutionResult | None = None,
    error: str | None = None,
) -> PipelineRunResult:
    """Build a lightweight PipelineRunResult for worker tests."""
    record = SimpleNamespace(
        run_id="worker-test-run",
        status=status,
    )

    return PipelineRunResult(
        record=record,
        execution=execution,
        error=error,
    )


def make_stage_result(
    *,
    stage_name: str = "file_discovery",
    status: str = "completed",
    warnings: tuple[str, ...] = (),
    errors: tuple[str, ...] = (),
) -> PipelineStageResult:
    """Build a pipeline stage result."""
    return PipelineStageResult(
        stage_name=stage_name,
        status=status,
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        warnings=warnings,
        errors=errors,
    )


def test_worker_rejects_invalid_pipeline(tmp_path):
    with pytest.raises(TypeError, match="pipeline"):
        AnalysisWorker(
            pipeline=object(),
            config=make_config(tmp_path),
        )


@pytest.mark.parametrize(
    "config",
    [
        None,
        "invalid-config",
        123,
    ],
)
def test_worker_rejects_invalid_config(tmp_path, config):
    with pytest.raises(TypeError, match="config"):
        AnalysisWorker(
            pipeline=make_pipeline(),
            config=config,
        )


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        "   ",
        123,
    ],
)
def test_worker_rejects_invalid_run_id(tmp_path, run_id):
    with pytest.raises(ValueError, match="run_id"):
        AnalysisWorker(
            pipeline=make_pipeline(),
            config=make_config(tmp_path),
            run_id=run_id,
        )


def test_worker_emits_started_and_finished(tmp_path):
    pipeline = make_pipeline()
    expected_result = make_result()

    received = {
        "started": 0,
        "finished": [],
    }

    def fake_execute(config, **kwargs):
        return expected_result

    pipeline.execute = fake_execute

    worker = AnalysisWorker(
        pipeline,
        make_config(tmp_path),
        run_id="worker-test-run",
    )

    def on_started():
        received["started"] += 1

    worker.signals.started.connect(on_started)
    worker.signals.finished.connect(
        received["finished"].append
    )

    worker.run()

    assert received["started"] == 1
    assert received["finished"] == [expected_result]


def test_worker_passes_pipeline_event_callbacks(tmp_path):
    pipeline = make_pipeline()
    stage_result = make_stage_result()

    received = {}

    def fake_execute(config, **kwargs):
        received.update(kwargs)

        kwargs["on_stage_started"]("file_discovery")
        kwargs["on_stage_completed"](stage_result)
        kwargs["on_progress_updated"](
            17,
            "file_discovery: completed",
        )

        return make_result()

    pipeline.execute = fake_execute

    worker = AnalysisWorker(
        pipeline,
        make_config(tmp_path),
    )

    stage_started = []
    stage_completed = []
    progress_updates = []

    worker.signals.stage_started.connect(
        stage_started.append
    )
    worker.signals.stage_completed.connect(
        stage_completed.append
    )
    worker.signals.progress_updated.connect(
        lambda percentage, message: progress_updates.append(
            (percentage, message)
        )
    )

    worker.run()

    assert callable(received["on_stage_started"])
    assert callable(received["on_stage_completed"])
    assert callable(received["on_progress_updated"])

    assert stage_started == ["file_discovery"]
    assert stage_completed == [stage_result]

    assert progress_updates == [
        (17, "file_discovery: completed")
    ]


def test_worker_forwards_stage_warnings_and_errors(tmp_path):
    pipeline = make_pipeline()

    stage_result = make_stage_result(
        status="failed",
        warnings=("XML warning",),
        errors=("Analyzer error",),
    )

    def fake_execute(config, **kwargs):
        kwargs["on_stage_completed"](stage_result)

        execution = PipelineExecutionResult(
            run_id="worker-test-run",
            status="failed",
            stage_results=(stage_result,),
        )

        return make_result(
            status=RunStatus.FAILED,
            execution=execution,
        )

    pipeline.execute = fake_execute

    worker = AnalysisWorker(
        pipeline,
        make_config(tmp_path),
    )

    warnings = []
    errors = []

    worker.signals.warning_occurred.connect(
        warnings.append
    )
    worker.signals.error_occurred.connect(
        errors.append
    )

    worker.run()

    assert warnings == ["XML warning"]
    assert errors == ["Analyzer error"]


def test_worker_forwards_pipeline_level_error(tmp_path):
    pipeline = make_pipeline()

    def fake_execute(config, **kwargs):
        return make_result(
            status=RunStatus.FAILED,
            error="Pipeline execution failed.",
        )

    pipeline.execute = fake_execute

    worker = AnalysisWorker(
        pipeline,
        make_config(tmp_path),
    )

    errors = []

    worker.signals.error_occurred.connect(
        errors.append
    )

    worker.run()

    assert errors == [
        "Pipeline execution failed."
    ]


def test_worker_passes_cancellation_event(tmp_path):
    pipeline = make_pipeline()
    received = {}

    def fake_execute(config, **kwargs):
        received["cancel_event"] = kwargs["cancel_event"]

        assert received["cancel_event"].is_set()

        return make_result(
            status=RunStatus.CANCELLED,
        )

    pipeline.execute = fake_execute

    worker = AnalysisWorker(
        pipeline,
        make_config(tmp_path),
    )

    cancelled = []

    worker.signals.cancelled.connect(
        cancelled.append
    )

    worker.request_cancel()

    assert worker.cancellation_requested is True

    worker.run()

    assert received["cancel_event"].is_set()

    assert cancelled == [
        "Analysis cancellation completed."
    ]


def test_worker_reports_unexpected_exception(tmp_path):
    pipeline = make_pipeline()

    def fake_execute(config, **kwargs):
        raise RuntimeError("Unexpected pipeline error")

    pipeline.execute = fake_execute

    worker = AnalysisWorker(
        pipeline,
        make_config(tmp_path),
    )

    errors = []
    finished = []

    worker.signals.error_occurred.connect(
        errors.append
    )
    worker.signals.finished.connect(
        finished.append
    )

    worker.run()

    assert errors == [
        "RuntimeError: Unexpected pipeline error"
    ]

    assert finished == []


def test_worker_can_only_run_once(tmp_path):
    pipeline = make_pipeline()
    calls = []

    def fake_execute(config, **kwargs):
        calls.append(True)
        return make_result()

    pipeline.execute = fake_execute

    worker = AnalysisWorker(
        pipeline,
        make_config(tmp_path),
    )

    errors = []

    worker.signals.error_occurred.connect(
        errors.append
    )

    worker.run()
    worker.run()

    assert len(calls) == 1

    assert errors == [
        "AnalysisWorker can only be executed once."
    ]


def test_workers_have_independent_signals(tmp_path):
    first_pipeline = make_pipeline()
    second_pipeline = make_pipeline()

    first_pipeline.execute = (
        lambda config, **kwargs: make_result()
    )

    second_pipeline.execute = (
        lambda config, **kwargs: make_result()
    )

    first_worker = AnalysisWorker(
        first_pipeline,
        make_config(tmp_path / "first"),
    )

    second_worker = AnalysisWorker(
        second_pipeline,
        make_config(tmp_path / "second"),
    )

    first_events = []
    second_events = []

    first_worker.signals.started.connect(
        lambda: first_events.append("started")
    )

    second_worker.signals.started.connect(
        lambda: second_events.append("started")
    )

    first_worker.run()

    assert first_events == ["started"]
    assert second_events == []