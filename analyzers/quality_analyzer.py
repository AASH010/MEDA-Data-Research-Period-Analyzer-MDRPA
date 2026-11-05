
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from .meda_common import MISSING_TEXT, norm, ordered_fields
except ImportError:
    from meda_common import MISSING_TEXT, norm, ordered_fields


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
    "confidence",
    "data_state",
)

TOP_VALUE_LIMIT = 20
VALUE_TRACKING_LIMIT = 5000

SOL_PATTERN = re.compile(r"^sol[_-]?0*(\d+)$", re.IGNORECASE)


REPORT_COLUMNS = [
    "sol_number",
    "sol_folder",
    "product_code",
    "csv_file",
    "field_name",
    "field_type",
    "metadata_description",
    "analysis_status",
    "total_rows",
    "missing_count",
    "non_empty_count",
    "numeric_count",
    "non_numeric_count",
    "distinct_values_lower_bound",
    "distinct_count_capped",
    "below_valid_minimum",
    "above_valid_maximum",
    "valid_minimum",
    "valid_maximum",
    "top_values_json",
    "notes",
]


# --------------------------------------------------
# Basic helpers
# --------------------------------------------------

def normalize_name(value: Any) -> str:
    return norm(value)


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    text = str(value).strip()

    if not text or text.casefold() in MISSING_TEXT:
        return None

    try:
        number = float(text)
    except (TypeError, ValueError, OverflowError):
        return None

    return number if math.isfinite(number) else None


