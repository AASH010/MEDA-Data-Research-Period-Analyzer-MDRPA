

from __future__ import annotations

from pathlib import Path

import pytest

from backend.analyzers import synchronization_analyzer as analyzer


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def make_inventory_row(
    *,
    filename="sample.csv",
    sol_folder="SOL100",
    sol_number=100,
    relative_path="SOL100/sample.csv",
):
    return {
        "filename": filename,
        "sol_folder": sol_folder,
        "sol_number": sol_number,
        "relative_path": relative_path,
        "extension": "csv",
        "product_code": "ATS",
    }


def make_metadata_record(
    *,
    source_file="sample.xml",
    sol_folder="SOL100",
    sol_number=100,
    relative_path="SOL100/sample.xml",
    source_relative_path=None,
):
    record = {
        "source_file": source_file,
        "sol_folder": sol_folder,
        "sol_number": sol_number,
    }

    if relative_path is not None:
        record["relative_path"] = relative_path

    if source_relative_path is not None:
        record["source_relative_path"] = source_relative_path

    return record


# --------------------------------------------------
# General helpers
# --------------------------------------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SOL100", 100),
        ("SOL_0100", 100),
        ("SOL-100", 100),
        ("sol250", 250),
        ("invalid", None),
        (None, None),
    ],
)
def test_get_sol_number(value, expected):
    assert analyzer.get_sol_number(value) == expected


def test_normalize_path_handles_windows_separators():
    assert (
        analyzer.normalize_path(
            r"SOL100\nested\sample.xml"
        )
        == "sol100/nested/sample.xml"
    )


def test_portable_stem_handles_windows_path():
    assert (
        analyzer.portable_stem(
            r"SOL100\nested\sample.XML"
        )
        == "sample"
    )


def test_file_identity_preserves_platform_semantics(tmp_path):
    first = tmp_path / "Sample.csv"
    second = tmp_path / "sample.csv"

    first.touch()
    second.touch()

    first_identity = analyzer.file_identity(first)
    second_identity = analyzer.file_identity(second)

    if analyzer.os.name == "nt":
        assert first_identity == second_identity
    else:
        assert first_identity != second_identity


# --------------------------------------------------
# Metadata indexing and matching
# --------------------------------------------------

def test_build_metadata_index_keeps_duplicate_records():
    first = make_metadata_record()
    second = make_metadata_record()

    index = analyzer.build_metadata_index([first, second])

    assert len(index["by_stem"]["sample"]) == 2
    assert len(index["by_path"]["sol100/sample.xml"]) == 2


def test_build_metadata_index_handles_windows_source_file():
    record = make_metadata_record(
        source_file=r"SOL100\nested\sample.xml",
        relative_path=None,
        source_relative_path=r"SOL100\nested\sample.xml",
    )

    index = analyzer.build_metadata_index([record])

    assert record in index["by_stem"]["sample"]
    assert (
        record
        in index["by_path"]["sol100/nested/sample.xml"]
    )


def test_find_metadata_record_matches_windows_relative_path():
    record = make_metadata_record(
        relative_path=None,
        source_relative_path=r"SOL100\nested\sample.xml",
    )

    index = analyzer.build_metadata_index([record])

    row = make_inventory_row(
        relative_path=r"SOL100\nested\sample.csv",
    )

    matched, status = analyzer.find_metadata_record(
        row,
        index,
    )

    assert matched is record
    assert status == "matched_by_relative_path"


def test_find_metadata_record_matches_by_sol_and_name():
    record = make_metadata_record()

    index = analyzer.build_metadata_index([record])

    row = make_inventory_row(
        relative_path="",
    )

    matched, status = analyzer.find_metadata_record(
        row,
        index,
    )

    assert matched is record
    assert status == "matched_by_sol_and_name"


def test_find_metadata_record_reports_ambiguous_path():
    first = make_metadata_record()
    second = make_metadata_record()

    index = analyzer.build_metadata_index([first, second])

    row = make_inventory_row()

    matched, status = analyzer.find_metadata_record(
        row,
        index,
    )

    assert matched is None
    assert status == "ambiguous_metadata_path"


