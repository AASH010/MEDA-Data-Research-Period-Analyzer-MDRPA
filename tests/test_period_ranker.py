import csv
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.analyzers import period_ranker as ranker


def test_safe_float_rejects_non_finite_values():
    assert ranker.safe_float("12.5") == 12.5
    assert ranker.safe_float("nan") is None
    assert ranker.safe_float("inf") is None
    assert ranker.safe_float("invalid") is None


def test_safe_int_requires_integer_value():
    assert ranker.safe_int("12") == 12
    assert ranker.safe_int("12.0") == 12
    assert ranker.safe_int("12.5") is None


def test_normalized_weights():
    result = ranker.normalized_weights({
        "a": 2,
        "b": 2,
    })

    assert result == {
        "a": 0.5,
        "b": 0.5,
    }


def test_normalized_weights_rejects_negative_values():
    with pytest.raises(ValueError):
        ranker.normalized_weights({
            "a": -1,
            "b": 2,
        })


def test_normalized_weights_rejects_zero_total():
    with pytest.raises(ValueError):
        ranker.normalized_weights({
            "a": 0,
            "b": 0,
        })


def test_read_csv_returns_empty_for_missing_report(tmp_path):
    path = tmp_path / "missing.csv"

    assert ranker.read_csv(path) == []


def test_read_csv_validates_required_columns(tmp_path):
    path = tmp_path / "report.csv"

    path.write_text(
        "sol_number,extension\n"
        "100,csv\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Missing required columns"):
        ranker.read_csv(
            path,
            {"sol_number", "extension", "product_code"},
        )


def test_read_csv_accepts_valid_schema(tmp_path):
    path = tmp_path / "report.csv"

    path.write_text(
        "sol_number,extension,product_code\n"
        "100,csv,ATS\n",
        encoding="utf-8",
    )

    rows = ranker.read_csv(
        path,
        {"sol_number", "extension", "product_code"},
    )

    assert len(rows) == 1
    assert rows[0]["sol_number"] == "100"


def test_read_csv_rejects_headerless_report(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="no header"):
        ranker.read_csv(path)


def test_discover_sol_numbers_uses_union():
    result = ranker.discover_sol_numbers(
        [{"sol_number": "100"}, {"sol_number": "101"}],
        [{"sol_number": "103"}],
        [{"sol_number": "invalid"}],
    )

    assert result == {100, 101, 103}


def test_resolve_sol_range_automatic():
    result = ranker.resolve_sol_range(
        None,
        None,
        {100, 101, 105},
    )

    assert result == (
        100,
        105,
        "automatic_from_reports",
    )


def test_resolve_sol_range_explicit():
    result = ranker.resolve_sol_range(
        90,
        110,
        {100, 101, 105},
    )

    assert result == (90, 110, "explicit_cli")


def test_resolve_sol_range_rejects_empty_data():
    with pytest.raises(ValueError):
        ranker.resolve_sol_range(None, None, set())


def test_resolve_sol_range_rejects_reversed_range():
    with pytest.raises(ValueError):
        ranker.resolve_sol_range(110, 100, {100, 110})


def test_build_windows():
    assert ranker.build_windows(100, 124, 10) == [
        (100, 109),
        (110, 119),
        (120, 124),
    ]


def test_build_windows_rejects_invalid_size():
    with pytest.raises(ValueError):
        ranker.build_windows(100, 110, 0)


def test_analyse_inventory_counts_products():
    rows = [
        {
            "sol_number": "100",
            "extension": "csv",
            "product_code": "ATS",
            "pair_status": "matched",
        },
        {
            "sol_number": "100",
            "extension": "csv",
            "product_code": "PS",
            "pair_status": "missing_xml",
        },
        {
            "sol_number": "100",
            "extension": "xml",
            "product_code": "ATS",
            "pair_status": "matched",
        },
    ]

    result = ranker.analyse_inventory(rows, 100, 100)

    assert result[100]["products"] == {"ATS", "PS"}
    assert result[100]["csv_files"] == 2
    assert result[100]["xml_files"] == 1
    assert result[100]["missing_pairs"] == 1


