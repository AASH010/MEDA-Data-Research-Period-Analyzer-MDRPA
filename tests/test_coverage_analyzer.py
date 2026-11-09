from __future__ import annotations

import csv
import json
import math
import random

import pytest

from backend.analyzers import coverage_analyzer as analyzer


# ==================================================
# Test helpers
# ==================================================

def make_fields(*names, data_type="ASCII_Real"):
    return [
        {
            "name": name,
            "data_type": data_type,
            "field_number": str(index + 1),
        }
        for index, name in enumerate(names)
    ]


def make_xml(names=("SCLK", "TEMPERATURE"), has_header=True, **extra):
    record = {
        "parse_status": "success",
        "has_header": has_header,
        "fields": make_fields(*names),
        "metadata_warnings": [],
    }
    record.update(extra)
    return record


def write_text(path, text, encoding="utf-8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding, newline="")
    return path


def write_rows(path, rows, header=("SCLK", "TEMPERATURE")):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if header is not None:
            writer.writerow(header)

        writer.writerows(rows)

    return path


def times_file(tmp_path, times, name="t.csv"):
    return write_rows(
        tmp_path / name,
        [[t, 1.0] for t in times],
    )


def analyze_times(tmp_path, times, **kwargs):
    return analyzer.analyze_csv(
        times_file(tmp_path, times),
        make_xml(),
        **kwargs,
    )


def make_dataset(tmp_path, sols=(100, 101, 103)):
    """A small on-disk dataset: inventory records + metadata."""

    inventory = []
    records = []

    for sol in sols:
        folder = f"SOL{sol}"
        relative = f"{folder}/WE__{sol:04d}___CAL_ATS.csv"
        csv_path = tmp_path / relative

        write_rows(
            csv_path,
            [[1, 10], [2, 11], [3, 12], [10, 13], [11, 14]],
        )

        inventory.append(
            {
                "sol_folder": folder,
                "sol_number": str(sol),
                "filename": csv_path.name,
                "relative_path": relative,
                "extension": ".csv",
                "product_code": "ATS",
                "file_size_bytes": str(csv_path.stat().st_size),
            }
        )

        records.append(
            make_xml(
                source_file=csv_path.with_suffix(".xml").name,
                sol_folder=folder,
                source_relative_path=relative.replace(".csv", ".xml"),
            )
        )

    return inventory, {"records": records}


# ==================================================
# Identification helpers
# ==================================================

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
    assert analyzer.safe_int(float("inf"), default=9) == 9  # OverflowError
    assert analyzer.safe_int("") == 0


def test_safe_float():
    assert analyzer.safe_float("12.5") == 12.5
    assert analyzer.safe_float("nan") is None
    assert analyzer.safe_float("inf") is None
    assert analyzer.safe_float("-inf") is None
    assert analyzer.safe_float("invalid") is None
    assert analyzer.safe_float(None) is None
    assert analyzer.safe_float("1e999") is None
    assert analyzer.safe_float(3) == 3.0


@pytest.mark.parametrize("value", [2.5, 1.0001, 3, 100.0])
def test_validate_gap_factor_accepts_valid_numbers(value):
    assert analyzer.validate_gap_factor(value) == float(value)


@pytest.mark.parametrize(
    "value",
    [1, 1.0, 0, -2, float("nan"), float("inf"), True, "2.5", None, [2]],
)
def test_validate_gap_factor_rejects_invalid(value):
    with pytest.raises(ValueError):
        analyzer.validate_gap_factor(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("", ""),
        ("   ", ""),
        (".", ""),
        ("SOL100/Nested/Sample.CSV", "sol100/nested/sample.csv"),
        (r"SOL100\Nested\Sample.csv", "sol100/nested/sample.csv"),
        ("./SOL100//a/./b.csv", "sol100/a/b.csv"),
        ("SOL100/a/", "sol100/a"),
        (123, "123"),
    ],
)
def test_normalize_relative_path(value, expected):
    assert analyzer._normalize_relative_path(value) == expected


def test_report_columns_are_unique_and_complete():
    columns = analyzer.REPORT_COLUMNS

    assert len(columns) == len(set(columns))

    for required in (
        "sol_number",
        "product_code",
        "row_count",
        "measurement_coverage_status",
        "column_mapping_status",
        "notes",
    ):
        assert required in columns


# ==================================================
# Loading previous stage reports
# ==================================================

def test_load_file_inventory_reads_rows_and_strips_bom(tmp_path):
    path = tmp_path / "inventory.csv"
    path.write_text(
        "sol_folder,filename\nSOL100,a.csv\n",
        encoding="utf-8-sig",
    )

    assert analyzer.load_file_inventory(path) == [
        {"sol_folder": "SOL100", "filename": "a.csv"}
    ]


def test_load_file_inventory_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        analyzer.load_file_inventory(tmp_path / "missing.csv")


def test_load_file_inventory_rejects_directory(tmp_path):
    with pytest.raises(FileNotFoundError):
        analyzer.load_file_inventory(tmp_path)


