
import csv
import json

from pathlib import Path

import csv
import json
import shutil

from pathlib import Path

from backend.pipeline.analysis_pipeline import AnalysisPipeline
from backend.pipeline.pipeline_validator import validate_pipeline_config
from backend.run_manager.run_manager import RunManager
from backend.run_manager.run_status import RunStatus


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


EXPECTED_ARTIFACTS = (
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
)


def read_csv_rows(path: Path) -> list[dict]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        return list(csv.DictReader(file))


def read_json(path: Path) -> dict:
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def test_pipeline_runs_all_six_stages_with_fixed_dataset(tmp_path):
    assert FIXTURE_DATASET.is_dir()

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

    run_id = "pipeline-fixed-dataset-integration"

    result = pipeline.execute(
        config,
        run_id=run_id,
    )

    # --------------------------------------------------
    # Overall pipeline result
    # --------------------------------------------------

    assert result.run_id == run_id
    assert result.successful is True
    assert result.error is None
    assert result.execution is not None
    assert result.execution.successful is True
    assert result.execution.status == "completed"

    # --------------------------------------------------
    # All six stages must execute in dependency order
    # --------------------------------------------------

    stage_results = result.execution.stage_results

    assert tuple(
        stage.stage_name
        for stage in stage_results
    ) == EXPECTED_STAGES

    assert all(
        stage.status == "completed"
        for stage in stage_results
    )

    # --------------------------------------------------
    # Run lifecycle
    # --------------------------------------------------

    stored_run = manager.get_run(run_id)

    assert stored_run is not None
    assert stored_run.status is RunStatus.COMPLETED
    assert stored_run.metadata.status == RunStatus.COMPLETED.value

    # --------------------------------------------------
    # Run-specific output artifacts
    # --------------------------------------------------

    output_dir = (
        tmp_path
        / "runs"
        / run_id
        / "output"
    )

    assert output_dir.is_dir()

    for filename in EXPECTED_ARTIFACTS:
        artifact = output_dir / filename

        assert artifact.is_file(), filename
        assert artifact.stat().st_size > 0, filename

    # --------------------------------------------------
    # File Discovery
    # --------------------------------------------------

    inventory_rows = read_csv_rows(
        output_dir / "file_inventory.csv"
    )

    assert len(inventory_rows) == 4

    discovered_products = {
        row["product_code"]
        for row in inventory_rows
    }

    assert discovered_products == {"ATS", "PS"}

    # --------------------------------------------------
    # XML Parser
    # --------------------------------------------------

    metadata = read_json(
        output_dir / "metadata_inventory.json"
    )

    assert metadata["summary"]["xml_files_discovered"] == 2
    assert metadata["summary"]["successfully_parsed"] == 2
    assert metadata["summary"]["failed_to_parse"] == 0

    assert len(metadata["records"]) == 2

    assert all(
        record["parse_status"] == "success"
        for record in metadata["records"]
    )

    # --------------------------------------------------
    # Coverage Analyzer
    # --------------------------------------------------

    coverage_rows = read_csv_rows(
        output_dir / "coverage_report.csv"
    )

    assert len(coverage_rows) == 2

    assert {
        row["product_code"]
        for row in coverage_rows
    } == {"ATS", "PS"}

    assert all(
        int(row["parsed_timestamp_count"]) == 3
        for row in coverage_rows
    )

    # --------------------------------------------------
    # Full and selected-range coverage summaries
    # --------------------------------------------------

    full_coverage_summary = read_json(
        output_dir / "coverage_summary.json"
    )

    range_coverage_summary = read_json(
        output_dir / "coverage_range_summary.json"
    )

    # The fixture contains only SOL100, and the selected
    # range is also SOL100. Both summaries must therefore
    # describe exactly the same dataset.
    assert full_coverage_summary == range_coverage_summary

    assert full_coverage_summary["start_sol"] == 100
    assert full_coverage_summary["end_sol"] == 100

    assert range_coverage_summary["start_sol"] == 100
    assert range_coverage_summary["end_sol"] == 100

    assert full_coverage_summary["report_count"] == len(
        coverage_rows
    )

    assert range_coverage_summary["report_count"] == len(
        coverage_rows
    )

    assert set(full_coverage_summary["products"]) == {
        "ATS",
        "PS",
    }

    assert set(range_coverage_summary["products"]) == {
        "ATS",
        "PS",
    }

    # --------------------------------------------------
    # Coverage stage summary
    # --------------------------------------------------

    coverage_stage = next(
        stage
        for stage in stage_results
        if stage.stage_name == "coverage_analyzer"
    )

    assert coverage_stage.summary is not None

    assert coverage_stage.summary["observed_range"] == {
        "start_sol": 100,
        "end_sol": 100,
    }

    assert (
        coverage_stage.summary["full_dataset"]
        == full_coverage_summary
    )

    assert (
        coverage_stage.summary["selected_range"]
        == range_coverage_summary
    )

    # --------------------------------------------------
    # Quality Analyzer
    # --------------------------------------------------

    quality_rows = read_csv_rows(
        output_dir / "quality_field_report.csv"
    )

    assert quality_rows

    quality_flag_rows = [
        row
        for row in quality_rows
        if row["field_name"] == "Quality_Flag"
        and row["field_type"] == "quality_field_candidate"
    ]

    assert len(quality_flag_rows) == 2

    assert all(
        row["analysis_status"] == "analysed"
        for row in quality_flag_rows
    )

    # --------------------------------------------------
    # Synchronization Analyzer
    # --------------------------------------------------

    sync_file_rows = read_csv_rows(
        output_dir / "synchronization_file_report.csv"
    )

    sync_pair_rows = read_csv_rows(
        output_dir / "synchronization_pair_report.csv"
    )

    assert len(sync_file_rows) == 2
    assert len(sync_pair_rows) == 1

    pair = sync_pair_rows[0]

    assert pair["sol_number"] == "100"
    assert pair["product_1"] == "ATS"
    assert pair["product_2"] == "PS"
    assert pair["comparison_status"] == "analysed"
    assert int(pair["matched_timestamps"]) == 3

    # --------------------------------------------------
    # Period Ranker
    # --------------------------------------------------

    ranking_rows = read_csv_rows(
        output_dir / "period_ranking.csv"
    )

    assert ranking_rows

    ranking_summary = read_json(
        output_dir / "period_ranking_summary.json"
    )

    assert ranking_summary["sol_range"] == {
        "start": 100,
        "end": 100,
    }

    assert (
        ranking_summary["sol_range_detection"]["analysis_start"]
        == 100
    )

    assert (
        ranking_summary["sol_range_detection"]["analysis_end"]
        == 100
    )

    # --------------------------------------------------
    # Every stage must write only inside this run
    # --------------------------------------------------

    for stage in stage_results:
        assert stage.output_paths

        for output_path in stage.output_paths:
            assert output_path.is_file()
            assert output_path.parent == output_dir