def test_analyse_quality_counts_only_range_check_category():
    rows = [
        {
            "sol_number": "100",
            "field_type": "range_check",
            "analysis_status": "analysed",
            "numeric_count": "100",
            "below_valid_minimum": "5",
            "above_valid_maximum": "5",
            "valid_minimum": "0",
            "valid_maximum": "10",
        },
        {
            "sol_number": "100",
            "field_type": "quality_field_candidate",
            "analysis_status": "analysed",
            "numeric_count": "100",
            "below_valid_minimum": "5",
            "above_valid_maximum": "5",
            "valid_minimum": "0",
            "valid_maximum": "10",
        },
        {
            "sol_number": "100",
            "field_type": "measurement_uncertainty",
            "analysis_status": "analysed",
            "numeric_count": "100",
            "below_valid_minimum": "5",
            "above_valid_maximum": "5",
            "valid_minimum": "0",
            "valid_maximum": "10",
        },
    ]

    result = ranker.analyse_quality(rows)

    assert result[100]["field_reports"] == 3
    assert result[100]["analysed_fields"] == 3
    assert result[100]["range_checked_fields"] == 1
    assert result[100]["range_checked_values"] == 100
    assert result[100]["below_minimum"] == 5
    assert result[100]["above_maximum"] == 5


def test_analyse_quality_ignores_invalid_range_counts():
    rows = [
        {
            "sol_number": "100",
            "field_type": "range_check",
            "analysis_status": "analysed",
            "numeric_count": "10",
            "below_valid_minimum": "8",
            "above_valid_maximum": "5",
            "valid_minimum": "0",
            "valid_maximum": "10",
        },
    ]

    result = ranker.analyse_quality(rows)

    assert result[100]["range_checked_fields"] == 0
    assert result[100]["range_checked_values"] == 0


def test_analyse_quality_ignores_unanalysed_rows():
    rows = [
        {
            "sol_number": "100",
            "field_type": "range_check",
            "analysis_status": "not_analysed",
            "numeric_count": "10",
            "below_valid_minimum": "1",
            "above_valid_maximum": "1",
            "valid_minimum": "0",
            "valid_maximum": "10",
        },
    ]

    result = ranker.analyse_quality(rows)

    assert result[100]["analysed_fields"] == 0
    assert result[100]["range_checked_fields"] == 0


def test_calculate_sol_metrics_missing_inventory_is_unavailable():
    result = ranker.calculate_sol_metrics(
        sol=100,
        inventory={},
        coverage={},
        quality={},
        sync_files={},
        sync_pairs={},
        required_products=["ATS", "PS"],
        integrity_weights={
            "timestamps": 0.5,
            "values": 0.5,
        },
        inventory_available=False,
    )

    assert result["file_availability_score"] is None
    assert result["available_required_products"] == 0


def test_calculate_sol_metrics_empty_available_inventory_is_zero():
    result = ranker.calculate_sol_metrics(
        sol=100,
        inventory={},
        coverage={},
        quality={},
        sync_files={},
        sync_pairs={},
        required_products=["ATS", "PS"],
        integrity_weights={
            "timestamps": 0.5,
            "values": 0.5,
        },
        inventory_available=True,
    )

    assert result["file_availability_score"] == 0


def test_calculate_sol_metrics_inventory_score():
    inventory = {
        100: {
            "products": {"ATS", "PS"},
            "csv_files": 2,
            "xml_files": 2,
            "inventory_entries": 4,
            "missing_pairs": 0,
        }
    }

    result = ranker.calculate_sol_metrics(
        sol=100,
        inventory=inventory,
        coverage={},
        quality={},
        sync_files={},
        sync_pairs={},
        required_products=["ATS", "PS", "RDS", "WS"],
        integrity_weights={
            "timestamps": 0.5,
            "values": 0.5,
        },
    )

    assert result["file_availability_score"] == 50
    assert result["available_required_products"] == 2