def test_load_metadata_inventory_valid_with_bom(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text(
        json.dumps({"records": [{"a": 1}]}),
        encoding="utf-8-sig",
    )

    assert analyzer.load_metadata_inventory(path) == {
        "records": [{"a": 1}]
    }


def test_load_metadata_inventory_without_records_key(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text("{}", encoding="utf-8")

    assert analyzer.load_metadata_inventory(path) == {}


def test_load_metadata_inventory_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        analyzer.load_metadata_inventory(tmp_path / "missing.json")


def test_load_metadata_inventory_invalid_json(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="not valid JSON"):
        analyzer.load_metadata_inventory(path)


def test_load_metadata_inventory_rejects_non_object(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text("[1, 2]", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        analyzer.load_metadata_inventory(path)


def test_load_metadata_inventory_rejects_non_list_records(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text('{"records": {}}', encoding="utf-8")

    with pytest.raises(ValueError, match="must be a list"):
        analyzer.load_metadata_inventory(path)


# ==================================================
# Metadata indexing and XML matching
# ==================================================

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


def test_build_metadata_index_dedupes_paths_that_normalize_equal():
    record = {
        "source_relative_path": "SOL100/sample.xml",
        "relative_path": r"sol100\SAMPLE.xml",
    }

    index = analyzer.build_metadata_index({"records": [record]})

    assert index[("path", "sol100/sample.xml")] == [record]


def test_build_metadata_index_indexes_distinct_paths_separately():
    record = {
        "source_relative_path": "SOL100/a.xml",
        "relative_path": "SOL100/b.xml",
    }

    index = analyzer.build_metadata_index({"records": [record]})

    assert index[("path", "sol100/a.xml")] == [record]
    assert index[("path", "sol100/b.xml")] == [record]


def test_build_metadata_index_name_key_is_casefolded():
    record = {"source_file": "Sample.XML", "sol_folder": "Sol100"}

    index = analyzer.build_metadata_index({"records": [record]})

    assert index[("name", "sol100", "sample.xml")] == [record]


def test_build_metadata_index_ignores_incomplete_and_non_dict_records():
    index = analyzer.build_metadata_index(
        {
            "records": [
                "not a dict",
                None,
                {"source_file": "a.xml"},      # no sol
                {"sol_folder": "SOL1"},        # no source file
                {},
            ]
        }
    )

    assert dict(index) == {}


def test_build_metadata_index_handles_missing_records_key():
    assert dict(analyzer.build_metadata_index({})) == {}


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


def test_find_xml_record_is_case_insensitive_on_path():
    expected = {"source_relative_path": "sol100/Sample.XML"}

    metadata_index = analyzer.build_metadata_index({"records": [expected]})

    assert analyzer.find_xml_record(
        {"relative_path": "SOL100/SAMPLE.CSV"},
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


def test_find_xml_record_falls_back_to_name_when_path_has_no_match():
    expected = {"source_file": "sample.xml", "sol_folder": "SOL100"}

    metadata_index = analyzer.build_metadata_index({"records": [expected]})

    csv_record = {
        "sol_folder": "SOL100",
        "filename": "sample.csv",
        "relative_path": "SOL100/elsewhere/sample.csv",
    }

    assert analyzer.find_xml_record(csv_record, metadata_index) is expected


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


@pytest.mark.parametrize(
    "csv_record",
    [
        {},
        {"sol_folder": "SOL100"},
        {"filename": "sample.csv"},
        {"sol_folder": "", "filename": ""},
    ],
)
def test_find_xml_record_requires_sol_and_filename(csv_record):
    assert analyzer.find_xml_record(csv_record, {}) is None


def test_find_xml_record_handles_path_without_suffix():
    expected = {"source_relative_path": "SOL100/sample.xml"}

    metadata_index = analyzer.build_metadata_index({"records": [expected]})

    assert analyzer.find_xml_record(
        {"relative_path": "SOL100/sample"},
        metadata_index,
    ) is expected


def test_find_xml_record_does_not_crash_on_degenerate_path():
    # "/" has an empty name, so with_suffix() raises ValueError.
    expected = {"source_file": "sample.xml", "sol_folder": "SOL100"}

    metadata_index = analyzer.build_metadata_index({"records": [expected]})

    result = analyzer.find_xml_record(
        {
            "relative_path": "/",
            "sol_folder": "SOL100",
            "filename": "sample.csv",
        },
        metadata_index,
    )

    assert result is expected


# ==================================================
# CSV path resolution
# ==================================================

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


def test_resolve_csv_path_accepts_windows_separators(tmp_path):
    csv_path = tmp_path / "SOL100" / "nested" / "sample.csv"
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text("x\n", encoding="utf-8")

    record = {
        "sol_folder": "SOL100",
        "filename": "sample.csv",
        "relative_path": r"SOL100\nested\sample.csv",
    }

    assert analyzer.resolve_csv_path(tmp_path, record) == csv_path


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


def test_resolve_csv_path_finds_nested_file_by_unique_name(tmp_path):
    nested = tmp_path / "SOL100" / "deep" / "er"
    nested.mkdir(parents=True)
    csv_path = nested / "sample.csv"
    csv_path.write_text("x\n", encoding="utf-8")

    record = {"sol_folder": "SOL100", "filename": "sample.csv"}

    assert analyzer.resolve_csv_path(tmp_path, record) == csv_path


def test_resolve_csv_path_filename_fallback_is_case_insensitive(tmp_path):
    nested = tmp_path / "SOL100" / "n"
    nested.mkdir(parents=True)
    csv_path = nested / "Sample.CSV"
    csv_path.write_text("x\n", encoding="utf-8")

    record = {"sol_folder": "SOL100", "filename": "sample.csv"}

    assert analyzer.resolve_csv_path(tmp_path, record) == csv_path


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


def test_resolve_csv_path_missing_sol_dir(tmp_path):
    record = {"sol_folder": "SOL999", "filename": "a.csv"}

    assert analyzer.resolve_csv_path(tmp_path, record) is None


@pytest.mark.parametrize(
    "record",
    [
        {},
        {"sol_folder": "SOL100"},
        {"filename": "a.csv"},
    ],
)
def test_resolve_csv_path_requires_sol_and_filename(tmp_path, record):
    assert analyzer.resolve_csv_path(tmp_path, record) is None


def test_resolve_csv_path_relative_path_pointing_to_directory(tmp_path):
    (tmp_path / "SOL100" / "dir.csv").mkdir(parents=True)

    record = {
        "sol_folder": "SOL100",
        "filename": "dir.csv",
        "relative_path": "SOL100/dir.csv",
    }

    assert analyzer.resolve_csv_path(tmp_path, record) is None


def test_resolve_csv_path_blocks_parent_traversal(tmp_path):
    root = tmp_path / "input"
    (root / "SOL100").mkdir(parents=True)
    outside = tmp_path / "secret.csv"
    outside.write_text("x\n", encoding="utf-8")

    record = {
        "sol_folder": "SOL100",
        "filename": "secret.csv",
        "relative_path": "../secret.csv",
    }

    assert analyzer.resolve_csv_path(root, record) is None


def test_resolve_csv_path_blocks_absolute_path(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    outside = tmp_path / "secret.csv"
    outside.write_text("x\n", encoding="utf-8")

    record = {"relative_path": str(outside)}

    assert analyzer.resolve_csv_path(root, record) is None


def test_resolve_csv_path_blocks_sol_folder_escape(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "a.csv").write_text("x\n", encoding="utf-8")

    record = {"sol_folder": "../outside", "filename": "a.csv"}

    assert analyzer.resolve_csv_path(root, record) is None


def test_resolve_csv_path_blocks_filename_escape(tmp_path):
    root = tmp_path / "input"
    (root / "SOL100").mkdir(parents=True)
    (root / "secret.csv").write_text("x\n", encoding="utf-8")

    record = {"sol_folder": "SOL100", "filename": "../secret.csv"}

    assert analyzer.resolve_csv_path(root, record) is None


def test_resolve_csv_path_shares_cache_between_calls(tmp_path, monkeypatch):
    nested = tmp_path / "SOL100" / "n"
    nested.mkdir(parents=True)
    (nested / "a.csv").write_text("x\n", encoding="utf-8")
    (nested / "b.csv").write_text("x\n", encoding="utf-8")

    calls = []
    original = analyzer._files_by_casefolded_name

    def counting(sol_dir):
        calls.append(sol_dir)
        return original(sol_dir)

    monkeypatch.setattr(analyzer, "_files_by_casefolded_name", counting)

    cache = {}

    first = analyzer.resolve_csv_path(
        tmp_path, {"sol_folder": "SOL100", "filename": "a.csv"}, cache
    )
    second = analyzer.resolve_csv_path(
        tmp_path, {"sol_folder": "SOL100", "filename": "b.csv"}, cache
    )

    assert first == nested / "a.csv"
    assert second == nested / "b.csv"
    assert len(calls) == 1


def test_resolve_csv_path_without_cache_walks_each_time(
    tmp_path, monkeypatch
):
    nested = tmp_path / "SOL100" / "n"
    nested.mkdir(parents=True)
    (nested / "a.csv").write_text("x\n", encoding="utf-8")

    calls = []
    original = analyzer._files_by_casefolded_name

    def counting(sol_dir):
        calls.append(sol_dir)
        return original(sol_dir)

    monkeypatch.setattr(analyzer, "_files_by_casefolded_name", counting)

    record = {"sol_folder": "SOL100", "filename": "a.csv"}

    analyzer.resolve_csv_path(tmp_path, record)
    analyzer.resolve_csv_path(tmp_path, record)

    assert len(calls) == 2


def test_safe_path_helpers_swallow_os_errors(tmp_path):
    class Boom:
        def is_file(self):
            raise PermissionError("no")

        def is_dir(self):
            raise OSError("no")

    assert analyzer._safe_is_file(Boom()) is False
    assert analyzer._safe_is_dir(Boom()) is False
    assert analyzer._safe_is_file(tmp_path) is False
    assert analyzer._safe_is_dir(tmp_path) is True


def test_lexically_within(tmp_path):
    assert analyzer._lexically_within(tmp_path, tmp_path / "a" / "b")
    assert analyzer._lexically_within(tmp_path, tmp_path)
    assert not analyzer._lexically_within(tmp_path, tmp_path / ".." / "x")
    assert not analyzer._lexically_within(tmp_path / "a", tmp_path / "b")


# ==================================================
# CSV column mapping
# ==================================================

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


def test_build_column_mapping_has_header_false_ignores_header_content():
    fields = [{"name": "A"}, {"name": "B"}]

    mapping, status, skip = analyzer.build_column_mapping(
        ["x", "x", "x"], fields, False
    )

    assert (mapping, status, skip) == (
        {0: 0, 1: 1},
        "positional_no_header",
        False,
    )


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


def test_build_column_mapping_rejects_empty_xml_fields():
    assert analyzer.build_column_mapping(["A"], [], True) == (
        None,
        "invalid_xml_field_names",
        False,
    )


def test_build_column_mapping_missing_xml_name_key():
    mapping, status, _ = analyzer.build_column_mapping(
        ["A"], [{}], True
    )

    assert mapping is None
    assert status == "invalid_xml_field_names"


def test_build_column_mapping_header_missing_when_required():
    mapping, status, skip = analyzer.build_column_mapping(
        None, [{"name": "A"}], True
    )

    assert (mapping, status, skip) == (None, "header_missing", False)


def test_build_column_mapping_header_unknown_without_header_row():
    mapping, status, skip = analyzer.build_column_mapping(
        None, [{"name": "A"}, {"name": "B"}], None
    )

    assert mapping == {0: 0, 1: 1}
    assert status == "positional_header_unknown"
    assert skip is False


def test_build_column_mapping_invalid_csv_header_names_strict():
    mapping, status, skip = analyzer.build_column_mapping(
        ["A", ""], [{"name": "A"}, {"name": "B"}], True
    )

    assert (mapping, status, skip) == (
        None,
        "invalid_csv_header_names",
        False,
    )


def test_build_column_mapping_blank_cell_row_is_data_when_header_unknown():
    # A first data row with an empty cell must not reject the file.
    mapping, status, skip = analyzer.build_column_mapping(
        ["3", ""], [{"name": "A"}, {"name": "B"}], None
    )

    assert mapping == {0: 0, 1: 1}
    assert status == "positional_header_unknown"
    assert skip is False


def test_build_column_mapping_duplicate_values_row_is_data_when_unknown():
    mapping, status, skip = analyzer.build_column_mapping(
        ["0", "0"], [{"name": "A"}, {"name": "B"}], None
    )

    assert mapping == {0: 0, 1: 1}
    assert status == "positional_header_unknown"
    assert skip is False


def test_build_column_mapping_column_count_mismatch_strict():
    mapping, status, skip = analyzer.build_column_mapping(
        ["A"], [{"name": "A"}, {"name": "B"}], True
    )

    assert (mapping, status, skip) == (
        None,
        "header_column_count_mismatch",
        True,
    )


def test_build_column_mapping_column_count_mismatch_unknown():
    mapping, status, skip = analyzer.build_column_mapping(
        ["A"], [{"name": "A"}, {"name": "B"}], None
    )

    assert mapping == {0: 0, 1: 1}
    assert status == "positional_header_unknown"
    assert skip is False


def test_build_column_mapping_duplicate_xml_names_positional():
    fields = [{"name": "A"}, {"name": "B"}, {"name": "B"}]

    mapping, status, skip = analyzer.build_column_mapping(
        ["A", "B1", "B2"], fields, True
    )

    assert mapping == {0: 0, 1: 1, 2: 2}
    assert status == "header_positional_duplicate_xml_names"
    assert skip is True


def test_build_column_mapping_duplicate_xml_names_nondup_mismatch_strict():
    fields = [{"name": "A"}, {"name": "B"}, {"name": "B"}]

    mapping, status, skip = analyzer.build_column_mapping(
        ["X", "B1", "B2"], fields, True
    )

    assert (mapping, status, skip) == (
        None,
        "duplicate_xml_field_mapping_ambiguous",
        True,
    )


def test_build_column_mapping_duplicate_xml_names_nondup_mismatch_unknown():
    fields = [{"name": "A"}, {"name": "B"}, {"name": "B"}]

    mapping, status, skip = analyzer.build_column_mapping(
        ["X", "B1", "B2"], fields, None
    )

    assert mapping == {0: 0, 1: 1, 2: 2}
    assert status == "positional_header_unknown"
    assert skip is False


def ws_fields_and_header():
    names = (
        ["SCLK"]
        + [f"F{i}" for i in range(1, 15)]
        + ["BOOM1_ALG_IN_STABLE_STATE", "BOOM2_ALG_IN_STABLE_STATE"]
        + ["F17"]
    )

    header = list(names)
    header[15] = "BOOM1_ALG_STATE_STABLE"
    header[16] = "BOOM2_ALG_STATE_STABLE"

    return names, header


def test_build_column_mapping_ws_aliases():
    names, header = ws_fields_and_header()
    fields = [{"name": name} for name in names]

    mapping, status, skip = analyzer.build_column_mapping(
        header, fields, True
    )

    assert mapping == {index: index for index in range(18)}
    assert status == "header_positional_ws_aliases"
    assert skip is True


def test_build_column_mapping_ws_aliases_wrong_alias_is_rejected():
    names, header = ws_fields_and_header()
    header[16] = "SOMETHING_ELSE"
    fields = [{"name": name} for name in names]

    mapping, status, skip = analyzer.build_column_mapping(
        header, fields, True
    )

    assert (mapping, status, skip) == (
        None,
        "header_mapping_ambiguous",
        True,
    )


def test_build_column_mapping_ws_aliases_only_one_position_differs():
    names, header = ws_fields_and_header()
    header[16] = names[16].replace("_", "-")  # normalizes equal -> no diff
    header[15] = "BOOM1_ALG_STATE_STABLE"
    fields = [{"name": name} for name in names]

    mapping, status, _ = analyzer.build_column_mapping(
        header, fields, True
    )

    # Only index 15 differs, so the alias rule (== [15, 16]) must not fire.
    assert mapping is None
    assert status == "header_mapping_ambiguous"


def test_build_column_mapping_ws_aliases_require_18_columns():
    names, header = ws_fields_and_header()
    names, header = names[:17], header[:17]
    fields = [{"name": name} for name in names]

    mapping, status, _ = analyzer.build_column_mapping(
        header, fields, True
    )

    assert mapping is None
    assert status == "header_mapping_ambiguous"


def test_build_column_mapping_ambiguous_strict_vs_unknown():
    fields = [{"name": "A"}, {"name": "B"}]

    assert analyzer.build_column_mapping(["A", "C"], fields, True) == (
        None,
        "header_mapping_ambiguous",
        True,
    )

    assert analyzer.build_column_mapping(["A", "C"], fields, None) == (
        {0: 0, 1: 1},
        "positional_header_unknown",
        False,
    )


# ==================================================
# CSV analysis: statuses that never read data
# ==================================================

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
    assert result["notes"] == ["No matching XML metadata record."]


def test_analyze_csv_with_empty_xml_record_dict(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("1,2\n", encoding="utf-8")

    result = analyzer.analyze_csv(csv_path, {})

    assert result["measurement_coverage_status"] == "no_xml_metadata"


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
    assert result["notes"] == ["Invalid XML"]


def test_analyze_csv_failed_xml_without_error_message(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("1,2\n", encoding="utf-8")

    result = analyzer.analyze_csv(csv_path, {"parse_status": "failed"})

    assert result["notes"] == ["XML parsing failed."]


@pytest.mark.parametrize("fields", [[], None])
def test_analyze_csv_with_no_xml_fields(tmp_path, fields):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("1,2\n", encoding="utf-8")

    result = analyzer.analyze_csv(
        csv_path,
        {"parse_status": "success", "fields": fields},
    )

    assert result["measurement_coverage_status"] == "no_xml_fields"
    assert result["column_mapping_status"] == "no_xml_fields"


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


def test_analyze_csv_with_only_blank_lines_is_empty(tmp_path):
    csv_path = write_text(tmp_path / "blank.csv", "\n\n  \n,\n")

    result = analyzer.analyze_csv(csv_path, make_xml())

    # "  " and "," are not empty rows for csv.reader but are blank.
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


@pytest.mark.parametrize("gap_factor", ["2.5", None, True])
def test_analyze_csv_rejects_non_numeric_gap_factor(tmp_path, gap_factor):
    with pytest.raises(ValueError):
        analyzer.analyze_csv(
            tmp_path / "x.csv",
            None,
            gap_factor=gap_factor,
        )


# ==================================================
# CSV analysis: header handling end to end
# ==================================================

def test_analyze_csv_handles_utf8_bom(tmp_path):
    csv_path = tmp_path / "bom.csv"
    csv_path.write_text(
        "SCLK,TEMPERATURE\n1,2\n", encoding="utf-8-sig"
    )

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["column_mapping_status"] == "header_exact_match"
    assert result["row_count"] == 1


def test_analyze_csv_skips_leading_blank_lines_before_header(tmp_path):
    csv_path = write_text(
        tmp_path / "lead.csv", "\n\nSCLK,TEMPERATURE\n1,2\n"
    )

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["column_mapping_status"] == "header_exact_match"
    assert result["row_count"] == 1
    assert result["parsed_timestamp_count"] == 1


def test_analyze_csv_header_only_reports_no_data_rows(tmp_path):
    csv_path = write_text(tmp_path / "h.csv", "SCLK,TEMPERATURE\n\n")

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["row_count"] == 0
    assert result["measurement_coverage_status"] == "no_data_rows"
    assert "no data rows" in "; ".join(result["notes"]).lower()


def test_analyze_csv_positional_no_header(tmp_path):
    csv_path = write_text(tmp_path / "n.csv", "1,200\n2,201\n")

    result = analyzer.analyze_csv(csv_path, make_xml(has_header=False))

    assert result["column_mapping_status"] == "positional_no_header"
    assert result["row_count"] == 2
    assert result["parsed_timestamp_count"] == 2
    assert result["first_time"] == "1"


def test_analyze_csv_unknown_header_keeps_first_data_row(tmp_path):
    csv_path = write_text(tmp_path / "u.csv", "1,200\n2,201\n")

    result = analyzer.analyze_csv(csv_path, make_xml(has_header=None))

    assert result["column_mapping_status"] == "positional_header_unknown"
    assert result["row_count"] == 2
    assert any(
        "does not establish header presence" in note
        for note in result["notes"]
    )


def test_analyze_csv_unknown_header_with_real_header_is_skipped(tmp_path):
    csv_path = write_text(
        tmp_path / "u.csv", "SCLK,TEMPERATURE\n1,200\n"
    )

    result = analyzer.analyze_csv(csv_path, make_xml(has_header=None))

    assert result["column_mapping_status"] == "header_exact_match"
    assert result["row_count"] == 1


def test_analyze_csv_unknown_header_row_with_empty_cell_is_not_rejected(
    tmp_path,
):
    csv_path = write_text(tmp_path / "u.csv", "3,\n4,5\n")

    result = analyzer.analyze_csv(csv_path, make_xml(has_header=None))

    assert result["column_mapping_status"] == "positional_header_unknown"
    assert result["measurement_coverage_status"] == (
        "timestamp_analysis_available"
    )
    assert result["row_count"] == 2
    assert result["numeric_missing_count"] == 1
    assert result["numeric_value_count"] == 1


def test_analyze_csv_reordered_header(tmp_path):
    csv_path = write_text(
        tmp_path / "r.csv", "TEMPERATURE,SCLK\n10,1\n11,2\n"
    )

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["column_mapping_status"] == "header_reordered_mapped"
    assert result["parsed_timestamp_count"] == 2
    assert result["numeric_value_count"] == 2
    assert any("columns mapped by name" in n for n in result["notes"])


def test_analyze_csv_ambiguous_mapping_is_not_measured(tmp_path):
    csv_path = write_text(
        tmp_path / "a.csv", "SCLK,SOMETHING\n1,2\n2,3\n"
    )

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["measurement_coverage_status"] == (
        "column_mapping_ambiguous"
    )
    assert result["column_mapping_status"] == "header_mapping_ambiguous"
    assert result["row_count"] == 0
    assert result["parsed_timestamp_count"] == 0
    assert any("could not be mapped safely" in n for n in result["notes"])


def test_analyze_csv_duplicate_xml_field_names_note(tmp_path):
    csv_path = write_text(
        tmp_path / "d.csv", "SCLK,B1,B2\n1,2,3\n2,3,4\n"
    )

    result = analyzer.analyze_csv(
        csv_path, make_xml(names=("SCLK", "B", "B"))
    )

    assert result["column_mapping_status"] == (
        "header_positional_duplicate_xml_names"
    )
    assert result["row_count"] == 2
    assert result["numeric_value_count"] == 4
    assert any("duplicate field names" in n for n in result["notes"])


def test_analyze_csv_ws_alias_note(tmp_path):
    names, header = ws_fields_and_header()
    row = ["1"] + ["0"] * 17

    csv_path = write_rows(
        tmp_path / "ws.csv", [row, row], header=header
    )

    result = analyzer.analyze_csv(csv_path, make_xml(names=names))

    assert result["column_mapping_status"] == "header_positional_ws_aliases"
    assert result["row_count"] == 2
    assert any("validated field-name aliases" in n for n in result["notes"])


def test_analyze_csv_metadata_warnings_are_deduplicated(tmp_path):
    csv_path = times_file(tmp_path, [1, 2])

    xml = make_xml(
        metadata_warnings=[
            {"code": "dup", "message": "Duplicate field"},
            {"code": "dup", "message": "Duplicate field"},
            {"code": "dup", "message": "Another message"},
            {"message": "no code"},
            {"code": "only_code"},
            "not a dict",
            None,
        ]
    )

    notes = analyzer.analyze_csv(csv_path, xml)["notes"]
    warnings = [n for n in notes if n.startswith("XML metadata warning")]

    assert warnings == [
        "XML metadata warning [dup]: Duplicate field",
        "XML metadata warning [dup]: Another message",
        "XML metadata warning [unknown]: no code",
        "XML metadata warning [only_code]: only_code",
    ]


def test_analyze_csv_ignores_non_list_metadata_warnings(tmp_path):
    csv_path = times_file(tmp_path, [1, 2])

    notes = analyzer.analyze_csv(
        csv_path, make_xml(metadata_warnings="oops")
    )["notes"]

    assert not any(n.startswith("XML metadata warning") for n in notes)


# ==================================================
# CSV analysis: timestamps
# ==================================================

def test_analyze_csv_gap_detection(tmp_path):
    result = analyze_times(tmp_path, [1, 2, 3, 10, 11])

    assert result["median_step_seconds"] == 1
    assert result["gap_count"] == 1
    assert result["largest_gap_seconds"] == 7
    assert result["gap_total_seconds"] == 7
    assert result["span_seconds"] == 10
    assert result["first_time"] == "1"
    assert result["last_time"] == "11"
    assert result["out_of_order_count"] == 0
    assert result["duplicate_timestamp_count"] == 0


def test_analyze_csv_gap_factor_changes_threshold(tmp_path):
    loose = analyze_times(tmp_path, [1, 2, 3, 10, 11], gap_factor=10)
    tight = analyze_times(tmp_path, [1, 2, 3, 10, 11], gap_factor=1.5)

    assert loose["gap_count"] == 0
    assert loose["largest_gap_seconds"] == 0
    assert loose["gap_total_seconds"] == 0
    assert tight["gap_count"] == 1


def test_analyze_csv_step_equal_to_threshold_is_not_a_gap(tmp_path):
    # steps 2,2,5 -> median 2, threshold 5.0, and 5 is not > 5.
    result = analyze_times(tmp_path, [0, 2, 4, 9], gap_factor=2.5)

    assert result["gap_count"] == 0


def test_analyze_csv_single_timestamp(tmp_path):
    result = analyze_times(tmp_path, [5])

    assert result["parsed_timestamp_count"] == 1
    assert result["span_seconds"] == 0
    assert result["median_step_seconds"] == ""
    assert result["gap_count"] == 0
    assert result["largest_gap_seconds"] == ""
    assert result["gap_total_seconds"] == ""
    assert result["first_time"] == "5"
    assert result["last_time"] == "5"


def test_analyze_csv_out_of_order_and_duplicates(tmp_path):
    result = analyze_times(tmp_path, [1, 3, 2, 2])

    assert result["parsed_timestamp_count"] == 4
    assert result["out_of_order_count"] == 1
    assert result["duplicate_timestamp_count"] == 1
    assert result["median_step_seconds"] == 2
    assert result["first_time"] == "1"
    assert result["last_time"] == "3"
    assert any("Out-of-order" in n for n in result["notes"])


def test_analyze_csv_sorted_duplicates(tmp_path):
    result = analyze_times(tmp_path, [1, 1, 2, 2, 2])

    assert result["out_of_order_count"] == 0
    assert result["duplicate_timestamp_count"] == 3
    assert not any("Out-of-order" in n for n in result["notes"])


def test_analyze_csv_first_and_last_use_min_and_max_not_row_order(tmp_path):
    result = analyze_times(tmp_path, [5, 1, 9, 3])

    assert result["first_time"] == "1"
    assert result["last_time"] == "9"
    assert result["span_seconds"] == 8


def test_analyze_csv_ties_keep_first_raw_text(tmp_path):
    result = analyze_times(tmp_path, ["1.0", "1", "2", "2.0"])

    assert result["first_time"] == "1.0"
    assert result["last_time"] == "2"


@pytest.mark.parametrize("seed", range(30))
def test_duplicate_count_matches_bruteforce(tmp_path, seed):
    """The array/zero-step optimisation must equal 'parsed - distinct'."""

    rng = random.Random(seed)
    size = rng.randint(1, 40)
    values = [rng.randint(0, 12) for _ in range(size)]

    if seed % 2:
        values.sort()

    result = analyze_times(tmp_path, values)

    assert result["parsed_timestamp_count"] == size
    assert result["duplicate_timestamp_count"] == size - len(set(values))
    assert result["out_of_order_count"] == sum(
        1 for a, b in zip(values, values[1:]) if b < a
    )


def test_analyze_csv_counts_missing_invalid_and_short_rows(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(analyzer, "MISSING_TEXT", frozenset({"", "na"}))

    csv_path = write_text(
        tmp_path / "mix.csv",
        "SCLK,TEMPERATURE\n"
        "1,10.5\n"
        "2,na\n"
        "3,abc\n"
        "4,inf\n"
        "na,5\n"
        "abc,6\n"
        "7\n"
        "\n"
        ",\n",
    )

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["row_count"] == 7
    assert result["parsed_timestamp_count"] == 5
    assert result["missing_timestamp_count"] == 1
    assert result["invalid_timestamp_count"] == 1
    assert result["numeric_value_count"] == 3
    assert result["numeric_missing_count"] == 2
    assert result["numeric_invalid_count"] == 2
    assert result["gap_count"] == 1
    assert result["largest_gap_seconds"] == 3
    assert result["span_seconds"] == 6


def test_analyze_csv_time_value_missing_when_row_is_too_short(tmp_path):
    csv_path = write_text(
        tmp_path / "short.csv", "TEMPERATURE,SCLK\n5,1\n6\n"
    )

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["row_count"] == 2
    assert result["parsed_timestamp_count"] == 1
    assert result["missing_timestamp_count"] == 1


def test_analyze_csv_all_timestamps_invalid(tmp_path):
    csv_path = write_text(
        tmp_path / "bad.csv", "SCLK,TEMPERATURE\nx,1\ny,2\n"
    )

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["measurement_coverage_status"] == (
        "timestamps_not_interpreted"
    )
    assert result["invalid_timestamp_count"] == 2
    assert result["first_time"] == ""
    assert result["span_seconds"] == ""
    assert result["numeric_value_count"] == 2


def test_analyze_csv_parser_results_are_validated(tmp_path, monkeypatch):
    def fake_parser(raw):
        if raw == "nil":
            return None
        if raw == "inf":
            return float("inf")
        if raw == "obj":
            return object()          # float(object()) -> TypeError
        if raw == "big":
            raise OverflowError
        if raw == "bad":
            raise TypeError
        return float(raw)

    monkeypatch.setattr(
        analyzer, "PARSERS", {"sclk": (fake_parser, "SCLK test axis")}
    )

    csv_path = write_text(
        tmp_path / "p.csv",
        "SCLK,TEMPERATURE\n1,1\nnil,1\ninf,1\nobj,1\nbig,1\nbad,1\n2,1\n",
    )

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["parsed_timestamp_count"] == 2
    assert result["invalid_timestamp_count"] == 5
    assert result["row_count"] == 7


def test_analyze_csv_without_time_field(tmp_path, monkeypatch):
    monkeypatch.setattr(
        analyzer, "pick_time_column", lambda fields, pref: (None, None, None)
    )

    # Pin numeric columns: the real numeric_column_indexes() excludes
    # time-named columns, which would otherwise hide SCLK here.
    monkeypatch.setattr(
        analyzer, "numeric_column_indexes", lambda fields, skip: [0, 1]
    )

    csv_path = write_text(
        tmp_path / "nt.csv", "SCLK,TEMPERATURE\n1,2\n3,4\n"
    )

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["measurement_coverage_status"] == (
        "time_field_not_detected"
    )
    assert result["time_field"] == ""
    assert result["time_kind"] == ""
    assert result["parsed_timestamp_count"] == 0
    assert result["missing_timestamp_count"] == 0
    # With no time column every numeric column is measured.
    assert result["numeric_value_count"] == 4
    assert any("No supported time field" in n for n in result["notes"])


def test_analyze_csv_utc_axis_has_no_conversion_note(tmp_path, monkeypatch):
    monkeypatch.setattr(
        analyzer,
        "pick_time_column",
        lambda fields, pref: (0, "TIME_UTC", "utc"),
    )
    monkeypatch.setattr(analyzer, "PARSERS", {"utc": (float, "UTC")})

    csv_path = write_text(
        tmp_path / "u.csv", "SCLK,TEMPERATURE\n1,2\n3,4\n"
    )

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["time_kind"] == "utc"
    assert not any("No UTC conversion" in n for n in result["notes"])


def test_analyze_csv_non_utc_axis_has_conversion_note(tmp_path):
    result = analyze_times(tmp_path, [1, 2])

    assert any(
        "No UTC conversion was performed" in n for n in result["notes"]
    )
    assert result["notes"][-1].startswith("Gap totals are sums")


def test_analyze_csv_unmapped_numeric_column_counts_as_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        analyzer,
        "build_column_mapping",
        lambda header, fields, has_header: (
            {0: 0},
            "positional_no_header",
            False,
        ),
    )

    csv_path = write_text(tmp_path / "m.csv", "1\n2\n")

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["numeric_missing_count"] == 2   # one per row
    assert result["numeric_value_count"] == 0
    assert result["parsed_timestamp_count"] == 2


def test_analyze_csv_unmapped_time_column_counts_as_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        analyzer,
        "build_column_mapping",
        lambda header, fields, has_header: (
            {1: 1},
            "positional_no_header",
            False,
        ),
    )

    csv_path = write_text(tmp_path / "m.csv", "1,5\n2,6\n")

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["missing_timestamp_count"] == 2
    assert result["parsed_timestamp_count"] == 0
    assert result["numeric_value_count"] == 2
    assert result["measurement_coverage_status"] == (
        "timestamps_not_interpreted"
    )


# ==================================================
# CSV analysis: read failures
# ==================================================

def test_analyze_csv_missing_file_is_read_failed(tmp_path):
    result = analyzer.analyze_csv(tmp_path / "ghost.csv", make_xml())

    assert result["measurement_coverage_status"] == "read_failed"
    assert result["row_count"] == 0
    assert result["notes"]


def test_analyze_csv_invalid_encoding_is_read_failed(tmp_path):
    csv_path = tmp_path / "bin.csv"
    csv_path.write_bytes(b"SCLK,TEMPERATURE\n1,\xff\xfe\n")

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["measurement_coverage_status"] == "read_failed"


def test_analyze_csv_csv_error_is_read_failed(tmp_path, monkeypatch):
    csv_path = write_text(tmp_path / "x.csv", "SCLK,TEMPERATURE\n1,2\n")

    def boom(*args, **kwargs):
        raise csv.Error("boom")

    monkeypatch.setattr(analyzer.csv, "reader", boom)

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["measurement_coverage_status"] == "read_failed"
    assert result["notes"] == ["boom"]


# ==================================================
# analyze_csv_safely / pool entry point
# ==================================================

def test_analyze_csv_safely_returns_normal_results(tmp_path):
    csv_path = times_file(tmp_path, [1, 2, 3])

    result = analyzer.analyze_csv_safely(csv_path, make_xml())

    assert result["measurement_coverage_status"] == (
        "timestamp_analysis_available"
    )


def test_analyze_csv_safely_converts_unexpected_errors(
    tmp_path, monkeypatch
):
    def boom(fields, pref):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(analyzer, "pick_time_column", boom)

    result = analyzer.analyze_csv_safely(
        times_file(tmp_path, [1, 2]), make_xml()
    )

    assert result["measurement_coverage_status"] == "analysis_failed"
    assert result["column_mapping_status"] == "analysis_failed"
    assert "RuntimeError: unexpected" in result["notes"][0]


def test_analyze_csv_safely_still_raises_for_invalid_gap_factor(tmp_path):
    with pytest.raises(ValueError):
        analyzer.analyze_csv_safely(tmp_path / "x.csv", None, gap_factor=1)


def test_analyze_task_matches_direct_call(tmp_path):
    csv_path = times_file(tmp_path, [1, 2, 3, 10])

    assert analyzer._analyze_task((csv_path, make_xml(), 2.5)) == (
        analyzer.analyze_csv(csv_path, make_xml(), gap_factor=2.5)
    )


def test_apply_analysis_joins_notes_and_copies_values():
    report = {"notes": "", "row_count": 0}

    analyzer._apply_analysis(
        report,
        {"row_count": 4, "notes": ["a", "b"], "gap_count": 1},
    )

    assert report == {"row_count": 4, "notes": "a; b", "gap_count": 1}


# ==================================================
# Integrated inventory analysis
# ==================================================

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
    assert "could not be resolved" in reports[0]["notes"]


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
    assert reports[0]["notes"] == "CSV file has zero bytes."


def test_analyze_coverage_full_row_shape(tmp_path):
    inventory, metadata = make_dataset(tmp_path, sols=(100,))

    (report,) = analyzer.analyze_coverage(tmp_path, inventory, metadata)

    assert report["sol_number"] == 100
    assert report["sol_folder"] == "SOL100"
    assert report["product_code"] == "ATS"
    assert report["row_count"] == 5
    assert report["gap_count"] == 1
    assert report["column_mapping_status"] == "header_exact_match"
    assert isinstance(report["notes"], str)
    assert set(report) <= set(analyzer.REPORT_COLUMNS)


def test_analyze_coverage_reports_no_xml_metadata(tmp_path):
    inventory, _ = make_dataset(tmp_path, sols=(100,))

    (report,) = analyzer.analyze_coverage(
        tmp_path, inventory, {"records": []}
    )

    assert report["measurement_coverage_status"] == "no_xml_metadata"
    assert report["row_count"] == 0


def test_analyze_coverage_sol_zero_is_not_dropped(tmp_path):
    csv_path = write_rows(tmp_path / "SOL0" / "a_CAL_ATS.csv", [[1, 2]])

    inventory = [
        {
            "sol_folder": "SOL0",
            "filename": "a_CAL_ATS.csv",
            "extension": ".csv",
        }
    ]

    (report,) = analyzer.analyze_coverage(
        tmp_path, inventory, {"records": []}
    )

    assert csv_path.exists()
    assert report["sol_number"] == 0          # was None before the fix
    assert report["product_code"] == "ATS"


@pytest.mark.parametrize(
    ("record_sol", "folder", "expected"),
    [
        ("100", "SOL100", 100),     # from the record
        (None, "SOL101", 101),      # from the folder name
        ("", "SOL102", 102),
        ("abc", "SOL103", 103),
        ("200", "SOL100", 200),     # record wins over folder
        (None, "unknown", None),    # nothing usable
        ("-5", "unknown", None),    # negative is rejected
    ],
)
def test_analyze_coverage_sol_number_resolution(
    tmp_path, record_sol, folder, expected
):
    record = {"sol_folder": folder, "filename": "a.csv", "extension": ".csv"}

    if record_sol is not None:
        record["sol_number"] = record_sol

    (report,) = analyzer.analyze_coverage(tmp_path, [record], {})

    assert report["sol_number"] == expected


def test_analyze_coverage_product_code_prefers_inventory(tmp_path):
    record = {
        "sol_folder": "SOL1",
        "filename": "x_CAL_PS.csv",
        "extension": ".csv",
        "product_code": "WS",
    }

    (report,) = analyzer.analyze_coverage(tmp_path, [record], {})

    assert report["product_code"] == "WS"


def test_analyze_coverage_product_code_empty_when_unknown(tmp_path):
    record = {"sol_folder": "SOL1", "filename": "x.csv", "extension": ".csv"}

    (report,) = analyzer.analyze_coverage(tmp_path, [record], {})

    assert report["product_code"] == ""


@pytest.mark.parametrize(
    ("extension", "filename", "analysed"),
    [
        (".csv", "a.csv", True),
        (".CSV", "a.csv", True),
        ("csv", "a.csv", True),
        ("", "a.csv", True),
        (None, "a.csv", True),
        ("", "a.xml", False),
        (".xml", "a.csv", False),
        ("", "a", False),
    ],
)
def test_analyze_coverage_extension_detection(
    tmp_path, extension, filename, analysed
):
    record = {"sol_folder": "SOL1", "filename": filename}

    if extension is not None:
        record["extension"] = extension

    reports = analyzer.analyze_coverage(tmp_path, [record], {})

    assert (len(reports) == 1) is analysed


def test_analyze_coverage_backfills_missing_file_size(tmp_path):
    inventory, metadata = make_dataset(tmp_path, sols=(100,))
    inventory[0].pop("file_size_bytes")
    path = tmp_path / inventory[0]["relative_path"]

    (report,) = analyzer.analyze_coverage(tmp_path, inventory, metadata)

    assert report["file_size_bytes"] == path.stat().st_size


def test_analyze_coverage_keeps_inventory_file_size(tmp_path):
    inventory, metadata = make_dataset(tmp_path, sols=(100,))
    inventory[0]["file_size_bytes"] = "12345"

    (report,) = analyzer.analyze_coverage(tmp_path, inventory, metadata)

    assert report["file_size_bytes"] == "12345"


def test_analyze_coverage_stat_failure_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(
        analyzer,
        "resolve_csv_path",
        lambda *args, **kwargs: tmp_path / "ghost.csv",
    )

    record = {"sol_folder": "SOL1", "filename": "a.csv", "extension": ".csv"}

    (report,) = analyzer.analyze_coverage(tmp_path, [record], {})

    assert report["measurement_coverage_status"] == "read_failed"
    assert report["notes"]


def test_analyze_coverage_unexpected_error_does_not_abort_run(
    tmp_path, monkeypatch
):
    inventory, metadata = make_dataset(tmp_path, sols=(100, 101))

    original = analyzer.analyze_csv
    calls = {"n": 0}

    def flaky(csv_path, xml_record, *args, **kwargs):
        calls["n"] += 1

        if calls["n"] == 1:
            raise RuntimeError("first file explodes")

        return original(csv_path, xml_record, *args, **kwargs)

    monkeypatch.setattr(analyzer, "analyze_csv", flaky)

    reports = analyzer.analyze_coverage(tmp_path, inventory, metadata)

    assert reports[0]["measurement_coverage_status"] == "analysis_failed"
    assert reports[1]["measurement_coverage_status"] == (
        "timestamp_analysis_available"
    )


def test_analyze_coverage_preserves_inventory_order(tmp_path):
    inventory, metadata = make_dataset(tmp_path, sols=(103, 100, 101))

    reports = analyzer.analyze_coverage(tmp_path, inventory, metadata)

    assert [r["sol_number"] for r in reports] == [103, 100, 101]


def test_analyze_coverage_walks_each_sol_dir_once(tmp_path, monkeypatch):
    nested = tmp_path / "SOL100" / "n"
    for name in ("a.csv", "b.csv", "c.csv"):
        write_rows(nested / name, [[1, 2]])

    calls = []
    original = analyzer._files_by_casefolded_name

    def counting(sol_dir):
        calls.append(sol_dir)
        return original(sol_dir)

    monkeypatch.setattr(analyzer, "_files_by_casefolded_name", counting)

    inventory = [
        {"sol_folder": "SOL100", "filename": n, "extension": ".csv"}
        for n in ("a.csv", "b.csv", "c.csv")
    ]

    reports = analyzer.analyze_coverage(tmp_path, inventory, {"records": []})

    assert len(reports) == 3
    assert len(calls) == 1


@pytest.mark.parametrize("workers", [0, -1, True, "2", 1.5, None])
def test_analyze_coverage_rejects_invalid_workers(tmp_path, workers):
    with pytest.raises(ValueError, match="workers"):
        analyzer.analyze_coverage(tmp_path, [], {}, workers=workers)


@pytest.mark.parametrize("gap_factor", [1, 0, float("nan"), "2.5", None])
def test_analyze_coverage_rejects_invalid_gap_factor_even_if_empty(
    tmp_path, gap_factor
):
    with pytest.raises(ValueError):
        analyzer.analyze_coverage(
            tmp_path, [], {}, gap_factor=gap_factor
        )


def test_analyze_coverage_parallel_equals_sequential(tmp_path):
    inventory, metadata = make_dataset(tmp_path, sols=(100, 101, 102, 103))

    # Add a missing file, an empty file and a file with no XML record.
    inventory.append(
        {"sol_folder": "SOL104", "filename": "gone.csv", "extension": ".csv"}
    )

    empty = tmp_path / "SOL105" / "empty.csv"
    empty.parent.mkdir(parents=True)
    empty.touch()
    inventory.append(
        {
            "sol_folder": "SOL105",
            "filename": "empty.csv",
            "relative_path": "SOL105/empty.csv",
            "extension": ".csv",
        }
    )

    write_rows(tmp_path / "SOL106" / "x_CAL_PS.csv", [[1, 2], [2, 3]])
    inventory.append(
        {
            "sol_folder": "SOL106",
            "filename": "x_CAL_PS.csv",
            "relative_path": "SOL106/x_CAL_PS.csv",
            "extension": ".csv",
        }
    )

    sequential = analyzer.analyze_coverage(
        tmp_path, inventory, metadata, workers=1
    )
    parallel = analyzer.analyze_coverage(
        tmp_path, inventory, metadata, workers=2
    )

    assert parallel == sequential
    assert len(sequential) == 7


# ==================================================
# Sol range and product summaries
# ==================================================

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


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([5], (5, 5, 1)),
        ([1, 2, 5, 6, 7], (5, 7, 3)),        # longest run is the last one
        ([7, 6, 5, 1, 2], (5, 7, 3)),        # unsorted input
        ([1, 1, 2, 2], (1, 2, 2)),           # duplicates
        ([1, 2, 3, 4], (1, 4, 4)),           # everything consecutive
        ([1, 2, 5, 6], (1, 2, 2)),           # tie -> first run wins
        ([1, 3, 5], (1, 1, 1)),              # nothing consecutive
    ],
)
def test_longest_consecutive_range_cases(values, expected):
    result = analyzer.longest_consecutive_range(values)

    assert (
        result["start_sol"],
        result["end_sol"],
        result["length_sols"],
    ) == expected


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
    assert summary["ATS"]["longest_consecutive_sol_range"] == {
        "start_sol": 100,
        "end_sol": 101,
        "length_sols": 2,
    }


def test_build_product_summary_empty_reports():
    assert analyzer.build_product_summary([], 1, 10) == {}


def test_build_product_summary_products_are_sorted():
    reports = [
        {"product_code": "WS", "sol_number": 1, "row_count": 1},
        {"product_code": "ATS", "sol_number": 1, "row_count": 1},
        {"product_code": "PS", "sol_number": 1, "row_count": 1},
    ]

    assert list(analyzer.build_product_summary(reports, 1, 1)) == [
        "ATS",
        "PS",
        "WS",
    ]


def test_build_product_summary_two_files_same_sol():
    reports = [
        {"product_code": "ATS", "sol_number": 5, "row_count": 3},
        {"product_code": "ATS", "sol_number": 5, "row_count": 4},
    ]

    summary = analyzer.build_product_summary(reports, 5, 5)["ATS"]

    assert summary["csv_file_count"] == 2
    assert summary["sols_with_rows"] == 1
    assert summary["total_rows"] == 7
    assert summary["missing_sols"] == []


@pytest.mark.parametrize(
    "report",
    [
        {"product_code": "", "sol_number": 1, "row_count": 1},
        {"product_code": None, "sol_number": 1, "row_count": 1},
        {"sol_number": 1, "row_count": 1},
        {"product_code": "ATS", "sol_number": 1, "row_count": 0},
        {"product_code": "ATS", "sol_number": 1, "row_count": -3},
        {"product_code": "ATS", "sol_number": 1, "row_count": "x"},
        {"product_code": "ATS", "sol_number": 1},
        {"product_code": "ATS", "row_count": 1},
    ],
)
def test_build_product_summary_skips_unusable_reports(report):
    assert analyzer.build_product_summary([report], 1, 10) == {}


def test_build_product_summary_accepts_string_row_counts():
    reports = [
        {"product_code": "ATS", "sol_number": 1, "row_count": "5"},
    ]

    summary = analyzer.build_product_summary(reports, 1, 1)

    assert summary["ATS"]["total_rows"] == 5


def test_build_product_summary_full_observed_range():
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
            "measurement_coverage_status": (
                "timestamp_analysis_available"
            ),
        },
    ]

    summary = analyzer.build_product_summary(
        reports,
        100,
        103,
    )

    assert summary["ATS"]["present_sols"] == [100, 101, 103]
    assert summary["ATS"]["missing_sols"] == [102]
    assert summary["ATS"]["csv_file_count"] == 3
    assert summary["ATS"]["total_rows"] == 22


def test_build_product_summary_partial_range_excludes_outside_sols():
    reports = [
        {
            "product_code": "ATS",
            "sol_number": 99,
            "row_count": 100,
            "numeric_value_count": 200,
            "parsed_timestamp_count": 100,
            "measurement_coverage_status": (
                "timestamp_analysis_available"
            ),
        },
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
            "measurement_coverage_status": (
                "timestamp_analysis_available"
            ),
        },
        {
            "product_code": "ATS",
            "sol_number": 104,
            "row_count": 200,
            "numeric_value_count": 400,
            "parsed_timestamp_count": 200,
            "measurement_coverage_status": (
                "timestamp_analysis_available"
            ),
        },
    ]

    summary = analyzer.build_product_summary(
        reports,
        100,
        103,
    )

    assert summary["ATS"]["present_sols"] == [100, 101, 103]
    assert summary["ATS"]["missing_sols"] == [102]

    assert summary["ATS"]["csv_file_count"] == 3
    assert summary["ATS"]["total_rows"] == 22
    assert summary["ATS"]["total_numeric_values"] == 44
    assert summary["ATS"]["total_parsed_timestamps"] == 22


def test_build_product_summary_range_boundaries_are_inclusive():
    reports = [
        {
            "product_code": "ATS",
            "sol_number": 99,
            "row_count": 10,
        },
        {
            "product_code": "ATS",
            "sol_number": 100,
            "row_count": 10,
        },
        {
            "product_code": "ATS",
            "sol_number": 102,
            "row_count": 10,
        },
        {
            "product_code": "ATS",
            "sol_number": 103,
            "row_count": 10,
        },
    ]

    summary = analyzer.build_product_summary(
        reports,
        100,
        102,
    )

    assert summary["ATS"]["present_sols"] == [100, 102]
    assert summary["ATS"]["csv_file_count"] == 2
    assert summary["ATS"]["total_rows"] == 20
    assert summary["ATS"]["missing_sols"] == [101]


def test_build_product_summary_returns_empty_for_unmatched_range():
    reports = [
        {
            "product_code": "ATS",
            "sol_number": 100,
            "row_count": 10,
        },
        {
            "product_code": "PS",
            "sol_number": 101,
            "row_count": 5,
        },
    ]

    summary = analyzer.build_product_summary(
        reports,
        200,
        210,
    )

    assert summary == {}


def test_build_product_summary_ignores_invalid_sol_values():
    reports = [
        {
            "product_code": "ATS",
            "sol_number": 100,
            "row_count": 10,
        },
        {
            "product_code": "ATS",
            "sol_number": True,
            "row_count": 20,
        },
        {
            "product_code": "ATS",
            "sol_number": None,
            "row_count": 30,
        },
        {
            "product_code": "ATS",
            "sol_number": "101",
            "row_count": 40,
        },
    ]

    summary = analyzer.build_product_summary(
        reports,
        100,
        101,
    )

    assert summary["ATS"]["present_sols"] == [100]
    assert summary["ATS"]["csv_file_count"] == 1
    assert summary["ATS"]["total_rows"] == 10


# ==================================================
# Output writers
# ==================================================

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


def test_save_coverage_csv_header_and_extra_keys(tmp_path):
    output_file = tmp_path / "c.csv"

    analyzer.save_coverage_csv(
        [{"sol_number": 1, "not_a_column": "ignored"}], output_file
    )

    with output_file.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    assert reader.fieldnames == analyzer.REPORT_COLUMNS
    assert "not_a_column" not in rows[0]
    assert rows[0]["filename"] == ""          # missing keys become ""


def test_save_coverage_csv_empty_reports_writes_header_only(tmp_path):
    output_file = tmp_path / "c.csv"

    analyzer.save_coverage_csv([], output_file)

    lines = output_file.read_text(encoding="utf-8-sig").splitlines()

    assert lines == [",".join(analyzer.REPORT_COLUMNS)]


def test_save_coverage_csv_has_bom_and_keeps_newlines_in_notes(tmp_path):
    output_file = tmp_path / "c.csv"

    analyzer.save_coverage_csv(
        [{"notes": "line1\nline2, with comma"}], output_file
    )

    assert output_file.read_bytes().startswith(b"\xef\xbb\xbf")

    with output_file.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    assert rows[0]["notes"] == "line1\nline2, with comma"


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


def test_save_summary_json_keeps_unicode(tmp_path):
    output_file = tmp_path / "s.json"

    analyzer.save_summary_json({"note": "مرحبا ✓"}, output_file)

    assert "مرحبا ✓" in output_file.read_text(encoding="utf-8")


def test_writers_leave_no_temp_files(tmp_path):
    analyzer.save_coverage_csv([{"sol_number": 1}], tmp_path / "c.csv")
    analyzer.save_summary_json({"a": 1}, tmp_path / "s.json")

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "c.csv",
        "s.json",
    ]


def test_writers_overwrite_existing_files(tmp_path):
    target = tmp_path / "s.json"

    analyzer.save_summary_json({"v": 1}, target)
    analyzer.save_summary_json({"v": 2}, target)

    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 2}


def test_failed_write_keeps_previous_report_and_cleans_up(tmp_path):
    target = tmp_path / "s.json"
    analyzer.save_summary_json({"v": "good"}, target)

    with pytest.raises(TypeError):
        analyzer.save_summary_json({"v": object()}, target)

    assert json.loads(target.read_text(encoding="utf-8")) == {"v": "good"}
    assert [p.name for p in tmp_path.iterdir()] == ["s.json"]


# ==================================================
# Command line entry point
# ==================================================

def write_inventory(path, inventory):
    columns = sorted({key for row in inventory for key in row})

    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(inventory)


def cli_args(tmp_path, *extra):
    return [
        "--input", str(tmp_path / "input"),
        "--inventory", str(tmp_path / "inventory.csv"),
        "--metadata", str(tmp_path / "metadata.json"),
        "--output", str(tmp_path / "out" / "report.csv"),
        "--summary", str(tmp_path / "out" / "summary.json"),
        "--start-sol", "100",
        "--end-sol", "103",
        *extra,
    ]


@pytest.fixture
def cli_dataset(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    inventory, metadata = make_dataset(input_dir)

    write_inventory(tmp_path / "inventory.csv", inventory)
    (tmp_path / "metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    return tmp_path


def test_build_arg_parser_defaults():
    args = analyzer.build_arg_parser().parse_args([])

    assert args.start_sol == 107
    assert args.end_sol == 250
    assert args.gap_factor == 2.5
    assert args.workers == 1
    assert str(args.inventory).endswith("file_inventory.csv")


def test_main_end_to_end(cli_dataset, capsys):
    code = analyzer.main(cli_args(cli_dataset))

    assert code == 0

    out = capsys.readouterr().out
    assert "Coverage analysis completed." in out
    assert "CSV files analyzed: 3" in out
    assert "Products found: 1" in out

    with (cli_dataset / "out" / "report.csv").open(
        newline="", encoding="utf-8-sig"
    ) as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 3
    assert {row["product_code"] for row in rows} == {"ATS"}

    summary = json.loads(
        (cli_dataset / "out" / "summary.json").read_text(encoding="utf-8")
    )

    assert summary["analysis_range"] == {"start_sol": 100, "end_sol": 103}
    assert summary["csv_files_analyzed"] == 3
    assert summary["coverage_status_counts"] == {
        "timestamp_analysis_available": 3
    }
    assert summary["products"]["ATS"]["present_sols"] == [100, 101, 103]
    assert summary["products"]["ATS"]["missing_sols"] == [102]
    assert summary["gap_definition"]["factor"] == 2.5
    assert summary["generated_at_utc"]
    assert summary["interpretation_notes"]


def test_main_parallel_matches_sequential(cli_dataset):
    assert analyzer.main(cli_args(cli_dataset)) == 0
    sequential = (cli_dataset / "out" / "report.csv").read_text(
        encoding="utf-8-sig"
    )

    assert analyzer.main(cli_args(cli_dataset, "--workers", "2")) == 0
    parallel = (cli_dataset / "out" / "report.csv").read_text(
        encoding="utf-8-sig"
    )

    assert parallel == sequential


def test_main_workers_zero_means_auto(cli_dataset, monkeypatch):
    monkeypatch.setattr(analyzer.os, "cpu_count", lambda: None)

    assert analyzer.main(cli_args(cli_dataset, "--workers", "0")) == 0


def test_main_uses_gap_factor(cli_dataset):
    assert analyzer.main(cli_args(cli_dataset, "--gap-factor", "10")) == 0

    summary = json.loads(
        (cli_dataset / "out" / "summary.json").read_text(encoding="utf-8")
    )

    assert summary["gap_definition"]["factor"] == 10.0

    with (cli_dataset / "out" / "report.csv").open(
        newline="", encoding="utf-8-sig"
    ) as file:
        assert {row["gap_count"] for row in csv.DictReader(file)} == {"0"}


def test_main_missing_inventory_returns_error(tmp_path, capsys):
    code = analyzer.main(cli_args(tmp_path))

    assert code == 1
    assert "File inventory not found" in capsys.readouterr().err


def test_main_missing_metadata_returns_error(cli_dataset, capsys):
    (cli_dataset / "metadata.json").unlink()

    assert analyzer.main(cli_args(cli_dataset)) == 1
    assert "Metadata inventory not found" in capsys.readouterr().err


def test_main_invalid_metadata_json_returns_error(cli_dataset, capsys):
    (cli_dataset / "metadata.json").write_text("{bad", encoding="utf-8")

    assert analyzer.main(cli_args(cli_dataset)) == 1
    assert "not valid JSON" in capsys.readouterr().err


def test_main_unwritable_output_returns_error(cli_dataset, capsys):
    # The report path is an existing directory -> os.replace fails.
    (cli_dataset / "out" / "report.csv").mkdir(parents=True)

    assert analyzer.main(cli_args(cli_dataset)) == 1
    assert "Error:" in capsys.readouterr().err
    assert not (cli_dataset / "out" / "report.csv.tmp").exists()


def test_main_rejects_inverted_sol_range(cli_dataset):
    with pytest.raises(SystemExit) as exc:
        analyzer.main(
            cli_args(cli_dataset)
            + ["--start-sol", "200", "--end-sol", "100"]
        )

    assert exc.value.code == 2


@pytest.mark.parametrize("value", ["1", "0.5", "nan", "inf", "-3"])
def test_main_rejects_invalid_gap_factor(cli_dataset, value):
    with pytest.raises(SystemExit) as exc:
        analyzer.main(cli_args(cli_dataset, "--gap-factor", value))

    assert exc.value.code == 2


def test_main_rejects_negative_workers(cli_dataset):
    with pytest.raises(SystemExit) as exc:
        analyzer.main(cli_args(cli_dataset, "--workers", "-1"))

    assert exc.value.code == 2


def test_main_uses_sys_argv_when_not_given(cli_dataset, monkeypatch):
    monkeypatch.setattr(
        analyzer.sys, "argv", ["prog", *cli_args(cli_dataset)]
    )

    assert analyzer.main() == 0


# ==================================================
# Remaining edge cases (platform / cleanup / entry point)
# ==================================================

def test_lexically_within_returns_false_when_commonpath_fails(
    tmp_path, monkeypatch
):
    def boom(paths):
        raise ValueError("Paths don't have the same drive")

    monkeypatch.setattr(analyzer.os.path, "commonpath", boom)

    assert analyzer._lexically_within(tmp_path, tmp_path / "a") is False


def test_files_by_name_skips_broken_symlinks(tmp_path):
    sol_dir = tmp_path / "SOL100"
    sol_dir.mkdir()
    (sol_dir / "real.csv").write_text("x\n", encoding="utf-8")

    try:
        (sol_dir / "broken.csv").symlink_to(tmp_path / "does_not_exist")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not supported here")

    by_name = analyzer._files_by_casefolded_name(sol_dir)

    assert "real.csv" in by_name
    assert "broken.csv" not in by_name


def test_write_atomically_survives_cleanup_failure(tmp_path, monkeypatch):
    """If removing the temp file also fails, the original error wins."""

    target = tmp_path / "s.json"

    def boom_unlink(self, *args, **kwargs):
        raise OSError("cannot delete")

    monkeypatch.setattr(analyzer.Path, "unlink", boom_unlink)

    with pytest.raises(TypeError):
        analyzer.save_summary_json({"v": object()}, target)


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_module_runs_as_script(cli_dataset):
    import runpy
    import sys

    argv = ["coverage_analyzer.py", *cli_args(cli_dataset)]
    old_argv = sys.argv

    try:
        sys.argv = argv

        with pytest.raises(SystemExit) as exc:
            runpy.run_module(
                "backend.analyzers.coverage_analyzer",
                run_name="__main__",
            )
    finally:
        sys.argv = old_argv

    assert exc.value.code == 0
    assert (cli_dataset / "out" / "summary.json").is_file()


# ==================================================
# End-to-end with the real shared parsers (meda_common)
# ==================================================

def test_real_utc_axis_end_to_end(tmp_path):
    csv_path = write_text(
        tmp_path / "utc.csv",
        "TIME_UTC,TEMPERATURE\n"
        "2021-03-01T00:00:00Z,1\n"
        "2021-03-01T00:00:01Z,2\n"
        "2021-03-01T00:00:02Z,3\n"
        "2021-03-01T00:01:00Z,4\n"
        "naive-not-utc,5\n"
        "2021-03-01T00:01:01,6\n",   # naive -> rejected on a UTC axis
    )

    result = analyzer.analyze_csv(
        csv_path, make_xml(names=("TIME_UTC", "TEMPERATURE"))
    )

    assert result["time_kind"] == "utc"
    assert result["parsed_timestamp_count"] == 4
    assert result["invalid_timestamp_count"] == 2
    assert result["span_seconds"] == 60
    assert result["gap_count"] == 1
    assert result["numeric_value_count"] == 6
    assert not any("No UTC conversion" in n for n in result["notes"])


def test_real_lmst_axis_end_to_end(tmp_path):
    csv_path = write_text(
        tmp_path / "lmst.csv",
        "LMST,TEMPERATURE\n"
        "Sol-0107M10:00:00,1\n"
        "Sol-0107M10:00:01,2\n"
        "Sol-0107M10:00:02,3\n"
        "garbage,4\n",
    )

    result = analyzer.analyze_csv(
        csv_path, make_xml(names=("LMST", "TEMPERATURE"))
    )

    assert result["time_kind"] == "lmst"
    assert result["parsed_timestamp_count"] == 3
    assert result["invalid_timestamp_count"] == 1
    assert any("No UTC conversion" in n for n in result["notes"])


def test_real_numeric_columns_exclude_time_named_columns(tmp_path):
    csv_path = write_text(
        tmp_path / "n.csv", "SCLK,TEMPERATURE\n1,2\n2,3\n"
    )

    result = analyzer.analyze_csv(csv_path, make_xml())

    # Only TEMPERATURE is counted as a numeric measurement.
    assert result["numeric_value_count"] == 2


def test_real_missing_text_variants_are_missing_not_invalid(tmp_path):
    csv_path = write_text(
        tmp_path / "m.csv",
        "SCLK,TEMPERATURE\n1,NaN\n2,null\n3,N/A\n4,missing\n5,\n6,7\n",
    )

    result = analyzer.analyze_csv(csv_path, make_xml())

    assert result["numeric_missing_count"] == 5
    assert result["numeric_invalid_count"] == 0
    assert result["numeric_value_count"] == 1


def test_real_get_product_code_is_uppercased_in_reports(tmp_path):
    record = {
        "sol_folder": "SOL1",
        "filename": "x_cal_ats.csv",
        "extension": ".csv",
    }

    (report,) = analyzer.analyze_coverage(tmp_path, [record], {})

    assert report["product_code"] == "ATS"


# ==================================================
# Worker selection and pool fail-safe
# ==================================================

@pytest.mark.parametrize(
    ("requested", "tasks", "cpus", "expected"),
    [
        ("optimized", 0, 16, 1),
        ("optimized", 3, 16, 1),
        ("optimized", 4, 8, 4),
        ("optimized", 100, 8, 7),
        ("optimized", 100, 32, 8),
        ("optimized", 100, 2, 1),
        ("optimized", 100, 1, 1),
        (" Optimized ", 100, 4, 3),
        (1, 100, 8, 1),
        (4, 100, 8, 4),
        (4, 2, 8, 2),
        (4, 0, 8, 1),
    ],
)
def test_choose_workers(requested, tasks, cpus, expected):
    assert analyzer.choose_workers(
        requested, tasks, cpu_count=cpus
    ) == expected


def test_choose_workers_uses_os_cpu_count_by_default(monkeypatch):
    monkeypatch.setattr(analyzer.os, "cpu_count", lambda: None)

    assert analyzer.choose_workers("optimized", 100) == 1

    monkeypatch.setattr(analyzer.os, "cpu_count", lambda: 6)

    assert analyzer.choose_workers("optimized", 100) == 5


@pytest.mark.parametrize(
    "requested", [0, -1, True, 2.5, None, "auto", "", [2]]
)
def test_choose_workers_rejects_invalid_requested(requested):
    with pytest.raises(ValueError, match="workers"):
        analyzer.choose_workers(requested, 10)


@pytest.mark.parametrize("tasks", [-1, True, "3", None, 1.5])
def test_choose_workers_rejects_invalid_task_count(tasks):
    with pytest.raises(ValueError, match="task_count"):
        analyzer.choose_workers(2, tasks)


def test_pool_start_failure_falls_back_to_sequential(
    tmp_path, monkeypatch
):
    inventory, metadata = make_dataset(tmp_path, sols=(100, 101, 102))
    expected = analyzer.analyze_coverage(
        tmp_path, inventory, metadata, workers=1
    )

    class Broken:
        def __init__(self, *args, **kwargs):
            raise OSError("cannot start processes")

    monkeypatch.setattr(analyzer, "ProcessPoolExecutor", Broken)

    assert analyzer.analyze_coverage(
        tmp_path, inventory, metadata, workers=2
    ) == expected


def test_pool_crash_falls_back_to_sequential(tmp_path, monkeypatch):
    inventory, metadata = make_dataset(tmp_path, sols=(100, 101, 102))
    expected = analyzer.analyze_coverage(
        tmp_path, inventory, metadata, workers=1
    )

    class Crashing:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def map(self, *args, **kwargs):
            raise analyzer.BrokenProcessPool("worker died")

    monkeypatch.setattr(analyzer, "ProcessPoolExecutor", Crashing)

    assert analyzer.analyze_coverage(
        tmp_path, inventory, metadata, workers=2
    ) == expected


def test_main_workers_zero_uses_choose_workers(cli_dataset, monkeypatch):
    seen = {}
    original = analyzer.analyze_coverage

    def spy(*args, **kwargs):
        seen["workers"] = kwargs["workers"]
        return original(*args, **kwargs)

    monkeypatch.setattr(analyzer, "analyze_coverage", spy)
    monkeypatch.setattr(
        analyzer,
        "choose_workers",
        lambda requested, count: 1 if count else 99,
    )

    assert analyzer.main(cli_args(cli_dataset, "--workers", "0")) == 0
    assert seen["workers"] == 1

def test_analyze_csv_classifies_all_special_constant_categories(tmp_path):
    csv_path = write_text(
        tmp_path / "special_constants.csv",
        "SCLK,TEMPERATURE\n"
        "1,-999\n"
        "2,-998\n"
        "3,-997\n"
        "4,-996\n"
        "5,-995\n"
        "6,-994\n"
        "7,-993\n"
        "8,12.5\n"
        "9,abc\n",
    )

    xml = make_xml()

    xml["fields"][1]["special_constants"] = [
        {
            "missing_constant": "-999",
            "invalid_constant": "-998",
            "error_constant": ["-997", "-993"],
            "saturated_constant": "-996",
            "unknown_constant": ["-995", "-993"],
            "not_applicable_constant": "-994",
        }
    ]

    result = analyzer.analyze_csv(csv_path, xml)

    assert result["numeric_missing_count"] == 1
    assert result["numeric_invalid_count"] == 2
    assert result["numeric_value_count"] == 1

    assert result["special_error_count"] == 1
    assert result["special_saturated_count"] == 1
    assert result["special_unknown_count"] == 1
    assert result["special_not_applicable_count"] == 1
    assert result["special_ambiguous_count"] == 1

def test_analyze_csv_classifies_all_special_constant_categories(tmp_path):
    csv_path = write_text(
        tmp_path / "special_constants.csv",
        "SCLK,TEMPERATURE\n"
        "1,-999\n"
        "2,-998\n"
        "3,-997\n"
        "4,-996\n"
        "5,-995\n"
        "6,-994\n"
        "7,-993\n"
        "8,12.5\n"
        "9,abc\n",
    )

    xml = make_xml()

    xml["fields"][1]["special_constants"] = [
        {
            "missing_constant": "-999",
            "invalid_constant": "-998",
            "error_constant": ["-997", "-993"],
            "saturated_constant": "-996",
            "unknown_constant": ["-995", "-993"],
            "not_applicable_constant": "-994",
        }
    ]

    result = analyzer.analyze_csv(csv_path, xml)

    assert result["numeric_missing_count"] == 1
    assert result["numeric_invalid_count"] == 2
    assert result["numeric_value_count"] == 1

    assert result["special_error_count"] == 1
    assert result["special_saturated_count"] == 1
    assert result["special_unknown_count"] == 1
    assert result["special_not_applicable_count"] == 1
    assert result["special_ambiguous_count"] == 1

def test_prepared_special_constant_matches_existing_classification():
    from backend.analyzers.meda_common import (
        classify_special_constant,
        classify_prepared_special_constant,
        prepare_special_constant_metadata,
    )

    field = {
        "special_constants": [
            {
                "missing_constant": "-999",
                "invalid_constant": "-998",
                "error_constant": "-997",
                "saturated_constant": "-996",
                "unknown_constant": "-995",
                "not_applicable_constant": "-994",
                "another_constant": "-993",
            }
        ]
    }

    prepared = prepare_special_constant_metadata(field)

    values = [
        "-999",
        "-999.0",
        "-998",
        "-997",
        "-996",
        "-995",
        "-994",
        "-993",
        "12.5",
        "abc",
        "NaN",
    ]

    for raw in values:
        assert classify_prepared_special_constant(
            raw, prepared
        ) == classify_special_constant(raw, field)


def test_prepared_special_constant_preserves_ambiguous_classification():
    from backend.analyzers.meda_common import (
        classify_prepared_special_constant,
        prepare_special_constant_metadata,
    )

    field = {
        "special_constants": [
            {
                "error_constant": "-993",
                "unknown_constant": "-993.0",
            }
        ]
    }

    prepared = prepare_special_constant_metadata(field)

    assert classify_prepared_special_constant(
        "-993", prepared
    ) == "ambiguous_special_constant"


def test_prepared_special_constant_does_not_mutate_field():
    from copy import deepcopy

    from backend.analyzers.meda_common import (
        prepare_special_constant_metadata,
    )

    field = {
        "special_constants": [
            {
                "missing_constant": {
                    "#text": "-999",
                    "@unit": "example",
                }
            }
        ]
    }

    original = deepcopy(field)

    prepare_special_constant_metadata(field)

    assert field == original


def test_analyze_csv_prepares_special_metadata_once_per_numeric_field(
    tmp_path, monkeypatch
):
    csv_path = write_text(
        tmp_path / "prepared.csv",
        "SCLK,TEMPERATURE\n"
        "1,-999\n"
        "2,10\n"
        "3,20\n"
        "4,30\n",
    )

    xml = make_xml()
    xml["fields"][1]["special_constants"] = [
        {"missing_constant": "-999"}
    ]

    original = analyzer.prepare_special_constant_metadata
    calls = []

    def spy(field):
        calls.append(field)
        return original(field)

    monkeypatch.setattr(
        analyzer,
        "prepare_special_constant_metadata",
        spy,
    )

    result = analyzer.analyze_csv(csv_path, xml)

    assert len(calls) == 1
    assert result["numeric_missing_count"] == 1
    assert result["numeric_value_count"] == 3
    assert result["numeric_invalid_count"] == 0


def test_special_constant_metadata_is_prepared_once_per_numeric_field(
    tmp_path,
    monkeypatch,
):
    csv_path = write_text(
        tmp_path / "prepared_metadata.csv",
        "SCLK,TEMPERATURE,PRESSURE\n"
        "1,-999,-998\n"
        "2,10.5,20.5\n"
        "3,11.5,21.5\n"
        "4,12.5,22.5\n",
    )

    xml = make_xml(
    names=("SCLK", "TEMPERATURE", "PRESSURE")
    )

    xml["fields"][1]["special_constants"] = {
        "missing_constant": "-999",
    }

    xml["fields"][2]["special_constants"] = {
        "invalid_constant": "-998",
    }

    original_prepare = analyzer.prepare_special_constant_metadata
    calls = []

    def counted_prepare(field):
        calls.append(field)
        return original_prepare(field)

    monkeypatch.setattr(
        analyzer,
        "prepare_special_constant_metadata",
        counted_prepare,
    )

    result = analyzer.analyze_csv(csv_path, xml)

    # Two numeric fields, therefore exactly two preparations.
    assert len(calls) == 2

    assert result["numeric_missing_count"] == 1
    assert result["numeric_invalid_count"] == 1
    assert result["numeric_value_count"] == 6


def test_special_constant_preparation_is_not_repeated_per_row(
    tmp_path,
    monkeypatch,
):
    csv_path = write_text(
        tmp_path / "many_rows.csv",
        "SCLK,TEMPERATURE\n"
        "1,-999\n"
        "2,-999\n"
        "3,-999\n"
        "4,-999\n"
        "5,-999\n",
    )

    xml = make_xml()

    xml["fields"][1]["special_constants"] = {
        "missing_constant": "-999",
    }

    original_prepare = analyzer.prepare_special_constant_metadata
    calls = 0

    def counted_prepare(field):
        nonlocal calls
        calls += 1
        return original_prepare(field)

    monkeypatch.setattr(
        analyzer,
        "prepare_special_constant_metadata",
        counted_prepare,
    )

    result = analyzer.analyze_csv(csv_path, xml)

    assert calls == 1
    assert result["numeric_missing_count"] == 5
    assert result["numeric_value_count"] == 0
