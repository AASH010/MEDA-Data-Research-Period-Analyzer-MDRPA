from __future__ import annotations

import csv
import importlib.util
import json
import runpy
import sys
from array import array
from pathlib import Path

import pytest

from backend.analyzers import synchronization_analyzer as analyzer


# ==================================================
# Helpers and fixtures
# ==================================================

def make_inventory_row(
    *,
    filename="sample.csv",
    sol_folder="SOL100",
    sol_number=100,
    relative_path="SOL100/sample.csv",
    product_code="ATS",
):
    return {
        "filename": filename,
        "sol_folder": sol_folder,
        "sol_number": sol_number,
        "relative_path": relative_path,
        "extension": "csv",
        "product_code": product_code,
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


def fields_of(*names):
    return [{"name": name} for name in names]


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def fake_meda(monkeypatch):
    """
    Deterministic stand-ins for meda_common so the tests of this
    module do not depend on the real parsers.

    Time fields:
      TIME  -> kind "utc"
      LMSTF -> kind "lmst"
      ODD   -> kind "weird" (no registered parser)
      KINDLESS -> empty kind
    """

    def parse(value):
        if value == "none":
            return None
        if value == "boom":
            raise ValueError("bad value")
        if value == "huge":
            return 10 ** 400          # float() -> OverflowError
        if value == "obj":
            return object()           # float() -> TypeError
        if value == "nanval":
            return float("nan")
        if value == "infval":
            return float("inf")
        return float(value)

    def pick(fields, axis_preference):
        for index, field in enumerate(fields):
            name = field["name"]

            if name == "TIME":
                return index, name, "utc"
            if name == "LMSTF":
                return index, name, "lmst"
            if name == "ODD":
                return index, name, "weird"
            if name == "KINDLESS":
                return index, name, ""

        return None, None, None

    monkeypatch.setattr(
        analyzer,
        "PARSERS",
        {"utc": (parse,), "lmst": (parse,)},
    )
    monkeypatch.setattr(analyzer, "pick_time_column", pick)
    monkeypatch.setattr(
        analyzer,
        "ordered_fields",
        lambda fields: list(fields),
    )
    monkeypatch.setattr(
        analyzer,
        "norm",
        lambda value: str(value).strip().upper(),
    )
    monkeypatch.setattr(
        analyzer,
        "MISSING_TEXT",
        frozenset({"", "nan", "null"}),
    )


# ==================================================
# General helpers
# ==================================================

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SOL100", 100),
        ("SOL_0100", 100),
        ("SOL-100", 100),
        ("sol250", 250),
        ("invalid", None),
        (None, None),
        (7, 7),
        ("12", 12),
        (3.9, 3),
    ],
)
def test_get_sol_number(value, expected):
    assert analyzer.get_sol_number(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.5, 1.5),
        ("2.5", 2.5),
        (None, None),
        ("abc", None),
        (float("inf"), None),
        (float("nan"), None),
        (10 ** 400, None),
    ],
)
def test_safe_float(value, expected):
    assert analyzer.safe_float(value) == expected


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        ("5", -1, 5),
        (None, -1, -1),
        ("x", 9, 9),
        (float("inf"), 4, 4),
    ],
)
def test_safe_int(value, default, expected):
    assert analyzer.safe_int(value, default) == expected


def test_safe_int_default_is_minus_one():
    assert analyzer.safe_int("not a number") == -1


def test_inventory_sol_number_prefers_sol_number():
    assert (
        analyzer.inventory_sol_number(
            {"sol_number": "7", "sol_folder": "SOL9"}
        )
        == 7
    )


def test_inventory_sol_number_falls_back_to_folder():
    assert (
        analyzer.inventory_sol_number(
            {"sol_number": "", "sol_folder": "SOL_0009"}
        )
        == 9
    )


def test_inventory_sol_number_returns_none_when_unknown():
    assert (
        analyzer.inventory_sol_number(
            {"sol_number": "", "sol_folder": "unknown"}
        )
        is None
    )


def test_normalize_path_handles_windows_separators():
    assert (
        analyzer.normalize_path(
            r"SOL100\nested\sample.xml"
        )
        == "sol100/nested/sample.xml"
    )


def test_portable_path_strips_and_normalizes():
    assert analyzer.portable_path("  a\\b\\c.csv ") == "a/b/c.csv"
    assert analyzer.portable_path(None) == ""


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


def test_is_missing(fake_meda):
    assert analyzer.is_missing(None) is True
    assert analyzer.is_missing("") is True
    assert analyzer.is_missing("  NaN ") is True
    assert analyzer.is_missing("12") is False


def test_get_metadata_relative_path_prefers_source_relative_path():
    record = {
        "source_relative_path": " a/b.xml ",
        "relative_path": "other.xml",
    }

    assert analyzer.get_metadata_relative_path(record) == "a/b.xml"


def test_get_metadata_relative_path_falls_back_and_defaults():
    assert (
        analyzer.get_metadata_relative_path(
            {"relative_path": "x.xml"}
        )
        == "x.xml"
    )
    assert analyzer.get_metadata_relative_path({}) == ""


def test_get_inventory_relative_path_fallbacks():
    assert (
        analyzer.get_inventory_relative_path(
            {"relative_path": "a.csv", "source_relative_path": "b.csv"}
        )
        == "a.csv"
    )
    assert (
        analyzer.get_inventory_relative_path(
            {"source_relative_path": "b.csv"}
        )
        == "b.csv"
    )
    assert analyzer.get_inventory_relative_path({}) == ""


# ==================================================
# Input loading
# ==================================================

def test_load_inventory_reads_csv_with_bom(tmp_path):
    path = tmp_path / "inventory.csv"
    path.write_text(
        "filename,extension\nsample.csv,csv\n",
        encoding="utf-8-sig",
    )

    rows = analyzer.load_inventory(path)

    assert rows == [{"filename": "sample.csv", "extension": "csv"}]


def test_load_inventory_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        analyzer.load_inventory(tmp_path / "missing.csv")


def test_load_metadata_accepts_list_and_filters_non_dicts(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps([{"a": 1}, "text", 5]), encoding="utf-8")

    assert analyzer.load_metadata(path) == [{"a": 1}]


