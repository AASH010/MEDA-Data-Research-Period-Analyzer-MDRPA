
from __future__ import annotations

import csv
import json

import pytest

from backend.analyzers import coverage_analyzer as analyzer


# --------------------------------------------------
# Identification helpers
# --------------------------------------------------

@pytest.mark.parametrize(
    ("folder_name", "expected"),
    [
        ("SOL100", 100),
        ("SOL_0100", 100),
        ("SOL-100", 100),
        ("sol250", 250),
        ("SOL0", 0),
        ("invalid", None),
        ("SOL100-extra", None),
    ],
)
def test_get_sol_number(folder_name, expected):
    assert analyzer.get_sol_number(folder_name) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("WE__0100___________CAL_ATS.csv", "ATS"),
        ("WE__0100___________CAL_PS.xml", "PS"),
        ("sample_CAL_WS_product.csv", "WS"),
        ("sample.csv", None),
    ],
)
def test_get_product_code(filename, expected):
    assert analyzer.get_product_code(filename) == expected


def test_normalize_name():
    assert analyzer.normalize_name("Solar_Time-Field") == "solartimefield"


def test_safe_int():
    assert analyzer.safe_int("12") == 12
    assert analyzer.safe_int("invalid", default=-1) == -1
    assert analyzer.safe_int(None, default=5) == 5


def test_safe_float():
    assert analyzer.safe_float("12.5") == 12.5
    assert analyzer.safe_float("nan") is None
    assert analyzer.safe_float("inf") is None
    assert analyzer.safe_float("invalid") is None


# --------------------------------------------------
# Metadata indexing and XML matching
# --------------------------------------------------

def test_build_metadata_index_supports_source_relative_path():
    record = {
        "source_file": "sample.xml",
        "sol_folder": "SOL100",
        "source_relative_path": "SOL100/nested/sample.xml",
    }

    index = analyzer.build_metadata_index({
        "records": [record],
    })

    assert index[("path", "sol100/nested/sample.xml")] == [record]


def test_build_metadata_index_supports_legacy_relative_path():
    record = {
        "source_file": "sample.xml",
        "sol_folder": "SOL100",
        "relative_path": "SOL100/nested/sample.xml",
    }

    index = analyzer.build_metadata_index({
        "records": [record],
    })

    assert index[("path", "sol100/nested/sample.xml")] == [record]


def test_build_metadata_index_supports_both_path_fields():
    record = {
        "source_file": "sample.xml",
        "sol_folder": "SOL100",
        "source_relative_path": "SOL100/sample.xml",
        "relative_path": "SOL100/sample.xml",
    }

    index = analyzer.build_metadata_index({
        "records": [record],
    })

    assert index[("path", "sol100/sample.xml")] == [record]


def test_find_xml_record_uses_relative_path_first():
    first = {
        "source_file": "sample.xml",
        "sol_folder": "SOL100",
        "source_relative_path": "SOL100/first/sample.xml",
    }

    second = {
        "source_file": "sample.xml",
        "sol_folder": "SOL100",
        "source_relative_path": "SOL100/second/sample.xml",
    }

    metadata_index = analyzer.build_metadata_index({
        "records": [first, second],
    })

    csv_record = {
        "sol_folder": "SOL100",
        "filename": "sample.csv",
        "relative_path": "SOL100/second/sample.csv",
    }

    assert analyzer.find_xml_record(
        csv_record,
        metadata_index,
    ) is second


def test_find_xml_record_uses_source_relative_path():
    expected = {
        "source_file": "sample.xml",
        "sol_folder": "SOL100",
        "source_relative_path": "SOL100/nested/sample.xml",
    }

    metadata_index = analyzer.build_metadata_index({
        "records": [expected],
    })

    csv_record = {
        "sol_folder": "SOL100",
        "filename": "sample.csv",
        "relative_path": "SOL100/nested/sample.csv",
    }

    assert analyzer.find_xml_record(
        csv_record,
        metadata_index,
    ) is expected


