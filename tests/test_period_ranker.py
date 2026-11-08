
import csv
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.analyzers import period_ranker as ranker


# =========================================================
# Shared test helpers
# =========================================================

def make_sol_metrics(
    file_availability=80,
    data_integrity=90,
    quality=70,
    synchronization=85,
):
    return {
        "file_availability_score": file_availability,
        "data_integrity_score": data_integrity,
        "quality_indicator_score": quality,
        "synchronization_score": synchronization,
    }


def make_rankable_row(
    start,
    end,
    score,
    group="file_availability,data_integrity",
    status="rankable",
):
    return {
        "rank": "",
        "comparison_group": group,
        "window_start_sol": start,
        "window_end_sol": end,
        "window_label": f"Sol {start}-{end}",
        "ranking_status": status,
        "exploratory_score": score,
    }


def write_csv_report(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=headers,
        )
        writer.writeheader()
        writer.writerows(rows)


def make_run_args(output_dir):
    return SimpleNamespace(
        inventory=str(output_dir / "file_inventory.csv"),
        coverage=str(output_dir / "coverage_report.csv"),
        quality=str(output_dir / "quality_field_report.csv"),
        sync_files=str(
            output_dir / "synchronization_file_report.csv"
        ),
        sync_pairs=str(
            output_dir / "synchronization_pair_report.csv"
        ),
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
        output=str(output_dir / "period_ranking.csv"),
        summary=str(
            output_dir / "period_ranking_summary.json"
        ),
    )


def create_minimal_analyzer_reports(output_dir):
    """Create valid minimal reports for one complete Sol."""

    inventory_headers = [
        "sol_number",
        "extension",
        "product_code",
    ]

    inventory_rows = [
        {
            "sol_number": 100,
            "extension": "csv",
            "product_code": "ATS",
        },
        {
            "sol_number": 100,
            "extension": "xml",
            "product_code": "ATS",
        },
    ]

    coverage_headers = [
        "sol_number",
        "row_count",
        "parsed_timestamp_count",
        "missing_timestamp_count",
        "invalid_timestamp_count",
        "numeric_value_count",
        "numeric_missing_count",
        "numeric_invalid_count",
    ]

    coverage_rows = [
        {
            "sol_number": 100,
            "row_count": 10,
            "parsed_timestamp_count": 10,
            "missing_timestamp_count": 0,
            "invalid_timestamp_count": 0,
            "numeric_value_count": 10,
            "numeric_missing_count": 0,
            "numeric_invalid_count": 0,
        },
    ]

    quality_headers = [
        "sol_number",
        "field_type",
        "analysis_status",
        "numeric_count",
        "below_valid_minimum",
        "above_valid_maximum",
        "valid_minimum",
        "valid_maximum",
    ]

    quality_rows = [
        {
            "sol_number": 100,
            "field_type": "range_check",
            "analysis_status": "analysed",
            "numeric_count": 10,
            "below_valid_minimum": 0,
            "above_valid_maximum": 0,
            "valid_minimum": 0,
            "valid_maximum": 100,
        },
    ]

    sync_file_headers = [
        "sol_number",
        "analysis_status",
        "parsed_timestamps",
    ]

    sync_file_rows = [
        {
            "sol_number": 100,
            "analysis_status": "analysed",
            "parsed_timestamps": 10,
        },
    ]

    sync_pair_headers = [
        "sol_number",
        "comparison_status",
        "match_rate_sparser_percent",
        "matched_timestamps",
        "overlap_duration",
    ]

    sync_pair_rows = [
        {
            "sol_number": 100,
            "comparison_status": "analysed",
            "match_rate_sparser_percent": 95,
            "matched_timestamps": 10,
            "overlap_duration": 10,
        },
    ]

    write_csv_report(
        output_dir / "file_inventory.csv",
        inventory_headers,
        inventory_rows,
    )

    write_csv_report(
        output_dir / "coverage_report.csv",
        coverage_headers,
        coverage_rows,
    )

    write_csv_report(
        output_dir / "quality_field_report.csv",
        quality_headers,
        quality_rows,
    )

    write_csv_report(
        output_dir / "synchronization_file_report.csv",
        sync_file_headers,
        sync_file_rows,
    )

    write_csv_report(
        output_dir / "synchronization_pair_report.csv",
        sync_pair_headers,
        sync_pair_rows,
    )


# =========================================================
# Numeric conversion and general helpers
# =========================================================

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("12.5", 12.5),
        ("0", 0.0),
        ("-4.25", -4.25),
        (12, 12.0),
        (None, None),
        ("", None),
        ("invalid", None),
        ("nan", None),
        ("inf", None),
        ("-inf", None),
    ],
)
def test_safe_float(value, expected):
    assert ranker.safe_float(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("12", 12),
        ("12.0", 12),
        (12, 12),
        ("0", 0),
        ("-5", -5),
        ("12.5", None),
        ("invalid", None),
        ("nan", None),
        ("inf", None),
        (None, None),
    ],
)
def test_safe_int(value, expected):
    assert ranker.safe_int(value) == expected


def test_sol_number_uses_safe_integer_conversion():
    assert ranker.sol_number("100") == 100
    assert ranker.sol_number("100.5") is None
    assert ranker.sol_number("invalid") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-10, 0),
        (0, 0),
        (50, 50),
        (100, 100),
        (150, 100),
    ],
)
def test_clamp(value, expected):
    assert ranker.clamp(value) == expected


def test_average_returns_mean():
    assert ranker.average([10, 20, 30]) == 20


def test_average_returns_none_for_empty_input():
    assert ranker.average([]) is None


# =========================================================
# Weight validation
# =========================================================

def test_normalized_weights():
    result = ranker.normalized_weights({
        "a": 2,
        "b": 2,
    })

    assert result == {
        "a": 0.5,
        "b": 0.5,
    }


