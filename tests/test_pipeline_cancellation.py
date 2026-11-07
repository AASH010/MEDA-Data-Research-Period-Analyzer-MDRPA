from threading import Event

import pytest

from backend.pipeline.pipeline_executor import execute_pipeline_stages
from backend.pipeline.pipeline_validator import PipelineConfig
from backend.pipeline import pipeline_executor
from backend.run_manager.run_paths import RunPaths


def _write_artifact(path, content="test"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _patch_successful_analyzers(monkeypatch):
    """Install predictable analyzer doubles for cancellation tests."""

    monkeypatch.setattr(
        pipeline_executor.file_discovery,
        "discover_files",
        lambda input_dir: [
            {
                "sol_number": 100,
                "sol_folder": "SOL100",
                "filename": "sample.csv",
            }
        ],
    )

    monkeypatch.setattr(
        pipeline_executor.file_discovery,
        "write_inventory",
        lambda records, path: _write_artifact(path),
    )

    monkeypatch.setattr(
        pipeline_executor.xml_parser,
        "build_metadata_inventory",
        lambda input_dir: {
            "records": [{"parse_status": "success"}],
            "summary": {
                "xml_files_discovered": 1,
                "successfully_parsed": 1,
                "failed_to_parse": 0,
            },
        },
    )

    monkeypatch.setattr(
        pipeline_executor.xml_parser,
        "save_json",
        lambda data, path: _write_artifact(path),
    )

    monkeypatch.setattr(
        pipeline_executor.coverage_analyzer,
        "analyze_coverage",
        lambda input_dir, inventory, metadata, gap_factor: [
            {"sol_number": 100},
        ],
    )

    monkeypatch.setattr(
        pipeline_executor.coverage_analyzer,
        "save_coverage_csv",
        lambda reports, path: _write_artifact(path),
    )

    monkeypatch.setattr(
        pipeline_executor.coverage_analyzer,
        "build_product_summary",
        lambda reports, start, end: {"ATS": {}},
    )

    monkeypatch.setattr(
        pipeline_executor.coverage_analyzer,
        "save_summary_json",
        lambda summary, path: _write_artifact(path),
    )

    monkeypatch.setattr(
        pipeline_executor.quality_analyzer,
        "run_analysis",
        lambda input_dir, inventory, metadata: [
            {"analysis_status": "analysed"},
        ],
    )

    monkeypatch.setattr(
        pipeline_executor.quality_analyzer,
        "write_report",
        lambda path, rows: _write_artifact(path),
    )

    # The executor passes start_sol/end_sol, so the double must accept them.
    monkeypatch.setattr(
        pipeline_executor.quality_analyzer,
        "build_summary",
        lambda rows, **kwargs: {
            "report_row_count": len(rows),
        },
    )

    monkeypatch.setattr(
        pipeline_executor.quality_analyzer,
        "save_summary",
        lambda path, summary: _write_artifact(path),
    )

    monkeypatch.setattr(
        pipeline_executor.synchronization_analyzer,
        "run_analysis",
        lambda input_dir, inventory, metadata, tolerance: (
            [{"analysis_status": "analysed"}],
            [{"comparison_status": "analysed"}],
        ),
    )

    monkeypatch.setattr(
        pipeline_executor.synchronization_analyzer,
        "write_csv",
        lambda path, rows, columns: _write_artifact(path),
    )

    # The executor passes start_sol/end_sol, so the double must accept them.
    monkeypatch.setattr(
        pipeline_executor.synchronization_analyzer,
        "build_summary",
        lambda files, pairs, tolerance, **kwargs: {
            "file_count": len(files),
            "pair_count": len(pairs),
        },
    )

    monkeypatch.setattr(
        pipeline_executor.synchronization_analyzer,
        "save_summary",
        lambda path, summary: _write_artifact(path),
    )

    monkeypatch.setattr(
        pipeline_executor.period_ranker,
        "run",
        lambda args: _write_ranker_outputs(args),
    )


def _write_ranker_outputs(args):
    _write_artifact(
        __import__("pathlib").Path(args.output)
    )
    _write_artifact(
        __import__("pathlib").Path(args.summary),
        "{}",
    )
    return {}


@pytest.fixture
def pipeline_context(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    run_paths = RunPaths.create(
        "pipeline-cancellation-test",
        tmp_path / "runs",
    )

    config = PipelineConfig(
        input_dir=input_dir,
        start_sol=100,
        end_sol=100,
    )

    _patch_successful_analyzers(monkeypatch)

    return config, run_paths


def test_pipeline_cancels_before_first_stage(
    pipeline_context,
    monkeypatch,
):
    config, run_paths = pipeline_context

    calls = {"discovery": 0}

    def track_discovery(input_dir):
        calls["discovery"] += 1
        return []

    monkeypatch.setattr(
        pipeline_executor.file_discovery,
        "discover_files",
        track_discovery,
    )

    cancel_event = Event()
    cancel_event.set()

    result = execute_pipeline_stages(
        config,
        run_paths,
        cancel_event=cancel_event,
    )

    assert result.status == "cancelled"
    assert result.successful is False

    assert calls["discovery"] == 0

    assert [
        stage.status
        for stage in result.stage_results
    ] == [
        "cancelled",
        "cancelled",
        "cancelled",
        "cancelled",
        "cancelled",
        "cancelled",
    ]

    assert [
        stage.stage_name
        for stage in result.stage_results
    ] == [
        "file_discovery",
        "xml_parser",
        "coverage_analyzer",
        "quality_analyzer",
        "synchronization_analyzer",
        "period_ranker",
    ]


def test_pipeline_finishes_current_stage_then_cancels_remaining(
    pipeline_context,
    monkeypatch,
):
    config, run_paths = pipeline_context

    cancel_event = Event()
    calls = {
        "quality": 0,
        "synchronization": 0,
        "ranker": 0,
    }

    def quality_requests_cancellation(
        input_dir,
        inventory,
        metadata,
    ):
        calls["quality"] += 1

        # Simulate a cancellation request while the current analyzer
        # is running. The current stage must still finish normally.
        cancel_event.set()

        return [{"analysis_status": "analysed"}]

    def track_synchronization(*args, **kwargs):
        calls["synchronization"] += 1
        return [], []

    def track_ranker(args):
        calls["ranker"] += 1
        return {}

    monkeypatch.setattr(
        pipeline_executor.quality_analyzer,
        "run_analysis",
        quality_requests_cancellation,
    )

    monkeypatch.setattr(
        pipeline_executor.synchronization_analyzer,
        "run_analysis",
        track_synchronization,
    )

    monkeypatch.setattr(
        pipeline_executor.period_ranker,
        "run",
        track_ranker,
    )

    result = execute_pipeline_stages(
        config,
        run_paths,
        cancel_event=cancel_event,
    )

    assert result.status == "cancelled"
    assert result.successful is False

    assert [
        stage.status
        for stage in result.stage_results
    ] == [
        "completed",
        "completed",
        "completed",
        "completed",
        "cancelled",
        "cancelled",
    ]

    assert calls["quality"] == 1
    assert calls["synchronization"] == 0
    assert calls["ranker"] == 0

    # Artifacts from completed stages must remain available.
    assert (
        run_paths.output_dir / "file_inventory.csv"
    ).is_file()

    assert (
        run_paths.output_dir / "metadata_inventory.json"
    ).is_file()

    assert (
        run_paths.output_dir / "coverage_report.csv"
    ).is_file()

    assert (
        run_paths.output_dir / "quality_field_report.csv"
    ).is_file()

    # Later stages must not create their artifacts.
    assert not (
        run_paths.output_dir / "synchronization_file_report.csv"
    ).exists()

    assert not (
        run_paths.output_dir / "period_ranking.csv"
    ).exists()


def test_pipeline_rejects_invalid_cancel_event(
    pipeline_context,
):
    config, run_paths = pipeline_context

    with pytest.raises(
        TypeError,
        match="threading.Event",
    ):
        execute_pipeline_stages(
            config,
            run_paths,
            cancel_event=True,
        )


def test_pipeline_remains_backward_compatible_without_cancel_event(
    pipeline_context,
):
    config, run_paths = pipeline_context

    result = execute_pipeline_stages(
        config,
        run_paths,
    )

    assert result.status == "completed"
    assert result.successful is True

    assert [
        stage.status
        for stage in result.stage_results
    ] == [
        "completed",
        "completed",
        "completed",
        "completed",
        "completed",
        "completed",
    ]