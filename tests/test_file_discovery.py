import csv
import os
from pathlib import Path

import pytest

from backend.analyzers.file_discovery import (
    OUTPUT_COLUMNS,
    SUPPORTED_EXTENSIONS,
    discover_files,
    get_filename_sol,
    get_product_code,
    get_sol_number,
    write_inventory,
)


def make_meda_stem(
    sol: int = 100,
    product: str = "ATS",
    suffix: str = "P01",
) -> str:
    return (
        f"WE__{sol:04d}___________"
        f"CAL_{product}_________________{suffix}"
    )


def create_file(
    path: Path,
    content: str = "time,value\n1,2\n",
) -> Path:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        content,
        encoding="utf-8",
    )

    return path


def find_record(
    records: list[dict],
    relative_path: str,
) -> dict:
    return next(
        record
        for record in records
        if record["relative_path"] == relative_path
    )


# ---------------------------------------------------------------------
# Filename and folder parsing
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    ("folder_name", "expected"),
    [
        ("SOL100", 100),
        ("SOL_0100", 100),
        ("SOL-100", 100),
        ("sol100", 100),
        ("SOL000", 0),
        ("DATA100", None),
        ("SOL", None),
        ("SOL_ABC", None),
        ("", None),
        (None, None),
        (100, None),
    ],
)
def test_get_sol_number(folder_name, expected):
    assert get_sol_number(folder_name) == expected


def test_get_filename_sol():
    filename = make_meda_stem() + ".CSV"

    assert get_filename_sol(filename) == 100


@pytest.mark.parametrize(
    "filename",
    [
        "WE__0100___________CAL_ATS_________________P01.CSV",
        "we__0100___________cal_ats_________________p01.csv",
    ],
)
def test_get_filename_sol_is_case_insensitive(filename):
    assert get_filename_sol(filename) == 100


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        (
            "WE__0100___________CAL_ATS_________________P01.CSV",
            100,
        ),
        (
            "WE__0007___________CAL_WS_________________P01.XML",
            7,
        ),
        (
            "INVALID_FILENAME.CSV",
            None,
        ),
        (
            "WE__ABC__CAL_ATS.CSV",
            None,
        ),
        (
            "",
            None,
        ),
        (
            None,
            None,
        ),
    ],
)
def test_get_filename_sol_values(filename, expected):
    assert get_filename_sol(filename) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("WE__0100___________CAL_ATS_________________P01.CSV", "ATS"),
        ("WE__0100___________CAL_PS_________________P01.CSV", "PS"),
        ("WE__0100___________CAL_RHS_________________P01.XML", "RHS"),
        ("we__0100___________cal_ws_________________p01.csv", "WS"),
        ("INVALID_FILENAME.CSV", None),
        ("", None),
        (None, None),
    ],
)
def test_get_product_code(filename, expected):
    assert get_product_code(filename) == expected


def test_supported_extensions_are_csv_and_xml():
    assert SUPPORTED_EXTENSIONS == {
        ".csv",
        ".xml",
    }


# ---------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------

def test_discover_files_rejects_missing_input_directory(tmp_path):
    missing = tmp_path / "missing"

    with pytest.raises(FileNotFoundError):
        discover_files(missing)


def test_discover_files_rejects_file_as_input(tmp_path):
    input_file = tmp_path / "input.txt"
    input_file.write_text(
        "not a directory",
        encoding="utf-8",
    )

    with pytest.raises(NotADirectoryError):
        discover_files(input_file)


def test_discover_files_accepts_string_path(tmp_path):
    input_root = tmp_path / "dataset"
    input_root.mkdir()

    records = discover_files(str(input_root))

    assert records == []


def test_discover_files_returns_empty_list_without_sol_folders(tmp_path):
    create_file(
        tmp_path / "unrelated" / "file.csv",
    )

    records = discover_files(tmp_path)

    assert records == []


# ---------------------------------------------------------------------
# Sol folder and file discovery
# ---------------------------------------------------------------------