def test_find_metadata_record_reports_missing_filename():
    index = analyzer.build_metadata_index([])

    matched, status = analyzer.find_metadata_record(
        {"filename": ""},
        index,
    )

    assert matched is None
    assert status == "missing_inventory_filename"


# --------------------------------------------------
# CSV path resolution
# --------------------------------------------------

def test_resolve_csv_path_handles_windows_relative_path(tmp_path):
    csv_path = tmp_path / "SOL100" / "nested" / "sample.csv"
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text("time,value\n1,2\n", encoding="utf-8")

    row = make_inventory_row(
        relative_path=r"SOL100\nested\sample.csv",
    )

    resolved = analyzer.resolve_csv_path(tmp_path, row)

    assert resolved == csv_path


def test_resolve_csv_path_uses_sol_folder_fallback(tmp_path):
    csv_path = tmp_path / "SOL100" / "sample.csv"
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text("time,value\n1,2\n", encoding="utf-8")

    row = make_inventory_row(
        relative_path="missing/sample.csv",
    )

    resolved = analyzer.resolve_csv_path(tmp_path, row)

    assert resolved == csv_path


def test_resolve_csv_path_returns_none_for_missing_file(tmp_path):
    row = make_inventory_row()

    assert analyzer.resolve_csv_path(tmp_path, row) is None


def test_resolve_csv_path_returns_none_for_ambiguous_filename(tmp_path):
    first = tmp_path / "SOL100" / "a" / "sample.csv"
    second = tmp_path / "SOL100" / "b" / "sample.csv"

    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)

    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")

    row = make_inventory_row(
        relative_path="",
    )

    assert analyzer.resolve_csv_path(tmp_path, row) is None


# --------------------------------------------------
# One-to-one matching
# --------------------------------------------------

def test_match_one_to_one_matches_exact_values():
    matched, differences = analyzer.match_one_to_one(
        [1.0, 2.0, 3.0],
        [1.0, 2.0, 3.0],
        0.0,
    )

    assert matched == 3
    assert differences == [0.0, 0.0, 0.0]


def test_match_one_to_one_retains_duplicate_occurrences():
    matched, differences = analyzer.match_one_to_one(
        [1.0, 1.0, 2.0],
        [1.0, 2.0],
        0.0,
    )

    assert matched == 2
    assert differences == [0.0, 0.0]


def test_match_one_to_one_sorts_unsorted_inputs():
    matched, differences = analyzer.match_one_to_one(
        [2.0, 1.0, 1.0],
        [2.05, 1.05],
        0.1,
    )

    assert matched == 2
    assert differences == pytest.approx([0.05, 0.05])


@pytest.mark.parametrize(
    "tolerance",
    [-1.0, float("inf"), float("nan")],
)
def test_match_one_to_one_rejects_invalid_tolerance(tolerance):
    with pytest.raises(ValueError):
        analyzer.match_one_to_one(
            [1.0],
            [1.0],
            tolerance,
        )


# --------------------------------------------------
# Timestamp series comparison
# --------------------------------------------------

def test_compare_timestamp_series_matches_same_axis():
    result = analyzer.compare_timestamp_series(
        [1.0, 2.0, 3.0],
        [1.0, 2.0, 3.0],
        0.0,
        "lmst",
        "lmst",
    )

    assert result["comparison_status"] == "analysed"
    assert result["matched_timestamps"] == 3
    assert result["first_count"] == 3
    assert result["second_count"] == 3
    assert result["match_rate_first_percent"] == 100.0


def test_compare_timestamp_series_sorts_unsorted_inputs():
    result = analyzer.compare_timestamp_series(
        [3.0, 1.0, 2.0],
        [2.0, 1.0, 3.0],
        0.0,
        "sclk",
        "sclk",
    )

    assert result["comparison_status"] == "analysed"
    assert result["overlap_start"] == 1.0
    assert result["overlap_end"] == 3.0
    assert result["matched_timestamps"] == 3