def test_normalized_weights_preserves_relative_proportions():
    result = ranker.normalized_weights({
        "a": 2,
        "b": 3,
        "c": 5,
    })

    assert result["a"] == pytest.approx(0.2)
    assert result["b"] == pytest.approx(0.3)
    assert result["c"] == pytest.approx(0.5)
    assert sum(result.values()) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "weights",
    [
        {"a": -1, "b": 2},
        {"a": "invalid", "b": 2},
        {"a": float("nan"), "b": 2},
        {"a": float("inf"), "b": 2},
        {"a": 0, "b": 0},
        {},
    ],
)
def test_normalized_weights_rejects_invalid_values(weights):
    with pytest.raises(ValueError):
        ranker.normalized_weights(weights)


# =========================================================
# CSV input validation
# =========================================================

def test_read_csv_returns_empty_for_missing_report(tmp_path):
    assert ranker.read_csv(
        tmp_path / "missing.csv"
    ) == []


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

    assert rows == [
        {
            "sol_number": "100",
            "extension": "csv",
            "product_code": "ATS",
        }
    ]


def test_read_csv_validates_required_columns(tmp_path):
    path = tmp_path / "report.csv"

    path.write_text(
        "sol_number,extension\n"
        "100,csv\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Missing required columns",
    ):
        ranker.read_csv(
            path,
            {"sol_number", "extension", "product_code"},
        )


def test_read_csv_rejects_headerless_report(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="no header"):
        ranker.read_csv(path)


@pytest.mark.parametrize(
    "header",
    [
        "sol_number,,product_code",
        "sol_number,sol_number,product_code",
        "sol_number, ,product_code",
    ],
)
def test_read_csv_rejects_invalid_headers(tmp_path, header):
    path = tmp_path / "invalid.csv"
    path.write_text(
        header + "\n100,100,ATS\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        ranker.read_csv(path)


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


def test_read_csv_supports_utf8_bom(tmp_path):
    path = tmp_path / "bom.csv"

    path.write_text(
        "sol_number,extension,product_code\n"
        "100,csv,ATS\n",
        encoding="utf-8-sig",
    )

    rows = ranker.read_csv(path)

    assert rows[0]["sol_number"] == "100"


# =========================================================
# Sol discovery and range resolution
# =========================================================

def test_discover_sol_numbers_uses_union():
    result = ranker.discover_sol_numbers(
        [{"sol_number": "100"}, {"sol_number": "101"}],
        [{"sol_number": "103"}],
        [{"sol_number": "invalid"}],
    )

    assert result == {100, 101, 103}


def test_discover_sol_numbers_ignores_negative_values():
    result = ranker.discover_sol_numbers(
        [
            {"sol_number": "-1"},
            {"sol_number": "100"},
            {"sol_number": "invalid"},
        ]
    )

    assert result == {100}


def test_resolve_sol_range_automatic():
    assert ranker.resolve_sol_range(
        None,
        None,
        {100, 101, 105},
    ) == (
        100,
        105,
        "automatic_from_reports",
    )


def test_resolve_sol_range_explicit():
    assert ranker.resolve_sol_range(
        90,
        110,
        {100, 101, 105},
    ) == (90, 110, "explicit_cli")


def test_resolve_sol_range_explicit_start_only():
    assert ranker.resolve_sol_range(
        90,
        None,
        {100, 101, 105},
    ) == (
        90,
        105,
        "explicit_start_auto_end",
    )


def test_resolve_sol_range_explicit_end_only():
    assert ranker.resolve_sol_range(
        None,
        110,
        {100, 101, 105},
    ) == (
        100,
        110,
        "auto_start_explicit_end",
    )


@pytest.mark.parametrize(
    ("start", "end", "discovered"),
    [
        (None, None, set()),
        (110, 100, {100, 110}),
        (-1, 100, {100}),
        (100, -1, {100}),
    ],
)
def test_resolve_sol_range_rejects_invalid_ranges(
    start,
    end,
    discovered,
):
    with pytest.raises(ValueError):
        ranker.resolve_sol_range(
            start,
            end,
            discovered,
        )


# =========================================================
# Candidate windows
# =========================================================

def test_build_windows():
    assert ranker.build_windows(100, 124, 10) == [
        (100, 109),
        (110, 119),
        (120, 124),
    ]


def test_build_windows_exact_multiple():
    assert ranker.build_windows(100, 119, 10) == [
        (100, 109),
        (110, 119),
    ]


def test_build_windows_single_sol():
    assert ranker.build_windows(100, 100, 1) == [
        (100, 100),
    ]


def test_build_windows_large_window():
    assert ranker.build_windows(100, 104, 10) == [
        (100, 104),
    ]


@pytest.mark.parametrize(
    ("start", "end", "size"),
    [
        (-1, 10, 5),
        (10, -1, 5),
        (110, 100, 5),
        (100, 110, 0),
        (100, 110, -1),
    ],
)
def test_build_windows_rejects_invalid_arguments(
    start,
    end,
    size,
):
    with pytest.raises(ValueError):
        ranker.build_windows(start, end, size)


def test_window_label():
    assert ranker.window_label((100, 109)) == "Sol 100-109"


# =========================================================
# Inventory analysis
# =========================================================

def test_analyse_inventory_counts_products_and_files():
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
    assert result[100]["inventory_entries"] == 3
    assert result[100]["missing_pairs"] == 1


def test_analyse_inventory_ignores_rows_outside_range():
    rows = [
        {
            "sol_number": "99",
            "extension": "csv",
            "product_code": "ATS",
        },
        {
            "sol_number": "100",
            "extension": "csv",
            "product_code": "PS",
        },
        {
            "sol_number": "101",
            "extension": "csv",
            "product_code": "RDS",
        },
    ]

    result = ranker.analyse_inventory(rows, 100, 100)

    assert set(result) == {100}
    assert result[100]["products"] == {"PS"}


def test_analyse_inventory_normalizes_extension_and_product():
    result = ranker.analyse_inventory(
        [
            {
                "sol_number": "100",
                "extension": ".CSV",
                "product_code": " ats ",
            },
        ],
        100,
        100,
    )

    assert result[100]["products"] == {"ATS"}
    assert result[100]["csv_files"] == 1


# =========================================================
# Coverage analysis
# =========================================================

def test_analyse_coverage_aggregates_counts():
    rows = [
        {
            "sol_number": "100",
            "row_count": "10",
            "parsed_timestamp_count": "8",
            "missing_timestamp_count": "1",
            "invalid_timestamp_count": "1",
            "numeric_value_count": "7",
            "numeric_missing_count": "2",
            "numeric_invalid_count": "1",
        },
        {
            "sol_number": "100",
            "row_count": "5",
            "parsed_timestamp_count": "5",
            "missing_timestamp_count": "0",
            "invalid_timestamp_count": "0",
            "numeric_value_count": "5",
            "numeric_missing_count": "0",
            "numeric_invalid_count": "0",
        },
    ]

    result = ranker.analyse_coverage(rows)

    assert result[100]["files"] == 2
    assert result[100]["rows"] == 15
    assert result[100]["parsed_timestamps"] == 13
    assert result[100]["missing_timestamps"] == 1
    assert result[100]["invalid_timestamps"] == 1
    assert result[100]["numeric_values"] == 12


def test_analyse_coverage_ignores_invalid_counts():
    result = ranker.analyse_coverage([
        {
            "sol_number": "100",
            "row_count": "-5",
            "parsed_timestamp_count": "invalid",
            "missing_timestamp_count": "2.5",
            "invalid_timestamp_count": "2",
            "numeric_value_count": "10",
            "numeric_missing_count": "-1",
            "numeric_invalid_count": "0",
        },
    ])

    assert result[100]["rows"] == 0
    assert result[100]["parsed_timestamps"] == 0
    assert result[100]["missing_timestamps"] == 0
    assert result[100]["invalid_timestamps"] == 2
    assert result[100]["numeric_values"] == 10
    assert result[100]["numeric_missing"] == 0


# =========================================================
# Quality analysis
# =========================================================

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
    ]

    result = ranker.analyse_quality(rows)

    assert result[100]["field_reports"] == 2
    assert result[100]["analysed_fields"] == 2
    assert result[100]["range_checked_fields"] == 1
    assert result[100]["range_checked_values"] == 100
    assert result[100]["below_minimum"] == 5
    assert result[100]["above_maximum"] == 5


