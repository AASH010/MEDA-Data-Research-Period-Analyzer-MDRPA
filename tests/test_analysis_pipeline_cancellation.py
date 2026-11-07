
from threading import Event

import pytest

from backend.pipeline import analysis_pipeline
from backend.pipeline.analysis_pipeline import AnalysisPipeline
from backend.pipeline.pipeline_executor import (
    PipelineExecutionResult,
    PipelineStageResult,
)
from backend.run_manager.run_manager import RunManager
from backend.run_manager.run_status import RunStatus


@pytest.fixture
def pipeline_context(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    runs_root = tmp_path / "runs"
    manager = RunManager(runs_root=runs_root)

    pipeline = AnalysisPipeline(manager)

    config = {
        "input_dir": input_dir,
        "start_sol": 100,
        "end_sol": 100,
    }

    return pipeline, manager, config


def _cancelled_execution(run_id):
    now = "2026-01-01T00:00:00+00:00"

    stages = (
        PipelineStageResult(
            stage_name="file_discovery",
            status="completed",
            started_at=now,
            finished_at=now,
            output_paths=(),
        ),
        PipelineStageResult(
            stage_name="xml_parser",
            status="cancelled",
            started_at=now,
            finished_at=now,
            warnings=("Cancellation requested.",),
        ),
        PipelineStageResult(
            stage_name="coverage_analyzer",
            status="cancelled",
            started_at=now,
            finished_at=now,
            warnings=("Cancellation requested.",),
        ),
        PipelineStageResult(
            stage_name="quality_analyzer",
            status="cancelled",
            started_at=now,
            finished_at=now,
            warnings=("Cancellation requested.",),
        ),
        PipelineStageResult(
            stage_name="synchronization_analyzer",
            status="cancelled",
            started_at=now,
            finished_at=now,
            warnings=("Cancellation requested.",),
        ),
        PipelineStageResult(
            stage_name="period_ranker",
            status="cancelled",
            started_at=now,
            finished_at=now,
            warnings=("Cancellation requested.",),
        ),
    )

    return PipelineExecutionResult(
        run_id=run_id,
        status="cancelled",
        stage_results=stages,
    )


def test_cancelled_execution_updates_run_status_and_metadata(
    pipeline_context,
    monkeypatch,
):
    pipeline, manager, config = pipeline_context

    received = {}

    def fake_execute_pipeline_stages(
        validated_config,
        run_paths,
        *,
        cancel_event=None,
    ):
        received["cancel_event"] = cancel_event

        return _cancelled_execution(run_paths.run_id)

    monkeypatch.setattr(
        analysis_pipeline,
        "execute_pipeline_stages",
        fake_execute_pipeline_stages,
    )

    cancel_event = Event()
    cancel_event.set()

    result = pipeline.execute(
        config,
        run_id="cancelled-run",
        cancel_event=cancel_event,
    )

    assert received["cancel_event"] is cancel_event

    assert result.run_id == "cancelled-run"
    assert result.status == RunStatus.CANCELLED.value
    assert result.cancelled is True
    assert result.successful is False
    assert result.error is None

    assert result.execution is not None
    assert result.execution.status == "cancelled"

    persisted = manager.load_persisted_metadata(
        "cancelled-run"
    )

    assert persisted.status == RunStatus.CANCELLED.value
    assert persisted.failure_reason is None

    summary = persisted.settings["execution_summary"]

    assert summary["status"] == "cancelled"
    assert summary["error"] is None
    assert len(summary["stages"]) == 6

    assert summary["stages"][0]["status"] == "completed"
    assert summary["stages"][1]["status"] == "cancelled"


def test_cancel_event_defaults_to_none_and_preserves_success(
    pipeline_context,
    monkeypatch,
):
    pipeline, manager, config = pipeline_context

    received = {}

    def fake_execute_pipeline_stages(
        validated_config,
        run_paths,
        *,
        cancel_event=None,
    ):
        received["cancel_event"] = cancel_event

        return PipelineExecutionResult(
            run_id=run_paths.run_id,
            status="completed",
            stage_results=(),
        )

    monkeypatch.setattr(
        analysis_pipeline,
        "execute_pipeline_stages",
        fake_execute_pipeline_stages,
    )

    result = pipeline.execute(
        config,
        run_id="normal-run",
    )

    assert received["cancel_event"] is None

    assert result.status == RunStatus.COMPLETED.value
    assert result.successful is True
    assert result.cancelled is False

    persisted = manager.load_persisted_metadata(
        "normal-run"
    )

    assert persisted.status == RunStatus.COMPLETED.value
    assert "execution_summary" not in persisted.settings


def test_invalid_cancel_event_is_rejected_before_run_creation(
    pipeline_context,
):
    pipeline, manager, config = pipeline_context

    with pytest.raises(
        TypeError,
        match="threading.Event",
    ):
        pipeline.execute(
            config,
            run_id="invalid-cancel-run",
            cancel_event=True,
        )

    assert manager.list_runs() == ()


def test_cancelled_run_is_restored_after_manager_restart(
    pipeline_context,
    monkeypatch,
):
    pipeline, manager, config = pipeline_context

    def fake_execute_pipeline_stages(
        validated_config,
        run_paths,
        *,
        cancel_event=None,
    ):
        return _cancelled_execution(run_paths.run_id)

    monkeypatch.setattr(
        analysis_pipeline,
        "execute_pipeline_stages",
        fake_execute_pipeline_stages,
    )

    result = pipeline.execute(
        config,
        run_id="recover-cancelled-run",
        cancel_event=Event(),
    )

    assert result.status == RunStatus.CANCELLED.value

    recovered_manager = RunManager(
        runs_root=manager.runs_root,
    )

    recovered = recovered_manager.get_run(
        "recover-cancelled-run"
    )

    assert recovered.status is RunStatus.CANCELLED
    assert (
        recovered.metadata.settings["execution_summary"]["status"]
        == "cancelled"
    )
    assert recovered.metadata.failure_reason is None
