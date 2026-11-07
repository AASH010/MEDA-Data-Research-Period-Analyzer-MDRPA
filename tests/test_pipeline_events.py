
"""Tests for pipeline stage lifecycle and progress callbacks."""

from threading import Event
from pathlib import Path

import pytest

from backend.pipeline.analysis_pipeline import AnalysisPipeline
from backend.pipeline.pipeline_executor import (
    PipelineStageResult,
)
from backend.pipeline.pipeline_validator import (
    validate_pipeline_config,
)
from backend.run_manager.run_manager import RunManager
from backend.run_manager.run_paths import RunPaths


FIXTURE_DATASET = (
    Path(__file__).parent
    / "fixtures"
    / "pipeline_dataset"
)

EXPECTED_STAGES = (
    "file_discovery",
    "xml_parser",
    "coverage_analyzer",
    "quality_analyzer",
    "synchronization_analyzer",
    "period_ranker",
)


@pytest.fixture
def pipeline_context(tmp_path):
    manager = RunManager(
        runs_root=tmp_path / "runs",
    )

    pipeline = AnalysisPipeline(manager)

    config = validate_pipeline_config({
        "input_dir": FIXTURE_DATASET,
        "start_sol": 100,
        "end_sol": 100,
        "window_size": 1,
        "min_sol_fraction": 1.0,
        "min_metrics": 1,
        "required_products": ["ATS", "PS"],
    })

    return pipeline, manager, config


def test_pipeline_emits_ordered_stage_and_progress_events(
    pipeline_context,
):
    pipeline, _, config = pipeline_context

    started = []
    completed = []
    progress = []

    result = pipeline.execute(
        config,
        run_id="pipeline-events-success",
        on_stage_started=started.append,
        on_stage_completed=completed.append,
        on_progress_updated=lambda percentage, message: (
            progress.append((percentage, message))
        ),
    )

    assert result.successful is True

    assert started == list(EXPECTED_STAGES)

    assert [
        stage.stage_name
        for stage in completed
    ] == list(EXPECTED_STAGES)

    assert all(
        isinstance(stage, PipelineStageResult)
        for stage in completed
    )

    assert [
        percentage
        for percentage, _ in progress
    ] == [17, 33, 50, 67, 83, 100]

    assert [
        message
        for _, message in progress
    ] == [
        f"{stage}: completed"
        for stage in EXPECTED_STAGES
    ]


def test_pipeline_reports_cancelled_stages_without_start_events(
    pipeline_context,
):
    pipeline, _, config = pipeline_context

    cancel_event = Event()
    cancel_event.set()

    started = []
    completed = []
    progress = []

    result = pipeline.execute(
        config,
        run_id="pipeline-events-cancelled",
        cancel_event=cancel_event,
        on_stage_started=started.append,
        on_stage_completed=completed.append,
        on_progress_updated=lambda percentage, message: (
            progress.append((percentage, message))
        ),
    )

    assert result.cancelled is True

    # No analyzer actually started.
    assert started == []

    assert [
        stage.stage_name
        for stage in completed
    ] == list(EXPECTED_STAGES)

    assert all(
        stage.status == "cancelled"
        for stage in completed
    )

    assert [
        percentage
        for percentage, _ in progress
    ] == [17, 33, 50, 67, 83, 100]

    assert all(
        message.endswith(": cancelled")
        for _, message in progress
    )


def test_pipeline_reports_failed_stage_and_skipped_stages(
    pipeline_context,
    monkeypatch,
):
    from backend.pipeline import pipeline_executor

    pipeline, _, config = pipeline_context

    def fail_discovery(input_dir):
        raise RuntimeError("Discovery test failure.")

    monkeypatch.setattr(
        pipeline_executor.file_discovery,
        "discover_files",
        fail_discovery,
    )

    started = []
    completed = []
    progress = []

    result = pipeline.execute(
        config,
        run_id="pipeline-events-failed",
        on_stage_started=started.append,
        on_stage_completed=completed.append,
        on_progress_updated=lambda percentage, message: (
            progress.append((percentage, message))
        ),
    )

    assert result.successful is False
    assert result.status == "FAILED"

    assert started == ["file_discovery"]

    assert [
        stage.status
        for stage in completed
    ] == [
        "failed",
        "skipped",
        "skipped",
        "skipped",
        "skipped",
        "skipped",
    ]

    assert [
        percentage
        for percentage, _ in progress
    ] == [17, 33, 50, 67, 83, 100]

    assert progress[0][1] == "file_discovery: failed"
    assert progress[-1][1] == "period_ranker: skipped"


def test_callback_exception_does_not_change_pipeline_result(
    pipeline_context,
):
    pipeline, _, config = pipeline_context

    def broken_callback(stage_name):
        raise RuntimeError("Observer failure.")

    result = pipeline.execute(
        config,
        run_id="pipeline-events-callback-error",
        on_stage_started=broken_callback,
    )

    assert result.successful is True
    assert result.error is None


def test_invalid_callback_is_rejected_before_run_creation(
    pipeline_context,
):
    pipeline, manager, config = pipeline_context

    with pytest.raises(
        TypeError,
        match="on_stage_started",
    ):
        pipeline.execute(
            config,
            run_id="pipeline-events-invalid-callback",
            on_stage_started=True,
        )

    assert manager.list_runs() == ()


def test_executor_callback_arguments_are_optional():
    import inspect

    from backend.pipeline.pipeline_executor import (
        execute_pipeline_stages,
    )

    parameters = inspect.signature(
        execute_pipeline_stages
    ).parameters

    assert parameters["cancel_event"].default is None
    assert parameters["on_stage_started"].default is None
    assert parameters["on_stage_completed"].default is None
    assert parameters["on_progress_updated"].default is None


def test_progress_percentage_is_bounded():
    percentages = [
        round(index / len(EXPECTED_STAGES) * 100)
        for index in range(1, len(EXPECTED_STAGES) + 1)
    ]

    assert percentages == [17, 33, 50, 67, 83, 100]
    assert all(0 <= value <= 100 for value in percentages)