def test_load_metadata_accepts_records_dict(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text(
        json.dumps({"records": [{"a": 1}, None]}),
        encoding="utf-8",
    )

    assert analyzer.load_metadata(path) == [{"a": 1}]


def test_load_metadata_rejects_dict_without_records_list(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps({"records": "nope"}), encoding="utf-8")

    with pytest.raises(ValueError, match="records"):
        analyzer.load_metadata(path)


def test_load_metadata_rejects_unsupported_structure(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(5), encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported"):
        analyzer.load_metadata(path)


def test_load_metadata_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        analyzer.load_metadata(tmp_path / "missing.json")


# ==================================================
# Metadata indexing and matching
# ==================================================

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


def test_build_metadata_index_skips_records_without_source_file():
    index = analyzer.build_metadata_index(
        [{"source_file": "  ", "sol_number": 1}, {"sol_number": 2}]
    )

    assert not index["by_stem"]
    assert not index["by_sol_name"]
    assert not index["by_path"]


def test_build_metadata_index_without_sol_or_path():
    record = {"source_file": "x.xml"}

    index = analyzer.build_metadata_index([record])

    assert index["by_stem"]["x"] == [record]
    assert not index["by_sol_name"]
    assert not index["by_path"]


def test_metadata_sol_number_uses_folder_fallback():
    assert (
        analyzer.metadata_sol_number(
            {"sol_number": None, "sol_folder": "SOL_0042"}
        )
        == 42
    )
    assert analyzer.metadata_sol_number({}) is None


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


def test_find_metadata_record_sol_from_folder():
    record = make_metadata_record()
    index = analyzer.build_metadata_index([record])

    row = make_inventory_row(relative_path="", sol_number="")

    matched, status = analyzer.find_metadata_record(row, index)

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


def test_find_metadata_record_reports_ambiguous_sol_and_name():
    first = make_metadata_record(relative_path="a/sample.xml")
    second = make_metadata_record(relative_path="b/sample.xml")

    index = analyzer.build_metadata_index([first, second])

    matched, status = analyzer.find_metadata_record(
        make_inventory_row(relative_path=""),
        index,
    )

    assert matched is None
    assert status == "ambiguous_metadata_match"


def test_find_metadata_record_matches_unique_stem():
    record = make_metadata_record(sol_number=200, sol_folder="SOL200")
    index = analyzer.build_metadata_index([record])

    matched, status = analyzer.find_metadata_record(
        make_inventory_row(relative_path=""),
        index,
    )

    assert matched is record
    assert status == "matched_by_unique_stem"


def test_find_metadata_record_reports_ambiguous_stem():
    first = make_metadata_record(
        sol_number=200,
        sol_folder="SOL200",
        relative_path="a/sample.xml",
    )
    second = make_metadata_record(
        sol_number=300,
        sol_folder="SOL300",
        relative_path="b/sample.xml",
    )

    index = analyzer.build_metadata_index([first, second])

    row = make_inventory_row(
        relative_path="",
        sol_number="",
        sol_folder="unknown",
    )

    matched, status = analyzer.find_metadata_record(row, index)

    assert matched is None
    assert status == "ambiguous_metadata_stem"


def test_find_metadata_record_reports_not_found():
    index = analyzer.build_metadata_index([])

    matched, status = analyzer.find_metadata_record(
        make_inventory_row(relative_path="x/none.csv", filename="none.csv"),
        index,
    )

    assert matched is None
    assert status == "metadata_not_found"


def test_find_metadata_record_reports_missing_filename():
    index = analyzer.build_metadata_index([])

    matched, status = analyzer.find_metadata_record(
        {"filename": ""},
        index,
    )

    assert matched is None
    assert status == "missing_inventory_filename"


# ==================================================
# CSV path resolution
# ==================================================

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


def test_resolve_csv_path_finds_unique_nested_file_in_sol_folder(
    tmp_path,
):
    csv_path = tmp_path / "SOL100" / "deep" / "sample.csv"
    write_text(csv_path, "x")

    row = make_inventory_row(relative_path="")

    assert analyzer.resolve_csv_path(tmp_path, row) == csv_path


def test_resolve_csv_path_ignores_same_name_outside_sol_folder(
    tmp_path,
):
    inside = write_text(tmp_path / "SOL100" / "deep" / "sample.csv", "a")
    write_text(tmp_path / "SOL200" / "sample.csv", "b")

    row = make_inventory_row(relative_path="")

    assert analyzer.resolve_csv_path(tmp_path, row) == inside


def test_resolve_csv_path_matches_filename_case_insensitively(tmp_path):
    csv_path = write_text(tmp_path / "SOL100" / "deep" / "SAMPLE.CSV", "x")

    row = make_inventory_row(relative_path="")

    assert analyzer.resolve_csv_path(tmp_path, row) == csv_path


def test_resolve_csv_path_falls_back_to_global_search(tmp_path):
    csv_path = write_text(tmp_path / "SOL200" / "sample.csv", "x")

    # SOL100 exists but does not contain the file.
    (tmp_path / "SOL100").mkdir()

    row = make_inventory_row(relative_path="")

    assert analyzer.resolve_csv_path(tmp_path, row) == csv_path


def test_resolve_csv_path_global_search_without_sol_folder(tmp_path):
    csv_path = write_text(tmp_path / "anywhere" / "sample.csv", "x")

    row = make_inventory_row(relative_path="", sol_folder="")

    assert analyzer.resolve_csv_path(tmp_path, row) == csv_path


def test_resolve_csv_path_ignores_sol_folder_outside_root(tmp_path):
    root = tmp_path / "input"
    csv_path = write_text(root / "anywhere" / "sample.csv", "x")
    (tmp_path / "other").mkdir()

    row = make_inventory_row(relative_path="", sol_folder="../other")

    assert analyzer.resolve_csv_path(root, row) == csv_path


def test_resolve_csv_path_ignores_missing_sol_folder(tmp_path):
    csv_path = write_text(tmp_path / "x" / "sample.csv", "x")

    row = make_inventory_row(relative_path="", sol_folder="NOPE")

    assert analyzer.resolve_csv_path(tmp_path, row) == csv_path


def test_resolve_csv_path_global_ambiguity_returns_none(tmp_path):
    write_text(tmp_path / "a" / "sample.csv", "a")
    write_text(tmp_path / "b" / "sample.csv", "b")

    row = make_inventory_row(relative_path="", sol_folder="")

    assert analyzer.resolve_csv_path(tmp_path, row) is None


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


def test_resolve_csv_path_returns_none_when_root_is_not_a_directory(
    tmp_path,
):
    row = make_inventory_row()

    assert analyzer.resolve_csv_path(tmp_path / "missing", row) is None


def test_resolve_csv_path_returns_none_when_root_cannot_resolve(
    monkeypatch,
):
    class BrokenPath:
        def __init__(self, *args):
            pass

        def expanduser(self):
            return self

        def resolve(self):
            raise OSError("cannot resolve")

    monkeypatch.setattr(analyzer, "Path", BrokenPath)

    assert (
        analyzer.resolve_csv_path("whatever", make_inventory_row())
        is None
    )


@pytest.mark.parametrize("filename", ["", "/", None])
def test_resolve_csv_path_returns_none_for_unusable_filename(
    tmp_path,
    filename,
):
    row = make_inventory_row(filename=filename, relative_path="")

    assert analyzer.resolve_csv_path(tmp_path, row) is None


def test_resolve_csv_path_rejects_parent_directory_traversal(
    tmp_path,
):
    input_root = tmp_path / "input"
    input_root.mkdir()

    outside_file = tmp_path / "outside.csv"
    outside_file.write_text("time,value\n1,2\n", encoding="utf-8")

    row = make_inventory_row(
        filename="outside.csv",
        sol_folder="SOL100",
        relative_path="../outside.csv",
    )

    assert analyzer.resolve_csv_path(input_root, row) is None


def test_resolve_csv_path_rejects_symlink_outside_input_root(
    tmp_path,
):
    input_root = tmp_path / "input"
    sol_directory = input_root / "SOL100"
    sol_directory.mkdir(parents=True)

    outside_file = tmp_path / "outside.csv"
    outside_file.write_text("time,value\n1,2\n", encoding="utf-8")

    link = sol_directory / "sample.csv"

    try:
        link.symlink_to(outside_file)
    except (OSError, NotImplementedError):
        pytest.skip("Symbolic links are not available on this system.")

    row = make_inventory_row(
        filename="sample.csv",
        relative_path="",
    )

    assert analyzer.resolve_csv_path(input_root, row) is None


def test_resolve_csv_path_global_search_skips_outside_symlinks(
    tmp_path,
):
    input_root = tmp_path / "input"
    real = write_text(input_root / "real" / "sample.csv", "x")
    outside = write_text(tmp_path / "outside.csv", "y")

    link = input_root / "other" / "sample.csv"
    link.parent.mkdir(parents=True)

    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symbolic links are not available on this system.")

    row = make_inventory_row(relative_path="", sol_folder="")

    assert analyzer.resolve_csv_path(input_root, row) == real


def test_resolve_csv_path_accepts_shared_file_index(tmp_path):
    first = write_text(tmp_path / "a" / "one.csv", "1")
    second = write_text(tmp_path / "b" / "two.csv", "2")

    index = analyzer.FileIndex()

    row_one = make_inventory_row(
        filename="one.csv", relative_path="", sol_folder=""
    )
    row_two = make_inventory_row(
        filename="two.csv", relative_path="", sol_folder=""
    )

    assert analyzer.resolve_csv_path(tmp_path, row_one, index) == first
    assert analyzer.resolve_csv_path(tmp_path, row_two, index) == second


def test_file_index_is_built_lazily_once_and_rebuilt_for_new_root(
    tmp_path,
):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"

    write_text(root_a / "x.csv", "1")
    write_text(root_b / "y.csv", "2")

    index = analyzer.FileIndex()

    assert index._by_name is None

    assert [p.name for p in index.candidates(root_a, "X.CSV")] == ["x.csv"]

    built = index._by_name

    # Same root: no rebuild, so a file added later is not seen.
    write_text(root_a / "late.csv", "3")

    assert index.candidates(root_a, "late.csv") == []
    assert index._by_name is built

    # Different root: rebuilt.
    assert [p.name for p in index.candidates(root_b, "y.csv")] == ["y.csv"]
    assert index.candidates(root_b, "x.csv") == []


# ==================================================
# CSV column mapping
# ==================================================

def mapping_for(header, names, has_header=None):
    return analyzer.build_column_mapping(
        header,
        fields_of(*names),
        has_header,
    )


def test_mapping_without_fields(fake_meda):
    assert analyzer.build_column_mapping(["A"], [], None) == (
        None,
        False,
        "no_xml_fields",
    )


def test_mapping_rejects_empty_xml_field_name(fake_meda):
    assert mapping_for(["A", "B"], ["A", ""])[2] == "invalid_xml_field_names"


def test_mapping_rejects_empty_header(fake_meda):
    assert mapping_for([], ["A"])[2] == "empty_csv_header"


def test_mapping_rejects_column_count_mismatch(fake_meda):
    assert mapping_for(["A"], ["A", "B"])[2] == "column_count_mismatch"


def test_mapping_rejects_duplicate_csv_headers(fake_meda):
    assert mapping_for(["A", "a"], ["A", "B"])[2] == "duplicate_csv_header_names"


def test_mapping_exact_match(fake_meda):
    mapping, skip_header, status = mapping_for(["a", "b"], ["A", "B"])

    assert mapping == {0: 0, 1: 1}
    assert skip_header is True
    assert status == "header_exact_match"


def ws_names():
    names = [f"F{i}" for i in range(18)]
    names[15] = "BOOM1_ALG_IN_STABLE_STATE"
    names[16] = "BOOM2_ALG_IN_STABLE_STATE"
    return names


def test_mapping_accepts_ws_aliases(fake_meda):
    names = ws_names()
    header = list(names)
    header[15] = "BOOM1_ALG_STATE_STABLE"
    header[16] = "BOOM2_ALG_STATE_STABLE"

    mapping, skip_header, status = mapping_for(header, names)

    assert mapping == {i: i for i in range(18)}
    assert skip_header is True
    assert status == "header_positional_ws_aliases"


def test_mapping_rejects_ws_aliases_at_wrong_positions(fake_meda):
    names = ws_names()
    header = list(names)
    header[15] = "BOOM1_ALG_STATE_STABLE"
    header[3] = "SOMETHING_ELSE"

    mapping, _, status = mapping_for(header, names, has_header=True)

    assert mapping is None
    assert status == "header_mapping_ambiguous"


def test_mapping_18_fields_can_still_be_reordered(fake_meda):
    names = [f"F{i}" for i in range(18)]

    mapping, skip_header, status = mapping_for(
        list(reversed(names)),
        names,
    )

    assert status == "header_reordered_mapped"
    assert skip_header is True
    assert mapping[0] == 17


def test_mapping_duplicate_xml_names_positional(fake_meda):
    mapping, skip_header, status = mapping_for(
        ["A", "A2", "B"],
        ["A", "A", "B"],
    )

    assert mapping == {0: 0, 1: 1, 2: 2}
    assert skip_header is True
    assert status == "header_positional_duplicate_xml_names"


def test_mapping_duplicate_xml_names_ambiguous_when_other_column_differs(
    fake_meda,
):
    mapping, skip_header, status = mapping_for(
        ["X", "Y", "Z"],
        ["A", "A", "B"],
    )

    assert mapping is None
    assert skip_header is False
    assert status == "duplicate_xml_names_mapping_ambiguous"


def test_mapping_duplicate_xml_names_ambiguous_with_empty_header(
    fake_meda,
):
    mapping, _, status = mapping_for(
        ["A", "", "B"],
        ["A", "A", "B"],
    )

    assert mapping is None
    assert status == "duplicate_xml_names_mapping_ambiguous"


def test_mapping_reordered_headers(fake_meda):
    mapping, skip_header, status = mapping_for(["B", "A"], ["A", "B"])

    assert mapping == {0: 1, 1: 0}
    assert skip_header is True
    assert status == "header_reordered_mapped"


def test_mapping_declared_header_without_safe_mapping(fake_meda):
    mapping, _, status = mapping_for(["A", "C"], ["A", "B"], True)

    assert mapping is None
    assert status == "header_mapping_ambiguous"


def test_mapping_partial_header_match(fake_meda):
    mapping, _, status = mapping_for(["A", "C"], ["A", "B"], None)

    assert mapping is None
    assert status == "partial_header_match"


def test_mapping_unknown_header_status(fake_meda):
    mapping, _, status = mapping_for(["X", "Y"], ["A", "B"], None)

    assert mapping is None
    assert status == "header_status_unknown"


def test_mapping_positional_when_xml_declares_no_header(fake_meda):
    mapping, skip_header, status = mapping_for(["1", "2"], ["A", "B"], False)

    assert mapping == {0: 0, 1: 1}
    assert skip_header is False
    assert status == "positional_no_header"


def test_mapping_unexpected_header_flag_is_ambiguous(fake_meda):
    mapping, _, status = mapping_for(["X", "Y"], ["A", "B"], "maybe")

    assert mapping is None
    assert status == "header_mapping_ambiguous"


# ==================================================
# File-level report helpers
# ==================================================

def test_empty_file_report_uses_sol_number():
    row = make_inventory_row()

    report = analyzer.empty_file_report(row, "some_status", "some notes")

    assert report["sol_number"] == 100
    assert report["analysis_status"] == "some_status"
    assert report["notes"] == "some notes"
    assert report["csv_file"] == "sample.csv"
    assert report["total_rows"] == 0
    assert set(report) == set(analyzer.FILE_REPORT_COLUMNS)


def test_empty_file_report_falls_back_to_sol_folder():
    row = make_inventory_row(sol_number="", sol_folder="SOL_0007")

    assert analyzer.empty_file_report(row, "s", "n")["sol_number"] == 7


def test_empty_file_report_without_any_sol():
    report = analyzer.empty_file_report({}, "s", "n")

    assert report["sol_number"] is None
    assert report["sol_folder"] == ""
    assert report["product_code"] == ""
    assert report["csv_file"] == ""


# ==================================================
# File-level timestamp analysis
# ==================================================

def analyse(
    tmp_path,
    content,
    names=("TIME", "V"),
    *,
    has_header=True,
    record_extra=None,
    row=None,
):
    csv_path = tmp_path / "data.csv"

    if content is not None:
        csv_path.write_text(content, encoding="utf-8")

    record = {
        "fields": fields_of(*names),
        "has_header": has_header,
        "parse_status": "parsed",
    }
    record.update(record_extra or {})

    return analyzer.analyse_timestamp_file(
        csv_path,
        row or make_inventory_row(),
        record,
    )


def test_analyse_reports_failed_xml_with_error(tmp_path, fake_meda):
    report, timestamps = analyse(
        tmp_path,
        "TIME,V\n1,1\n",
        record_extra={"parse_status": "failed", "parse_error": "bad xml"},
    )

    assert report["analysis_status"] == "xml_parse_failed"
    assert report["notes"] == "bad xml"
    assert timestamps == []


def test_analyse_reports_failed_xml_without_error(tmp_path, fake_meda):
    report, _ = analyse(
        tmp_path,
        "TIME,V\n1,1\n",
        record_extra={"parse_status": "failed"},
    )

    assert report["notes"] == "XML parsing failed."


def test_analyse_reports_no_xml_fields(tmp_path, fake_meda):
    report, timestamps = analyse(tmp_path, "x\n", names=())

    assert report["analysis_status"] == "no_xml_fields"
    assert timestamps == []


@pytest.mark.parametrize("names", [("A", "B"), ("KINDLESS", "B")])
def test_analyse_reports_no_time_field(tmp_path, fake_meda, names):
    report, timestamps = analyse(tmp_path, "x,y\n1,2\n", names=names)

    assert report["analysis_status"] == "no_time_field"
    assert timestamps == []


def test_analyse_reports_unsupported_parser(tmp_path, fake_meda):
    report, timestamps = analyse(tmp_path, "ODD,V\n1,2\n", names=("ODD", "V"))

    assert report["analysis_status"] == "unsupported_time_parser"
    assert "weird" in report["notes"]
    assert timestamps == []


def test_analyse_reports_empty_csv(tmp_path, fake_meda):
    report, timestamps = analyse(tmp_path, "")

    assert report["analysis_status"] == "empty_file"
    assert report["selected_time_field"] == "TIME"
    assert timestamps == []


def test_analyse_reports_mapping_failure(tmp_path, fake_meda):
    report, timestamps = analyse(tmp_path, "TIME\n1\n")

    assert report["analysis_status"] == "column_count_mismatch"
    assert "could not be mapped" in report["notes"]
    assert timestamps == []


def test_analyse_reports_time_column_not_mapped(
    tmp_path,
    fake_meda,
    monkeypatch,
):
    monkeypatch.setattr(
        analyzer,
        "build_column_mapping",
        lambda *args: ({}, True, "custom"),
    )

    report, timestamps = analyse(tmp_path, "TIME,V\n1,1\n")

    assert report["analysis_status"] == "time_column_not_mapped"
    assert timestamps == []


def test_analyse_reports_read_error(tmp_path, fake_meda):
    report, timestamps = analyse(tmp_path, None)

    assert report["analysis_status"] == "read_error"
    assert timestamps == []


def test_analyse_reports_no_parseable_timestamps(tmp_path, fake_meda):
    report, timestamps = analyse(
        tmp_path,
        "TIME,V\nnan,1\nboom,2\n,3\n",
    )

    assert report["analysis_status"] == "no_parseable_timestamps"
    assert report["total_rows"] == 3
    assert report["missing_timestamps"] == 2
    assert report["invalid_timestamps"] == 1
    assert report["notes"] == "Column mapping: header_exact_match."
    assert timestamps == []


def test_analyse_counts_every_invalid_kind(tmp_path, fake_meda):
    content = (
        "TIME,V\n"
        "1,a\n"
        "none,b\n"      # parser returned None
        "boom,c\n"      # parser raised ValueError
        "huge,d\n"      # float() OverflowError
        "obj,e\n"       # float() TypeError
        "nanval,f\n"    # NaN
        "infval,g\n"    # infinity
        "2,h\n"
    )

    report, timestamps = analyse(tmp_path, content)

    assert report["analysis_status"] == "analysed"
    assert report["total_rows"] == 8
    assert report["parsed_timestamps"] == 2
    assert report["invalid_timestamps"] == 6
    assert timestamps == [1.0, 2.0]


def test_analyse_skips_blank_rows_and_counts_short_rows(
    tmp_path,
    fake_meda,
):
    content = (
        "V,TIME\n"
        "a,1\n"
        "\n"            # [] -> skipped
        ",\n"           # blank values -> skipped
        "5\n"           # too short -> missing
        "b,null\n"      # missing text
        "c,2\n"
    )

    report, timestamps = analyse(tmp_path, content, names=("V", "TIME"))

    assert report["total_rows"] == 4
    assert report["missing_timestamps"] == 2
    assert timestamps == [1.0, 2.0]


def test_analyse_sorted_input_statistics(tmp_path, fake_meda):
    content = "TIME,V\n1,a\n2,a\n3,a\n3,a\n6,a\n"

    report, timestamps = analyse(tmp_path, content)

    assert report["analysis_status"] == "analysed"
    assert timestamps == [1.0, 2.0, 3.0, 3.0, 6.0]
    assert report["parsed_timestamps"] == 5
    assert report["duplicate_timestamps"] == 1
    assert report["out_of_order_timestamps"] == 0
    assert report["median_step"] == 1.0
    assert report["first_timestamp"] == 1.0
    assert report["last_timestamp"] == 6.0
    assert report["notes"] == "Column mapping: header_exact_match."


def test_analyse_unsorted_input_is_sorted_and_flagged(
    tmp_path,
    fake_meda,
):
    content = "TIME,V\n3,a\n1,a\n2,a\n2,a\n"

    report, timestamps = analyse(tmp_path, content)

    assert timestamps == [1.0, 2.0, 2.0, 3.0]
    assert report["out_of_order_timestamps"] == 1
    assert report["duplicate_timestamps"] == 1
    assert "sorted before pair comparison" in report["notes"]


def test_analyse_single_timestamp_has_empty_median(tmp_path, fake_meda):
    report, timestamps = analyse(tmp_path, "TIME,V\n5,a\n")

    assert timestamps == [5.0]
    assert report["median_step"] == ""
    assert report["duplicate_timestamps"] == 0


def test_analyse_all_equal_timestamps_has_empty_median(
    tmp_path,
    fake_meda,
):
    report, _ = analyse(tmp_path, "TIME,V\n5,a\n5,a\n5,a\n")

    assert report["median_step"] == ""
    assert report["duplicate_timestamps"] == 2


def test_analyse_even_step_count_uses_exact_median(tmp_path, fake_meda):
    report, _ = analyse(tmp_path, "TIME,V\n0,a\n1,a\n3,a\n")

    assert report["median_step"] == 1.5


def test_analyse_non_utc_axis_adds_note(tmp_path, fake_meda):
    report, timestamps = analyse(
        tmp_path,
        "LMSTF,V\n1,a\n2,a\n",
        names=("LMSTF", "V"),
    )

    assert report["time_kind"] == "lmst"
    assert "no UTC conversion" in report["notes"]
    assert timestamps == [1.0, 2.0]


def test_analyse_headerless_csv_keeps_first_row(tmp_path, fake_meda):
    report, timestamps = analyse(
        tmp_path,
        "1,a\n2,a\n3,a\n",
        has_header=False,
    )

    assert report["analysis_status"] == "analysed"
    assert report["total_rows"] == 3
    assert timestamps == [1.0, 2.0, 3.0]
    assert "positional_no_header" in report["notes"]


def test_analyse_uses_reordered_header_mapping(tmp_path, fake_meda):
    report, timestamps = analyse(tmp_path, "V,TIME\na,1\nb,2\n")

    assert report["analysis_status"] == "analysed"
    assert timestamps == [1.0, 2.0]
    assert "header_reordered_mapped" in report["notes"]


# ==================================================
# One-to-one matching
# ==================================================

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


def test_match_one_to_one_handles_unsorted_inputs():
    first = [3.0, 1.0, 2.0]
    second = [2.05, 1.05, 3.05]

    matched, differences = analyzer.match_one_to_one(
        first,
        second,
        tolerance=0.1,
    )

    assert matched == 3
    assert differences == pytest.approx([0.05, 0.05, 0.05])


def test_match_one_to_one_handles_empty_inputs():
    matched, differences = analyzer.match_one_to_one(
        [],
        [1.0, 2.0],
        tolerance=0.1,
    )

    assert matched == 0
    assert differences == []


def test_match_one_to_one_handles_no_matches():
    matched, differences = analyzer.match_one_to_one(
        [1.0, 2.0],
        [5.0, 6.0],
        tolerance=0.1,
    )

    assert matched == 0
    assert differences == []


def test_match_one_to_one_does_not_reuse_second_timestamp():
    matched, differences = analyzer.match_one_to_one(
        [1.0, 1.01],
        [1.005],
        tolerance=0.1,
    )

    assert matched == 1
    assert len(differences) == 1


def test_match_one_to_one_respects_tolerance_boundary():
    # 1.5 - 1.0 is exactly representable, so the boundary is exact.
    # (1.1 - 1.0 would be 0.10000000000000009 > 0.1 in binary floats.)
    matched, differences = analyzer.match_one_to_one(
        [1.0],
        [1.5],
        tolerance=0.5,
    )

    assert matched == 1
    assert differences == [0.5]

    matched, differences = analyzer.match_one_to_one(
        [1.0],
        [1.5],
        tolerance=0.4999,
    )

    assert matched == 0
    assert differences == []


def test_match_one_to_one_returns_plain_list():
    _, differences = analyzer.match_one_to_one([1.0], [1.0], 0.0)

    assert isinstance(differences, list)


def test_match_range_only_uses_requested_slices():
    first = array("d", [0.0, 1.0, 2.0, 3.0, 9.0])
    second = array("d", [1.0, 2.0, 3.0, 50.0])

    # first[1:4] = 1, 2, 3 ; second[0:3] = 1, 2, 3
    matched, differences = analyzer._match_range(
        first, 1, 4, second, 0, 3, 0.0
    )

    assert matched == 3
    assert list(differences) == [0.0, 0.0, 0.0]

    # Empty slices never match.
    assert analyzer._match_range(first, 2, 2, second, 0, 3, 0.0)[0] == 0


def test_match_range_advances_both_pointers_when_unmatched():
    first = array("d", [1.0, 10.0])
    second = array("d", [5.0, 10.0])

    matched, differences = analyzer._match_range(
        first, 0, 2, second, 0, 2, 0.0
    )

    assert matched == 1
    assert list(differences) == [0.0]


# ==================================================
# Timestamp series comparison
# ==================================================

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
    assert result["match_rate_second_percent"] == 100.0
    assert result["match_rate_sparser_percent"] == 100.0
    assert result["overlap_duration"] == 2.0
    assert result["mean_match_difference"] == 0.0
    assert result["max_match_difference"] == 0.0
    assert "no UTC" not in result["notes"]
    assert "Tolerance is applied in the selected time coordinate" in result["notes"]


def test_compare_timestamp_series_utc_has_no_axis_note():
    result = analyzer.compare_timestamp_series(
        [1.0],
        [1.0],
        0.0,
        "utc",
        "utc",
    )

    assert "selected time coordinate" not in result["notes"]


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
    assert "different observation counts" in result["notes"]


def test_compare_timestamp_series_counts_only_common_interval():
    result = analyzer.compare_timestamp_series(
        [0.0, 1.0, 2.0, 3.0, 10.0],
        [1.0, 2.0, 3.0, 4.0],
        0.0,
        "utc",
        "utc",
    )

    assert result["overlap_start"] == 1.0
    assert result["overlap_end"] == 4.0
    assert result["first_count"] == 3
    assert result["second_count"] == 4
    assert result["matched_timestamps"] == 3
    assert result["match_rate_first_percent"] == 100.0
    assert result["match_rate_second_percent"] == 75.0
    assert result["match_rate_sparser_percent"] == 100.0


def test_compare_timestamp_series_overlap_without_matches():
    result = analyzer.compare_timestamp_series(
        [1.0, 5.0],
        [3.0, 4.0],
        0.0,
        "utc",
        "utc",
    )

    assert result["comparison_status"] == "analysed"
    assert result["matched_timestamps"] == 0
    assert result["first_count"] == 0
    assert result["second_count"] == 2
    assert result["match_rate_first_percent"] == 0.0
    assert result["match_rate_sparser_percent"] == 0.0
    assert result["mean_match_difference"] == ""
    assert result["max_match_difference"] == ""


def test_compare_timestamp_series_second_empty_inside_overlap():
    result = analyzer.compare_timestamp_series(
        [3.0, 4.0],
        [1.0, 5.0],
        0.0,
        "utc",
        "utc",
    )

    assert result["first_count"] == 2
    assert result["second_count"] == 0
    assert result["match_rate_second_percent"] == 0.0


def test_compare_timestamp_series_reports_match_differences():
    result = analyzer.compare_timestamp_series(
        [1.0, 2.0, 3.0],
        [1.0, 2.25, 3.0],
        0.5,
        "utc",
        "utc",
    )

    assert result["matched_timestamps"] == 3
    assert result["mean_match_difference"] == 0.083333
    assert result["max_match_difference"] == 0.25


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


@pytest.mark.parametrize(
    ("first", "second"),
    [([], [1.0, 2.0]), ([1.0, 2.0], [])],
)
def test_compare_timestamp_series_detects_empty_series(first, second):
    result = analyzer.compare_timestamp_series(
        first,
        second,
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


def test_compare_sorted_series_accepts_arrays():
    result = analyzer._compare_sorted_series(
        array("d", [1.0, 2.0, 3.0]),
        array("d", [1.0, 2.0, 3.0]),
        0.0,
        "utc",
        "utc",
    )

    assert result["matched_timestamps"] == 3

    empty = analyzer._compare_sorted_series(
        array("d"),
        array("d", [1.0]),
        0.0,
        "utc",
        "utc",
    )

    assert empty["comparison_status"] == "empty_series"


def test_compare_timestamp_series_equals_sorted_fast_path():
    unsorted_first = [5.0, 1.0, 3.0, 3.0, 2.0]
    unsorted_second = [3.1, 1.1, 5.2, 2.0]

    public = analyzer.compare_timestamp_series(
        unsorted_first, unsorted_second, 0.5, "utc", "utc"
    )
    internal = analyzer._compare_sorted_series(
        sorted(unsorted_first),
        sorted(unsorted_second),
        0.5,
        "utc",
        "utc",
    )

    assert public == internal


# ==================================================
# Product pair comparison inside one Sol
# ==================================================

def series(product, timestamps, kind="utc", name=None):
    return {
        "product_code": product,
        "csv_file": name or f"{product}.csv",
        "timestamps": array("d", timestamps),
        "time_kind": kind,
    }


def test_compare_sol_products_builds_pair_reports():
    reports = analyzer._compare_sol_products(
        100,
        [
            series("ATS", [1, 2, 3]),
            series("PS", [1, 2, 3]),
            series("WS", [1, 2, 3], kind="lmst"),
        ],
        0.0,
    )

    assert [
        (r["product_1"], r["product_2"], r["comparison_status"])
        for r in reports
    ] == [
        ("ATS", "PS", "analysed"),
        ("ATS", "WS", "incompatible_time_axes"),
        ("PS", "WS", "incompatible_time_axes"),
    ]
    assert reports[0]["sol_number"] == 100
    assert reports[0]["file_1"] == "ATS.csv"
    assert reports[0]["file_2"] == "PS.csv"


def test_compare_sol_products_skips_unknown_and_identical_products():
    reports = analyzer._compare_sol_products(
        100,
        [
            series("", [1, 2]),
            series("ATS", [1, 2]),
            series("ats", [1, 2], name="other.csv"),
        ],
        0.0,
    )

    assert reports == []


def test_compare_sol_products_single_product_has_no_pairs():
    assert (
        analyzer._compare_sol_products(1, [series("A", [1.0])], 0.0) == []
    )


# ==================================================
# Full run_analysis integration (real meda_common)
# ==================================================

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


# ==================================================
# run_analysis / _process_csv_row branches (fake meda)
# ==================================================

class Workspace:
    """Small helper that builds an input tree, inventory and metadata."""

    def __init__(self, tmp_path):
        self.root = tmp_path / "input"
        self.root.mkdir()
        self.inventory = []
        self.metadata = []

    def add(
        self,
        sol,
        product,
        times,
        *,
        name=None,
        names=("TIME", "V"),
        with_metadata=True,
        sol_number=None,
        sol_folder=None,
        content=None,
    ):
        name = name or f"{product or 'NOPRODUCT'}_{sol}.csv"
        folder = f"SOL{sol}"
        relative = f"{folder}/{name}"

        text = content
        if text is None:
            text = "TIME,V\n" + "".join(f"{t},1\n" for t in times)

        write_text(self.root / relative, text)

        self.inventory.append({
            "filename": name,
            "sol_folder": folder if sol_folder is None else sol_folder,
            "sol_number": sol if sol_number is None else sol_number,
            "relative_path": relative,
            "extension": "csv",
            "product_code": product,
        })

        if with_metadata:
            self.metadata.append({
                "source_file": Path(name).with_suffix(".xml").name,
                "sol_folder": folder,
                "sol_number": sol,
                "relative_path": str(Path(relative).with_suffix(".xml")),
                "has_header": True,
                "parse_status": "parsed",
                "fields": fields_of(*names),
            })

    def run(self, tolerance=0.0):
        return analyzer.run_analysis(
            self.root,
            self.inventory,
            self.metadata,
            tolerance,
        )


def test_run_analysis_ignores_non_csv_inventory_entries(
    tmp_path,
    fake_meda,
):
    workspace = Workspace(tmp_path)
    workspace.inventory.append({"filename": "a.xml", "extension": "xml"})
    workspace.inventory.append({"filename": "b", "extension": None})

    assert workspace.run() == ([], [])


def test_run_analysis_reports_unresolved_file(tmp_path, fake_meda):
    workspace = Workspace(tmp_path)
    workspace.inventory.append(
        make_inventory_row(filename="ghost.csv", relative_path="x/ghost.csv")
    )

    file_reports, pair_reports = workspace.run()

    assert file_reports[0]["analysis_status"] == "file_not_found_or_ambiguous"
    assert pair_reports == []


def test_run_analysis_reports_missing_metadata(tmp_path, fake_meda):
    workspace = Workspace(tmp_path)
    workspace.add(100, "ATS", [1, 2], with_metadata=False)

    file_reports, _ = workspace.run()

    assert file_reports[0]["analysis_status"] == "metadata_not_found"
    assert "unique matching XML metadata" in file_reports[0]["notes"]


def test_run_analysis_deduplicates_same_physical_file(tmp_path, fake_meda):
    workspace = Workspace(tmp_path)
    workspace.add(100, "ATS", [1, 2, 3])
    workspace.inventory.append(dict(workspace.inventory[0]))

    file_reports, _ = workspace.run()

    assert len(file_reports) == 1


def test_run_analysis_reports_empty_file(tmp_path, fake_meda):
    workspace = Workspace(tmp_path)
    workspace.add(100, "ATS", [], content="")

    file_reports, _ = workspace.run()

    assert file_reports[0]["analysis_status"] == "empty_file"
    assert file_reports[0]["notes"] == "CSV file has zero bytes."


def test_run_analysis_reports_stat_error(tmp_path, fake_meda, monkeypatch):
    class UnreadablePath:
        name = "x.csv"

        def __str__(self):
            return "/virtual/x.csv"

        def stat(self):
            raise OSError("stat failed")

    monkeypatch.setattr(
        analyzer,
        "resolve_csv_path",
        lambda *args, **kwargs: UnreadablePath(),
    )

    workspace = Workspace(tmp_path)
    workspace.inventory.append(make_inventory_row())
    workspace.metadata.append(
        {**make_metadata_record(), "fields": fields_of("TIME", "V")}
    )

    file_reports, _ = workspace.run()

    assert file_reports[0]["analysis_status"] == "file_stat_error"
    assert file_reports[0]["notes"] == "stat failed"


def test_run_analysis_notes_metadata_matching_method(tmp_path, fake_meda):
    workspace = Workspace(tmp_path)
    workspace.add(100, "ATS", [1, 2, 3])

    # Force a non-"sol and name" match: keep only a record that
    # matches by unique stem.
    workspace.metadata[0]["sol_number"] = 999
    workspace.metadata[0]["sol_folder"] = "SOL999"
    workspace.metadata[0]["relative_path"] = "elsewhere/ATS_100.xml"

    file_reports, _ = workspace.run()

    assert file_reports[0]["analysis_status"] == "analysed"
    assert file_reports[0]["notes"].endswith(
        "Metadata matching method: matched_by_unique_stem."
    )


def test_run_analysis_metadata_note_without_previous_notes(
    tmp_path,
    fake_meda,
    monkeypatch,
):
    workspace = Workspace(tmp_path)
    workspace.add(100, "ATS", [1, 2, 3])
    workspace.metadata[0]["sol_number"] = 999
    workspace.metadata[0]["sol_folder"] = "SOL999"
    workspace.metadata[0]["relative_path"] = "elsewhere/ATS_100.xml"

    monkeypatch.setattr(
        analyzer,
        "analyse_timestamp_file",
        lambda *args: (
            {"analysis_status": "read_error", "notes": ""},
            [],
        ),
    )

    file_reports, _ = workspace.run()

    assert (
        file_reports[0]["notes"]
        == "Metadata matching method: matched_by_unique_stem."
    )


def test_run_analysis_excludes_files_without_sol_from_pairs(
    tmp_path,
    fake_meda,
):
    workspace = Workspace(tmp_path)
    workspace.add(100, "ATS", [1, 2, 3], sol_number="", sol_folder="unknown")
    workspace.add(100, "PS", [1, 2, 3])

    file_reports, pair_reports = workspace.run()

    assert pair_reports == []
    assert "Sol number could not be identified" in file_reports[0]["notes"]


def test_run_analysis_does_not_pair_unanalysed_files(tmp_path, fake_meda):
    workspace = Workspace(tmp_path)
    workspace.add(100, "ATS", [1, 2, 3])
    workspace.add(100, "PS", [], content="TIME,V\nnan,1\n")

    file_reports, pair_reports = workspace.run()

    assert [r["analysis_status"] for r in file_reports] == [
        "analysed",
        "no_parseable_timestamps",
    ]
    assert pair_reports == []


def test_run_analysis_orders_pairs_by_sol_for_interleaved_inventory(
    tmp_path,
    fake_meda,
):
    workspace = Workspace(tmp_path)

    # Sols are interleaved in the inventory.
    workspace.add(102, "ATS", [1, 2, 3])
    workspace.add(101, "ATS", [1, 2, 3])
    workspace.add(102, "PS", [1, 2, 3])
    workspace.add(101, "PS", [1, 2, 4])
    workspace.add(101, "WS", [1, 2, 3])

    _, pair_reports = workspace.run()

    assert [
        (r["sol_number"], r["product_1"], r["product_2"])
        for r in pair_reports
    ] == [
        (101, "ATS", "PS"),
        (101, "ATS", "WS"),
        (101, "PS", "WS"),
        (102, "ATS", "PS"),
    ]


def test_run_analysis_frees_series_after_each_sol(tmp_path, fake_meda):
    workspace = Workspace(tmp_path)
    workspace.add(100, "ATS", [1, 2, 3])
    workspace.add(100, "PS", [1, 2, 3])
    workspace.add(101, "ATS", [1, 2, 3])

    seen = []
    original = analyzer._compare_sol_products

    def spy(sol_number, products, tolerance):
        seen.append((sol_number, len(products)))
        return original(sol_number, products, tolerance)

    analyzer._compare_sol_products = spy
    try:
        workspace.run()
    finally:
        analyzer._compare_sol_products = original

    # Sol 100 compared once with both files; Sol 101 once alone.
    assert seen == [(100, 2), (101, 1)]


def test_run_analysis_skips_comparison_for_sol_without_series(
    tmp_path,
    fake_meda,
):
    workspace = Workspace(tmp_path)
    workspace.add(100, "ATS", [], content="")

    file_reports, pair_reports = workspace.run()

    assert file_reports[0]["analysis_status"] == "empty_file"
    assert pair_reports == []


def test_run_analysis_marks_incompatible_time_axes(tmp_path, fake_meda):
    workspace = Workspace(tmp_path)
    workspace.add(100, "ATS", [1, 2, 3])
    workspace.add(
        100,
        "PS",
        [],
        names=("LMSTF", "V"),
        content="LMSTF,V\n1,1\n2,1\n",
    )

    _, pair_reports = workspace.run()

    assert pair_reports[0]["comparison_status"] == "incompatible_time_axes"


def test_run_analysis_resolves_files_via_shared_index(tmp_path, fake_meda):
    workspace = Workspace(tmp_path)
    workspace.add(100, "ATS", [1, 2, 3])
    workspace.add(100, "PS", [1, 2, 3])

    # Break the relative paths so the fallback index is used.
    for row in workspace.inventory:
        row["relative_path"] = ""

    file_reports, pair_reports = workspace.run()

    assert [r["analysis_status"] for r in file_reports] == [
        "analysed",
        "analysed",
    ]
    assert pair_reports[0]["matched_timestamps"] == 3


# ==================================================
# Reports
# ==================================================

def test_write_csv_creates_parent_and_ignores_extra_keys(tmp_path):
    path = tmp_path / "nested" / "deeper" / "report.csv"

    analyzer.write_csv(
        path,
        [{"a": 1, "b": "x", "ignored": "nope"}, {"a": 2}],
        ["a", "b"],
    )

    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    assert rows == [{"a": "1", "b": "x"}, {"a": "2", "b": ""}]


def test_save_summary_writes_json_with_unicode(tmp_path):
    path = tmp_path / "nested" / "summary.json"

    analyzer.save_summary(path, {"name": "مريخ", "n": 1})

    text = path.read_text(encoding="utf-8")

    assert "مريخ" in text
    assert json.loads(text) == {"name": "مريخ", "n": 1}


# ==================================================
# SOL range summary
# ==================================================

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


def test_build_summary_full_dataset_counters():
    file_reports = [
        {
            "sol_number": 1,
            "analysis_status": "analysed",
            "notes": "Column mapping: header_exact_match. Other.",
        },
        {
            "sol_number": 2,
            "analysis_status": "analysed",
            "notes": "Column mapping: header_exact_match.",
        },
        {
            "sol_number": 3,
            "analysis_status": "analysed",
            "notes": "no mapping text here",
        },
        {
            "sol_number": 4,
            "analysis_status": "empty_file",
            "notes": "",
        },
    ]
    pair_reports = [
        {
            "sol_number": 1,
            "comparison_status": "analysed",
            "matched_timestamps": 0,
        },
    ]

    summary = analyzer.build_summary(file_reports, pair_reports, 0.5)

    assert summary["analyzer"] == "MEDA Synchronization Analyzer"
    assert summary["tolerance"] == 0.5
    assert summary["start_sol"] is None
    assert summary["end_sol"] is None
    assert summary["total_files"] == 4
    assert summary["analysed_files"] == 3
    assert summary["unanalysed_files"] == 1
    assert summary["file_status_counts"] == {
        "analysed": 3,
        "empty_file": 1,
    }
    assert summary["mapping_status_counts"] == {"header_exact_match": 2}
    assert summary["analysed_pairs"] == 1
    assert summary["pairs_with_matches"] == 0
    assert summary["pair_status_counts"] == {"analysed": 1}
    assert "generated_at_utc" in summary
    assert summary["important_limitations"]


def test_build_summary_range_ignores_rows_without_integer_sol():
    file_reports = [
        {"sol_number": None, "analysis_status": "analysed", "notes": ""},
        {"sol_number": True, "analysis_status": "analysed", "notes": ""},
        {"sol_number": "5", "analysis_status": "analysed", "notes": ""},
        {"sol_number": 5, "analysis_status": "analysed", "notes": ""},
    ]
    pair_reports = [
        {"sol_number": None, "comparison_status": "analysed",
         "matched_timestamps": 1},
        {"sol_number": 5, "comparison_status": "analysed",
         "matched_timestamps": 1},
    ]

    summary = analyzer.build_summary(
        file_reports,
        pair_reports,
        1.0,
        start_sol=0,
    )

    assert summary["total_files"] == 1
    assert summary["total_product_pairs"] == 1


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
        (100, 102.5),
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


# ==================================================
# CLI
# ==================================================

def test_parse_args_defaults(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog"])

    args = analyzer.parse_args()

    assert args.input == analyzer.DEFAULT_INPUT
    assert args.inventory == analyzer.DEFAULT_INVENTORY
    assert args.metadata == analyzer.DEFAULT_METADATA
    assert args.file_report == analyzer.DEFAULT_FILE_REPORT
    assert args.pair_report == analyzer.DEFAULT_PAIR_REPORT
    assert args.summary == analyzer.DEFAULT_SUMMARY
    assert args.tolerance == analyzer.DEFAULT_TOLERANCE
    assert args.time_axis == list(analyzer.DEFAULT_AXIS_PREFERENCE)


def test_parse_args_custom_values(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--input", "in",
            "--inventory", "inv.csv",
            "--metadata", "meta.json",
            "--file-report", "f.csv",
            "--pair-report", "p.csv",
            "--summary", "s.json",
            "--tolerance", "2.5",
            "--time-axis", "lmst", "utc",
        ],
    )

    args = analyzer.parse_args()

    assert args.input == Path("in")
    assert args.tolerance == 2.5
    assert args.time_axis == ["lmst", "utc"]


@pytest.mark.parametrize("tolerance", ["-1", "nan", "inf"])
def test_main_rejects_invalid_tolerance(monkeypatch, tolerance):
    monkeypatch.setattr(
        sys, "argv", ["prog", f"--tolerance={tolerance}"]
    )

    with pytest.raises(SystemExit, match="tolerance"):
        analyzer.main()


def test_main_runs_full_pipeline(tmp_path, monkeypatch, capsys, fake_meda):
    workspace = Workspace(tmp_path)
    workspace.add(100, "ATS", [1, 2, 3])
    workspace.add(100, "PS", [1, 2, 3])

    inventory_path = tmp_path / "inventory.csv"

    with inventory_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(workspace.inventory[0]),
        )
        writer.writeheader()
        writer.writerows(workspace.inventory)

    # A non-CSV row exercises the extension filter in main().
    with inventory_path.open("a", encoding="utf-8", newline="") as file:
        file.write("a.xml,SOL100,100,SOL100/a.xml,xml,ATS\n")

    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps({"records": workspace.metadata}),
        encoding="utf-8",
    )

    out = tmp_path / "out"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--input", str(workspace.root),
            "--inventory", str(inventory_path),
            "--metadata", str(metadata_path),
            "--file-report", str(out / "files.csv"),
            "--pair-report", str(out / "pairs.csv"),
            "--summary", str(out / "summary.json"),
            "--tolerance", "0",
            "--time-axis", "utc",
        ],
    )

    analyzer.main()

    printed = capsys.readouterr().out

    assert "Synchronization analysis completed." in printed
    assert "Analysed files: 2" in printed
    assert "Product pairs: 1" in printed

    with (out / "pairs.csv").open(encoding="utf-8-sig", newline="") as f:
        pair_rows = list(csv.DictReader(f))

    assert pair_rows[0]["matched_timestamps"] == "3"
    assert list(pair_rows[0]) == analyzer.PAIR_REPORT_COLUMNS

    with (out / "files.csv").open(encoding="utf-8-sig", newline="") as f:
        assert list(csv.DictReader(f).fieldnames) == (
            analyzer.FILE_REPORT_COLUMNS
        )

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))

    assert summary["analysed_files"] == 2
    assert summary["input_directory"] == str(workspace.root)
    assert summary["inventory_file"] == str(inventory_path)
    assert summary["metadata_file"] == str(metadata_path)
    assert summary["pair_report"] == str(out / "pairs.csv")


# ==================================================
# Import fallback and __main__ entry point
# ==================================================

def _drop_standalone_meda_common():
    sys.modules.pop("meda_common", None)


def test_module_falls_back_to_absolute_meda_common_import(monkeypatch):
    module_path = Path(analyzer.__file__)

    monkeypatch.syspath_prepend(str(module_path.parent))

    spec = importlib.util.spec_from_file_location(
        "synchronization_analyzer_standalone",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)
    finally:
        _drop_standalone_meda_common()

    assert callable(module.run_analysis)
    assert module.MISSING_TEXT is not None


def test_module_runs_main_when_executed_as_script(monkeypatch, tmp_path):
    module_path = Path(analyzer.__file__)

    monkeypatch.syspath_prepend(str(module_path.parent))
    monkeypatch.setattr(
        sys,
        "argv",
        ["prog", "--inventory", str(tmp_path / "missing_inventory.csv")],
    )

    try:
        with pytest.raises(FileNotFoundError, match="inventory"):
            runpy.run_path(str(module_path), run_name="__main__")
    finally:
        _drop_standalone_meda_common()