def test_analyse_quality_ignores_impossible_range_counts():
    result = ranker.analyse_quality([
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
    ])

    assert result[100]["range_checked_fields"] == 0
    assert result[100]["range_checked_values"] == 0


def test_analyse_quality_ignores_unanalysed_rows():
    result = ranker.analyse_quality([
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
    ])

    assert result[100]["analysed_fields"] == 0
    assert result[100]["range_checked_fields"] == 0


def test_analyse_quality_accepts_case_and_whitespace():
    result = ranker.analyse_quality([
        {
            "sol_number": "100",
            "field_type": " RANGE_CHECK ",
            "analysis_status": " ANALYSED ",
            "numeric_count": "10",
            "below_valid_minimum": "1",
            "above_valid_maximum": "1",
            "valid_minimum": "0",
            "valid_maximum": "10",
        },
    ])

    assert result[100]["range_checked_fields"] == 1


# =========================================================
# Synchronization analysis
# =========================================================

def test_analyse_sync_files_counts_analysed_files():
    result = ranker.analyse_sync_files([
        {
            "sol_number": "100",
            "analysis_status": "analysed",
            "parsed_timestamps": "10",
        },
        {
            "sol_number": "100",
            "analysis_status": "not_analysed",
            "parsed_timestamps": "20",
        },
    ])

    assert result[100]["files"] == 2
    assert result[100]["analysed_files"] == 1
    assert result[100]["parsed_timestamps"] == 10


def test_analyse_sync_pairs_accepts_only_valid_match_rates():
    result = ranker.analyse_sync_pairs([
        {
            "sol_number": "100",
            "comparison_status": "analysed",
            "match_rate_sparser_percent": "90",
            "matched_timestamps": "10",
            "overlap_duration": "5",
        },
        {
            "sol_number": "100",
            "comparison_status": "analysed",
            "match_rate_sparser_percent": "110",
            "matched_timestamps": "5",
            "overlap_duration": "2",
        },
        {
            "sol_number": "100",
            "comparison_status": "not_analysed",
            "match_rate_sparser_percent": "50",
            "matched_timestamps": "100",
            "overlap_duration": "10",
        },
    ])

    assert result[100]["pairs"] == 3
    assert result[100]["analysed_pairs"] == 2
    assert result[100]["match_rates"] == [90.0]
    assert result[100]["matched_timestamps"] == 15
    assert result[100]["overlap_durations"] == [5.0, 2.0]


# =========================================================
# Per-Sol metrics and integrity
# =========================================================

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

    assert score == pytest.approx(85)
    assert components["timestamps"] == pytest.approx(80)
    assert components["values"] == pytest.approx(90)


def test_calculate_integrity_returns_none_when_unavailable():
    score, components = ranker.calculate_integrity(
        {},
        {
            "timestamps": 0.5,
            "values": 0.5,
        },
    )

    assert score is None
    assert components == {}


def test_calculate_integrity_renormalizes_available_components():
    score, components = ranker.calculate_integrity(
        {
            "parsed_timestamps": 80,
            "missing_timestamps": 20,
            "numeric_values": 0,
            "numeric_missing": 0,
            "numeric_invalid": 0,
        },
        {
            "timestamps": 0.5,
            "values": 0.5,
        },
    )

    assert score == pytest.approx(80)
    assert components == {"timestamps": 80}