def test_pipeline_integrates_special_constants_from_xml_to_quality_summary(
    tmp_path,
):
    # --------------------------------------------------
    # Prepare an isolated copy of the existing fixture
    # --------------------------------------------------

    input_dir = tmp_path / "special_constants_dataset"

    shutil.copytree(
        FIXTURE_DATASET,
        input_dir,
    )

    ats_xml_path = (
        input_dir
        / "SOL100"
        / "WE__0100__SAMPLE_CAL_ATS.xml"
    )

    ats_csv_path = (
        input_dir
        / "SOL100"
        / "WE__0100__SAMPLE_CAL_ATS.csv"
    )

    # --------------------------------------------------
    # Add documented Special Constants to Temperature
    # --------------------------------------------------

    xml_content = ats_xml_path.read_text(
        encoding="utf-8",
    )

    original_constants = """            <Special_Constants>
                <valid_minimum>-100</valid_minimum>
                <valid_maximum>100</valid_maximum>
            </Special_Constants>"""

    updated_constants = """            <Special_Constants>
                <valid_minimum>-100</valid_minimum>
                <valid_maximum>100</valid_maximum>
                <missing_constant>-999</missing_constant>
                <invalid_constant>-998</invalid_constant>
            </Special_Constants>"""

    assert xml_content.count(original_constants) == 1

    xml_content = xml_content.replace(
        original_constants,
        updated_constants,
        1,
    )

    ats_xml_path.write_text(
        xml_content,
        encoding="utf-8",
    )

    # --------------------------------------------------
    # Add matching values to the CSV
    # --------------------------------------------------

    csv_content = ats_csv_path.read_text(
        encoding="utf-8",
    )

    csv_content = csv_content.replace(
        "100M00:00:01,10.0,0",
        "100M00:00:01,-999,0",
        1,
    )

    csv_content = csv_content.replace(
        "100M00:00:02,11.0,1",
        "100M00:00:02,-998,1",
        1,
    )

    ats_csv_path.write_text(
        csv_content,
        encoding="utf-8",
    )

    # --------------------------------------------------
    # Execute the complete pipeline
    # --------------------------------------------------

    manager = RunManager(
        runs_root=tmp_path / "runs",
    )

    pipeline = AnalysisPipeline(manager)

    config = validate_pipeline_config({
        "input_dir": input_dir,
        "start_sol": 100,
        "end_sol": 100,
        "window_size": 1,
        "min_sol_fraction": 1.0,
        "min_metrics": 1,
        "required_products": ["ATS", "PS"],
    })

    run_id = "pipeline-special-constants-integration"

    result = pipeline.execute(
        config,
        run_id=run_id,
    )

    assert result.run_id == run_id
    assert result.successful is True
    assert result.error is None
    assert result.execution is not None
    assert result.execution.successful is True

    assert all(
        stage.status == "completed"
        for stage in result.execution.stage_results
    )

    output_dir = (
        tmp_path
        / "runs"
        / run_id
        / "output"
    )

    # --------------------------------------------------
    # Verify XML Parser -> Metadata Inventory
    # --------------------------------------------------

    metadata = read_json(
        output_dir / "metadata_inventory.json"
    )

    assert metadata["summary"]["successfully_parsed"] == 2

    ats_record = next(
        record
        for record in metadata["records"]
        if record["product_code"] == "ATS"
    )

    temperature_field = next(
        field
        for field in ats_record["fields"]
        if field["name"] == "Temperature"
    )

    assert temperature_field["special_constants"] == [
        {
            "valid_minimum": "-100",
            "valid_maximum": "100",
            "missing_constant": "-999",
            "invalid_constant": "-998",
        }
    ]

    # --------------------------------------------------
    # Verify Metadata Inventory -> Quality Report
    # --------------------------------------------------

    quality_rows = read_csv_rows(
        output_dir / "quality_field_report.csv"
    )

    special_rows = [
        row
        for row in quality_rows
        if row["product_code"] == "ATS"
        and row["field_name"] == "Temperature"
        and row["field_type"] == "special_constant_check"
    ]

    assert len(special_rows) == 1

    special_row = special_rows[0]

    assert special_row["analysis_status"] == "analysed"
    assert int(special_row["special_constant_count"]) == 2

    assert json.loads(
        special_row["special_constant_counts_json"]
    ) == {
        "invalid_constant": 1,
        "missing_constant": 1,
    }

    # --------------------------------------------------
    # Verify Quality Report -> Quality Summary
    # --------------------------------------------------

    quality_summary = read_json(
        output_dir / "quality_summary.json"
    )

    assert quality_summary["special_constant_check_reports"] == 1

    assert quality_summary["total_special_constant_matches"] == 2

    assert quality_summary["special_constant_type_counts"] == {
        "invalid_constant": 1,
        "missing_constant": 1,
    }
