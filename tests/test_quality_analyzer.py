from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from backend.analyzers import quality_analyzer as qa


# --------------------------------------------------
# Shared fixtures and helpers
# --------------------------------------------------

def make_inventory_row(
    *,
    filename="sample.csv",
    sol_folder="SOL100",
    sol_number=100,
    relative_path="SOL100/sample.csv",
    extension="csv",
):
    return {
        "filename": filename,
        "sol_folder": sol_folder,
        "sol_number": sol_number,
        "relative_path": relative_path,
        "extension": extension,
        "product_code": "ATS",
    }


def make_xml_record(
    *,
    source_file="sample.xml",
    sol_folder="SOL100",
    source_relative_path=None,
    relative_path=None,
    fields=None,
    has_header=True,
):
    if fields is None:
        fields = [
            {
                "name": "Quality Flag",
                "field_number": 1,
                "data_type": "integer",
                "description": "Quality flag",
            },
        ]

    record = {
        "source_file": source_file,
        "sol_folder": sol_folder,
        "has_header": has_header,
        "fields": fields,
    }

    if source_relative_path is not None:
        record["source_relative_path"] = source_relative_path

    if relative_path is not None:
        record["relative_path"] = relative_path

    return record


def write_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.writer(file)
        writer.writerows(rows)


# --------------------------------------------------
# Basic normalization and conversion
# --------------------------------------------------

def test_normalize_name_uses_shared_normalization():
    assert qa.normalize_name(" Quality Flag ") == "qualityflag"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("12.5", 12.5),
        ("-3", -3.0),
        ("0", 0.0),
        ("", None),
        ("N/A", None),
        ("invalid", None),
        (None, None),
        ("nan", None),
        ("inf", None),
    ],
)
def test_safe_float(value, expected):
    assert qa.safe_float(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("", True),
        ("N/A", True),
        ("null", True),
        ("  ", True),
        ("0", False),
        ("0.0", False),
        ("valid", False),
    ],
)
def test_is_missing(value, expected):
    assert qa.is_missing(value) is expected


def test_safe_int_uses_default_for_invalid_values():
    assert qa.safe_int("12") == 12
    assert qa.safe_int("invalid") == 0
    assert qa.safe_int("invalid", default=-1) == -1


def test_get_sol_number_supports_numeric_and_folder_values():
    assert qa.get_sol_number(100) == 100
    assert qa.get_sol_number("100") == 100
    assert qa.get_sol_number("SOL100") == 100
    assert qa.get_sol_number("SOL_0100") == 100
    assert qa.get_sol_number("SOL-100") == 100
    assert qa.get_sol_number("invalid") is None


def test_get_product_code():
    assert qa.get_product_code(
        "WE__0100_CAL_ATS_SAMPLE.csv"
    ) == "ATS"

    assert qa.get_product_code("sample.csv") == ""


def test_normalize_relative_path_handles_windows_separators():
    assert (
        qa.normalize_relative_path(
            r"SOL100\subfolder\sample.xml"
        )
        == "sol100/subfolder/sample.xml"
    )


# --------------------------------------------------
# Bounded value counter
# --------------------------------------------------

def test_bounded_value_counter_counts_repeated_values():
    counter = qa.BoundedValueCounter(capacity=5)

    counter.add("A")
    counter.add("A")
    counter.add("B")

    assert counter.counts["A"] == 2
    assert counter.counts["B"] == 1
    assert counter.distinct_lower_bound() == 2
    assert counter.distinct_tracking_capped is False


def test_bounded_value_counter_limits_distinct_tracking():
    counter = qa.BoundedValueCounter(capacity=2)

    counter.add("A")
    counter.add("B")
    counter.add("C")

    assert counter.distinct_lower_bound() == 2
    assert counter.distinct_tracking_capped is True
    assert len(counter.counts) <= 2


def test_bounded_value_counter_returns_sorted_top_values():
    counter = qa.BoundedValueCounter(capacity=5)

    counter.add("B")
    counter.add("A")
    counter.add("A")
    counter.add("C")
    counter.add("B")
    counter.add("B")

    assert counter.top_values() == {
        "B": 3,
        "A": 2,
        "C": 1,
    }