def test_calculate_integrity_respects_zero_component_weight():
    score, components = ranker.calculate_integrity(
        {
            "parsed_timestamps": 80,
            "missing_timestamps": 20,
            "numeric_values": 100,
            "numeric_missing": 0,
            "numeric_invalid": 0,
        },
        {
            "timestamps": 0,
            "values": 1,
        },
    )

    assert score == pytest.approx(100)
    assert components["timestamps"] == pytest.approx(80)
    assert components["values"] == pytest.approx(100)


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
    result = ranker.calculate_sol_metrics(
        sol=100,
        inventory={
            100: {
                "products": {"ATS", "PS"},
                "csv_files": 2,
                "xml_files": 2,
                "inventory_entries": 4,
                "missing_pairs": 0,
            }
        },
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
    assert result["required_products"] == 4


def test_calculate_sol_metrics_quality_score():
    result = ranker.calculate_sol_metrics(
        sol=100,
        inventory={},
        coverage={},
        quality={
            100: {
                "range_checked_values": 100,
                "below_minimum": 5,
                "above_maximum": 5,
            }
        },
        sync_files={},
        sync_pairs={},
        required_products=None,
        integrity_weights={
            "timestamps": 0.5,
            "values": 0.5,
        },
    )

    assert result["quality_indicator_score"] == 90


def test_calculate_sol_metrics_synchronization_score():
    result = ranker.calculate_sol_metrics(
        sol=100,
        inventory={},
        coverage={},
        quality={},
        sync_files={},
        sync_pairs={
            100: {
                "analysed_pairs": 2,
                "match_rates": [80, 100],
                "matched_timestamps": 20,
            }
        },
        required_products=None,
        integrity_weights={
            "timestamps": 0.5,
            "values": 0.5,
        },
    )

    assert result["synchronization_score"] == 90
    assert result["sync_pairs_analysed"] == 2


# =========================================================
# Window aggregation
# =========================================================

def test_aggregate_window_rankable():
    metrics = {
        sol: make_sol_metrics()
        for sol in range(100, 110)
    }

    result = ranker.aggregate_window(
        (100, 109),
        metrics,
        ranker.normalized_weights(ranker.DEFAULT_WEIGHTS),
        window_size=10,
        min_sol_fraction=0.5,
        min_metrics=3,
    )

    assert result["ranking_status"] == "rankable"
    assert result["available_metrics"] == 4
    assert result["exploratory_score"] is not None
    assert result["total_sols"] == 10
    assert result["is_partial_window"] is False


def test_aggregate_window_score_uses_configured_weights():
    metrics = {
        sol: make_sol_metrics(
            file_availability=100,
            data_integrity=80,
            quality=60,
            synchronization=40,
        )
        for sol in range(100, 102)
    }

    weights = ranker.normalized_weights({
        "file_availability": 0.25,
        "data_integrity": 0.25,
        "quality_indicators": 0.25,
        "synchronization": 0.25,
    })

    result = ranker.aggregate_window(
        (100, 101),
        metrics,
        weights,
        window_size=2,
        min_sol_fraction=1.0,
        min_metrics=4,
    )

    assert result["exploratory_score"] == 70


def test_aggregate_window_excludes_unavailable_metric():
    metrics = {
        sol: make_sol_metrics(
            file_availability=100,
            data_integrity=80,
            quality=None,
            synchronization=40,
        )
        for sol in range(100, 102)
    }

    result = ranker.aggregate_window(
        (100, 101),
        metrics,
        ranker.normalized_weights({
            "file_availability": 0.25,
            "data_integrity": 0.25,
            "quality_indicators": 0.25,
            "synchronization": 0.25,
        }),
        window_size=2,
        min_sol_fraction=1.0,
        min_metrics=3,
    )

    assert result["ranking_status"] == "rankable"
    assert result["comparison_group"] == (
        "file_availability,data_integrity,synchronization"
    )
    assert result["available_metrics"] == 3
    assert result["exploratory_score"] == pytest.approx(73.333)


def test_aggregate_window_excludes_zero_weight_metric():
    metrics = {
        sol: make_sol_metrics()
        for sol in range(100, 102)
    }

    result = ranker.aggregate_window(
        (100, 101),
        metrics,
        {
            "file_availability": 0.5,
            "data_integrity": 0.5,
            "quality_indicators": 0,
            "synchronization": 0,
        },
        window_size=2,
        min_sol_fraction=1.0,
        min_metrics=2,
    )

    assert result["ranking_status"] == "rankable"
    assert result["comparison_group"] == (
        "file_availability,data_integrity"
    )
    assert result["available_metrics"] == 2


def test_aggregate_window_insufficient_metrics():
    metrics = {
        sol: make_sol_metrics(
            file_availability=80,
            data_integrity=None,
            quality=None,
            synchronization=None,
        )
        for sol in range(100, 110)
    }

    result = ranker.aggregate_window(
        (100, 109),
        metrics,
        ranker.normalized_weights(ranker.DEFAULT_WEIGHTS),
        window_size=10,
        min_sol_fraction=0.5,
        min_metrics=3,
    )

    assert result["ranking_status"] == "insufficient_data"
    assert result["exploratory_score"] is None
    assert result["available_metrics"] == 1


def test_aggregate_window_partial_is_not_ranked():
    metrics = {
        sol: make_sol_metrics()
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
    assert result["is_partial_window"] is True


def test_aggregate_window_uses_ceil_for_minimum_sol_count():
    metrics = {
        100: make_sol_metrics(),
        101: make_sol_metrics(),
        102: make_sol_metrics(),
        103: make_sol_metrics(file_availability=None),
        104: make_sol_metrics(file_availability=None),
    }

    result = ranker.aggregate_window(
        (100, 104),
        metrics,
        ranker.normalized_weights(ranker.DEFAULT_WEIGHTS),
        window_size=5,
        min_sol_fraction=0.5,
        min_metrics=3,
    )

    assert result["ranking_status"] == "rankable"
    assert result["file_availability_sols"] == 3


def test_aggregate_window_rejects_metric_below_availability_threshold():
    metrics = {
        100: make_sol_metrics(),
        101: make_sol_metrics(),
        102: make_sol_metrics(),
        103: make_sol_metrics(file_availability=None),
        104: make_sol_metrics(file_availability=None),
    }

    result = ranker.aggregate_window(
        (100, 104),
        metrics,
        ranker.normalized_weights(ranker.DEFAULT_WEIGHTS),
        window_size=5,
        min_sol_fraction=0.8,
        min_metrics=3,
    )

    assert result["ranking_status"] == "rankable"
    assert result["file_availability_score"] is None
    assert result["file_availability_sols"] == 3
    assert result["available_metrics"] == 3
    assert result["comparison_group"] == (
        "data_integrity,quality_indicators,synchronization"
    )


# =========================================================
# Ranking and comparison groups
# =========================================================

def test_rank_windows_orders_by_descending_score():
    rows = [
        make_rankable_row(100, 109, 70),
        make_rankable_row(110, 119, 95),
        make_rankable_row(120, 129, 80),
    ]

    result = ranker.rank_windows(rows)

    assert [row["rank"] for row in result] == [3, 1, 2]


def test_rank_windows_uses_start_sol_as_tie_breaker():
    rows = [
        make_rankable_row(120, 129, 90),
        make_rankable_row(100, 109, 90),
        make_rankable_row(110, 119, 90),
    ]

    result = ranker.rank_windows(rows)

    ranks_by_start = {
        row["window_start_sol"]: row["rank"]
        for row in result
    }

    assert ranks_by_start == {
        100: 1,
        110: 2,
        120: 3,
    }

    # The function preserves the original input order.
    assert [
        row["window_start_sol"] for row in result
    ] == [120, 100, 110]


def test_rank_windows_keeps_comparison_groups_separate():
    rows = [
        make_rankable_row(
            100, 109, 90,
            group="file_availability,data_integrity",
        ),
        make_rankable_row(
            110, 119, 80,
            group="file_availability,data_integrity",
        ),
        make_rankable_row(
            120, 129, 99,
            group="data_integrity,synchronization",
        ),
    ]

    result = ranker.rank_windows(rows)

    assert [row["rank"] for row in result] == [1, 2, 1]


def test_rank_windows_does_not_rank_unrankable_rows():
    rows = [
        make_rankable_row(100, 109, 90),
        make_rankable_row(
            110,
            119,
            None,
            status="insufficient_data",
        ),
        make_rankable_row(120, 129, 80),
    ]

    result = ranker.rank_windows(rows)

    assert result[0]["rank"] == 1
    assert result[1]["rank"] == ""
    assert result[2]["rank"] == 2


def test_rank_windows_does_not_compare_different_signatures():
    rows = [
        make_rankable_row(
            100, 109, 99,
            group="file_availability,data_integrity",
        ),
        make_rankable_row(
            110, 119, 50,
            group="data_integrity,synchronization",
        ),
    ]

    result = ranker.rank_windows(rows)

    assert [row["rank"] for row in result] == [1, 1]


# =========================================================
# Summary generation
# =========================================================

def test_build_summary_does_not_choose_global_best_across_groups():
    rows = [
        make_rankable_row(
            100, 109, 95,
            group="metric_a",
        ),
        make_rankable_row(
            110, 119, 90,
            group="metric_b",
        ),
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


def test_build_summary_selects_best_window_for_single_group():
    rows = [
        make_rankable_row(100, 109, 80),
        make_rankable_row(110, 119, 95),
    ]

    summary = ranker.build_summary(
        rows,
        {},
        100,
        119,
        10,
        ["ATS"],
        "command_line",
        0.5,
        3,
    )

    assert summary["comparison_group_count"] == 1
    assert summary["best_ranked_window"]["exploratory_score"] == 95
    assert summary["best_ranked_window"]["window_start_sol"] == 110


def test_build_summary_excludes_unrankable_windows():
    rows = [
        make_rankable_row(100, 109, 90),
        make_rankable_row(
            110,
            119,
            None,
            status="partial_window",
        ),
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

    assert summary["total_candidate_windows"] == 2
    assert summary["rankable_windows"] == 1
    assert summary["unrankable_windows"] == 1


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


def test_build_summary_preserves_configuration_metadata():
    weights = {
        "file_availability": 0.2,
        "data_integrity": 0.45,
        "quality_indicators": 0.15,
        "synchronization": 0.2,
    }

    summary = ranker.build_summary(
        [],
        weights,
        100,
        119,
        10,
        ["ATS", "PS"],
        "command_line",
        0.75,
        3,
    )

    assert summary["sol_range"] == {
        "start": 100,
        "end": 119,
    }
    assert summary["window_size"] == 10
    assert summary["ranking_weights"] == weights
    assert summary["required_products"] == ["ATS", "PS"]
    assert summary["required_products_source"] == "command_line"
    assert summary["required_products_explicitly_configured"] is True
    assert summary["min_sol_fraction"] == 0.75
    assert summary["min_metrics"] == 3


# =========================================================
# CSV and JSON output
# =========================================================

def test_write_ranking_csv_creates_parent_directory(tmp_path):
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

    assert path.is_file()


def test_write_ranking_csv_uses_expected_columns(tmp_path):
    path = tmp_path / "ranking.csv"

    ranker.write_ranking_csv(
        path,
        [{
            "rank": 1,
            "window_start_sol": 100,
            "window_end_sol": 109,
            "unexpected_field": "must_not_be_written",
        }],
    )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert reader.fieldnames == ranker.RANKING_COLUMNS
    assert len(rows) == 1
    assert rows[0]["rank"] == "1"
    assert "unexpected_field" not in reader.fieldnames


def test_write_ranking_csv_supports_empty_rows(tmp_path):
    path = tmp_path / "ranking.csv"

    ranker.write_ranking_csv(path, [])

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert reader.fieldnames == ranker.RANKING_COLUMNS
    assert rows == []


def test_write_json_creates_valid_json(tmp_path):
    path = tmp_path / "nested" / "summary.json"

    ranker.write_json(
        path,
        {
            "sol_range": {
                "start": 100,
                "end": 109,
            },
            "status": "completed",
        },
    )

    assert path.is_file()

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    assert data["sol_range"]["start"] == 100
    assert data["status"] == "completed"


def test_write_json_rejects_non_finite_numbers(tmp_path):
    path = tmp_path / "summary.json"

    with pytest.raises(ValueError):
        ranker.write_json(
            path,
            {"invalid_score": math.nan},
        )


# =========================================================
# Command-line argument validation
# =========================================================

def test_parse_args_defaults(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["period_ranker"],
    )

    args = ranker.parse_args()

    assert args.window_size == ranker.DEFAULT_WINDOW_SIZE
    assert args.start_sol is None
    assert args.end_sol is None
    assert args.required_products is None
    assert args.min_metrics == 3


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--start-sol", "-1"], "Start Sol cannot be negative"),
        (["--end-sol", "-1"], "End Sol cannot be negative"),
        (
            ["--start-sol", "110", "--end-sol", "100"],
            "Start Sol cannot exceed End Sol",
        ),
        (["--window-size", "0"], "Window size must be at least 1"),
        (
            ["--min-sol-fraction", "0"],
            "min-sol-fraction must be greater than 0",
        ),
        (
            ["--min-sol-fraction", "1.1"],
            "min-sol-fraction must be greater than 0",
        ),
        (
            ["--min-sol-fraction", "nan"],
            "min-sol-fraction must be finite",
        ),
        (
            ["--min-metrics", "0"],
            "min-metrics must be between 1 and 4",
        ),
        (
            ["--min-metrics", "5"],
            "min-metrics must be between 1 and 4",
        ),
    ],
)
def test_parse_args_rejects_invalid_arguments(
    monkeypatch,
    arguments,
    message,
):
    monkeypatch.setattr(
        sys,
        "argv",
        ["period_ranker", *arguments],
    )

    with pytest.raises(SystemExit):
        ranker.parse_args()


# =========================================================
# End-to-end integration
# =========================================================

def test_run_reads_reports_and_writes_ranking_and_summary(
    tmp_path,
):
    output_dir = tmp_path / "run_output"
    output_dir.mkdir()

    create_minimal_analyzer_reports(output_dir)

    args = make_run_args(output_dir)

    summary = ranker.run(args)

    ranking_path = Path(args.output)
    summary_path = Path(args.summary)

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

    assert summary["total_candidate_windows"] == 1
    assert summary["rankable_windows"] == 1
    assert summary["comparison_group_count"] == 1

    with ranking_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        ranking_rows = list(csv.DictReader(handle))

    assert len(ranking_rows) == 1
    assert ranking_rows[0]["ranking_status"] == "rankable"
    assert ranking_rows[0]["rank"] == "1"

    with summary_path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        saved_summary = json.load(handle)

    assert saved_summary["rankable_windows"] == 1
    assert saved_summary["sol_range"]["start"] == 100
    assert saved_summary["sol_range"]["end"] == 100

    assert (
        saved_summary["best_ranked_window"]["window_start_sol"]
        == 100
    )


def test_run_uses_automatic_sol_range(tmp_path):
    output_dir = tmp_path / "automatic_run"
    output_dir.mkdir()

    create_minimal_analyzer_reports(output_dir)

    args = make_run_args(output_dir)
    args.start_sol = None
    args.end_sol = None

    summary = ranker.run(args)

    assert summary["sol_range"] == {
        "start": 100,
        "end": 100,
    }

    assert summary["sol_range_detection"]["source"] == (
        "automatic_from_reports"
    )


def test_run_rejects_reports_without_valid_sol_numbers(tmp_path):
    output_dir = tmp_path / "empty_run"
    output_dir.mkdir()

    # All five reports exist and have valid headers,
    # but none contains a valid Sol number.
    create_minimal_analyzer_reports(output_dir)

    inventory_path = output_dir / "file_inventory.csv"

    write_csv_report(
        inventory_path,
        ["sol_number", "extension", "product_code"],
        [
            {
                "sol_number": "invalid",
                "extension": "csv",
                "product_code": "ATS",
            }
        ],
    )

    for filename, headers in [
        (
            "coverage_report.csv",
            [
                "sol_number",
                "row_count",
                "parsed_timestamp_count",
                "missing_timestamp_count",
                "invalid_timestamp_count",
                "numeric_value_count",
                "numeric_missing_count",
                "numeric_invalid_count",
            ],
        ),
        (
            "quality_field_report.csv",
            [
                "sol_number",
                "field_type",
                "analysis_status",
                "numeric_count",
                "below_valid_minimum",
                "above_valid_maximum",
                "valid_minimum",
                "valid_maximum",
            ],
        ),
        (
            "synchronization_file_report.csv",
            [
                "sol_number",
                "analysis_status",
                "parsed_timestamps",
            ],
        ),
        (
            "synchronization_pair_report.csv",
            [
                "sol_number",
                "comparison_status",
                "match_rate_sparser_percent",
                "matched_timestamps",
                "overlap_duration",
            ],
        ),
    ]:
        write_csv_report(
            output_dir / filename,
            headers,
            [{"sol_number": "invalid"}],
        )

    args = make_run_args(output_dir)

    with pytest.raises(
        ValueError,
        match="No valid Sol numbers",
    ):
        ranker.run(args)


def test_run_rejects_empty_required_products(tmp_path):
    output_dir = tmp_path / "invalid_products_run"
    output_dir.mkdir()

    create_minimal_analyzer_reports(output_dir)

    args = make_run_args(output_dir)
    args.required_products = []

    with pytest.raises(
        ValueError,
        match="at least one product code",
    ):
        ranker.run(args)

# ---------------------------------------------------------
# Additional edge-case and error-path tests
# ---------------------------------------------------------

def test_read_csv_rejects_duplicate_headers(tmp_path):
    path = tmp_path / "duplicate_headers.csv"
    path.write_text(
        "sol_number,extension,sol_number\n"
        "100,csv,100\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate headers"):
        ranker.read_csv(path)


def test_read_csv_rejects_empty_header(tmp_path):
    path = tmp_path / "empty_header.csv"
    path.write_text(
        "sol_number,,product_code\n"
        "100,csv,ATS\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="empty"):
        ranker.read_csv(path)


def test_read_csv_wraps_csv_reader_errors(tmp_path, monkeypatch):
    path = tmp_path / "broken.csv"
    path.write_text("header\nvalue\n", encoding="utf-8")

    class BrokenReader:
        fieldnames = ["header"]

        def __init__(self, *args, **kwargs):
            pass

        def __iter__(self):
            raise csv.Error("simulated CSV parsing error")

    monkeypatch.setattr(ranker.csv, "DictReader", BrokenReader)

    with pytest.raises(ValueError, match="Could not read CSV report"):
        ranker.read_csv(path)


def test_analyse_coverage_ignores_invalid_sol_numbers():
    result = ranker.analyse_coverage([
        {"sol_number": "invalid", "row_count": "10"},
        {"sol_number": "100", "row_count": "5"},
    ])

    assert set(result) == {100}
    assert result[100]["rows"] == 5

def test_analyse_quality_ignores_invalid_sol_numbers():
    result = ranker.analyse_quality([
        {
            "sol_number": "invalid",
            "field_type": "range_check",
            "analysis_status": "analysed",
        },
        {
            "sol_number": "100",
            "field_type": "range_check",
            "analysis_status": "analysed",
            "numeric_count": "10",
            "below_valid_minimum": "1",
            "above_valid_maximum": "1",
            "valid_minimum": "0",
            "valid_maximum": "10",
        },
    ])

    assert 100 in result
    assert "invalid" not in result
    assert result[100]["range_checked_fields"] == 1


def test_analyse_quality_ignores_rows_without_valid_bounds():
    result = ranker.analyse_quality([
        {
            "sol_number": "100",
            "field_type": "range_check",
            "analysis_status": "analysed",
            "numeric_count": "10",
            "below_valid_minimum": "0",
            "above_valid_maximum": "0",
            "valid_minimum": "",
            "valid_maximum": "",
        },
    ])

    assert result[100]["analysed_fields"] == 1
    assert result[100]["range_checked_fields"] == 0


def test_analyse_quality_ignores_negative_range_counts():
    result = ranker.analyse_quality([
        {
            "sol_number": "100",
            "field_type": "range_check",
            "analysis_status": "analysed",
            "numeric_count": "10",
            "below_valid_minimum": "-1",
            "above_valid_maximum": "0",
            "valid_minimum": "0",
            "valid_maximum": "10",
        },
    ])

    assert result[100]["range_checked_fields"] == 0
    assert result[100]["range_checked_values"] == 0


def test_analyse_sync_files_ignores_invalid_sol_numbers():
    result = ranker.analyse_sync_files([
        {
            "sol_number": "invalid",
            "analysis_status": "analysed",
            "parsed_timestamps": "10",
        },
        {
            "sol_number": "100",
            "analysis_status": "analysed",
            "parsed_timestamps": "10",
        },
    ])

    assert set(result) == {100}
    assert result[100]["parsed_timestamps"] == 10


def test_analyse_sync_pairs_ignores_invalid_sol_numbers():
    result = ranker.analyse_sync_pairs([
        {
            "sol_number": "invalid",
            "comparison_status": "analysed",
            "match_rate_sparser_percent": "90",
        },
        {
            "sol_number": "100",
            "comparison_status": "analysed",
            "match_rate_sparser_percent": "90",
        },
    ])

    assert set(result) == {100}
    assert result[100]["analysed_pairs"] == 1
    assert result[100]["match_rates"] == [90.0]


def test_aggregate_window_handles_unavailable_average(monkeypatch):
    metrics = {
        sol: {
            "file_availability_score": 80,
            "data_integrity_score": None,
            "quality_indicator_score": None,
            "synchronization_score": None,
        }
        for sol in range(100, 110)
    }

    monkeypatch.setattr(ranker, "average", lambda values: None)

    result = ranker.aggregate_window(
        (100, 109),
        metrics,
        ranker.normalized_weights(ranker.DEFAULT_WEIGHTS),
        window_size=10,
        min_sol_fraction=0.5,
        min_metrics=1,
    )

    assert result["ranking_status"] == "insufficient_data"
    assert result["exploratory_score"] is None
    assert result["available_metrics"] == 0


@pytest.mark.parametrize(
    "arguments",
    [
        ["--window-size", "0"],
        ["--min-sol-fraction", "0"],
        ["--min-sol-fraction", "1.5"],
        ["--min-sol-fraction", "nan"],
        ["--min-metrics", "0"],
        ["--min-metrics", "5"],
        ["--start-sol", "10", "--end-sol", "5"],
        ["--weight-files", "-1"],
        [
            "--weight-files", "0",
            "--weight-integrity", "0",
            "--weight-quality", "0",
            "--weight-sync", "0",
        ],
        [
            "--integrity-timestamps", "0",
            "--integrity-values", "0",
        ],
        ["--required-products"],
    ],
)
def test_parse_args_rejects_invalid_arguments(
    monkeypatch,
    arguments,
):
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        ["period_ranker", *arguments],
    )

    with pytest.raises(SystemExit) as error:
        ranker.parse_args()

    assert error.value.code == 2

# ---------------------------------------------------------
# Targeted tests for remaining uncovered paths
# ---------------------------------------------------------

def test_read_csv_rejects_none_header(tmp_path, monkeypatch):
    path = tmp_path / "none_header.csv"
    path.write_text("header\nvalue\n", encoding="utf-8")

    class NoneHeaderReader:
        fieldnames = ["sol_number", None]

        def __init__(self, *args, **kwargs):
            pass

        def __iter__(self):
            return iter([])

    monkeypatch.setattr(
        ranker.csv,
        "DictReader",
        NoneHeaderReader,
    )

    with pytest.raises(ValueError, match="Invalid empty header"):
        ranker.read_csv(path)


def test_analyse_inventory_handles_empty_product_and_unknown_extension():
    result = ranker.analyse_inventory(
        [
            {
                "sol_number": "100",
                "extension": "csv",
                "product_code": "",
                "pair_status": "",
            },
            {
                "sol_number": "100",
                "extension": "txt",
                "product_code": "ATS",
                "pair_status": "",
            },
        ],
        100,
        100,
    )

    assert result[100]["inventory_entries"] == 2
    assert result[100]["csv_files"] == 1
    assert result[100]["xml_files"] == 0
    assert result[100]["products"] == set()


@pytest.mark.parametrize(
    "count",
    ["invalid", "-1"],
)
def test_analyse_sync_files_ignores_invalid_timestamp_counts(count):
    result = ranker.analyse_sync_files([
        {
            "sol_number": "100",
            "analysis_status": "analysed",
            "parsed_timestamps": count,
        },
    ])

    assert result[100]["analysed_files"] == 1
    assert result[100]["parsed_timestamps"] == 0


def test_calculate_integrity_ignores_zero_weight_numeric_component():
    score, components = ranker.calculate_integrity(
        {
            "parsed_timestamps": 8,
            "missing_timestamps": 2,
            "invalid_timestamps": 0,
            "numeric_values": 5,
            "numeric_missing": 5,
            "numeric_invalid": 0,
        },
        {
            "timestamps": 1.0,
            "values": 0.0,
        },
    )

    assert score == 80.0
    assert components == {
        "timestamps": 80.0,
        "values": 50.0,
    }


def test_calculate_integrity_returns_none_when_only_available_weight_is_zero():
    score, components = ranker.calculate_integrity(
        {
            "parsed_timestamps": 8,
            "missing_timestamps": 2,
            "invalid_timestamps": 0,
            "numeric_values": 5,
            "numeric_missing": 5,
            "numeric_invalid": 0,
        },
        {
            "timestamps": 0.0,
            "values": 0.0,
        },
    )

    assert score is None
    assert components == {
        "timestamps": 80.0,
        "values": 50.0,
    }


def test_calculate_sol_metrics_rejects_impossible_quality_score():
    result = ranker.calculate_sol_metrics(
        sol=100,
        inventory={},
        coverage={},
        quality={
            100: {
                "range_checked_values": 10,
                "below_minimum": 8,
                "above_maximum": 5,
            }
        },
        sync_files={},
        sync_pairs={},
        required_products=None,
        integrity_weights={
            "timestamps": 1.0,
            "values": 1.0,
        },
        inventory_available=False,
    )

    assert result["quality_indicator_score"] is None


@pytest.mark.parametrize(
    "arguments",
    [
        ["--start-sol", "-1"],
        ["--end-sol", "-1"],
    ],
)
def test_parse_args_rejects_negative_sol_boundaries(
    monkeypatch,
    arguments,
):
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        ["period_ranker", *arguments],
    )

    with pytest.raises(SystemExit) as error:
        ranker.parse_args()

    assert error.value.code == 2


def test_parse_args_normalizes_explicit_required_products(monkeypatch):
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "period_ranker",
            "--required-products",
            " ats ",
            "ps",
            "RDS",
        ],
    )

    args = ranker.parse_args()

    assert args.required_products == ["ATS", "PS", "RDS"]