def test_compare_timestamp_series_retains_duplicates():
    result = analyzer.compare_timestamp_series(
        [1.0, 1.0, 2.0],
        [1.0, 2.0],
        0.0,
        "lmst",
        "lmst",
    )

    assert result["comparison_status"] == "analysed"
    assert result["first_count"] == 3
    assert result["second_count"] == 2
    assert result["matched_timestamps"] == 2
    assert result["first_unmatched"] == 1


def test_compare_timestamp_series_rejects_different_axes():
    result = analyzer.compare_timestamp_series(
        [1.0, 2.0],
        [1.0, 2.0],
        0.0,
        "lmst",
        "ltst",
    )

    assert result["comparison_status"] == "incompatible_time_axes"
    assert result["matched_timestamps"] == 0


def test_compare_timestamp_series_detects_no_overlap():
    result = analyzer.compare_timestamp_series(
        [1.0, 2.0],
        [5.0, 6.0],
        0.0,
        "sclk",
        "sclk",
    )

    assert result["comparison_status"] == "no_temporal_overlap"


def test_compare_timestamp_series_detects_empty_series():
    result = analyzer.compare_timestamp_series(
        [],
        [1.0, 2.0],
        0.0,
        "utc",
        "utc",
    )

    assert result["comparison_status"] == "empty_series"


@pytest.mark.parametrize(
    "tolerance",
    [-1.0, float("inf"), float("nan")],
)
def test_compare_timestamp_series_rejects_invalid_tolerance(tolerance):
    with pytest.raises(ValueError):
        analyzer.compare_timestamp_series(
            [1.0],
            [1.0],
            tolerance,
            "utc",
            "utc",
        )


# --------------------------------------------------
# Full run_analysis integration
# --------------------------------------------------

def test_run_analysis_processes_inventory_and_builds_product_pair(
    tmp_path,
):
    input_root = tmp_path / "input"
    sol_dir = input_root / "SOL100"
    sol_dir.mkdir(parents=True)

    first_csv = sol_dir / "sample_ATS.csv"
    second_csv = sol_dir / "sample_PS.csv"

    # LMST requires the Sol number followed by M.
    csv_content = (
        "LMST,MEASUREMENT\n"
        "100M00:00:01,10\n"
        "100M00:00:02,20\n"
        "100M00:00:03,30\n"
    )

    first_csv.write_text(csv_content, encoding="utf-8")
    second_csv.write_text(csv_content, encoding="utf-8")

    fields = [
        {
            "name": "LMST",
            "field_number": 1,
            "data_type": "string",
        },
        {
            "name": "MEASUREMENT",
            "field_number": 2,
            "data_type": "float",
        },
    ]

    inventory = [
        {
            "filename": "sample_ATS.csv",
            "sol_folder": "SOL100",
            "sol_number": 100,
            "relative_path": "SOL100/sample_ATS.csv",
            "extension": "csv",
            "product_code": "ATS",
        },
        {
            "filename": "sample_PS.csv",
            "sol_folder": "SOL100",
            "sol_number": 100,
            "relative_path": "SOL100/sample_PS.csv",
            "extension": "csv",
            "product_code": "PS",
        },
    ]

    metadata_records = [
        {
            "source_file": "sample_ATS.xml",
            "sol_folder": "SOL100",
            "sol_number": 100,
            "relative_path": "SOL100/sample_ATS.xml",
            "has_header": True,
            "parse_status": "parsed",
            "fields": fields,
        },
        {
            "source_file": "sample_PS.xml",
            "sol_folder": "SOL100",
            "sol_number": 100,
            "relative_path": "SOL100/sample_PS.xml",
            "has_header": True,
            "parse_status": "parsed",
            "fields": fields,
        },
    ]

    file_reports, pair_reports = analyzer.run_analysis(
        input_root=input_root,
        inventory=inventory,
        metadata_records=metadata_records,
        tolerance=0.0,
    )

    assert len(file_reports) == 2

    assert all(
        row["analysis_status"] == "analysed"
        for row in file_reports
    ), file_reports

    assert len(pair_reports) == 1

    pair = pair_reports[0]

    assert pair["sol_number"] == 100
    assert pair["product_1"] == "ATS"
    assert pair["product_2"] == "PS"
    assert pair["comparison_status"] == "analysed"
    assert pair["matched_timestamps"] == 3