def test_find_xml_record_normalizes_windows_separators():
    expected = {
        "source_file": "sample.xml",
        "sol_folder": "SOL100",
        "source_relative_path": "SOL100/nested/sample.xml",
    }

    metadata_index = analyzer.build_metadata_index({
        "records": [expected],
    })

    csv_record = {
        "sol_folder": "SOL100",
        "filename": "sample.csv",
        "relative_path": r"SOL100\nested\sample.csv",
    }

    assert analyzer.find_xml_record(
        csv_record,
        metadata_index,
    ) is expected


def test_find_xml_record_falls_back_to_unique_filename():
    expected = {
        "source_file": "sample.xml",
        "sol_folder": "SOL100",
    }

    metadata_index = analyzer.build_metadata_index({
        "records": [expected],
    })

    csv_record = {
        "sol_folder": "SOL100",
        "filename": "sample.csv",
    }

    assert analyzer.find_xml_record(
        csv_record,
        metadata_index,
    ) is expected


def test_find_xml_record_rejects_ambiguous_filename_fallback():
    first = {
        "source_file": "sample.xml",
        "sol_folder": "SOL100",
    }

    second = {
        "source_file": "sample.xml",
        "sol_folder": "SOL100",
    }

    metadata_index = analyzer.build_metadata_index({
        "records": [first, second],
    })

    csv_record = {
        "sol_folder": "SOL100",
        "filename": "sample.csv",
    }

    assert analyzer.find_xml_record(
        csv_record,
        metadata_index,
    ) is None


def test_find_xml_record_rejects_ambiguous_relative_path():
    first = {
        "source_file": "sample.xml",
        "sol_folder": "SOL100",
        "source_relative_path": "SOL100/sample.xml",
    }

    second = {
        "source_file": "sample.xml",
        "sol_folder": "SOL100",
        "source_relative_path": "SOL100/sample.xml",
    }

    metadata_index = analyzer.build_metadata_index({
        "records": [first, second],
    })

    csv_record = {
        "sol_folder": "SOL100",
        "filename": "sample.csv",
        "relative_path": "SOL100/sample.csv",
    }

    assert analyzer.find_xml_record(
        csv_record,
        metadata_index,
    ) is None


def test_find_xml_record_does_not_match_different_sol():
    expected = {
        "source_file": "sample.xml",
        "sol_folder": "SOL101",
    }

    metadata_index = analyzer.build_metadata_index({
        "records": [expected],
    })

    csv_record = {
        "sol_folder": "SOL100",
        "filename": "sample.csv",
    }

    assert analyzer.find_xml_record(
        csv_record,
        metadata_index,
    ) is None


# --------------------------------------------------
# CSV path resolution
# --------------------------------------------------

def test_resolve_csv_path_uses_relative_path(tmp_path):
    csv_path = tmp_path / "SOL100" / "nested" / "sample.csv"
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text("time,value\n1,2\n", encoding="utf-8")

    record = {
        "sol_folder": "SOL100",
        "filename": "sample.csv",
        "relative_path": "SOL100/nested/sample.csv",
    }

    assert analyzer.resolve_csv_path(
        tmp_path,
        record,
    ) == csv_path


def test_resolve_csv_path_uses_unique_filename_fallback(tmp_path):
    sol_dir = tmp_path / "SOL100"
    sol_dir.mkdir()

    csv_path = sol_dir / "sample.csv"
    csv_path.write_text("time,value\n1,2\n", encoding="utf-8")

    record = {
        "sol_folder": "SOL100",
        "filename": "sample.csv",
    }

    assert analyzer.resolve_csv_path(
        tmp_path,
        record,
    ) == csv_path


def test_resolve_csv_path_rejects_ambiguous_filename(tmp_path):
    sol_dir = tmp_path / "SOL100"
    first_dir = sol_dir / "first"
    second_dir = sol_dir / "second"

    first_dir.mkdir(parents=True)
    second_dir.mkdir(parents=True)

    (first_dir / "sample.csv").touch()
    (second_dir / "sample.csv").touch()

    record = {
        "sol_folder": "SOL100",
        "filename": "sample.csv",
    }

    assert analyzer.resolve_csv_path(
        tmp_path,
        record,
    ) is None