def test_recursive_discovery_and_pairing(tmp_path):
    root = tmp_path / "dataset"

    stem = make_meda_stem()

    csv_path = create_file(
        root / "SOL100" / "nested" / f"{stem}.CSV",
    )

    xml_path = create_file(
        root / "SOL100" / "nested" / f"{stem}.XML",
        "<Product></Product>",
    )

    records = discover_files(root)

    assert len(records) == 2

    csv_record = find_record(
        records,
        csv_path.relative_to(root).as_posix(),
    )

    xml_record = find_record(
        records,
        xml_path.relative_to(root).as_posix(),
    )

    assert csv_record["sol_folder"] == "SOL100"
    assert csv_record["sol_number"] == 100
    assert csv_record["extension"] == ".csv"
    assert csv_record["product_code"] == "ATS"
    assert csv_record["file_status"] == "available"
    assert csv_record["pair_status"] == "matched"
    assert csv_record["matching_file"] == xml_path.name
    assert csv_record["matching_relative_path"] == (
        xml_path.relative_to(root).as_posix()
    )

    assert xml_record["pair_status"] == "matched"
    assert xml_record["matching_file"] == csv_path.name


def test_discovery_supports_multiple_sol_folder_formats(tmp_path):
    root = tmp_path / "dataset"

    create_file(
        root / "SOL100" / f"{make_meda_stem(100)}.CSV",
    )

    create_file(
        root / "SOL_0101" / f"{make_meda_stem(101)}.CSV",
    )

    create_file(
        root / "SOL-102" / f"{make_meda_stem(102)}.CSV",
    )

    records = discover_files(root)

    assert len(records) == 3

    assert {
        record["sol_number"]
        for record in records
    } == {100, 101, 102}


def test_nested_sol_folder_owns_its_files(tmp_path):
    root = tmp_path / "dataset"

    outer_file = create_file(
        root / "SOL100" / f"{make_meda_stem(100)}.CSV",
    )

    nested_file = create_file(
        root / "SOL100" / "SOL101" / f"{make_meda_stem(101)}.CSV",
    )

    records = discover_files(root)

    paths = {
        record["relative_path"]
        for record in records
    }

    assert paths == {
        outer_file.relative_to(root).as_posix(),
        nested_file.relative_to(root).as_posix(),
    }

    outer_record = find_record(
        records,
        outer_file.relative_to(root).as_posix(),
    )

    nested_record = find_record(
        records,
        nested_file.relative_to(root).as_posix(),
    )

    assert outer_record["sol_number"] == 100
    assert nested_record["sol_number"] == 101


def test_discovery_ignores_files_outside_sol_folders(tmp_path):
    root = tmp_path / "dataset"

    outside_file = create_file(
        root / "other" / "file.csv",
    )

    inside_file = create_file(
        root / "SOL100" / f"{make_meda_stem()}.CSV",
    )

    records = discover_files(root)

    assert len(records) == 1
    assert records[0]["filename"] == inside_file.name
    assert records[0]["filename"] != outside_file.name


# ---------------------------------------------------------------------
# CSV/XML pairing
# ---------------------------------------------------------------------

def test_same_stem_in_different_subfolders_does_not_pair(tmp_path):
    root = tmp_path / "dataset"
    stem = make_meda_stem()

    csv_path = create_file(
        root / "SOL100" / "A" / f"{stem}.CSV",
    )

    xml_path = create_file(
        root / "SOL100" / "B" / f"{stem}.XML",
        "<Product></Product>",
    )

    records = discover_files(root)

    csv_record = find_record(
        records,
        csv_path.relative_to(root).as_posix(),
    )

    xml_record = find_record(
        records,
        xml_path.relative_to(root).as_posix(),
    )

    assert csv_record["pair_status"] == "missing_xml"
    assert xml_record["pair_status"] == "missing_csv"

    assert csv_record["matching_file"] == ""
    assert xml_record["matching_file"] == ""


def test_pairing_is_case_insensitive_for_stem_and_extension(tmp_path):
    root = tmp_path / "dataset"
    stem = make_meda_stem()

    csv_path = create_file(
        root / "SOL100" / f"{stem}.CSV",
    )

    xml_path = create_file(
        root / "SOL100" / f"{stem.lower()}.xml",
        "<Product></Product>",
    )

    records = discover_files(root)

    csv_record = find_record(
        records,
        csv_path.relative_to(root).as_posix(),
    )

    xml_record = find_record(
        records,
        xml_path.relative_to(root).as_posix(),
    )

    assert csv_record["pair_status"] == "matched"
    assert csv_record["matching_file"] == xml_path.name

    assert xml_record["pair_status"] == "matched"
    assert xml_record["matching_file"] == csv_path.name