@pytest.mark.parametrize(
    "tolerance",
    [-1.0, float("inf"), float("nan")],
)
def test_run_analysis_rejects_invalid_tolerance(
    tmp_path,
    tolerance,
):
    with pytest.raises(ValueError):
        analyzer.run_analysis(
            input_root=tmp_path,
            inventory=[],
            metadata_records=[],
            tolerance=tolerance,
        )
# --------------------------------------------------
# SOL range summary
# --------------------------------------------------

def test_build_summary_supports_selected_sol_range():
    file_reports = [
        {
            "sol_number": 100,
            "analysis_status": "analysed",
            "notes": "Column mapping: header_exact_match.",
        },
        {
            "sol_number": 101,
            "analysis_status": "analysed",
            "notes": "Column mapping: header_exact_match.",
        },
        {
            "sol_number": 102,
            "analysis_status": "read_error",
            "notes": "",
        },
    ]

    pair_reports = [
        {
            "sol_number": 100,
            "comparison_status": "analysed",
            "matched_timestamps": 3,
        },
        {
            "sol_number": 101,
            "comparison_status": "no_temporal_overlap",
            "matched_timestamps": 0,
        },
        {
            "sol_number": 102,
            "comparison_status": "analysed",
            "matched_timestamps": 2,
        },
    ]

    full_summary = analyzer.build_summary(
        file_reports,
        pair_reports,
        tolerance=1.0,
    )

    range_summary = analyzer.build_summary(
        file_reports,
        pair_reports,
        tolerance=1.0,
        start_sol=100,
        end_sol=101,
    )

    assert full_summary["total_files"] == 3
    assert full_summary["total_product_pairs"] == 3

    assert range_summary["start_sol"] == 100
    assert range_summary["end_sol"] == 101

    assert range_summary["total_files"] == 2
    assert range_summary["analysed_files"] == 2

    assert range_summary["total_product_pairs"] == 2
    assert range_summary["analysed_pairs"] == 1
    assert range_summary["pairs_with_matches"] == 1

    # Original reports must remain unchanged.
    assert len(file_reports) == 3
    assert len(pair_reports) == 3


@pytest.mark.parametrize(
    ("start_sol", "end_sol", "expected_files"),
    [
        (101, None, 2),
        (None, 101, 2),
    ],
)
def test_build_summary_supports_single_sol_bound(
    start_sol,
    end_sol,
    expected_files,
):
    file_reports = [
        {
            "sol_number": 100,
            "analysis_status": "analysed",
            "notes": "",
        },
        {
            "sol_number": 101,
            "analysis_status": "analysed",
            "notes": "",
        },
        {
            "sol_number": 102,
            "analysis_status": "analysed",
            "notes": "",
        },
    ]

    summary = analyzer.build_summary(
        file_reports,
        [],
        tolerance=1.0,
        start_sol=start_sol,
        end_sol=end_sol,
    )

    assert summary["total_files"] == expected_files


@pytest.mark.parametrize(
    ("start_sol", "end_sol"),
    [
        (102, 100),
        (-1, 100),
        (100, -1),
        (True, 100),
        (100, False),
        (100.5, 102),
    ],
)
def test_build_summary_rejects_invalid_sol_range(
    start_sol,
    end_sol,
):
    with pytest.raises((TypeError, ValueError)):
        analyzer.build_summary(
            [],
            [],
            tolerance=1.0,
            start_sol=start_sol,
            end_sol=end_sol,
        )