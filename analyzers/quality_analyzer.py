"""
MEDA Quality Analyzer

Purpose:
- Inspect metadata-defined quality/flag/status fields.
- Count missing and non-empty values.
- Count distinct values and report their most frequent occurrences.
- Check values against XML-declared valid_minimum / valid_maximum.
- Never assign scientific meanings to undocumented flags.

Inputs:
    input/...
    output/file_inventory.csv
    output/metadata_inventory.json

Outputs:
    output/quality_field_report.csv
    output/quality_summary.json

Uses Python standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional


DEFAULT_INPUT = Path("input")
DEFAULT_INVENTORY = Path("output/file_inventory.csv")
DEFAULT_METADATA = Path("output/metadata_inventory.json")
DEFAULT_OUTPUT = Path("output/quality_field_report.csv")
DEFAULT_SUMMARY = Path("output/quality_summary.json")

QUALITY_KEYWORDS = (
    "quality",
    "qual",
    "flag",
    "status",
    "validity",
    "valid_flag",
    "data_state",
)

MISSING_TEXT = {
    "",
    "na",
    "n/a",
    "nan",
    "null",
    "none",
    "missing",
}


def normalise_name(value: Any) -> str:
    """Normalise a field or filename for matching."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def safe_float(value: Any) -> Optional[float]:
    """Convert a value to float when possible."""
    if value is None:
        return None

    text = str(value).strip()
    if not text or text.lower() in MISSING_TEXT:
        return None

    try:
        number = float(text)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError):
        pass

    return None