def test_resolve_csv_path_returns_none_when_missing(tmp_path):
    record = {
        "sol_folder": "SOL100",
        "filename": "missing.csv",
    }

    assert analyzer.resolve_csv_path(
        tmp_path,
        record,
    ) is None


# --------------------------------------------------
# CSV column mapping
# --------------------------------------------------

def test_build_column_mapping_exact_header():
    fields = [
        {"name": "SCLK"},
        {"name": "TEMPERATURE"},
    ]

    mapping, status, skip_header = analyzer.build_column_mapping(
        ["SCLK", "TEMPERATURE"],
        fields,
        True,
    )

    assert mapping == {0: 0, 1: 1}
    assert status == "header_exact_match"
    assert skip_header is True


def test_build_column_mapping_without_header():
    fields = [
        {"name": "SCLK"},
        {"name": "TEMPERATURE"},
    ]

    mapping, status, skip_header = analyzer.build_column_mapping(
        None,
        fields,
        False,
    )

    assert mapping == {0: 0, 1: 1}
    assert status == "positional_no_header"
    assert skip_header is False


def test_build_column_mapping_reordered_header():
    fields = [
        {"name": "SCLK"},
        {"name": "TEMPERATURE"},
    ]

    mapping, status, skip_header = analyzer.build_column_mapping(
        ["TEMPERATURE", "SCLK"],
        fields,
        True,
    )

    assert mapping == {0: 1, 1: 0}
    assert status == "header_reordered_mapped"
    assert skip_header is True


def test_build_column_mapping_rejects_duplicate_csv_headers():
    fields = [
        {"name": "SCLK"},
        {"name": "TEMPERATURE"},
    ]

    mapping, status, skip_header = analyzer.build_column_mapping(
        ["SCLK", "SCLK"],
        fields,
        True,
    )

    assert mapping is None
    assert status == "duplicate_csv_header_names"
    assert skip_header is False


def test_build_column_mapping_rejects_invalid_xml_field_names():
    fields = [
        {"name": "SCLK"},
        {"name": ""},
    ]

    mapping, status, skip_header = analyzer.build_column_mapping(
        ["SCLK", "TEMPERATURE"],
        fields,
        True,
    )

    assert mapping is None
    assert status == "invalid_xml_field_names"
    assert skip_header is False


# --------------------------------------------------
# CSV analysis
# --------------------------------------------------

def test_analyze_csv_with_valid_metadata(tmp_path):
    csv_path = tmp_path / "sample.csv"

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.writer(file)
        writer.writerow(["SCLK", "TEMPERATURE"])
        writer.writerow(["1", "200.5"])
        writer.writerow(["2", "201.5"])
        writer.writerow(["3", "202.5"])

    xml_record = {
        "parse_status": "success",
        "has_header": True,
        "fields": [
            {
                "name": "SCLK",
                "data_type": "ASCII_Real",
                "field_number": "1",
            },
            {
                "name": "TEMPERATURE",
                "data_type": "ASCII_Real",
                "field_number": "2",
            },
        ],
        "metadata_warnings": [],
    }

    result = analyzer.analyze_csv(
        csv_path,
        xml_record,
    )

    assert result["row_count"] == 3
    assert result["time_field"] == "SCLK"
    assert result["time_kind"] == "sclk"
    assert result["parsed_timestamp_count"] == 3
    assert result["numeric_value_count"] == 3
    assert result["measurement_coverage_status"] == (
        "timestamp_analysis_available"
    )
    assert result["column_mapping_status"] == "header_exact_match"