def test_missing_counterpart_is_reported(tmp_path):
    root = tmp_path / "dataset"

    csv_path = create_file(
        root / "SOL100" / f"{make_meda_stem()}.CSV",
    )

    records = discover_files(root)

    record = find_record(
        records,
        csv_path.relative_to(root).as_posix(),
    )

    assert record["pair_status"] == "missing_xml"
    assert "missing_xml" in record["issues"].split(";")


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows default filesystems are case-insensitive; .xml and .XML cannot coexist.",
)
def test_multiple_counterpart_files_are_reported(tmp_path):
    root = tmp_path / "dataset"
    stem = make_meda_stem()

    csv_path = create_file(
        root / "SOL100" / f"{stem}.CSV",
    )

    create_file(
        root / "SOL100" / f"{stem}.xml",
        "<Product></Product>",
    )

    create_file(
        root / "SOL100" / f"{stem}.XML",
        "<Product></Product>",
    )

    records = discover_files(root)

    csv_record = find_record(
        records,
        csv_path.relative_to(root).as_posix(),
    )

    assert csv_record["pair_status"] == "multiple_matching_files"
    assert (
        "multiple_counterpart_files"
        in csv_record["issues"].split(";")
    )


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows default filesystems are case-insensitive; .CSV and .csv cannot coexist.",
)
def test_duplicate_same_type_files_are_reported(tmp_path):
    root = tmp_path / "dataset"
    stem = make_meda_stem()

    first = create_file(
        root / "SOL100" / f"{stem}.CSV",
    )

    second = create_file(
        root / "SOL100" / f"{stem}.csv",
    )

    xml_path = create_file(
        root / "SOL100" / f"{stem}.XML",
        "<Product></Product>",
    )

    records = discover_files(root)

    first_record = find_record(
        records,
        first.relative_to(root).as_posix(),
    )

    second_record = find_record(
        records,
        second.relative_to(root).as_posix(),
    )

    xml_record = find_record(
        records,
        xml_path.relative_to(root).as_posix(),
    )

    assert (
        "duplicate_filename_case_variant"
        in first_record["issues"].split(";")
    )

    assert (
        "duplicate_filename_case_variant"
        in second_record["issues"].split(";")
    )

    assert xml_record["pair_status"] == "multiple_matching_files"


# ---------------------------------------------------------------------
# File status and inventory diagnostics
# ---------------------------------------------------------------------

def test_empty_file_detection(tmp_path):
    root = tmp_path / "dataset"

    file_path = create_file(
        root / "SOL100" / f"{make_meda_stem()}.CSV",
        "",
    )

    records = discover_files(root)

    record = find_record(
        records,
        file_path.relative_to(root).as_posix(),
    )

    assert record["file_status"] == "empty"
    assert record["is_empty"] is True
    assert record["file_size_bytes"] == 0
    assert "empty_file" in record["issues"].split(";")


def test_non_empty_file_detection(tmp_path):
    root = tmp_path / "dataset"

    file_path = create_file(
        root / "SOL100" / f"{make_meda_stem()}.CSV",
        "time,value\n1,2\n",
    )

    records = discover_files(root)

    record = find_record(
        records,
        file_path.relative_to(root).as_posix(),
    )

    assert record["file_status"] == "available"
    assert record["is_empty"] is False
    assert record["file_size_bytes"] > 0
    assert "empty_file" not in record["issues"].split(";")


def test_filename_sol_mismatch_is_reported(tmp_path):
    root = tmp_path / "dataset"

    file_path = create_file(
        root / "SOL100" / f"{make_meda_stem(101)}.CSV",
    )

    records = discover_files(root)

    record = find_record(
        records,
        file_path.relative_to(root).as_posix(),
    )

    assert record["sol_number"] == 100
    assert "sol_number_mismatch" in record["issues"].split(";")


def test_missing_filename_sol_is_reported(tmp_path):
    root = tmp_path / "dataset"

    file_path = create_file(
        root / "SOL100" / "invalid_filename.CSV",
    )

    records = discover_files(root)

    record = find_record(
        records,
        file_path.relative_to(root).as_posix(),
    )

    assert (
        "sol_number_not_detected_in_filename"
        in record["issues"].split(";")
    )


def test_missing_product_code_is_reported(tmp_path):
    root = tmp_path / "dataset"

    file_path = create_file(
        root / "SOL100" / "WE__0100__UNKNOWN.CSV",
    )

    records = discover_files(root)

    record = find_record(
        records,
        file_path.relative_to(root).as_posix(),
    )

    assert record["product_code"] == ""
    assert (
        "product_code_not_detected"
        in record["issues"].split(";")
    )


def test_unsupported_file_is_retained_in_inventory(tmp_path):
    root = tmp_path / "dataset"

    file_path = create_file(
        root / "SOL100" / "notes.txt",
        "not a MEDA product",
    )

    records = discover_files(root)

    assert len(records) == 1

    record = find_record(
        records,
        file_path.relative_to(root).as_posix(),
    )

    assert record["extension"] == ".txt"
    assert record["pair_status"] == "not_applicable"

    assert (
        "unsupported_file_type"
        in record["issues"].split(";")
    )