# --------------------------------------------------
# Metadata loading and indexing
# --------------------------------------------------

def test_load_metadata_accepts_records_list(tmp_path):
    path = tmp_path / "metadata.json"

    path.write_text(
        json.dumps([
            {"source_file": "sample.xml"},
        ]),
        encoding="utf-8",
    )

    result = qa.load_metadata(path)

    assert "records" in result
    assert len(result["records"]) == 1


def test_load_metadata_rejects_invalid_structure(tmp_path):
    path = tmp_path / "metadata.json"

    path.write_text(
        json.dumps({"items": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        qa.load_metadata(path)


def test_load_metadata_rejects_non_object_and_non_list(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text('"invalid"', encoding="utf-8")

    with pytest.raises(ValueError):
        qa.load_metadata(path)


def test_build_metadata_index_indexes_source_relative_path():
    record = make_xml_record(
        source_relative_path="SOL100/sub/sample.xml",
    )

    index = qa.build_metadata_index({
        "records": [record],
    })

    assert "sol100/sub/sample.xml" in index["by_path"]


def test_build_metadata_index_indexes_relative_path():
    record = make_xml_record(
        relative_path="SOL100/sub/sample.xml",
    )

    index = qa.build_metadata_index({
        "records": [record],
    })

    assert "sol100/sub/sample.xml" in index["by_path"]


def test_build_metadata_index_preserves_duplicate_records():
    first = make_xml_record(
        source_file="first.xml",
        source_relative_path="SOL100/first.xml",
    )

    second = make_xml_record(
        source_file="second.xml",
        source_relative_path="SOL100/second.xml",
    )

    index = qa.build_metadata_index({
        "records": [first, second],
    })

    assert len(index["by_stem"]["first"]) == 1
    assert len(index["by_stem"]["second"]) == 1


# --------------------------------------------------
# Metadata matching
# --------------------------------------------------

def test_find_metadata_record_uses_source_relative_path():
    record = make_xml_record(
        source_file="sample.xml",
        source_relative_path="SOL100/sub/sample.xml",
    )

    index = qa.build_metadata_index({
        "records": [record],
    })

    inventory_row = make_inventory_row(
        relative_path="SOL100/sub/sample.csv",
    )

    matched, status = qa.find_metadata_record(
        inventory_row,
        index,
    )

    assert matched is record
    assert status == "matched_by_relative_path"


def test_find_metadata_record_uses_relative_path():
    record = make_xml_record(
        source_file="sample.xml",
        relative_path="SOL100/sub/sample.xml",
    )

    index = qa.build_metadata_index({
        "records": [record],
    })

    inventory_row = make_inventory_row(
        relative_path="SOL100/sub/sample.csv",
    )

    matched, status = qa.find_metadata_record(
        inventory_row,
        index,
    )

    assert matched is record
    assert status == "matched_by_relative_path"


def test_find_metadata_record_normalizes_windows_separators():
    record = make_xml_record(
        source_file="sample.xml",
        source_relative_path=r"SOL100\sub\sample.xml",
    )

    index = qa.build_metadata_index({
        "records": [record],
    })

    inventory_row = make_inventory_row(
        relative_path=r"SOL100\sub\sample.csv",
    )

    matched, status = qa.find_metadata_record(
        inventory_row,
        index,
    )

    assert matched is record
    assert status == "matched_by_relative_path"


def test_find_metadata_record_prefers_relative_path_over_sol_name():
    first = make_xml_record(
        source_file="sample.xml",
        source_relative_path="SOL100/other/sample.xml",
    )

    second = make_xml_record(
        source_file="sample.xml",
        source_relative_path="SOL100/target/sample.xml",
    )

    index = qa.build_metadata_index({
        "records": [first, second],
    })

    inventory_row = make_inventory_row(
        relative_path="SOL100/target/sample.csv",
    )

    matched, status = qa.find_metadata_record(
        inventory_row,
        index,
    )

    assert matched is second
    assert status == "matched_by_relative_path"


def test_find_metadata_record_falls_back_to_sol_and_name():
    record = make_xml_record(
        source_file="sample.xml",
        sol_folder="SOL100",
    )

    index = qa.build_metadata_index({
        "records": [record],
    })

    inventory_row = make_inventory_row(
        sol_folder="SOL100",
        relative_path="SOL100/other/sample.csv",
    )

    matched, status = qa.find_metadata_record(
        inventory_row,
        index,
    )

    assert matched is record
    assert status == "matched_by_sol_and_name"


def test_find_metadata_record_falls_back_to_unique_stem():
    record = make_xml_record(
        source_file="sample.xml",
        sol_folder="SOL100",
        source_relative_path="SOL100/other/sample.xml",
    )

    index = qa.build_metadata_index({
        "records": [record],
    })

    inventory_row = make_inventory_row(
        sol_folder="SOL102",
        relative_path="SOL102/target/sample.csv",
    )

    matched, status = qa.find_metadata_record(
        inventory_row,
        index,
    )

    assert matched is record
    assert status == "matched_by_unique_stem"


def test_find_metadata_record_reports_ambiguous_unique_stem():
    first = make_xml_record(
        source_file="sample.xml",
        sol_folder="SOL100",
        source_relative_path="SOL100/a/sample.xml",
    )

    second = make_xml_record(
        source_file="sample.xml",
        sol_folder="SOL101",
        source_relative_path="SOL101/b/sample.xml",
    )

    index = qa.build_metadata_index({
        "records": [first, second],
    })

    inventory_row = make_inventory_row(
        sol_folder="SOL102",
        relative_path="SOL102/target/sample.csv",
    )

    matched, status = qa.find_metadata_record(
        inventory_row,
        index,
    )

    assert matched is None
    assert status == "ambiguous_metadata_stem"


def test_find_metadata_record_handles_missing_filename():
    index = qa.build_metadata_index({"records": []})

    matched, status = qa.find_metadata_record(
        {"filename": ""},
        index,
    )

    assert matched is None
    assert status == "missing_inventory_filename"


# --------------------------------------------------
# CSV path resolution
# --------------------------------------------------

def test_find_csv_path_uses_relative_path(tmp_path):
    csv_path = tmp_path / "SOL100" / "sub" / "sample.csv"
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text("QualityFlag\n1\n", encoding="utf-8")

    inventory_row = make_inventory_row(
        relative_path="SOL100/sub/sample.csv",
    )

    result = qa.find_csv_path(
        tmp_path,
        inventory_row,
    )

    assert result == csv_path


def test_find_csv_path_returns_none_for_missing_file(tmp_path):
    inventory_row = make_inventory_row(
        relative_path="SOL100/missing.csv",
        filename="missing.csv",
    )

    assert qa.find_csv_path(
        tmp_path,
        inventory_row,
    ) is None


def test_find_csv_path_returns_none_for_ambiguous_filename(tmp_path):
    first = tmp_path / "SOL100" / "a" / "sample.csv"
    second = tmp_path / "SOL100" / "b" / "sample.csv"

    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)

    first.write_text("A\n1\n", encoding="utf-8")
    second.write_text("A\n2\n", encoding="utf-8")

    inventory_row = make_inventory_row(
        relative_path="",
        filename="sample.csv",
    )

    result = qa.find_csv_path(
        tmp_path,
        inventory_row,
    )

    assert result is None


# --------------------------------------------------
# Field classification
# --------------------------------------------------

def test_quality_candidate_requires_quality_related_term():
    assert qa.field_is_quality_candidate({
        "name": "Quality Flag",
    })

    assert qa.field_is_quality_candidate({
        "name": "Measurement Validity",
    })

    assert not qa.field_is_quality_candidate({
        "name": "Temperature",
    })


def test_generic_flag_alone_is_not_quality_candidate():
    assert not qa.field_is_quality_candidate({
        "name": "Flag",
    })

    assert not qa.field_is_quality_candidate({
        "name": "Status",
    })


def test_operational_context_candidate_is_separate():
    field = {
        "name": "Heater Operational Flag",
    }

    assert qa.field_is_operational_context_candidate(field)
    assert not qa.field_is_quality_candidate(field)


def test_quality_flag_is_not_operational_candidate():
    field = {
        "name": "Quality Flag",
    }

    assert qa.field_is_quality_candidate(field)
    assert not qa.field_is_operational_context_candidate(field)


def test_uncertainty_candidate():
    assert qa.field_is_uncertainty_candidate({
        "name": "Temperature Uncertainty",
    })

    assert qa.field_is_uncertainty_candidate({
        "name": "Measurement Sigma",
    })

    assert not qa.field_is_uncertainty_candidate({
        "name": "Temperature",
    })


def test_get_field_bounds():
    field = {
        "valid_minimum": "-5",
        "valid_maximum": "10",
    }

    assert qa.get_field_bounds(field) == (-5.0, 10.0)


def test_field_has_range():
    assert qa.field_has_range({
        "valid_minimum": "0",
    })

    assert qa.field_has_range({
        "valid_maximum": "10",
    })

    assert not qa.field_has_range({
        "valid_minimum": "",
        "valid_maximum": None,
    })


def test_select_field_categories_keeps_categories_separate():
    fields = [
        {
            "name": "Quality Flag",
        },
        {
            "name": "Heater Operational Flag",
        },
        {
            "name": "Temperature Uncertainty",
        },
        {
            "name": "Temperature",
            "valid_minimum": "0",
            "valid_maximum": "100",
        },
    ]

    selected = qa.select_field_categories(fields)

    categories = [
        item[2]
        for item in selected
    ]

    assert ["quality_field_candidate"] in categories

    assert [
        "operational_context_flag_candidate"
    ] in categories

    assert ["measurement_uncertainty"] in categories

    assert ["range_check"] in categories


# --------------------------------------------------
# CSV column mapping
# --------------------------------------------------

def test_build_column_mapping_exact_header():
    fields = [
        {"name": "Sol"},
        {"name": "Temperature"},
    ]

    mapping, skip, status = qa.build_column_mapping(
        ["Sol", "Temperature"],
        fields,
        True,
    )

    assert mapping == {0: 0, 1: 1}
    assert skip is True
    assert status == "header_exact_match"


def test_build_column_mapping_reordered_header():
    fields = [
        {"name": "Sol"},
        {"name": "Temperature"},
    ]

    mapping, skip, status = qa.build_column_mapping(
        ["Temperature", "Sol"],
        fields,
        True,
    )

    assert mapping == {0: 1, 1: 0}
    assert skip is True
    assert status == "header_reordered_mapped"


def test_build_column_mapping_headerless_csv():
    fields = [
        {"name": "Sol"},
        {"name": "Temperature"},
    ]

    mapping, skip, status = qa.build_column_mapping(
        ["100", "12.5"],
        fields,
        False,
    )

    assert mapping == {0: 0, 1: 1}
    assert skip is False
    assert status == "headerless_positional_mapping"


def test_build_column_mapping_rejects_duplicate_csv_headers():
    fields = [
        {"name": "Sol"},
        {"name": "Temperature"},
    ]

    mapping, skip, status = qa.build_column_mapping(
        ["Sol", "Sol"],
        fields,
        True,
    )

    assert mapping is None
    assert skip is False
    assert status == "duplicate_csv_header_names"


def test_build_column_mapping_rejects_column_count_mismatch():
    fields = [
        {"name": "Sol"},
        {"name": "Temperature"},
    ]

    mapping, skip, status = qa.build_column_mapping(
        ["Sol"],
        fields,
        True,
    )

    assert mapping is None
    assert skip is False
    assert status == "column_count_mismatch"


def test_build_column_mapping_rejects_invalid_xml_field_names():
    fields = [
        {"name": "Sol"},
        {"name": ""},
    ]

    mapping, skip, status = qa.build_column_mapping(
        ["Sol", "Temperature"],
        fields,
        True,
    )

    assert mapping is None
    assert skip is False
    assert status == "invalid_xml_field_names"


# --------------------------------------------------
# Field statistics
# --------------------------------------------------

def test_update_field_stats_checks_documented_boundaries():
    field = {
        "name": "Temperature",
        "valid_minimum": "0",
        "valid_maximum": "10",
    }

    stats = qa.new_field_stats(
        field,
        "range_check",
    )

    values = (
        "-1",
        "0",
        "5",
        "10",
        "11",
        "invalid",
        "",
    )

    for value in values:
        qa.update_field_stats(stats, value)

    assert stats["total_rows"] == 7
    assert stats["missing_count"] == 1
    assert stats["non_empty_count"] == 6
    assert stats["numeric_count"] == 5
    assert stats["non_numeric_count"] == 1
    assert stats["below_valid_minimum"] == 1
    assert stats["above_valid_maximum"] == 1


def test_update_field_stats_accepts_boundary_values():
    field = {
        "name": "Temperature",
        "valid_minimum": "0",
        "valid_maximum": "10",
    }

    stats = qa.new_field_stats(
        field,
        "range_check",
    )

    qa.update_field_stats(stats, "0")
    qa.update_field_stats(stats, "10")

    assert stats["numeric_count"] == 2
    assert stats["below_valid_minimum"] == 0
    assert stats["above_valid_maximum"] == 0


def test_update_field_stats_does_not_count_missing_as_numeric():
    stats = qa.new_field_stats(
        {"name": "Temperature"},
        "range_check",
    )

    qa.update_field_stats(stats, "")
    qa.update_field_stats(stats, "N/A")

    assert stats["total_rows"] == 2
    assert stats["missing_count"] == 2
    assert stats["numeric_count"] == 0
    assert stats["non_empty_count"] == 0


# --------------------------------------------------
# Report row construction
# --------------------------------------------------

def test_make_report_row_without_statistics():
    inventory_row = make_inventory_row()

    row = qa.make_report_row(
        inventory_row,
        None,
        None,
        "file_status",
        "metadata_not_found",
        "Metadata unavailable.",
    )

    assert row["sol_number"] == 100
    assert row["sol_folder"] == "SOL100"
    assert row["csv_file"] == "sample.csv"
    assert row["field_type"] == "file_status"
    assert row["analysis_status"] == "metadata_not_found"
    assert row["total_rows"] == 0


def test_make_report_row_includes_statistics():
    field = {
        "name": "Temperature",
        "description": "Temperature measurement",
        "valid_minimum": "0",
        "valid_maximum": "10",
    }

    stats = qa.new_field_stats(
        field,
        "range_check",
    )

    qa.update_field_stats(stats, "5")
    qa.update_field_stats(stats, "11")

    row = qa.make_report_row(
        make_inventory_row(),
        field,
        stats,
        "range_check",
        "analysed",
        "Test report.",
    )

    assert row["field_name"] == "Temperature"
    assert row["total_rows"] == 2
    assert row["numeric_count"] == 2
    assert row["above_valid_maximum"] == 1
    assert row["valid_minimum"] == 0.0
    assert row["valid_maximum"] == 10.0

    top_values = json.loads(row["top_values_json"])

    assert top_values == {
        "11": 1,
        "5": 1,
    }


# --------------------------------------------------
# CSV analysis
# --------------------------------------------------

def test_analyze_csv_returns_metadata_not_found_status(tmp_path):
    csv_path = tmp_path / "sample.csv"

    write_csv(
        csv_path,
        [
            ["QualityFlag"],
            ["1"],
        ],
    )

    reports = qa.analyze_csv(
        csv_path,
        make_inventory_row(),
        None,
        "metadata_not_found",
    )

    assert len(reports) == 1
    assert reports[0]["analysis_status"] == "metadata_not_found"
    assert reports[0]["field_type"] == "file_status"


def test_analyze_csv_reports_no_xml_fields(tmp_path):
    csv_path = tmp_path / "sample.csv"

    write_csv(
        csv_path,
        [
            ["QualityFlag"],
            ["1"],
        ],
    )

    xml_record = make_xml_record(fields=[])

    reports = qa.analyze_csv(
        csv_path,
        make_inventory_row(),
        xml_record,
        "matched_by_sol_and_name",
    )

    assert len(reports) == 1
    assert reports[0]["analysis_status"] == "no_xml_fields"


def test_analyze_csv_reports_no_target_fields(tmp_path):
    csv_path = tmp_path / "sample.csv"

    write_csv(
        csv_path,
        [
            ["Temperature"],
            ["20"],
        ],
    )

    xml_record = make_xml_record(
        fields=[
            {
                "name": "Temperature",
                "field_number": 1,
                "data_type": "float",
            },
        ],
    )

    reports = qa.analyze_csv(
        csv_path,
        make_inventory_row(),
        xml_record,
        "matched_by_sol_and_name",
    )

    assert len(reports) == 1
    assert reports[0]["analysis_status"] == "no_target_fields"


def test_analyze_csv_analyzes_quality_field(tmp_path):
    csv_path = tmp_path / "sample.csv"

    write_csv(
        csv_path,
        [
            ["Quality Flag"],
            ["1"],
            ["0"],
            ["1"],
        ],
    )

    xml_record = make_xml_record(
        fields=[
            {
                "name": "Quality Flag",
                "field_number": 1,
                "data_type": "integer",
                "description": "Quality flag",
            },
        ],
    )

    reports = qa.analyze_csv(
        csv_path,
        make_inventory_row(),
        xml_record,
        "matched_by_sol_and_name",
    )

    assert len(reports) == 1

    report = reports[0]

    assert report["analysis_status"] == "analysed"
    assert report["field_type"] == "quality_field_candidate"
    assert report["total_rows"] == 3
    assert report["numeric_count"] == 3


def test_analyze_csv_uses_documented_numeric_bounds(tmp_path):
    csv_path = tmp_path / "sample.csv"

    write_csv(
        csv_path,
        [
            ["Temperature"],
            ["-1"],
            ["5"],
            ["11"],
        ],
    )

    xml_record = make_xml_record(
        fields=[
            {
                "name": "Temperature",
                "field_number": 1,
                "data_type": "float",
                "valid_minimum": "0",
                "valid_maximum": "10",
            },
        ],
    )

    reports = qa.analyze_csv(
        csv_path,
        make_inventory_row(),
        xml_record,
        "matched_by_sol_and_name",
    )

    assert len(reports) == 1

    report = reports[0]

    assert report["analysis_status"] == "analysed"
    assert report["field_type"] == "range_check"
    assert report["below_valid_minimum"] == 1
    assert report["above_valid_maximum"] == 1

    # Range checks are diagnostics, not scientific validity verdicts.
    assert "not automatically classified" in report["notes"]


def test_analyze_csv_reports_empty_file(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("", encoding="utf-8")

    xml_record = make_xml_record()

    reports = qa.analyze_csv(
        csv_path,
        make_inventory_row(filename="empty.csv"),
        xml_record,
        "matched_by_sol_and_name",
    )

    assert len(reports) == 1
    assert reports[0]["analysis_status"] == "empty_file"


# --------------------------------------------------
# Full inventory analysis
# --------------------------------------------------

def test_run_analysis_processes_csv_inventory(tmp_path):
    csv_path = tmp_path / "SOL100" / "sample.csv"

    write_csv(
        csv_path,
        [
            ["Quality Flag"],
            ["1"],
            ["0"],
        ],
    )

    inventory = [
        make_inventory_row(),
    ]

    metadata = {
        "records": [
            make_xml_record(
                source_file="sample.xml",
                source_relative_path="SOL100/sample.xml",
                fields=[
                    {
                        "name": "Quality Flag",
                        "field_number": 1,
                        "data_type": "integer",
                    },
                ],
            ),
        ],
    }

    reports = qa.run_analysis(
        tmp_path,
        inventory,
        metadata,
    )

    assert len(reports) == 1
    assert reports[0]["analysis_status"] == "analysed"
    assert reports[0]["field_type"] == "quality_field_candidate"


def test_run_analysis_ignores_non_csv_inventory_entries(tmp_path):
    inventory = [
        make_inventory_row(extension="xml"),
    ]

    reports = qa.run_analysis(
        tmp_path,
        inventory,
        {"records": []},
    )

    assert reports == []


def test_run_analysis_reports_missing_csv(tmp_path):
    inventory = [
        make_inventory_row(),
    ]

    reports = qa.run_analysis(
        tmp_path,
        inventory,
        {"records": []},
    )

    assert len(reports) == 1
    assert (
        reports[0]["analysis_status"]
        == "file_not_found_or_ambiguous"
    )


# --------------------------------------------------
# Report and summary output
# --------------------------------------------------

def test_write_report_creates_parent_directory(tmp_path):
    output_path = tmp_path / "reports" / "quality.csv"

    rows = [
        {
            "sol_number": 100,
            "field_name": "QualityFlag",
            "analysis_status": "analysed",
        },
    ]

    qa.write_report(output_path, rows)

    assert output_path.is_file()

    with output_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        result = list(csv.DictReader(file))

    assert len(result) == 1
    assert result[0]["sol_number"] == "100"
    assert result[0]["field_name"] == "QualityFlag"


def test_build_summary_counts_categories_separately():
    rows = [
        {
            "analysis_status": "analysed",
            "field_type": "quality_field_candidate",
            "total_rows": 5,
            "missing_count": 1,
            "notes": "Column mapping: header_exact_match.",
        },
        {
            "analysis_status": "analysed",
            "field_type": "operational_context_flag_candidate",
            "total_rows": 5,
            "missing_count": 0,
            "notes": "Column mapping: header_exact_match.",
        },
        {
            "analysis_status": "analysed",
            "field_type": "measurement_uncertainty",
            "total_rows": 5,
            "missing_count": 0,
            "notes": "Column mapping: header_exact_match.",
        },
        {
            "analysis_status": "analysed",
            "field_type": "range_check",
            "total_rows": 5,
            "missing_count": 0,
            "below_valid_minimum": 1,
            "above_valid_maximum": 2,
            "notes": "Column mapping: header_exact_match.",
        },
        {
            "analysis_status": "metadata_not_found",
            "field_type": "file_status",
        },
    ]

    summary = qa.build_summary(rows)

    assert summary["report_row_count"] == 5
    assert summary["analysed_field_reports"] == 4

    assert summary["quality_field_candidate_reports"] == 1
    assert summary["operational_context_flag_candidate_reports"] == 1
    assert summary["measurement_uncertainty_reports"] == 1
    assert summary["range_check_reports"] == 1

    assert summary["file_status_reports"] == 1

    assert summary["total_values_below_declared_minimum"] == 1
    assert summary["total_values_above_declared_maximum"] == 2

    assert summary["column_mapping_status_counts"] == {
        "header_exact_match": 4,
    }

    assert "limitations" in summary
    assert isinstance(summary["limitations"], list)


def test_save_summary_writes_valid_json(tmp_path):
    output_path = tmp_path / "reports" / "summary.json"

    summary = {
        "analyzer": "MEDA Quality Analyzer",
        "report_row_count": 3,
    }

    qa.save_summary(output_path, summary)

    assert output_path.is_file()

    loaded = json.loads(
        output_path.read_text(encoding="utf-8")
    )

    assert loaded["analyzer"] == "MEDA Quality Analyzer"
    assert loaded["report_row_count"] == 3


# --------------------------------------------------
# Report schema stability
# --------------------------------------------------

def test_report_columns_are_unique():
    assert len(qa.REPORT_COLUMNS) == len(
        set(qa.REPORT_COLUMNS)
    )


def test_report_columns_include_ranker_required_fields():
    required_columns = {
        "sol_number",
        "analysis_status",
        "valid_minimum",
        "valid_maximum",
        "numeric_count",
        "below_valid_minimum",
        "above_valid_maximum",
    }

    assert required_columns.issubset(
        set(qa.REPORT_COLUMNS)
    )


def test_report_schema_keeps_categories_separate():
    assert "field_type" in qa.REPORT_COLUMNS

    assert (
        "quality_field_candidate"
        != "operational_context_flag_candidate"
    )

    assert (
        "measurement_uncertainty"
        != "range_check"
    )