def is_missing(value: Any) -> bool:
    if value is None:
        return True

    return str(value).strip().casefold() in MISSING_TEXT


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_sol_number(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        pass

    match = SOL_PATTERN.match(str(value))

    return int(match.group(1)) if match else None


def get_product_code(filename: str) -> str:
    match = re.search(
        r"(?:^|_)CAL_([A-Z0-9]+)(?:_|\.|$)",
        filename,
        re.IGNORECASE,
    )

    return match.group(1).upper() if match else ""


# --------------------------------------------------
# Bounded frequency tracking
# --------------------------------------------------

class BoundedValueCounter:
    """
    Space-Saving frequency tracker.

    Memory usage is bounded by VALUE_TRACKING_LIMIT.
    Counts are approximate when the limit is reached.
    """

    def __init__(self, capacity: int = VALUE_TRACKING_LIMIT):
        self.capacity = capacity
        self.counts: dict[str, int] = {}
        self.total_distinct_seen = 0
        self.seen_values: set[str] = set()
        self.distinct_tracking_capped = False

    def add(self, value: str) -> None:
        if value not in self.seen_values:
            if len(self.seen_values) < self.capacity:
                self.seen_values.add(value)
                self.total_distinct_seen += 1
            else:
                self.distinct_tracking_capped = True

        if value in self.counts:
            self.counts[value] += 1
            return

        if len(self.counts) < self.capacity:
            self.counts[value] = 1
            return

        least_common = min(
            self.counts,
            key=self.counts.get,
        )

        minimum_count = self.counts.pop(least_common)

        self.counts[value] = minimum_count + 1

    def top_values(self, limit: int = TOP_VALUE_LIMIT) -> dict:
        return dict(
            sorted(
                self.counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:limit]
        )

    def distinct_lower_bound(self) -> int:
        return len(self.seen_values)


# --------------------------------------------------
# Input loading
# --------------------------------------------------

def load_inventory(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"File inventory not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        return list(csv.DictReader(file))


def load_metadata(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Metadata inventory not found: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list):
        return {"records": data}

    if not isinstance(data, dict):
        raise ValueError(
            "Metadata inventory must be a JSON object or a list."
        )

    records = data.get("records")

    if not isinstance(records, list):
        raise ValueError(
            "Metadata inventory must contain a records list."
        )

    return data


# --------------------------------------------------
# Metadata indexing
# --------------------------------------------------

def metadata_sol(record: dict) -> str:
    sol = record.get("sol_folder")

    if sol:
        return str(sol).casefold()

    sol_number = record.get("sol_number")

    if sol_number is not None:
        return f"sol{sol_number}".casefold()

    return ""


def build_metadata_index(metadata: dict) -> dict:
    """
    Build indexes without silently overwriting duplicate metadata.

    Keys:
        (Sol folder, XML filename)
        relative XML path
        unique XML stem fallback
    """

    by_sol_name = defaultdict(list)
    by_path = defaultdict(list)
    by_stem = defaultdict(list)

    for record in metadata.get("records", []):

        if not isinstance(record, dict):
            continue

        source_file = str(
            record.get("source_file") or ""
        )

        if not source_file:
            continue

        sol = metadata_sol(record)
        source_name = Path(source_file).name.casefold()
        stem = Path(source_file).stem.casefold()

        if sol:
            by_sol_name[(sol, source_name)].append(record)

        by_stem[stem].append(record)

        relative_path = record.get("relative_path")

        if relative_path:
            normalized_path = (
                str(relative_path)
                .replace("\\", "/")
                .casefold()
            )

            by_path[normalized_path].append(record)

    return {
        "by_sol_name": by_sol_name,
        "by_path": by_path,
        "by_stem": by_stem,
    }


def find_metadata_record(
    inventory_row: dict,
    index: dict,
) -> tuple[dict | None, str]:

    filename = str(
        inventory_row.get("filename") or ""
    )

    if not filename:
        return None, "missing_inventory_filename"

    xml_name = Path(filename).stem + ".xml"

    sol_folder = str(
        inventory_row.get("sol_folder") or ""
    ).casefold()

    if sol_folder:
        matches = index["by_sol_name"].get(
            (sol_folder, xml_name.casefold()),
            [],
        )

        if len(matches) == 1:
            return matches[0], "matched_by_sol_and_name"

        if len(matches) > 1:
            return None, "ambiguous_metadata_match"

    relative_path = inventory_row.get("relative_path")

    if relative_path:
        xml_relative = (
            str(Path(str(relative_path)).with_suffix(".xml"))
            .replace("\\", "/")
            .casefold()
        )

        matches = index["by_path"].get(xml_relative, [])

        if len(matches) == 1:
            return matches[0], "matched_by_relative_path"

        if len(matches) > 1:
            return None, "ambiguous_metadata_path"

    stem = Path(filename).stem.casefold()
    matches = index["by_stem"].get(stem, [])

    if len(matches) == 1:
        return matches[0], "matched_by_unique_stem"

    if len(matches) > 1:
        return None, "ambiguous_metadata_stem"

    return None, "metadata_not_found"


# --------------------------------------------------
# CSV path resolution
# --------------------------------------------------

def find_csv_path(
    input_root: Path,
    inventory_row: dict,
) -> Path | None:

    relative_path = inventory_row.get("relative_path")

    if relative_path:
        candidate = input_root / Path(str(relative_path))

        if candidate.is_file():
            return candidate

    filename = str(
        inventory_row.get("filename") or ""
    )

    sol_folder = str(
        inventory_row.get("sol_folder") or ""
    )

    if not filename:
        return None

    if sol_folder:
        sol_directory = input_root / sol_folder

        direct = sol_directory / filename

        if direct.is_file():
            return direct

        if sol_directory.is_dir():
            matches = [
                path
                for path in sol_directory.rglob("*")
                if path.is_file()
                and path.name.casefold() == filename.casefold()
            ]

            if len(matches) == 1:
                return matches[0]

            if len(matches) > 1:
                return None

    matches = [
        path
        for path in input_root.rglob("*")
        if path.is_file()
        and path.name.casefold() == filename.casefold()
    ]

    return matches[0] if len(matches) == 1 else None


# --------------------------------------------------
# Metadata field selection
# --------------------------------------------------

def get_fields(record: dict) -> list[dict]:
    fields = record.get("fields", [])

    if not isinstance(fields, list):
        return []

    valid_fields = [
        field
        for field in fields
        if isinstance(field, dict)
    ]

    return ordered_fields(valid_fields)


def field_description(field: dict) -> str:
    return str(
        field.get("description")
        or field.get("field_description")
        or ""
    )


def field_is_quality_related(field: dict) -> bool:
    searchable = " ".join(
        str(field.get(key) or "")
        for key in (
            "name",
            "description",
            "unit",
        )
    ).casefold()

    return any(
        keyword in searchable
        for keyword in QUALITY_KEYWORDS
    )


def get_field_bounds(
    field: dict,
) -> tuple[float | None, float | None]:

    minimum = safe_float(field.get("valid_minimum"))
    maximum = safe_float(field.get("valid_maximum"))

    return minimum, maximum


def field_has_range(field: dict) -> bool:
    minimum, maximum = get_field_bounds(field)

    return minimum is not None or maximum is not None


def select_field_categories(
    fields: list[dict],
) -> list[tuple[int, dict, list[str]]]:

    selected = []

    for index, field in enumerate(fields):

        categories = []

        if field_is_quality_related(field):
            categories.append("quality_field")

        if field_has_range(field):
            categories.append("range_check")

        if categories:
            selected.append((index, field, categories))

    return selected


# --------------------------------------------------
# CSV header and XML field mapping
# --------------------------------------------------

def build_column_mapping(
    first_row: list[str],
    fields: list[dict],
    has_header: Any,
) -> tuple[dict[int, int] | None, bool, str]:

    field_names = [
        normalize_name(field.get("name") or "")
        for field in fields
    ]

    if not field_names or any(not name for name in field_names):
        return None, False, "invalid_xml_field_names"

    if len(set(field_names)) != len(field_names):
        return None, False, "duplicate_xml_field_names"

    header_names = [
        normalize_name(value)
        for value in first_row
    ]

    if len(set(header_names)) != len(header_names):
        return None, False, "duplicate_csv_header_names"

    positions = {
        name: index
        for index, name in enumerate(header_names)
        if name
    }

    # Exact match, including the original XML field order.
    if header_names == field_names:
        return (
            {index: index for index in range(len(fields))},
            True,
            "header_exact_match",
        )

    # Header exists but columns have been rearranged.
    if all(name in positions for name in field_names):
        mapping = {
            xml_index: positions[name]
            for xml_index, name in enumerate(field_names)
        }

        return mapping, True, "header_reordered_mapped"

    # Explicit XML header declaration that does not match CSV.
    if has_header is True:
        return None, False, "header_mapping_ambiguous"

    # An unknown header state plus partial name matches is ambiguous.
    matching_names = set(field_names).intersection(
        set(header_names)
    )

    if matching_names:
        return None, False, "partial_header_match"

    # Headerless positional mapping.
    if len(first_row) != len(fields):
        return None, False, "column_count_mismatch"

    return (
        {index: index for index in range(len(fields))},
        False,
        "positional_mapping",
    )


# --------------------------------------------------
# Per-field statistics
# --------------------------------------------------

def new_field_stats(
    field: dict,
    category: str,
) -> dict:

    minimum, maximum = get_field_bounds(field)

    return {
        "field": field,
        "category": category,
        "total_rows": 0,
        "missing_count": 0,
        "non_empty_count": 0,
        "numeric_count": 0,
        "non_numeric_count": 0,
        "below_valid_minimum": 0,
        "above_valid_maximum": 0,
        "minimum": minimum,
        "maximum": maximum,
        "value_counter": BoundedValueCounter(),
    }


def update_field_stats(
    stats: dict,
    raw_value: str | None,
) -> None:

    stats["total_rows"] += 1

    if is_missing(raw_value):
        stats["missing_count"] += 1
        return

    text_value = str(raw_value).strip()

    stats["non_empty_count"] += 1
    stats["value_counter"].add(text_value)

    number = safe_float(text_value)

    if number is None:
        stats["non_numeric_count"] += 1
        return

    stats["numeric_count"] += 1

    minimum = stats["minimum"]
    maximum = stats["maximum"]

    if minimum is not None and number < minimum:
        stats["below_valid_minimum"] += 1

    if maximum is not None and number > maximum:
        stats["above_valid_maximum"] += 1


# --------------------------------------------------
# Report row construction
# --------------------------------------------------

def make_report_row(
    inventory_row: dict,
    field: dict | None,
    stats: dict | None,
    category: str,
    status: str,
    notes: str,
) -> dict:

    sol_folder = str(
        inventory_row.get("sol_folder") or ""
    )

    filename = str(
        inventory_row.get("filename") or ""
    )

    sol_number = (
        get_sol_number(inventory_row.get("sol_number"))
        or get_sol_number(sol_folder)
    )

    product_code = (
        inventory_row.get("product_code")
        or get_product_code(filename)
    )

    row = {
        "sol_number": sol_number if sol_number is not None else "",
        "sol_folder": sol_folder,
        "product_code": product_code or "",
        "csv_file": filename,
        "field_name": field.get("name", "") if field else "",
        "field_type": category,
        "metadata_description": field_description(field) if field else "",
        "analysis_status": status,
        "total_rows": 0,
        "missing_count": 0,
        "non_empty_count": 0,
        "numeric_count": 0,
        "non_numeric_count": 0,
        "distinct_values_lower_bound": 0,
        "distinct_count_capped": False,
        "below_valid_minimum": 0,
        "above_valid_maximum": 0,
        "valid_minimum": "",
        "valid_maximum": "",
        "top_values_json": "{}",
        "notes": notes,
    }

    if stats is None:
        return row

    counter = stats["value_counter"]

    row.update({
        "total_rows": stats["total_rows"],
        "missing_count": stats["missing_count"],
        "non_empty_count": stats["non_empty_count"],
        "numeric_count": stats["numeric_count"],
        "non_numeric_count": stats["non_numeric_count"],
        "distinct_values_lower_bound": counter.distinct_lower_bound(),
        "distinct_count_capped": counter.distinct_tracking_capped,
        "below_valid_minimum": stats["below_valid_minimum"],
        "above_valid_maximum": stats["above_valid_maximum"],
        "valid_minimum": (
            stats["minimum"]
            if stats["minimum"] is not None
            else ""
        ),
        "valid_maximum": (
            stats["maximum"]
            if stats["maximum"] is not None
            else ""
        ),
        "top_values_json": json.dumps(
            counter.top_values(),
            ensure_ascii=False,
        ),
    })

    return row


# --------------------------------------------------
# Analyze one CSV in a single pass
# --------------------------------------------------

def analyze_csv(
    csv_path: Path,
    inventory_row: dict,
    xml_record: dict | None,
    metadata_status: str,
) -> list[dict]:

    if xml_record is None:
        return [
            make_report_row(
                inventory_row,
                None,
                None,
                "file_status",
                metadata_status,
                "A unique matching XML metadata record was not available.",
            )
        ]

    fields = get_fields(xml_record)

    if not fields:
        return [
            make_report_row(
                inventory_row,
                None,
                None,
                "file_status",
                "no_xml_fields",
                "XML metadata contains no usable field definitions.",
            )
        ]

    selected = select_field_categories(fields)

    if not selected:
        return [
            make_report_row(
                inventory_row,
                None,
                None,
                "file_status",
                "no_target_fields",
                "No quality-related fields or XML-declared valid ranges were found.",
            )
        ]

    try:
        with csv_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
            errors="replace",
        ) as file:

            reader = csv.reader(file)
            first_row = next(reader, None)

            if first_row is None:
                return [
                    make_report_row(
                        inventory_row,
                        None,
                        None,
                        "file_status",
                        "empty_file",
                        "CSV file contains no rows.",
                    )
                ]

            mapping, skip_first_row, mapping_status = build_column_mapping(
                first_row,
                fields,
                xml_record.get("has_header"),
            )

            if mapping is None:
                return [
                    make_report_row(
                        inventory_row,
                        None,
                        None,
                        "file_status",
                        mapping_status,
                        "CSV columns could not be mapped safely to XML fields.",
                    )
                ]

            # One statistics object per field/category.
            field_stats = []

            for field_index, field, categories in selected:
                for category in categories:
                    field_stats.append({
                        "field_index": field_index,
                        "field": field,
                        "stats": new_field_stats(field, category),
                    })

            malformed_rows = 0
            rows_iterator = reader

            if not skip_first_row:
                rows_iterator = iter([first_row, *reader])

            for row in rows_iterator:

                if not row or not any(str(value).strip() for value in row):
                    continue

                if len(row) != len(fields):
                    malformed_rows += 1

                for item in field_stats:

                    field_index = item["field_index"]
                    csv_index = mapping.get(field_index)

                    value = (
                        row[csv_index]
                        if csv_index is not None and csv_index < len(row)
                        else None
                    )

                    update_field_stats(
                        item["stats"],
                        value,
                    )

            report_rows = []

            for item in field_stats:

                notes = [
                    f"Column mapping: {mapping_status}."
                ]

                if item["stats"]["minimum"] is not None or (
                    item["stats"]["maximum"] is not None
                ):
                    notes.append(
                        "Range checks use XML-declared valid limits only."
                    )

                if item["stats"]["category"] == "quality_field":
                    notes.append(
                        "Observed values are reported without interpreting flag meanings."
                    )

                if item["stats"]["value_counter"].distinct_tracking_capped:
                    notes.append(
                        "Distinct-value tracking reached its configured memory limit; "
                        "the reported distinct count is a lower bound."
                    )

                if malformed_rows:
                    notes.append(
                        f"{malformed_rows} rows had a column count different "
                        "from the XML field count."
                    )

                report_rows.append(
                    make_report_row(
                        inventory_row,
                        item["field"],
                        item["stats"],
                        item["stats"]["category"],
                        "analysed",
                        " ".join(notes),
                    )
                )

            return report_rows

    except (OSError, UnicodeError, csv.Error) as error:
        return [
            make_report_row(
                inventory_row,
                None,
                None,
                "file_status",
                "read_failed",
                str(error),
            )
        ]


# --------------------------------------------------
# Full inventory analysis
# --------------------------------------------------

def run_analysis(
    input_root: Path,
    inventory: list[dict],
    metadata: dict,
) -> list[dict]:

    metadata_index = build_metadata_index(metadata)

    reports = []
    processed_paths = set()

    csv_records = [
        record
        for record in inventory
        if str(record.get("extension") or "")
        .strip()
        .casefold()
        .lstrip(".") == "csv"
    ]

    print(f"CSV inventory entries: {len(csv_records)}")

    for position, inventory_row in enumerate(csv_records, start=1):

        csv_path = find_csv_path(
            input_root,
            inventory_row,
        )

        if csv_path is None:
            reports.append(
                make_report_row(
                    inventory_row,
                    None,
                    None,
                    "file_status",
                    "file_not_found_or_ambiguous",
                    "CSV path could not be resolved uniquely.",
                )
            )
            continue

        resolved_path = str(csv_path.resolve()).casefold()

        if resolved_path in processed_paths:
            continue

        processed_paths.add(resolved_path)

        xml_record, metadata_status = find_metadata_record(
            inventory_row,
            metadata_index,
        )

        print(
            f"[{position}/{len(csv_records)}] "
            f"Processing {csv_path.name}"
        )

        file_reports = analyze_csv(
            csv_path,
            inventory_row,
            xml_record,
            metadata_status,
        )

        reports.extend(file_reports)

    return reports


# --------------------------------------------------
# Save reports and summary
# --------------------------------------------------

def write_report(
    path: Path,
    rows: list[dict],
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=REPORT_COLUMNS,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def build_summary(rows: list[dict]) -> dict:

    analysed = [
        row for row in rows
        if row.get("analysis_status") == "analysed"
    ]

    quality_rows = [
        row for row in analysed
        if row.get("field_type") == "quality_field"
    ]

    range_rows = [
        row for row in analysed
        if row.get("field_type") == "range_check"
    ]

    statuses = Counter(
        row.get("analysis_status", "unknown")
        for row in rows
    )

    return {
        "analyzer": "MEDA Quality Analyzer",
        "report_row_count": len(rows),
        "analysed_field_reports": len(analysed),
        "quality_field_reports": len(quality_rows),
        "range_check_reports": len(range_rows),
        "file_status_reports": sum(
            row.get("field_type") == "file_status"
            for row in rows
        ),
        "analysis_status_counts": dict(statuses),
        "total_rows_examined_by_field": sum(
            safe_int(row.get("total_rows"))
            for row in analysed
        ),
        "total_missing_values_by_field": sum(
            safe_int(row.get("missing_count"))
            for row in analysed
        ),
        "total_values_below_declared_minimum": sum(
            safe_int(row.get("below_valid_minimum"))
            for row in range_rows
        ),
        "total_values_above_declared_maximum": sum(
            safe_int(row.get("above_valid_maximum"))
            for row in range_rows
        ),
        "limitations": [
            "Quality flags are reported as observed; undocumented meanings are not inferred.",
            "Values outside XML-declared limits are flagged for review, not automatically classified as scientifically invalid.",
            "Special constants are not automatically treated as missing values.",
            "Quality-field and range-check reports are separate categories; a field may appear in both.",
            "Distinct-value tracking is bounded in memory. When capped, the reported distinct count is a lower bound.",
            "This analyzer does not determine overall instrument health or scientific suitability of a period.",
        ],
    }


def save_summary(
    path: Path,
    summary: dict,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            summary,
            file,
            indent=4,
            ensure_ascii=False,
        )


# --------------------------------------------------
# CLI
# --------------------------------------------------

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Analyze MEDA quality-related fields and "
            "XML-declared measurement ranges."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
    )

    parser.add_argument(
        "--inventory",
        type=Path,
        default=DEFAULT_INVENTORY,
    )

    parser.add_argument(
        "--metadata",
        type=Path,
        default=DEFAULT_METADATA,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    parser.add_argument(
        "--summary",
        type=Path,
        default=DEFAULT_SUMMARY,
    )

    return parser.parse_args()


def main() -> None:

    args = parse_args()

    print("Loading file inventory...")
    inventory = load_inventory(args.inventory)

    print("Loading XML metadata...")
    metadata = load_metadata(args.metadata)

    print("Analyzing quality fields and documented ranges...")

    reports = run_analysis(
        args.input,
        inventory,
        metadata,
    )

    summary = build_summary(reports)

    summary["input_directory"] = str(args.input)
    summary["inventory_file"] = str(args.inventory)
    summary["metadata_file"] = str(args.metadata)
    summary["report_file"] = str(args.output)

    write_report(
        args.output,
        reports,
    )

    save_summary(
        args.summary,
        summary,
    )

    print("")
    print("Quality analysis completed.")
    print(f"Report rows: {len(reports)}")
    print(f"Analysed field reports: {summary['analysed_field_reports']}")
    print(f"Quality field reports: {summary['quality_field_reports']}")
    print(f"Range check reports: {summary['range_check_reports']}")
    print(f"CSV report: {args.output.resolve()}")
    print(f"JSON summary: {args.summary.resolve()}")


if __name__ == "__main__":
    main()