def is_missing(value: Any) -> bool:
    """Identify empty or conventional textual missing values."""
    if value is None:
        return True

    return str(value).strip().lower() in MISSING_TEXT


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_inventory(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Inventory file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def metadata_records(data: Any) -> list[dict]:
    """
    Accept the metadata JSON structure produced by xml_parser.py.
    Supports either a list or a dictionary containing a records list.
    """
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        for key in ("records", "products", "metadata", "files"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    raise ValueError(
        "Unsupported metadata JSON structure. "
        "Expected a list of XML records or a dictionary containing a records list."
    )


def build_metadata_index(records: list[dict]) -> dict[str, dict]:
    index = {}

    for record in records:
        source_file = record.get("source_file")
        if source_file:
            index[normalise_name(Path(source_file).stem)] = record

    return index


def get_field_list(record: dict) -> list[dict]:
    fields = record.get("fields", [])

    if not isinstance(fields, list):
        return []

    return [field for field in fields if isinstance(field, dict)]


def field_is_quality_related(field: dict) -> bool:
    """Use metadata wording only; do not infer flag meanings."""
    searchable = " ".join(
        str(field.get(key, ""))
        for key in ("name", "description", "unit")
    ).lower()

    return any(keyword in searchable for keyword in QUALITY_KEYWORDS)


def get_field_bounds(field: dict) -> tuple[Optional[float], Optional[float]]:
    minimum = safe_float(field.get("valid_minimum"))
    maximum = safe_float(field.get("valid_maximum"))
    return minimum, maximum


def get_quality_fields(record: dict) -> list[dict]:
    """
    Select metadata fields that appear quality-related.

    Fields with declared numeric limits are also included so that
    documented range checks can be reported separately.
    """
    selected = []

    for field in get_field_list(record):
        minimum, maximum = get_field_bounds(field)

        if field_is_quality_related(field) or (
            minimum is not None or maximum is not None
        ):
            selected.append(field)

    return selected


def find_csv_path(input_root: Path, inventory_row: dict) -> Optional[Path]:
    """
    Resolve the CSV path using the inventory's Sol folder and filename.
    """
    filename = (inventory_row.get("filename") or "").strip()
    sol_folder = (inventory_row.get("sol_folder") or "").strip()

    if not filename:
        return None

    candidates = []

    if sol_folder:
        candidates.append(input_root / sol_folder / filename)

    candidates.append(input_root / filename)

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    # Fallback: search by filename in the input tree.
    matches = list(input_root.rglob(filename))
    return matches[0] if len(matches) == 1 else None


def match_metadata_field(
    metadata_fields: list[dict],
    csv_column: str,
) -> Optional[dict]:
    target = normalise_name(csv_column)

    for field in metadata_fields:
        field_name = field.get("name")

        if field_name and normalise_name(field_name) == target:
            return field

    return None


def analyse_column(
    csv_path: Path,
    column_name: str,
    metadata_field: dict,
    sol_number: str,
    product_code: str,
) -> dict:
    """
    Analyse one CSV column in a streaming manner.
    No full-column list is stored in memory.
    """
    total_rows = 0
    missing_count = 0
    non_empty_count = 0
    numeric_count = 0
    non_numeric_count = 0
    below_minimum = 0
    above_maximum = 0

    value_counts = Counter()

    minimum, maximum = get_field_bounds(metadata_field)

    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
        errors="replace",
    ) as handle:
        reader = csv.DictReader(handle)

        if not reader.fieldnames:
            return {
                "sol_number": sol_number,
                "product_code": product_code,
                "csv_file": csv_path.name,
                "field_name": column_name,
                "metadata_description": metadata_field.get("description", ""),
                "analysis_status": "no_header",
                "total_rows": 0,
                "missing_count": 0,
                "non_empty_count": 0,
                "numeric_count": 0,
                "non_numeric_count": 0,
                "distinct_values": 0,
                "below_valid_minimum": 0,
                "above_valid_maximum": 0,
                "valid_minimum": minimum,
                "valid_maximum": maximum,
                "top_values_json": "{}",
                "notes": "CSV header could not be read.",
            }

        if column_name not in reader.fieldnames:
            return {
                "sol_number": sol_number,
                "product_code": product_code,
                "csv_file": csv_path.name,
                "field_name": column_name,
                "metadata_description": metadata_field.get("description", ""),
                "analysis_status": "column_not_found",
                "total_rows": 0,
                "missing_count": 0,
                "non_empty_count": 0,
                "numeric_count": 0,
                "non_numeric_count": 0,
                "distinct_values": 0,
                "below_valid_minimum": 0,
                "above_valid_maximum": 0,
                "valid_minimum": minimum,
                "valid_maximum": maximum,
                "top_values_json": "{}",
                "notes": "Metadata field was not found in the CSV header.",
            }

        for row in reader:
            total_rows += 1
            value = row.get(column_name)

            if is_missing(value):
                missing_count += 1
                continue

            non_empty_count += 1
            text_value = str(value).strip()

            # Keep exact text values; do not interpret flag codes.
            value_counts[text_value] += 1

            number = safe_float(text_value)

            if number is None:
                non_numeric_count += 1
                continue

            numeric_count += 1

            if minimum is not None and number < minimum:
                below_minimum += 1

            if maximum is not None and number > maximum:
                above_maximum += 1

    top_values = dict(value_counts.most_common(20))

    notes = []
    if field_is_quality_related(metadata_field):
        notes.append("Metadata wording identifies this as a possible quality-related field.")

    if minimum is not None or maximum is not None:
        notes.append("Range checks use XML-declared limits only.")

    if not notes:
        notes.append("Included because XML metadata declares numeric limits.")

    return {
        "sol_number": sol_number,
        "product_code": product_code,
        "csv_file": csv_path.name,
        "field_name": column_name,
        "metadata_description": metadata_field.get("description", ""),
        "analysis_status": "analysed",
        "total_rows": total_rows,
        "missing_count": missing_count,
        "non_empty_count": non_empty_count,
        "numeric_count": numeric_count,
        "non_numeric_count": non_numeric_count,
        "distinct_values": len(value_counts),
        "below_valid_minimum": below_minimum,
        "above_valid_maximum": above_maximum,
        "valid_minimum": minimum,
        "valid_maximum": maximum,
        "top_values_json": json.dumps(
            top_values,
            ensure_ascii=False,
        ),
        "notes": " ".join(notes),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    columns = [
        "sol_number",
        "product_code",
        "csv_file",
        "field_name",
        "metadata_description",
        "analysis_status",
        "total_rows",
        "missing_count",
        "non_empty_count",
        "numeric_count",
        "non_numeric_count",
        "distinct_values",
        "below_valid_minimum",
        "above_valid_maximum",
        "valid_minimum",
        "valid_maximum",
        "top_values_json",
        "notes",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def build_summary(rows: list[dict]) -> dict:
    analysed = [
        row for row in rows
        if row.get("analysis_status") == "analysed"
    ]

    return {
        "analyzer": "MEDA Quality Analyzer",
        "total_field_reports": len(rows),
        "analysed_fields": len(analysed),
        "not_analysed_fields": len(rows) - len(analysed),
        "total_rows_examined": sum(
            row.get("total_rows", 0) for row in analysed
        ),
        "total_missing_values": sum(
            row.get("missing_count", 0) for row in analysed
        ),
        "total_below_declared_minimum": sum(
            row.get("below_valid_minimum", 0) for row in analysed
        ),
        "total_above_declared_maximum": sum(
            row.get("above_valid_maximum", 0) for row in analysed
        ),
        "important_limitations": [
            "Quality flag values are reported as observed; their meanings are not interpreted.",
            "A value outside XML-declared limits is flagged for review, not automatically declared scientifically invalid.",
            "Special constants are not interpreted or removed automatically.",
            "Only fields identified from XML metadata are analysed.",
            "This report does not establish overall scientific suitability of a Sol or period.",
        ],
    }


def run(args: argparse.Namespace) -> None:
    input_root = Path(args.input)
    inventory_path = Path(args.inventory)
    metadata_path = Path(args.metadata)
    output_path = Path(args.output)
    summary_path = Path(args.summary)

    print("Loading file inventory...")
    inventory = load_inventory(inventory_path)

    print("Loading XML metadata...")
    metadata_data = load_json(metadata_path)
    records = metadata_records(metadata_data)
    metadata_index = build_metadata_index(records)

    report_rows = []
    processed_files = set()

    csv_inventory = [
        row for row in inventory
        if (row.get("extension") or "").lower().lstrip(".") == "csv"
    ]

    print(f"CSV inventory entries: {len(csv_inventory)}")

    for index, item in enumerate(csv_inventory, start=1):
        csv_path = find_csv_path(input_root, item)

        if csv_path is None:
            continue

        resolved_path = str(csv_path.resolve())

        if resolved_path in processed_files:
            continue

        processed_files.add(resolved_path)

        metadata_record = metadata_index.get(
            normalise_name(csv_path.stem)
        )

        if not metadata_record:
            continue

        fields = get_quality_fields(metadata_record)

        if not fields:
            continue

        sol_number = item.get("sol_number", "")
        product_code = item.get("product_code", "")

        print(
            f"[{index}/{len(csv_inventory)}] "
            f"Analysing {csv_path.name} "
            f"({len(fields)} metadata fields)"
        )

        for metadata_field in fields:
            field_name = metadata_field.get("name")

            if not field_name:
                continue

            result = analyse_column(
                csv_path=csv_path,
                column_name=str(field_name),
                metadata_field=metadata_field,
                sol_number=sol_number,
                product_code=product_code,
            )
            report_rows.append(result)

    write_csv(output_path, report_rows)

    summary = build_summary(report_rows)
    summary["input_directory"] = str(input_root)
    summary["inventory_file"] = str(inventory_path)
    summary["metadata_file"] = str(metadata_path)
    summary["report_file"] = str(output_path)

    summary_path.parent.mkdir(parents=True, exist_ok=True)

    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)

    print("\nQuality analysis completed.")
    print(f"Field reports: {len(report_rows)}")
    print(f"CSV report: {output_path}")
    print(f"JSON summary: {summary_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyse MEDA quality-related fields using XML metadata."
    )

    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))

    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())