def test_multiple_files_for_product_and_type_are_reported(tmp_path):
    root = tmp_path / "dataset"

    first = create_file(
        root / "SOL100" / "A" / f"{make_meda_stem()}.CSV",
    )

    second = create_file(
        root / "SOL100" / "B" / f"{make_meda_stem()}.CSV",
    )

    records = discover_files(root)

    first_record = find_record(
        records,
        first.relative_to(root).as_posix(),
    )

    second_record = find_record(
        records,
        second.relative_to(root).as_posix(),
    )

    assert (
        "multiple_files_for_product_and_type"
        in first_record["issues"].split(";")
    )

    assert (
        "multiple_files_for_product_and_type"
        in second_record["issues"].split(";")
    )


# ---------------------------------------------------------------------
# Deterministic ordering and record schema
# ---------------------------------------------------------------------

def test_discovery_order_is_deterministic(tmp_path):
    root = tmp_path / "dataset"

    create_file(
        root / "SOL100" / "z_folder" / "z_file.txt",
    )

    create_file(
        root / "SOL100" / "A_folder" / "a_file.txt",
    )

    create_file(
        root / "SOL101" / "b_file.txt",
    )

    first_result = discover_files(root)
    second_result = discover_files(root)

    first_paths = [
        record["relative_path"]
        for record in first_result
    ]

    second_paths = [
        record["relative_path"]
        for record in second_result
    ]

    assert first_paths == second_paths
    assert first_paths == sorted(
        first_paths,
        key=lambda value: (value.casefold(), value),
    )


def test_inventory_record_contains_expected_columns(tmp_path):
    root = tmp_path / "dataset"

    create_file(
        root / "SOL100" / f"{make_meda_stem()}.CSV",
    )

    records = discover_files(root)

    assert len(records) == 1
    assert list(records[0].keys()) == OUTPUT_COLUMNS


# ---------------------------------------------------------------------
# Inventory writer
# ---------------------------------------------------------------------

def test_write_inventory_creates_parent_directory(tmp_path):
    output_file = (
        tmp_path
        / "run_001"
        / "output"
        / "file_inventory.csv"
    )

    records = [
        {
            "sol_folder": "SOL100",
            "sol_number": 100,
            "filename": "example.csv",
            "relative_path": "SOL100/example.csv",
            "extension": ".csv",
            "product_code": "ATS",
            "file_size_bytes": 10,
            "file_status": "available",
            "is_empty": False,
            "matching_file": "",
            "matching_relative_path": "",
            "pair_status": "missing_xml",
            "issues": "missing_xml",
        }
    ]

    write_inventory(records, output_file)

    assert output_file.is_file()


def test_write_inventory_preserves_output_schema(tmp_path):
    output_file = tmp_path / "inventory.csv"

    records = [
        {
            "sol_folder": "SOL100",
            "sol_number": 100,
            "filename": "example.csv",
            "relative_path": "SOL100/example.csv",
            "extension": ".csv",
            "product_code": "ATS",
            "file_size_bytes": 10,
            "file_status": "available",
            "is_empty": False,
            "matching_file": "",
            "matching_relative_path": "",
            "pair_status": "missing_xml",
            "issues": "missing_xml",
            "unexpected_internal_value": "ignored",
        }
    ]

    write_inventory(records, output_file)

    with output_file.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as handle:
        reader = csv.DictReader(handle)

        assert reader.fieldnames == OUTPUT_COLUMNS

        rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["sol_folder"] == "SOL100"
    assert rows[0]["sol_number"] == "100"
    assert rows[0]["product_code"] == "ATS"
    assert "unexpected_internal_value" not in rows[0]


def test_write_inventory_supports_empty_records(tmp_path):
    output_file = tmp_path / "empty_inventory.csv"

    write_inventory([], output_file)

    with output_file.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as handle:
        reader = csv.reader(handle)
        rows = list(reader)

    assert rows == [OUTPUT_COLUMNS]


def test_write_inventory_uses_explicit_output_path(tmp_path):
    first_output = tmp_path / "run_001" / "inventory.csv"
    second_output = tmp_path / "run_002" / "inventory.csv"

    write_inventory([], first_output)
    write_inventory([], second_output)

    assert first_output.is_file()
    assert second_output.is_file()
    assert first_output != second_output