def test_calculate_integrity():
    score, components = ranker.calculate_integrity(
        {
            "parsed_timestamps": 80,
            "missing_timestamps": 10,
            "invalid_timestamps": 10,
            "numeric_values": 90,
            "numeric_missing": 5,
            "numeric_invalid": 5,
        },
        {
            "timestamps": 0.5,
            "values": 0.5,
        },
    )

    assert score == 85
    assert components["timestamps"] == 80
    assert components["values"] == 90


def test_calculate_integrity_unavailable():
    score, components = ranker.calculate_integrity(
        {},
        {
            "timestamps": 0.5,
            "values": 0.5,
        },
    )

    assert score is None
    assert components == {}


def test_aggregate_window_rankable():
    metrics = {
        sol: {
            "file_availability_score": 80,
            "data_integrity_score": 90,
            "quality_indicator_score": 70,
            "synchronization_score": 85,
        }
        for sol in range(100, 110)
    }

    result = ranker.aggregate_window(
        (100, 109),
        metrics,
        ranker.normalized_weights({
            "file_availability": 0.20,
            "data_integrity": 0.45,
            "quality_indicators": 0.15,
            "synchronization": 0.20,
        }),
        window_size=10,
        min_sol_fraction=0.5,
        min_metrics=3,
    )

    assert result["ranking_status"] == "rankable"
    assert result["available_metrics"] == 4
    assert result["exploratory_score"] is not None


def test_aggregate_window_partial_is_not_ranked():
    metrics = {
        sol: {
            "file_availability_score": 80,
            "data_integrity_score": 90,
            "quality_indicator_score": 70,
            "synchronization_score": 85,
        }
        for sol in range(100, 105)
    }

    result = ranker.aggregate_window(
        (100, 104),
        metrics,
        ranker.normalized_weights(ranker.DEFAULT_WEIGHTS),
        window_size=10,
        min_sol_fraction=0.5,
        min_metrics=3,
    )

    assert result["ranking_status"] == "partial_window"
    assert result["exploratory_score"] is None


def test_rank_windows_keeps_comparison_groups_separate():
    rows = [
        {
            "ranking_status": "rankable",
            "comparison_group": "file_availability,data_integrity",
            "exploratory_score": 90,
            "window_start_sol": 100,
            "window_end_sol": 109,
            "rank": "",
        },
        {
            "ranking_status": "rankable",
            "comparison_group": "file_availability,data_integrity",
            "exploratory_score": 80,
            "window_start_sol": 110,
            "window_end_sol": 119,
            "rank": "",
        },
        {
            "ranking_status": "rankable",
            "comparison_group": "data_integrity,synchronization",
            "exploratory_score": 99,
            "window_start_sol": 120,
            "window_end_sol": 129,
            "rank": "",
        },
    ]

    result = ranker.rank_windows(rows)

    assert result[0]["rank"] == 1
    assert result[1]["rank"] == 2
    assert result[2]["rank"] == 1


def test_write_ranking_csv(tmp_path):
    path = tmp_path / "nested" / "ranking.csv"

    ranker.write_ranking_csv(
        path,
        [{
            "rank": 1,
            "window_start_sol": 100,
            "window_end_sol": 109,
            "window_label": "Sol 100-109",
            "ranking_status": "rankable",
        }],
    )

    assert path.exists()

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["rank"] == "1"


def test_build_summary_does_not_choose_global_best_across_groups():
    rows = [
        {
            "ranking_status": "rankable",
            "comparison_group": "metric_a",
            "exploratory_score": 95,
        },
        {
            "ranking_status": "rankable",
            "comparison_group": "metric_b",
            "exploratory_score": 90,
        },
    ]

    summary = ranker.build_summary(
        rows,
        {},
        100,
        119,
        10,
        ["ATS"],
        "default_configuration",
        0.5,
        3,
    )

    assert summary["best_ranked_window"] is None
    assert summary["comparison_group_count"] == 2
    assert set(
        summary["best_ranked_windows_by_comparison_group"]
    ) == {"metric_a", "metric_b"}