def test_analyze_csv_without_xml_metadata(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("1,2\n", encoding="utf-8")

    result = analyzer.analyze_csv(
        csv_path,
        None,
    )

    assert result["measurement_coverage_status"] == "no_xml_metadata"
    assert result["column_mapping_status"] == "no_xml_metadata"


def test_analyze_csv_with_failed_xml_metadata(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("1,2\n", encoding="utf-8")

    xml_record = {
        "parse_status": "failed",
        "parse_error": "Invalid XML",
    }

    result = analyzer.analyze_csv(
        csv_path,
        xml_record,
    )

    assert result["measurement_coverage_status"] == "xml_parse_failed"
    assert result["column_mapping_status"] == "xml_parse_failed"


def test_analyze_csv_with_empty_file(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.touch()

    xml_record = {
        "parse_status": "success",
        "has_header": True,
        "fields": [
            {
                "name": "SCLK",
                "data_type": "ASCII_Real",
                "field_number": "1",
            },
        ],
        "metadata_warnings": [],
    }

    result = analyzer.analyze_csv(
        csv_path,
        xml_record,
    )

    assert result["measurement_coverage_status"] == "empty_file"
    assert result["column_mapping_status"] == "not_available"


@pytest.mark.parametrize(
    "gap_factor",
    [1, 0, -1, float("nan"), float("inf")],
)
def test_analyze_csv_rejects_invalid_gap_factor(tmp_path, gap_factor):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("1,2\n", encoding="utf-8")

    with pytest.raises(ValueError):
        analyzer.analyze_csv(
            csv_path,
            None,
            gap_factor=gap_factor,
        )


# --------------------------------------------------
# Integrated inventory analysis
# --------------------------------------------------

def test_analyze_coverage_matches_nested_xml_by_relative_path(tmp_path):
    csv_path = tmp_path / "SOL100" / "nested" / "sample.csv"
    csv_path.parent.mkdir(parents=True)

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.writer(file)
        writer.writerow(["SCLK", "TEMPERATURE"])
        writer.writerow(["1", "200"])
        writer.writerow(["2", "201"])

    matching_xml = {
        "source_file": "sample.xml",
        "sol_folder": "SOL100",
        "source_relative_path": "SOL100/nested/sample.xml",
        "parse_status": "success",
        "has_header": True,
        "fields": [
            {
                "name": "SCLK",
                "data_type": "ASCII_Real",
                "field_number": "1",
            },
            {
                "name": "TEMPERATURE",
                "data_type": "ASCII_Real",
                "field_number": "2",
            },
        ],
        "metadata_warnings": [],
    }

    other_xml = {
        "source_file": "sample.xml",
        "sol_folder": "SOL100",
        "source_relative_path": "SOL100/other/sample.xml",
        "parse_status": "failed",
        "parse_error": "This is not the matching XML.",
    }

    inventory = [
        {
            "sol_folder": "SOL100",
            "sol_number": 100,
            "filename": "sample.csv",
            "relative_path": "SOL100/nested/sample.csv",
            "extension": ".csv",
            "product_code": "ATS",
            "file_size_bytes": csv_path.stat().st_size,
        },
    ]

    metadata = {
        "records": [
            other_xml,
            matching_xml,
        ],
    }

    reports = analyzer.analyze_coverage(
        tmp_path,
        inventory,
        metadata,
    )

    assert len(reports) == 1
    assert reports[0]["row_count"] == 2
    assert reports[0]["time_field"] == "SCLK"
    assert reports[0]["measurement_coverage_status"] == (
        "timestamp_analysis_available"
    )


def test_analyze_coverage_skips_non_csv_inventory_records(tmp_path):
    inventory = [
        {
            "sol_folder": "SOL100",
            "filename": "sample.xml",
            "extension": ".xml",
        },
    ]

    reports = analyzer.analyze_coverage(
        tmp_path,
        inventory,
        {"records": []},
    )

    assert reports == []


def test_analyze_coverage_reports_missing_csv_file(tmp_path):
    inventory = [
        {
            "sol_folder": "SOL100",
            "sol_number": 100,
            "filename": "missing.csv",
            "extension": ".csv",
            "product_code": "ATS",
        },
    ]

    reports = analyzer.analyze_coverage(
        tmp_path,
        inventory,
        {"records": []},
    )

    assert len(reports) == 1
    assert reports[0]["measurement_coverage_status"] == "file_not_found"


def test_analyze_coverage_reports_empty_csv_file(tmp_path):
    csv_path = tmp_path / "SOL100" / "empty.csv"
    csv_path.parent.mkdir(parents=True)
    csv_path.touch()

    inventory = [
        {
            "sol_folder": "SOL100",
            "sol_number": 100,
            "filename": "empty.csv",
            "relative_path": "SOL100/empty.csv",
            "extension": ".csv",
            "product_code": "ATS",
            "file_size_bytes": 0,
        },
    ]

    reports = analyzer.analyze_coverage(
        tmp_path,
        inventory,
        {"records": []},
    )

    assert len(reports) == 1
    assert reports[0]["measurement_coverage_status"] == "empty_file"


# --------------------------------------------------
# Sol range and product summaries
# --------------------------------------------------

def test_longest_consecutive_range():
    result = analyzer.longest_consecutive_range(
        [100, 101, 102, 105, 106, 110]
    )

    assert result == {
        "start_sol": 100,
        "end_sol": 102,
        "length_sols": 3,
    }


def test_longest_consecutive_range_empty():
    assert analyzer.longest_consecutive_range([]) == {
        "start_sol": None,
        "end_sol": None,
        "length_sols": 0,
    }


def test_build_product_summary():
    reports = [
        {
            "product_code": "ATS",
            "sol_number": 100,
            "row_count": 10,
            "numeric_value_count": 20,
            "parsed_timestamp_count": 10,
            "measurement_coverage_status": (
                "timestamp_analysis_available"
            ),
        },
        {
            "product_code": "ATS",
            "sol_number": 101,
            "row_count": 5,
            "numeric_value_count": 10,
            "parsed_timestamp_count": 5,
            "measurement_coverage_status": (
                "timestamp_analysis_available"
            ),
        },
        {
            "product_code": "ATS",
            "sol_number": 103,
            "row_count": 7,
            "numeric_value_count": 14,
            "parsed_timestamp_count": 7,
            "measurement_coverage_status": "timestamps_not_interpreted",
        },
        {
            "product_code": "PS",
            "sol_number": 100,
            "row_count": 0,
        },
    ]

    summary = analyzer.build_product_summary(
        reports,
        100,
        103,
    )

    assert set(summary) == {"ATS"}

    assert summary["ATS"]["csv_file_count"] == 3
    assert summary["ATS"]["sols_with_rows"] == 3
    assert summary["ATS"]["sols_without_rows"] == 1
    assert summary["ATS"]["present_sols"] == [100, 101, 103]
    assert summary["ATS"]["missing_sols"] == [102]
    assert summary["ATS"]["total_rows"] == 22
    assert summary["ATS"]["total_numeric_values"] == 44
    assert summary["ATS"]["total_parsed_timestamps"] == 22
    assert summary["ATS"]["files_with_available_timestamp_analysis"] == 2


# --------------------------------------------------
# Output writers
# --------------------------------------------------

def test_save_coverage_csv(tmp_path):
    output_file = tmp_path / "reports" / "coverage.csv"

    reports = [
        {
            "sol_number": 100,
            "sol_folder": "SOL100",
            "product_code": "ATS",
            "filename": "sample.csv",
            "row_count": 10,
            "measurement_coverage_status": (
                "timestamp_analysis_available"
            ),
        },
    ]

    analyzer.save_coverage_csv(
        reports,
        output_file,
    )

    assert output_file.is_file()

    with output_file.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 1
    assert rows[0]["sol_number"] == "100"
    assert rows[0]["filename"] == "sample.csv"


def test_save_summary_json(tmp_path):
    output_file = tmp_path / "reports" / "summary.json"

    summary = {
        "analysis_range": {
            "start_sol": 100,
            "end_sol": 110,
        },
        "products": {
            "ATS": {
                "sols_with_rows": 10,
            },
        },
    }

    analyzer.save_summary_json(
        summary,
        output_file,
    )

    assert output_file.is_file()

    loaded = json.loads(
        output_file.read_text(encoding="utf-8")
    )

    assert loaded == summary
