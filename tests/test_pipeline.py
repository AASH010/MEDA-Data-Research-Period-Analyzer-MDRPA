import json
from pathlib import Path

import pytest

from backend.pipeline.pipeline_validator import (
    PipelineConfig,
    validate_pipeline_config,
)
from backend.pipeline import pipeline_executor
from backend.pipeline.pipeline_executor import execute_pipeline_stages
from backend.run_manager.run_paths import RunPaths


# =========================================================
# Pipeline Validator Tests
# =========================================================


def test_default_config_values(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    config = validate_pipeline_config({"input_dir": input_dir})

    assert config.input_dir == input_dir.resolve()
    assert config.start_sol is None
    assert config.end_sol is None
    assert config.gap_factor == 2.5
    assert config.tolerance == 1.0
    assert config.window_size == 10
    assert config.min_sol_fraction == 0.5
    assert config.min_metrics == 3


def test_valid_mapping_config(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    config = validate_pipeline_config({
        "input_dir": input_dir,
        "start_sol": 100,
        "end_sol": 200,
        "gap_factor": 3,
        "tolerance": 2,
        "window_size": 5,
        "min_sol_fraction": 0.75,
        "min_metrics": 2,
        "required_products": ["ats", "ps"],
    })

    assert config.start_sol == 100
    assert config.end_sol == 200
    assert config.gap_factor == 3.0
    assert config.tolerance == 2.0
    assert config.window_size == 5
    assert config.min_sol_fraction == 0.75
    assert config.min_metrics == 2
    assert config.required_products == ("ATS", "PS")


def test_config_instance_is_validated(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    config = PipelineConfig(input_dir=input_dir)
    validated = validate_pipeline_config(config)

    assert validated.input_dir == input_dir.resolve()


@pytest.mark.parametrize("input_value", [None, "", 123])
def test_invalid_input_dir_type_or_value(input_value):
    with pytest.raises((TypeError, ValueError)):
        validate_pipeline_config({"input_dir": input_value})


def test_missing_input_dir_is_rejected():
    with pytest.raises(ValueError):
        validate_pipeline_config({})


def test_nonexistent_input_dir_is_rejected(tmp_path):
    with pytest.raises((ValueError, FileNotFoundError)):
        validate_pipeline_config({"input_dir": tmp_path / "missing"})


def test_input_dir_must_be_directory(tmp_path):
    file_path = tmp_path / "input.txt"
    file_path.write_text("test", encoding="utf-8")

    with pytest.raises((ValueError, NotADirectoryError)):
        validate_pipeline_config({"input_dir": file_path})


def test_unknown_config_key_is_rejected(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises(ValueError):
        validate_pipeline_config({
            "input_dir": input_dir,
            "unknown_option": True,
        })


@pytest.mark.parametrize(
    "start_sol,end_sol",
    [
        (-1, 10),
        (10, -1),
        (20, 10),
        (True, 10),
        (10, False),
    ],
)
def test_invalid_sol_range_is_rejected(tmp_path, start_sol, end_sol):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises((TypeError, ValueError)):
        validate_pipeline_config({
            "input_dir": input_dir,
            "start_sol": start_sol,
            "end_sol": end_sol,
        })


@pytest.mark.parametrize(
    "config_values,expected_start,expected_end",
    [
        ({"start_sol": 10}, 10, None),
        ({"end_sol": 20}, None, 20),
    ],
)
def test_partial_sol_range_is_accepted(
    tmp_path,
    config_values,
    expected_start,
    expected_end,
):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    config = validate_pipeline_config({
        "input_dir": input_dir,
        **config_values,
    })

    assert config.start_sol == expected_start
    assert config.end_sol == expected_end


@pytest.mark.parametrize(
    "field,value",
    [
        ("gap_factor", 0),
        ("gap_factor", -1),
        ("gap_factor", float("inf")),
        ("gap_factor", float("nan")),
        ("tolerance", 0),
        ("tolerance", -1),
        ("tolerance", float("inf")),
        ("tolerance", float("nan")),
    ],
)
def test_invalid_positive_numeric_parameters(tmp_path, field, value):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises((TypeError, ValueError)):
        validate_pipeline_config({
            "input_dir": input_dir,
            field: value,
        })


@pytest.mark.parametrize(
    "window_size",
    [0, -1, 1.5, True, "5"],
)
def test_invalid_window_size_is_rejected(tmp_path, window_size):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises((TypeError, ValueError)):
        validate_pipeline_config({
            "input_dir": input_dir,
            "window_size": window_size,
        })


@pytest.mark.parametrize(
    "fraction",
    [0, -0.1, 1.1, float("inf"), float("nan")],
)
def test_invalid_min_sol_fraction_is_rejected(tmp_path, fraction):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises((TypeError, ValueError)):
        validate_pipeline_config({
            "input_dir": input_dir,
            "min_sol_fraction": fraction,
        })


@pytest.mark.parametrize(
    "min_metrics",
    [0, 5, -1, 1.5, True, "3"],
)
def test_invalid_min_metrics_is_rejected(tmp_path, min_metrics):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises((TypeError, ValueError)):
        validate_pipeline_config({
            "input_dir": input_dir,
            "min_metrics": min_metrics,
        })


def test_required_products_are_normalized(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    config = validate_pipeline_config({
        "input_dir": input_dir,
        "required_products": [" ats ", "ps", "ATS", "rds"],
    })

    assert config.required_products == ("ATS", "PS", "RDS")


@pytest.mark.parametrize("products", [[], (), ""])
def test_empty_required_products_are_rejected(tmp_path, products):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises((ValueError, TypeError)):
        validate_pipeline_config({
            "input_dir": input_dir,
            "required_products": products,
        })


@pytest.mark.parametrize("products", [None, 123, {"ATS"}])
def test_invalid_required_products_type_is_rejected(tmp_path, products):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises((TypeError, ValueError)):
        validate_pipeline_config({
            "input_dir": input_dir,
            "required_products": products,
        })


@pytest.mark.parametrize(
    "field,value",
    [
        ("weight_files", -0.1),
        ("weight_integrity", -0.1),
        ("weight_quality", -0.1),
        ("weight_sync", -0.1),
        ("integrity_timestamps", -0.1),
        ("integrity_values", -0.1),
        ("weight_files", float("inf")),
        ("weight_integrity", float("nan")),
        ("weight_quality", True),
    ],
)
def test_invalid_weights_are_rejected(tmp_path, field, value):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises((TypeError, ValueError)):
        validate_pipeline_config({
            "input_dir": input_dir,
            field: value,
        })


def test_all_ranking_weights_zero_are_rejected(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises(ValueError):
        validate_pipeline_config({
            "input_dir": input_dir,
            "weight_files": 0,
            "weight_integrity": 0,
            "weight_quality": 0,
            "weight_sync": 0,
        })


def test_all_integrity_weights_zero_are_rejected(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises(ValueError):
        validate_pipeline_config({
            "input_dir": input_dir,
            "integrity_timestamps": 0,
            "integrity_values": 0,
        })


# =========================================================
# Pipeline Executor Test Helpers
# =========================================================


def _write_test_artifact(path, content="test"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _patch_successful_analyzers(
    monkeypatch,
    sols=(100,),
):
    """Replace analyzer work with predictable test doubles."""

    inventory_records = [
        {
            "sol_number": sol,
            "sol_folder": f"SOL{sol}",
            "filename": f"sample_{sol}.csv",
            "extension": ".csv",
            "product_code": "ATS",
        }
        for sol in sols
    ]

    coverage_reports = [
        {
            "sol_number": sol,
            "product_code": "ATS",
            "row_count": 1,
            "numeric_value_count": 2,
            "parsed_timestamp_count": 1,
            "measurement_coverage_status": (
                "timestamp_analysis_available"
            ),
        }
        for sol in sols
    ]

    monkeypatch.setattr(
        pipeline_executor.file_discovery,
        "discover_files",
        lambda input_dir: inventory_records,
    )

    monkeypatch.setattr(
        pipeline_executor.file_discovery,
        "write_inventory",
        lambda records, path: _write_test_artifact(path),
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
        lambda data, path: _write_test_artifact(path),
    )

    monkeypatch.setattr(
        pipeline_executor.coverage_analyzer,
        "analyze_coverage",
        lambda input_dir, inventory, metadata, gap_factor: (
            coverage_reports
        ),
    )

    monkeypatch.setattr(
        pipeline_executor.coverage_analyzer,
        "save_coverage_csv",
        lambda reports, path: _write_test_artifact(path),
    )

    # Keep the real build_product_summary and save_summary_json.
    # These are the functions whose range behavior is under test.

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
        lambda path, rows: _write_test_artifact(path),
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
        lambda path, summary: _write_test_artifact(path),
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
        lambda path, rows, columns: _write_test_artifact(path),
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
        lambda path, summary: _write_test_artifact(path),
    )

    def fake_ranker_run(args):
        _write_test_artifact(Path(args.output))
        _write_test_artifact(Path(args.summary))
        return {"rankable_windows": 1}

    monkeypatch.setattr(
        pipeline_executor.period_ranker,
        "run",
        fake_ranker_run,
    )


def _read_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


# =========================================================
# Pipeline Executor Tests
# =========================================================


def test_pipeline_executor_completes_all_stages(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    run_paths = RunPaths.create(
        "executor-success",
        tmp_path / "runs",
    )

    config = PipelineConfig(input_dir=input_dir)
    _patch_successful_analyzers(monkeypatch)

    result = execute_pipeline_stages(config, run_paths)

    assert result.run_id == "executor-success"
    assert result.status == "completed"
    assert result.successful is True

    assert [
        stage.stage_name for stage in result.stage_results
    ] == [
        "file_discovery",
        "xml_parser",
        "coverage_analyzer",
        "quality_analyzer",
        "synchronization_analyzer",
        "period_ranker",
    ]

    assert all(
        stage.status == "completed"
        for stage in result.stage_results
    )

    assert result.stage_results[0].summary["supported_file_count"] == 1

    expected_files = [
        "file_inventory.csv",
        "metadata_inventory.json",
        "coverage_report.csv",
        "coverage_summary.json",
        "coverage_range_summary.json",
        "quality_field_report.csv",
        "quality_summary.json",
        "synchronization_file_report.csv",
        "synchronization_pair_report.csv",
        "synchronization_summary.json",
        "period_ranking.csv",
        "period_ranking_summary.json",
    ]

    for filename in expected_files:
        artifact = run_paths.output_dir / filename
        assert artifact.is_file()
        assert artifact.parent == run_paths.output_dir


def test_pipeline_executor_creates_identical_summaries_without_selected_range(
    tmp_path,
    monkeypatch,
):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    run_paths = RunPaths.create(
        "executor-default-coverage-range",
        tmp_path / "runs",
    )

    config = PipelineConfig(input_dir=input_dir)
    _patch_successful_analyzers(
        monkeypatch,
        sols=(100, 101, 102),
    )

    result = execute_pipeline_stages(config, run_paths)

    assert result.status == "completed"

    full_summary = _read_json(
        run_paths.output_dir / "coverage_summary.json"
    )
    range_summary = _read_json(
        run_paths.output_dir / "coverage_range_summary.json"
    )

    assert full_summary == range_summary

    assert full_summary["start_sol"] == 100
    assert full_summary["end_sol"] == 102
    assert full_summary["report_count"] == 3

    assert full_summary["products"]["ATS"]["present_sols"] == [
        100,
        101,
        102,
    ]


def test_pipeline_executor_separates_full_and_selected_range_summaries(
    tmp_path,
    monkeypatch,
):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    run_paths = RunPaths.create(
        "executor-selected-coverage-range",
        tmp_path / "runs",
    )

    config = PipelineConfig(
        input_dir=input_dir,
        start_sol=101,
        end_sol=102,
    )

    _patch_successful_analyzers(
        monkeypatch,
        sols=(100, 101, 102, 103),
    )

    result = execute_pipeline_stages(config, run_paths)

    assert result.status == "completed"

    full_summary = _read_json(
        run_paths.output_dir / "coverage_summary.json"
    )
    range_summary = _read_json(
        run_paths.output_dir / "coverage_range_summary.json"
    )

    # Full dataset summary must retain every observed SOL.
    assert full_summary["start_sol"] == 100
    assert full_summary["end_sol"] == 103
    assert full_summary["report_count"] == 4

    assert full_summary["products"]["ATS"]["present_sols"] == [
        100,
        101,
        102,
        103,
    ]

    # Selected range summary must include only the requested SOLs.
    assert range_summary["start_sol"] == 101
    assert range_summary["end_sol"] == 102
    assert range_summary["report_count"] == 2

    assert range_summary["products"]["ATS"]["present_sols"] == [
        101,
        102,
    ]

    assert range_summary["products"]["ATS"]["csv_file_count"] == 2
    assert range_summary["products"]["ATS"]["total_rows"] == 2

    assert full_summary != range_summary

    coverage_stage = next(
        stage
        for stage in result.stage_results
        if stage.stage_name == "coverage_analyzer"
    )

    assert coverage_stage.summary["observed_range"] == {
        "start_sol": 100,
        "end_sol": 103,
    }

    assert (
        coverage_stage.summary["full_dataset"]["report_count"]
        == 4
    )

    assert (
        coverage_stage.summary["selected_range"]["report_count"]
        == 2
    )


@pytest.mark.parametrize(
    "start_sol,end_sol,expected_start,expected_end",
    [
        (102, None, 102, 103),
        (None, 101, 100, 101),
    ],
)
def test_pipeline_executor_resolves_partial_selected_range(
    tmp_path,
    monkeypatch,
    start_sol,
    end_sol,
    expected_start,
    expected_end,
):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    run_paths = RunPaths.create(
        f"executor-partial-range-{expected_start}-{expected_end}",
        tmp_path / "runs",
    )

    config = PipelineConfig(
        input_dir=input_dir,
        start_sol=start_sol,
        end_sol=end_sol,
    )

    _patch_successful_analyzers(
        monkeypatch,
        sols=(100, 101, 102, 103),
    )

    result = execute_pipeline_stages(config, run_paths)

    assert result.status == "completed"

    full_summary = _read_json(
        run_paths.output_dir / "coverage_summary.json"
    )
    range_summary = _read_json(
        run_paths.output_dir / "coverage_range_summary.json"
    )

    assert full_summary["start_sol"] == 100
    assert full_summary["end_sol"] == 103
    assert full_summary["report_count"] == 4

    assert range_summary["start_sol"] == expected_start
    assert range_summary["end_sol"] == expected_end

    expected_sols = list(
        range(expected_start, expected_end + 1)
    )

    assert range_summary["products"]["ATS"]["present_sols"] == (
        expected_sols
    )

    assert range_summary["report_count"] == len(expected_sols)


def test_pipeline_executor_rejects_non_overlapping_selected_range(
    tmp_path,
    monkeypatch,
):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    run_paths = RunPaths.create(
        "executor-non-overlapping-range",
        tmp_path / "runs",
    )

    config = PipelineConfig(
        input_dir=input_dir,
        start_sol=200,
        end_sol=300,
    )

    _patch_successful_analyzers(
        monkeypatch,
        sols=(100, 101, 102),
    )

    result = execute_pipeline_stages(config, run_paths)

    assert result.status == "failed"
    assert result.successful is False

    coverage_stage = next(
        stage
        for stage in result.stage_results
        if stage.stage_name == "coverage_analyzer"
    )

    assert coverage_stage.status == "failed"
    assert coverage_stage.errors
    assert "does not overlap the observed dataset range" in (
        coverage_stage.errors[0]
    )

    # The full-dataset summary is generated before selected-range
    # validation and remains available for inspection.
    assert (
        run_paths.output_dir / "coverage_summary.json"
    ).is_file()

    # The selected-range summary must not be created for an invalid range.
    assert not (
        run_paths.output_dir / "coverage_range_summary.json"
    ).exists()

    assert [
        stage.status for stage in result.stage_results
    ] == [
        "completed",
        "completed",
        "failed",
        "skipped",
        "skipped",
        "skipped",
    ]


def test_pipeline_executor_rejects_unsupported_files(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    run_paths = RunPaths.create(
        "executor-unsupported-files",
        tmp_path / "runs",
    )

    config = PipelineConfig(input_dir=input_dir)

    monkeypatch.setattr(
        pipeline_executor.file_discovery,
        "discover_files",
        lambda directory: [
            {
                "sol_number": 100,
                "sol_folder": "SOL100",
                "filename": "notes.txt",
                "extension": ".txt",
            }
        ],
    )

    monkeypatch.setattr(
        pipeline_executor.file_discovery,
        "write_inventory",
        lambda records, path: _write_test_artifact(path),
    )

    result = execute_pipeline_stages(config, run_paths)

    assert result.status == "failed"
    assert result.successful is False

    file_discovery_stage = result.stage_results[0]

    assert file_discovery_stage.stage_name == "file_discovery"
    assert file_discovery_stage.status == "failed"
    assert file_discovery_stage.errors
    assert "no supported CSV or XML files" in file_discovery_stage.errors[0]

    assert (run_paths.output_dir / "file_inventory.csv").is_file()

    assert [
        stage.status for stage in result.stage_results[1:]
    ] == [
        "skipped",
        "skipped",
        "skipped",
        "skipped",
        "skipped",
    ]


def test_pipeline_executor_accepts_filename_extension_fallback(
    tmp_path,
    monkeypatch,
):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    run_paths = RunPaths.create(
        "executor-extension-fallback",
        tmp_path / "runs",
    )

    config = PipelineConfig(input_dir=input_dir)
    _patch_successful_analyzers(monkeypatch)

    result = execute_pipeline_stages(config, run_paths)

    assert result.status == "completed"

    discovery_stage = result.stage_results[0]

    assert discovery_stage.status == "completed"
    assert discovery_stage.summary["supported_file_count"] == 1


def test_pipeline_executor_completes_with_xml_warnings(
    tmp_path,
    monkeypatch,
):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    run_paths = RunPaths.create(
        "executor-xml-warnings",
        tmp_path / "runs",
    )

    config = PipelineConfig(input_dir=input_dir)
    _patch_successful_analyzers(monkeypatch)

    monkeypatch.setattr(
        pipeline_executor.xml_parser,
        "build_metadata_inventory",
        lambda directory: {
            "records": [
                {"parse_status": "success"},
                {"parse_status": "failed"},
            ],
            "summary": {
                "xml_files_discovered": 2,
                "successfully_parsed": 1,
                "failed_to_parse": 1,
            },
        },
    )

    result = execute_pipeline_stages(config, run_paths)

    assert result.status == "completed_with_warnings"
    assert result.successful is True

    xml_stage = next(
        stage
        for stage in result.stage_results
        if stage.stage_name == "xml_parser"
    )

    assert xml_stage.status == "completed_with_warnings"
    assert xml_stage.warnings
    assert "1 XML file(s)" in xml_stage.warnings[0]

    assert [
        stage.status for stage in result.stage_results
    ] == [
        "completed",
        "completed_with_warnings",
        "completed",
        "completed",
        "completed",
        "completed",
    ]

    assert (run_paths.output_dir / "period_ranking.csv").is_file()


def test_pipeline_executor_stops_after_stage_failure(
    tmp_path,
    monkeypatch,
):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    run_paths = RunPaths.create(
        "executor-failure",
        tmp_path / "runs",
    )

    config = PipelineConfig(input_dir=input_dir)
    _patch_successful_analyzers(monkeypatch)

    calls = {
        "synchronization": 0,
        "ranker": 0,
    }

    def fail_quality(*args, **kwargs):
        raise RuntimeError("quality stage test failure")

    def track_synchronization(*args, **kwargs):
        calls["synchronization"] += 1
        return [], []

    def track_ranker(args):
        calls["ranker"] += 1
        return {}

    monkeypatch.setattr(
        pipeline_executor.quality_analyzer,
        "run_analysis",
        fail_quality,
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

    result = execute_pipeline_stages(config, run_paths)

    assert result.status == "failed"
    assert result.successful is False

    statuses = {
        stage.stage_name: stage.status
        for stage in result.stage_results
    }

    assert statuses == {
        "file_discovery": "completed",
        "xml_parser": "completed",
        "coverage_analyzer": "completed",
        "quality_analyzer": "failed",
        "synchronization_analyzer": "skipped",
        "period_ranker": "skipped",
    }

    assert calls["synchronization"] == 0
    assert calls["ranker"] == 0

    quality_stage = next(
        stage
        for stage in result.stage_results
        if stage.stage_name == "quality_analyzer"
    )

    assert quality_stage.errors
    assert "quality stage test failure" in quality_stage.errors[0]

    assert (run_paths.output_dir / "file_inventory.csv").is_file()
    assert (run_paths.output_dir / "metadata_inventory.json").is_file()
    assert (run_paths.output_dir / "coverage_report.csv").is_file()

    assert not (
        run_paths.output_dir / "synchronization_file_report.csv"
    ).exists()

    assert not (
        run_paths.output_dir / "period_ranking.csv"
    ).exists()


def test_pipeline_executor_requires_validated_config(tmp_path):
    run_paths = RunPaths.create(
        "executor-invalid-config",
        tmp_path / "runs",
    )

    with pytest.raises(TypeError):
        execute_pipeline_stages({"input_dir": tmp_path}, run_paths)


def test_pipeline_executor_requires_run_paths(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    config = PipelineConfig(input_dir=input_dir)

    with pytest.raises(TypeError):
        execute_pipeline_stages(config, tmp_path)


def test_pipeline_executor_rejects_missing_output_directory(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    run_paths = RunPaths.create(
        "executor-missing-output",
        tmp_path / "runs",
    )

    run_paths.output_dir.rmdir()

    config = PipelineConfig(input_dir=input_dir)

    with pytest.raises(FileNotFoundError):
        execute_pipeline_stages(config, run_paths)


# =========================================================
# Analysis Pipeline Test Helpers
# =========================================================

from backend.pipeline import analysis_pipeline
from backend.pipeline.analysis_pipeline import (
    AnalysisPipeline,
    PipelineRunResult,
)
from backend.pipeline.pipeline_executor import (
    PipelineExecutionResult,
    PipelineStageResult,
)
from backend.run_manager.run_manager import RunManager
from backend.run_manager.run_status import RunStatus


@pytest.fixture
def analysis_pipeline_instance(tmp_path):
    manager = RunManager(runs_root=tmp_path / "runs")
    return AnalysisPipeline(manager), manager


@pytest.fixture
def valid_pipeline_config(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    return PipelineConfig(
        input_dir=input_dir,
        start_sol=100,
        end_sol=200,
    )


# =========================================================
# Analysis Pipeline Construction Tests
# =========================================================


def test_analysis_pipeline_requires_run_manager():
    with pytest.raises(TypeError, match="RunManager"):
        AnalysisPipeline(object())


# =========================================================
# Successful Run Lifecycle Tests
# =========================================================


def test_analysis_pipeline_completes_run(
    analysis_pipeline_instance,
    valid_pipeline_config,
    monkeypatch,
):
    pipeline, manager = analysis_pipeline_instance

    def fake_execute(config, run_paths):
        return PipelineExecutionResult(
            run_id=run_paths.run_id,
            status="completed",
            stage_results=(),
        )

    monkeypatch.setattr(
        analysis_pipeline,
        "execute_pipeline_stages",
        fake_execute,
    )

    result = pipeline.execute(
        valid_pipeline_config,
        input_source="MEDA",
        application_version="1.0",
    )

    assert isinstance(result, PipelineRunResult)
    assert result.status == RunStatus.COMPLETED.value
    assert result.successful is True
    assert result.error is None
    assert result.execution is not None

    stored_record = manager.get_run(result.run_id)

    assert stored_record.status is RunStatus.COMPLETED
    assert stored_record.metadata.status == "COMPLETED"
    assert stored_record.metadata.start_sol == 100
    assert stored_record.metadata.end_sol == 200
    assert stored_record.metadata.input_source == "MEDA"
    assert stored_record.metadata.application_version == "1.0"

    assert (
        stored_record.metadata.settings["input_dir"]
        == str(valid_pipeline_config.input_dir.resolve())
    )

    assert (
        stored_record.metadata.settings["required_products"]
        == list(valid_pipeline_config.required_products)
    )


def test_analysis_pipeline_uses_supplied_run_id(
    analysis_pipeline_instance,
    valid_pipeline_config,
    monkeypatch,
):
    pipeline, manager = analysis_pipeline_instance

    monkeypatch.setattr(
        analysis_pipeline,
        "execute_pipeline_stages",
        lambda config, paths: PipelineExecutionResult(
            run_id=paths.run_id,
            status="completed",
            stage_results=(),
        ),
    )

    result = pipeline.execute(
        valid_pipeline_config,
        run_id="manual-pipeline-run",
    )

    assert result.run_id == "manual-pipeline-run"
    assert manager.get_run("manual-pipeline-run").status is RunStatus.COMPLETED


def test_analysis_pipeline_generates_range_run_id(
    analysis_pipeline_instance,
    valid_pipeline_config,
    monkeypatch,
):
    pipeline, manager = analysis_pipeline_instance

    monkeypatch.setattr(
        analysis_pipeline,
        "execute_pipeline_stages",
        lambda config, paths: PipelineExecutionResult(
            run_id=paths.run_id,
            status="completed",
            stage_results=(),
        ),
    )

    result = pipeline.execute(valid_pipeline_config)

    assert result.run_id == "run_range(100-200)_001"
    assert manager.get_run(result.run_id).status is RunStatus.COMPLETED


# =========================================================
# Failed Execution Lifecycle Tests
# =========================================================


def test_analysis_pipeline_marks_run_failed_when_stage_fails(
    analysis_pipeline_instance,
    valid_pipeline_config,
    monkeypatch,
):
    pipeline, manager = analysis_pipeline_instance

    def fake_execute(config, run_paths):
        return PipelineExecutionResult(
            run_id=run_paths.run_id,
            status="failed",
            stage_results=(),
        )

    monkeypatch.setattr(
        analysis_pipeline,
        "execute_pipeline_stages",
        fake_execute,
    )

    result = pipeline.execute(valid_pipeline_config)

    assert result.status == RunStatus.FAILED.value
    assert result.successful is False
    assert result.error is None
    assert result.execution is not None
    assert result.execution.status == "failed"

    stored_record = manager.get_run(result.run_id)

    assert stored_record.status is RunStatus.FAILED
    assert stored_record.metadata.status == "FAILED"


def test_analysis_pipeline_marks_run_failed_on_executor_exception(
    analysis_pipeline_instance,
    valid_pipeline_config,
    monkeypatch,
):
    pipeline, manager = analysis_pipeline_instance

    def raise_executor_error(config, run_paths):
        raise RuntimeError("unexpected executor error")

    monkeypatch.setattr(
        analysis_pipeline,
        "execute_pipeline_stages",
        raise_executor_error,
    )

    result = pipeline.execute(valid_pipeline_config)

    assert result.status == RunStatus.FAILED.value
    assert result.successful is False
    assert result.execution is None
    assert result.error is not None
    assert "unexpected executor error" in result.error

    stored_record = manager.get_run(result.run_id)

    assert stored_record.status is RunStatus.FAILED
    assert stored_record.metadata.status == "FAILED"


def test_analysis_pipeline_persists_stage_failure_details(
    analysis_pipeline_instance,
    valid_pipeline_config,
    monkeypatch,
):
    pipeline, manager = analysis_pipeline_instance

    def fake_execute(config, run_paths):
        return PipelineExecutionResult(
            run_id=run_paths.run_id,
            status="failed",
            stage_results=(
                PipelineStageResult(
                    stage_name="quality_analyzer",
                    status="failed",
                    started_at="2026-01-01T00:00:00",
                    finished_at="2026-01-01T00:00:01",
                    output_paths=(),
                    warnings=("Some quality fields were unavailable",),
                    errors=("Quality report generation failed",),
                    summary={"processed_records": 10},
                ),
                PipelineStageResult(
                    stage_name="synchronization_analyzer",
                    status="skipped",
                    started_at="2026-01-01T00:00:01",
                    finished_at="2026-01-01T00:00:01",
                ),
            ),
        )

    monkeypatch.setattr(
        analysis_pipeline,
        "execute_pipeline_stages",
        fake_execute,
    )

    result = pipeline.execute(valid_pipeline_config)

    assert result.status == RunStatus.FAILED.value
    assert result.execution is not None

    stored_record = manager.get_run(result.run_id)

    assert stored_record.status is RunStatus.FAILED
    assert stored_record.metadata.status == "FAILED"
    assert (
        stored_record.metadata.failure_reason
        == "quality_analyzer: Quality report generation failed"
    )

    execution_summary = stored_record.metadata.settings["execution_summary"]

    assert execution_summary["status"] == "failed"
    assert execution_summary["error"] is None
    assert len(execution_summary["stages"]) == 2

    failed_stage = execution_summary["stages"][0]

    assert failed_stage["stage_name"] == "quality_analyzer"
    assert failed_stage["status"] == "failed"
    assert failed_stage["warnings"] == [
        "Some quality fields were unavailable"
    ]
    assert failed_stage["errors"] == [
        "Quality report generation failed"
    ]

    skipped_stage = execution_summary["stages"][1]

    assert skipped_stage["stage_name"] == "synchronization_analyzer"
    assert skipped_stage["status"] == "skipped"


def test_analysis_pipeline_persists_executor_exception(
    analysis_pipeline_instance,
    valid_pipeline_config,
    monkeypatch,
):
    pipeline, manager = analysis_pipeline_instance

    def raise_executor_error(config, run_paths):
        raise RuntimeError("unexpected executor error")

    monkeypatch.setattr(
        analysis_pipeline,
        "execute_pipeline_stages",
        raise_executor_error,
    )

    result = pipeline.execute(valid_pipeline_config)

    assert result.status == RunStatus.FAILED.value
    assert result.execution is None
    assert result.error is not None
    assert "unexpected executor error" in result.error

    stored_record = manager.get_run(result.run_id)

    assert stored_record.status is RunStatus.FAILED
    assert stored_record.metadata.status == "FAILED"
    assert stored_record.metadata.failure_reason == result.error

    execution_summary = stored_record.metadata.settings["execution_summary"]

    assert execution_summary["status"] == "failed"
    assert execution_summary["error"] == result.error
    assert execution_summary["stages"] == []


# =========================================================
# Validation and Run Creation Boundary Tests
# =========================================================


def test_analysis_pipeline_validates_before_creating_run(
    analysis_pipeline_instance,
    tmp_path,
):
    pipeline, manager = analysis_pipeline_instance

    with pytest.raises(
        FileNotFoundError,
        match="Input directory does not exist",
    ):
        pipeline.execute({
            "input_dir": tmp_path / "missing",
        })

    assert manager.list_runs() == ()


def test_analysis_pipeline_requires_range_for_generated_run_id(
    analysis_pipeline_instance,
    tmp_path,
):
    pipeline, manager = analysis_pipeline_instance

    input_dir = tmp_path / "input"
    input_dir.mkdir()

    config = PipelineConfig(input_dir=input_dir)

    with pytest.raises(ValueError, match="start_sol and end_sol"):
        pipeline.execute(config)

    assert manager.list_runs() == ()


def test_analysis_pipeline_allows_manual_id_without_sol_range(
    analysis_pipeline_instance,
    tmp_path,
    monkeypatch,
):
    pipeline, manager = analysis_pipeline_instance

    input_dir = tmp_path / "input"
    input_dir.mkdir()

    config = PipelineConfig(input_dir=input_dir)

    monkeypatch.setattr(
        analysis_pipeline,
        "execute_pipeline_stages",
        lambda validated, paths: PipelineExecutionResult(
            run_id=paths.run_id,
            status="completed",
            stage_results=(),
        ),
    )

    result = pipeline.execute(
        config,
        run_id="manual-no-sol-range",
    )

    assert result.status == RunStatus.COMPLETED.value
    assert result.run_id == "manual-no-sol-range"
    assert manager.get_run(result.run_id).metadata.start_sol is None


# =========================================================
# Executor Result Contract Tests
# =========================================================


def test_analysis_pipeline_rejects_non_result_from_executor(
    analysis_pipeline_instance,
    valid_pipeline_config,
    monkeypatch,
):
    pipeline, manager = analysis_pipeline_instance

    monkeypatch.setattr(
        analysis_pipeline,
        "execute_pipeline_stages",
        lambda config, paths: None,
    )

    result = pipeline.execute(valid_pipeline_config)

    assert result.status == RunStatus.FAILED.value
    assert result.execution is None
    assert result.error is not None
    assert "PipelineExecutionResult" in result.error

    assert manager.get_run(result.run_id).status is RunStatus.FAILED


def test_analysis_pipeline_rejects_mismatched_execution_run_id(
    analysis_pipeline_instance,
    valid_pipeline_config,
    monkeypatch,
):
    pipeline, manager = analysis_pipeline_instance

    monkeypatch.setattr(
        analysis_pipeline,
        "execute_pipeline_stages",
        lambda config, paths: PipelineExecutionResult(
            run_id="different-run",
            status="completed",
            stage_results=(),
        ),
    )

    result = pipeline.execute(valid_pipeline_config)

    assert result.status == RunStatus.FAILED.value
    assert result.execution is None
    assert result.error is not None
    assert "does not match" in result.error

    assert manager.get_run(result.run_id).status is RunStatus.FAILED


def test_pipeline_package_exports_public_api():
    from backend.pipeline import (
        AnalysisPipeline,
        PipelineConfig,
        PipelineExecutionResult,
        PipelineRunResult,
        PipelineStageResult,
        execute_pipeline_stages,
        validate_pipeline_config,
    )

    assert AnalysisPipeline is not None
    assert PipelineConfig is not None
    assert PipelineExecutionResult is not None
    assert PipelineRunResult is not None
    assert PipelineStageResult is not None
    assert callable(execute_pipeline_stages)
    assert callable(validate_pipeline_config)