def test_build_summary_documents_missing_inventory():
    summary = ranker.build_summary(
        [],
        {},
        100,
        109,
        10,
        ["ATS"],
        "default_configuration",
        0.5,
        3,
    )

    assert any(
        "missing inventory report" in item
        for item in summary["important_limitations"]
    )


def test_run_reads_analyzer_reports_and_writes_ranking(
    tmp_path,
):
    from backend.analyzers import (
        coverage_analyzer,
        file_discovery,
        quality_analyzer,
        synchronization_analyzer,
    )

    output_dir = tmp_path / "run_output"
    output_dir.mkdir()

    inventory_path = output_dir / "file_inventory.csv"
    coverage_path = output_dir / "coverage_report.csv"
    quality_path = output_dir / "quality_field_report.csv"
    sync_files_path = (
        output_dir / "synchronization_file_report.csv"
    )
    sync_pairs_path = (
        output_dir / "synchronization_pair_report.csv"
    )

    ranking_path = output_dir / "period_ranking.csv"
    summary_path = (
        output_dir / "period_ranking_summary.json"
    )

    # 1. File Discovery report.
    inventory_rows = [
        {
            "sol_folder": "SOL100",
            "sol_number": 100,
            "filename": "sample_ATS.csv",
            "relative_path": "SOL100/sample_ATS.csv",
            "extension": "csv",
            "product_code": "ATS",
            "file_size_bytes": 100,
            "file_status": "available",
            "is_empty": False,
            "matching_file": "sample_ATS.xml",
            "matching_relative_path": "SOL100/sample_ATS.xml",
            "pair_status": "matched",
            "issues": "",
        },
        {
            "sol_folder": "SOL100",
            "sol_number": 100,
            "filename": "sample_ATS.xml",
            "relative_path": "SOL100/sample_ATS.xml",
            "extension": "xml",
            "product_code": "ATS",
            "file_size_bytes": 100,
            "file_status": "available",
            "is_empty": False,
            "matching_file": "sample_ATS.csv",
            "matching_relative_path": "SOL100/sample_ATS.csv",
            "pair_status": "matched",
            "issues": "",
        },
    ]

    file_discovery.write_inventory(
        inventory_rows,
        inventory_path,
    )

    # 2. Coverage Analyzer report.
    coverage_rows = [
        {
            "sol_number": 100,
            "sol_folder": "SOL100",
            "product_code": "ATS",
            "filename": "sample_ATS.csv",
            "file_size_bytes": 100,
            "row_count": 3,
            "time_field": "LMST",
            "time_kind": "lmst",
            "first_time": 1,
            "last_time": 3,
            "span_seconds": 2,
            "parsed_timestamp_count": 3,
            "missing_timestamp_count": 0,
            "invalid_timestamp_count": 0,
            "duplicate_timestamp_count": 0,
            "out_of_order_count": 0,
            "median_step_seconds": 1,
            "gap_count": 0,
            "largest_gap_seconds": 0,
            "gap_total_seconds": 0,
            "numeric_value_count": 3,
            "numeric_missing_count": 0,
            "numeric_invalid_count": 0,
            "measurement_coverage_status": (
                "timestamp_analysis_available"
            ),
            "column_mapping_status": "header_exact_match",
            "notes": "",
        },
    ]

    coverage_analyzer.save_coverage_csv(
        coverage_rows,
        coverage_path,
    )

    # 3. Quality Analyzer report.
    quality_rows = [
        {
            "sol_number": 100,
            "sol_folder": "SOL100",
            "product_code": "ATS",
            "csv_file": "sample_ATS.csv",
            "field_name": "MEASUREMENT",
            "field_type": "range_check",
            "metadata_description": "",
            "analysis_status": "analysed",
            "total_rows": 3,
            "missing_count": 0,
            "non_empty_count": 3,
            "numeric_count": 3,
            "non_numeric_count": 0,
            "distinct_values_lower_bound": 3,
            "distinct_count_capped": False,
            "below_valid_minimum": 0,
            "above_valid_maximum": 0,
            "valid_minimum": 0,
            "valid_maximum": 100,
            "top_values_json": "{}",
            "notes": "",
        },
    ]

    quality_analyzer.write_report(
        quality_path,
        quality_rows,
    )

    # 4. Synchronization Analyzer reports.
    sync_file_rows = [
        {
            "sol_number": 100,
            "sol_folder": "SOL100",
            "product_code": "ATS",
            "csv_file": "sample_ATS.csv",
            "selected_time_field": "LMST",
            "time_kind": "lmst",
            "analysis_status": "analysed",
            "total_rows": 3,
            "parsed_timestamps": 3,
            "missing_timestamps": 0,
            "invalid_timestamps": 0,
            "duplicate_timestamps": 0,
            "out_of_order_timestamps": 0,
            "median_step": 1,
            "first_timestamp": 1,
            "last_timestamp": 3,
            "notes": "",
        },
    ]

    sync_pair_rows = [
        {
            "sol_number": 100,
            "product_1": "ATS",
            "file_1": "sample_ATS.csv",
            "product_2": "PS",
            "file_2": "sample_PS.csv",
            "comparison_status": "analysed",
            "time_kind": "lmst",
            "tolerance": 0.0,
            "overlap_start": 1,
            "overlap_end": 3,
            "overlap_duration": 2,
            "first_count": 3,
            "second_count": 3,
            "matched_timestamps": 3,
            "first_unmatched": 0,
            "second_unmatched": 0,
            "match_rate_first_percent": 100,
            "match_rate_second_percent": 100,
            "match_rate_sparser_percent": 100,
            "mean_match_difference": 0,
            "max_match_difference": 0,
            "notes": "",
        },
    ]

    # Correct argument order: path, rows, columns.
    synchronization_analyzer.write_csv(
        sync_files_path,
        sync_file_rows,
        synchronization_analyzer.FILE_REPORT_COLUMNS,
    )

    synchronization_analyzer.write_csv(
        sync_pairs_path,
        sync_pair_rows,
        synchronization_analyzer.PAIR_REPORT_COLUMNS,
    )

    # 5. Execute Period Ranker using the five report files.
    # Use strings to match the paths produced by parse_args().
    args = SimpleNamespace(
        inventory=str(inventory_path),
        coverage=str(coverage_path),
        quality=str(quality_path),
        sync_files=str(sync_files_path),
        sync_pairs=str(sync_pairs_path),
        start_sol=100,
        end_sol=100,
        required_products=["ATS"],
        weight_files=0.20,
        weight_integrity=0.45,
        weight_quality=0.15,
        weight_sync=0.20,
        integrity_timestamps=1.0,
        integrity_values=1.0,
        window_size=1,
        min_sol_fraction=1.0,
        min_metrics=3,
        output=str(ranking_path),
        summary=str(summary_path),
    )

    summary = ranker.run(args)

    assert ranking_path.is_file()
    assert summary_path.is_file()

    assert summary["sol_range"] == {
        "start": 100,
        "end": 100,
    }

    assert summary["input_report_availability"] == {
        "inventory": True,
        "coverage": True,
        "quality": True,
        "sync_files": True,
        "sync_pairs": True,
    }

    with ranking_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        ranking_rows = list(csv.DictReader(handle))

    assert len(ranking_rows) == 1
    assert ranking_rows[0]["ranking_status"] == "rankable"
    assert ranking_rows[0]["rank"] == "1"


def test_read_csv_normalizes_header_names(tmp_path):
    path = tmp_path / "report.csv"

    path.write_text(
        " sol_number , extension , product_code \n"
        "100,csv,ATS\n",
        encoding="utf-8",
    )

    rows = ranker.read_csv(
        path,
        {"sol_number", "extension", "product_code"},
    )

    assert rows == [
        {
            "sol_number": "100",
            "extension": "csv",
            "product_code": "ATS",
        }
    ]