def test_run_uses_default_required_products_when_not_provided(
    tmp_path,
    monkeypatch,
):
    output_dir = tmp_path / "default_products_run"
    output_dir.mkdir()

    create_minimal_analyzer_reports(output_dir)

    monkeypatch.setattr(
        ranker,
        "DEFAULT_REQUIRED_PRODUCTS",
        ["ATS"],
    )

    args = make_run_args(output_dir)
    args.required_products = None

    summary = ranker.run(args)

    assert summary["rankable_windows"] == 1
    assert summary["total_candidate_windows"] == 1
    assert Path(args.output).is_file()
    assert Path(args.summary).is_file()
def test_run_reports_separate_comparison_groups(
    tmp_path,
    capsys,
):
    output_dir = tmp_path / "separate_groups_run"
    output_dir.mkdir()

    create_minimal_analyzer_reports(output_dir)

    # Remove inventory so file availability is unavailable.
    (output_dir / "file_inventory.csv").unlink()

    # Both Sols have integrity data.
    # Only Sol 100 has quality and synchronization data.
    write_csv_report(
        output_dir / "coverage_report.csv",
        [
            "sol_number",
            "row_count",
            "parsed_timestamp_count",
            "missing_timestamp_count",
            "invalid_timestamp_count",
            "numeric_value_count",
            "numeric_missing_count",
            "numeric_invalid_count",
        ],
        [
            {
                "sol_number": 100,
                "row_count": 10,
                "parsed_timestamp_count": 10,
                "missing_timestamp_count": 0,
                "invalid_timestamp_count": 0,
                "numeric_value_count": 10,
                "numeric_missing_count": 0,
                "numeric_invalid_count": 0,
            },
            {
                "sol_number": 101,
                "row_count": 10,
                "parsed_timestamp_count": 10,
                "missing_timestamp_count": 0,
                "invalid_timestamp_count": 0,
                "numeric_value_count": 10,
                "numeric_missing_count": 0,
                "numeric_invalid_count": 0,
            },
        ],
    )

    args = make_run_args(output_dir)
    args.end_sol = 101
    args.min_metrics = 1

    summary = ranker.run(args)
    output = capsys.readouterr().out

    assert summary["total_candidate_windows"] == 2
    assert summary["rankable_windows"] == 2
    assert summary["comparison_group_count"] == 2
    assert summary["best_ranked_window"] is None
    assert summary["best_ranked_windows_by_comparison_group"]

    assert (
        "separate comparison groups"
        in output
    )
def test_run_reports_when_no_candidate_is_rankable(
    tmp_path,
    capsys,
):
    output_dir = tmp_path / "no_rankable_candidates_run"
    output_dir.mkdir()

    create_minimal_analyzer_reports(output_dir)

    # Remove one metric source so only three metrics remain.
    (output_dir / "file_inventory.csv").unlink()

    args = make_run_args(output_dir)
    args.min_metrics = 4

    summary = ranker.run(args)
    output = capsys.readouterr().out

    assert summary["total_candidate_windows"] == 1
    assert summary["rankable_windows"] == 0
    assert summary["best_ranked_window"] is None

    assert (
        "No candidate window met the ranking requirements."
        in output
    )
def test_main_entrypoint_converts_runtime_errors_to_system_exit(
    tmp_path,
    monkeypatch,
):
    import runpy

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["period_ranker"],
    )

    with pytest.raises(
        SystemExit,
        match="ERROR: No valid Sol numbers",
    ):
        runpy.run_path(
            str(Path(ranker.__file__).resolve()),
            run_name="__main__",
        )
        