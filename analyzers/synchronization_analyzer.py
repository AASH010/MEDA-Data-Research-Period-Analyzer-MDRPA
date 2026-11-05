
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics

from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import chain, combinations
from pathlib import Path
from typing import Any

try:
    from .meda_common import (
        DEFAULT_AXIS_PREFERENCE,
        MISSING_TEXT,
        PARSERS,
        norm,
        ordered_fields,
        pick_time_column,
    )
except ImportError:
    from meda_common import (
        DEFAULT_AXIS_PREFERENCE,
        MISSING_TEXT,
        PARSERS,
        norm,
        ordered_fields,
        pick_time_column,
    )


DEFAULT_INPUT = Path("input")
DEFAULT_INVENTORY = Path("output/file_inventory.csv")
DEFAULT_METADATA = Path("output/metadata_inventory.json")

DEFAULT_FILE_REPORT = Path("output/synchronization_file_report.csv")
DEFAULT_PAIR_REPORT = Path("output/synchronization_pair_report.csv")
DEFAULT_SUMMARY = Path("output/synchronization_summary.json")

DEFAULT_TOLERANCE = 1.0

SOL_PATTERN = re.compile(
    r"^sol[_-]?0*(\d+)$",
    re.IGNORECASE,
)


FILE_REPORT_COLUMNS = [
    "sol_number",
    "sol_folder",
    "product_code",
    "csv_file",
    "selected_time_field",
    "time_kind",
    "analysis_status",
    "total_rows",
    "parsed_timestamps",
    "missing_timestamps",
    "invalid_timestamps",
    "duplicate_timestamps",
    "out_of_order_timestamps",
    "median_step",
    "first_timestamp",
    "last_timestamp",
    "notes",
]


PAIR_REPORT_COLUMNS = [
    "sol_number",
    "product_1",
    "file_1",
    "product_2",
    "file_2",
    "comparison_status",
    "time_kind",
    "tolerance",
    "overlap_start",
    "overlap_end",
    "overlap_duration",
    "first_count",
    "second_count",
    "matched_timestamps",
    "first_unmatched",
    "second_unmatched",
    "match_rate_first_percent",
    "match_rate_second_percent",
    "match_rate_sparser_percent",
    "mean_match_difference",
    "max_match_difference",
    "notes",
]


# ---------------------------------------------------------
# General helpers
# ---------------------------------------------------------

def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    return number if math.isfinite(number) else None


def safe_int(value: Any, default: int = -1) -> int:
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

    match = SOL_PATTERN.match(str(value).strip())

    return int(match.group(1)) if match else None


def normalize_path(value: Any) -> str:
    return str(value or "").replace("\\", "/").casefold()


def is_missing(value: Any) -> bool:
    return (
        value is None
        or str(value).strip().casefold() in MISSING_TEXT
    )


# ---------------------------------------------------------
# Input loading
# ---------------------------------------------------------

def load_inventory(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(
            f"File inventory not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        return list(csv.DictReader(file))


def load_metadata(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Metadata inventory not found: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list):
        records = data

    elif isinstance(data, dict):
        records = data.get("records")

        if not isinstance(records, list):
            raise ValueError(
                "Metadata JSON must contain a 'records' list."
            )

    else:
        raise ValueError(
            "Unsupported metadata JSON structure."
        )

    return [
        item for item in records
        if isinstance(item, dict)
    ]


# ---------------------------------------------------------
# Metadata indexing and matching
# ---------------------------------------------------------

def metadata_sol_number(record: dict) -> int | None:
    number = get_sol_number(record.get("sol_number"))

    if number is not None:
        return number

    return get_sol_number(record.get("sol_folder"))


def build_metadata_index(records: list[dict]) -> dict:
    """
    Keep all matches instead of silently overwriting records
    that have the same filename stem.
    """

    by_sol_name = defaultdict(list)
    by_stem = defaultdict(list)
    by_path = defaultdict(list)

    for record in records:
        source_file = str(
            record.get("source_file") or ""
        )

        if not source_file:
            continue

        stem = Path(source_file).stem.casefold()
        sol_number = metadata_sol_number(record)

        if sol_number is not None:
            by_sol_name[(sol_number, stem)].append(record)

        by_stem[stem].append(record)

        relative_path = record.get("relative_path")

        if relative_path:
            by_path[normalize_path(relative_path)].append(record)

    return {
        "by_sol_name": by_sol_name,
        "by_stem": by_stem,
        "by_path": by_path,
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

    stem = Path(filename).stem.casefold()

    # Priority 1: exact relative path.
    relative_path = inventory_row.get("relative_path")

    if relative_path:
        xml_relative = normalize_path(
            Path(str(relative_path)).with_suffix(".xml")
        )

        matches = index["by_path"].get(xml_relative, [])

        if len(matches) == 1:
            return matches[0], "matched_by_relative_path"

        if len(matches) > 1:
            return None, "ambiguous_metadata_path"

    # Priority 2: Sol number + filename stem.
    sol_number = get_sol_number(
        inventory_row.get("sol_number")
    )

    if sol_number is None:
        sol_number = get_sol_number(
            inventory_row.get("sol_folder")
        )

    if sol_number is not None:
        matches = index["by_sol_name"].get(
            (sol_number, stem),
            [],
        )

        if len(matches) == 1:
            return matches[0], "matched_by_sol_and_name"

        if len(matches) > 1:
            return None, "ambiguous_metadata_match"

    # Priority 3: unique filename stem.
    matches = index["by_stem"].get(stem, [])

    if len(matches) == 1:
        return matches[0], "matched_by_unique_stem"

    if len(matches) > 1:
        return None, "ambiguous_metadata_stem"

    return None, "metadata_not_found"


# ---------------------------------------------------------
# CSV path resolution
# ---------------------------------------------------------

def resolve_csv_path(
    input_root: Path,
    inventory_row: dict,
) -> Path | None:

    filename = str(
        inventory_row.get("filename") or ""
    ).strip()

    if not filename:
        return None

    relative_path = inventory_row.get("relative_path")

    if relative_path:
        candidate = input_root / Path(str(relative_path))

        if candidate.is_file():
            return candidate

    sol_folder = str(
        inventory_row.get("sol_folder") or ""
    ).strip()

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


# ---------------------------------------------------------
# CSV column mapping
# ---------------------------------------------------------

def build_column_mapping(
    first_row: list[str],
    fields: list[dict],
    has_header: Any,
) -> tuple[dict[int, int] | None, bool, str]:

    field_names = [
        norm(field.get("name") or "")
        for field in fields
    ]

    if not field_names or any(not name for name in field_names):
        return None, False, "invalid_xml_field_names"

    if len(set(field_names)) != len(field_names):
        return None, False, "duplicate_xml_field_names"

    header_names = [
        norm(value)
        for value in first_row
    ]

    if len(set(header_names)) != len(header_names):
        return None, False, "duplicate_csv_header_names"

    positions = {
        name: index
        for index, name in enumerate(header_names)
        if name
    }

    # Exact header match.
    if header_names == field_names:
        return (
            {index: index for index in range(len(fields))},
            True,
            "header_exact_match",
        )

    # Header exists, but the columns are reordered.
    if all(name in positions for name in field_names):
        mapping = {
            xml_index: positions[name]
            for xml_index, name in enumerate(field_names)
        }

        return mapping, True, "header_reordered_mapped"

    if has_header is True:
        return None, False, "header_mapping_ambiguous"

    # Do not silently assume that a partially matching first row
    # is either a header or a data row.
    if set(field_names).intersection(header_names):
        return None, False, "partial_header_match"

    # Headerless positional mapping.
    if len(first_row) != len(fields):
        return None, False, "column_count_mismatch"

    if has_header is None:
        status = "positional_header_unknown"
    else:
        status = "positional_no_header"

    return (
        {index: index for index in range(len(fields))},
        False,
        status,
    )


# ---------------------------------------------------------
# File-level timestamp analysis
# ---------------------------------------------------------

def empty_file_report(
    inventory_row: dict,
    status: str,
    notes: str,
) -> dict:

    sol_number = get_sol_number(
        inventory_row.get("sol_number")
    )

    if sol_number is None:
        sol_number = get_sol_number(
            inventory_row.get("sol_folder")
        )

    return {
        "sol_number": sol_number,
        "sol_folder": inventory_row.get("sol_folder", ""),
        "product_code": inventory_row.get("product_code", ""),
        "csv_file": inventory_row.get("filename", ""),
        "selected_time_field": "",
        "time_kind": "",
        "analysis_status": status,
        "total_rows": 0,
        "parsed_timestamps": 0,
        "missing_timestamps": 0,
        "invalid_timestamps": 0,
        "duplicate_timestamps": 0,
        "out_of_order_timestamps": 0,
        "median_step": "",
        "first_timestamp": "",
        "last_timestamp": "",
        "notes": notes,
    }


def analyse_timestamp_file(
    csv_path: Path,
    inventory_row: dict,
    xml_record: dict,
    axis_preference=DEFAULT_AXIS_PREFERENCE,
) -> tuple[dict, list[float]]:

    report = empty_file_report(
        inventory_row,
        "not_analysed",
        "",
    )

    if xml_record.get("parse_status") == "failed":
        report["analysis_status"] = "xml_parse_failed"
        report["notes"] = str(
            xml_record.get("parse_error") or "XML parsing failed."
        )
        return report, []

    fields = ordered_fields(xml_record.get("fields") or [])

    if not fields:
        report["analysis_status"] = "no_xml_fields"
        report["notes"] = "XML metadata contains no usable fields."
        return report, []

    time_index, time_name, time_kind = pick_time_column(
        fields,
        axis_preference,
    )

    if time_index is None or not time_kind:
        report["analysis_status"] = "no_time_field"
        report["notes"] = "No supported time field was detected."
        return report, []

    parser_entry = PARSERS.get(time_kind)

    if not parser_entry:
        report["analysis_status"] = "unsupported_time_parser"
        report["notes"] = f"No parser is registered for {time_kind}."
        return report, []

    time_parser = parser_entry[0]

    report["selected_time_field"] = time_name
    report["time_kind"] = time_kind

    timestamps = []
    previous_timestamp = None
    out_of_order_count = 0
    total_rows = 0
    missing_count = 0
    invalid_count = 0

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
                report["analysis_status"] = "empty_file"
                report["notes"] = "CSV file contains no rows."
                return report, []

            mapping, skip_header, mapping_status = build_column_mapping(
                first_row,
                fields,
                xml_record.get("has_header"),
            )

            if mapping is None:
                report["analysis_status"] = mapping_status
                report["notes"] = (
                    "CSV columns could not be mapped safely to XML fields."
                )
                return report, []

            csv_time_index = mapping.get(time_index)

            if csv_time_index is None:
                report["analysis_status"] = "time_column_not_mapped"
                report["notes"] = (
                    "Selected time field has no CSV column mapping."
                )
                return report, []

            # Stream rows instead of expanding the entire reader
            # into a list when the CSV has no header.
            rows = reader

            if not skip_header:
                rows = chain((first_row,), reader)

            for row in rows:

                if not row or not any(str(value).strip() for value in row):
                    continue

                total_rows += 1

                if csv_time_index >= len(row):
                    missing_count += 1
                    continue

                raw_value = row[csv_time_index].strip()

                if raw_value.casefold() in MISSING_TEXT:
                    missing_count += 1
                    continue

                try:
                    parsed_value = time_parser(raw_value)
                except (TypeError, ValueError, OverflowError):
                    parsed_value = None

                if parsed_value is None:
                    invalid_count += 1
                    continue

                timestamp = safe_float(parsed_value)

                if timestamp is None:
                    invalid_count += 1
                    continue

                if (
                    previous_timestamp is not None
                    and timestamp < previous_timestamp
                ):
                    out_of_order_count += 1

                previous_timestamp = timestamp
                timestamps.append(timestamp)

    except (OSError, UnicodeError, csv.Error) as error:
        report["analysis_status"] = "read_error"
        report["notes"] = str(error)
        return report, []

    if not timestamps:
        report.update({
            "analysis_status": "no_parseable_timestamps",
            "total_rows": total_rows,
            "missing_timestamps": missing_count,
            "invalid_timestamps": invalid_count,
            "out_of_order_timestamps": out_of_order_count,
            "notes": f"Column mapping: {mapping_status}.",
        })

        return report, []

    sorted_timestamps = sorted(timestamps)
    timestamp_counts = Counter(sorted_timestamps)

    positive_steps = [
        second - first
        for first, second in zip(
            sorted_timestamps,
            sorted_timestamps[1:],
        )
        if second > first
    ]

    median_step = (
        round(statistics.median(positive_steps), 6)
        if positive_steps
        else ""
    )

    notes = [f"Column mapping: {mapping_status}."]

    if time_kind != "utc":
        notes.append(
            "Values remain in their selected time coordinate; "
            "no UTC conversion was performed."
        )

    if out_of_order_count:
        notes.append(
            "Original CSV row order contained decreasing timestamps; "
            "series were sorted before pair comparison."
        )

    report.update({
        "analysis_status": "analysed",
        "total_rows": total_rows,
        "parsed_timestamps": len(timestamps),
        "missing_timestamps": missing_count,
        "invalid_timestamps": invalid_count,
        "duplicate_timestamps": sum(
            count - 1
            for count in timestamp_counts.values()
            if count > 1
        ),
        "out_of_order_timestamps": out_of_order_count,
        "median_step": median_step,
        "first_timestamp": sorted_timestamps[0],
        "last_timestamp": sorted_timestamps[-1],
        "notes": " ".join(notes),
    })

    return report, sorted_timestamps


# ---------------------------------------------------------
# One-to-one timestamp matching
# ---------------------------------------------------------

def match_one_to_one(
    first: list[float],
    second: list[float],
    tolerance: float,
) -> tuple[int, list[float]]:
    """
    Match sorted timestamp occurrences one-to-one.

    A timestamp occurrence can be used in at most one match.
    Duplicate timestamps are retained as separate observations.

    The two-pointer strategy produces a maximum-cardinality
    matching for sorted one-dimensional values under a fixed
    absolute tolerance.
    """

    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError(
            "Tolerance must be finite and non-negative."
        )

    i = 0
    j = 0

    matched = 0
    differences = []

    while i < len(first) and j < len(second):

        difference = first[i] - second[j]
        absolute_difference = abs(difference)

        if absolute_difference <= tolerance:
            matched += 1
            differences.append(absolute_difference)
            i += 1
            j += 1

        elif first[i] < second[j]:
            i += 1

        else:
            j += 1

    return matched, differences


def compare_timestamp_series(
    first: list[float],
    second: list[float],
    tolerance: float,
    kind_first: str,
    kind_second: str,
) -> dict:

    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError(
            "Tolerance must be finite and non-negative."
        )

    result = {
        "comparison_status": "analysed",
        "time_kind": kind_first,
        "tolerance": tolerance,
        "overlap_start": "",
        "overlap_end": "",
        "overlap_duration": "",
        "first_count": 0,
        "second_count": 0,
        "matched_timestamps": 0,
        "first_unmatched": 0,
        "second_unmatched": 0,
        "match_rate_first_percent": 0.0,
        "match_rate_second_percent": 0.0,
        "match_rate_sparser_percent": 0.0,
        "mean_match_difference": "",
        "max_match_difference": "",
        "notes": "",
    }

    if kind_first != kind_second:
        result["comparison_status"] = "incompatible_time_axes"
        result["notes"] = (
            "The products use different time axes; no cross-axis "
            "conversion was attempted."
        )
        return result

    if not first or not second:
        result["comparison_status"] = "empty_series"
        result["notes"] = "At least one timestamp series is empty."
        return result

    overlap_start = max(first[0], second[0])
    overlap_end = min(first[-1], second[-1])

    if overlap_start > overlap_end:
        result["comparison_status"] = "no_temporal_overlap"
        result["notes"] = "The timestamp series do not overlap."
        return result

    # Only observations inside the common interval are compared.
    first_overlap = [
        value for value in first
        if overlap_start <= value <= overlap_end
    ]

    second_overlap = [
        value for value in second
        if overlap_start <= value <= overlap_end
    ]

    matched, differences = match_one_to_one(
        first_overlap,
        second_overlap,
        tolerance,
    )

    first_count = len(first_overlap)
    second_count = len(second_overlap)

    first_unmatched = first_count - matched
    second_unmatched = second_count - matched

    first_rate = (
        matched / first_count * 100
        if first_count
        else 0.0
    )

    second_rate = (
        matched / second_count * 100
        if second_count
        else 0.0
    )

    sparser_count = min(first_count, second_count)

    sparser_rate = (
        matched / sparser_count * 100
        if sparser_count
        else 0.0
    )

    result.update({
        "overlap_start": overlap_start,
        "overlap_end": overlap_end,
        "overlap_duration": overlap_end - overlap_start,
        "first_count": first_count,
        "second_count": second_count,
        "matched_timestamps": matched,
        "first_unmatched": first_unmatched,
        "second_unmatched": second_unmatched,
        "match_rate_first_percent": round(first_rate, 3),
        "match_rate_second_percent": round(second_rate, 3),
        "match_rate_sparser_percent": round(sparser_rate, 3),
    })

    if differences:
        result["mean_match_difference"] = round(
            statistics.mean(differences),
            6,
        )

        result["max_match_difference"] = round(
            max(differences),
            6,
        )

    notes = [
        "Matching is one-to-one; each timestamp occurrence is used at most once.",
        "Counts and rates use observations inside the common temporal interval.",
    ]

    if first_count != second_count:
        notes.append(
            "The products have different observation counts; inspect "
            "both individual match rates and the sparser-series rate."
        )

    if kind_first != "utc":
        notes.append(
            "Tolerance is applied in the selected time coordinate, "
            "not necessarily physical SI seconds."
        )

    result["notes"] = " ".join(notes)

    return result


# ---------------------------------------------------------
# Full analysis
# ---------------------------------------------------------

def run_analysis(
    input_root: Path,
    inventory: list[dict],
    metadata_records: list[dict],
    tolerance: float,
    axis_preference=DEFAULT_AXIS_PREFERENCE,
) -> tuple[list[dict], list[dict]]:

    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError(
            "Tolerance must be finite and greater than or equal to zero."
        )

    metadata_index = build_metadata_index(metadata_records)

    csv_rows = [
        row for row in inventory
        if str(row.get("extension") or "")
        .strip()
        .casefold()
        .lstrip(".") == "csv"
    ]

    print(f"CSV inventory entries: {len(csv_rows)}")

    file_reports = []
    series_by_sol = defaultdict(list)
    processed_paths = set()

    for position, inventory_row in enumerate(csv_rows, start=1):

        csv_path = resolve_csv_path(
            input_root,
            inventory_row,
        )

        if csv_path is None:
            file_reports.append(
                empty_file_report(
                    inventory_row,
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

        if xml_record is None:
            file_reports.append(
                empty_file_report(
                    inventory_row,
                    metadata_status,
                    "A unique matching XML metadata record was not found.",
                )
            )
            continue

        if csv_path.stat().st_size == 0:
            file_reports.append(
                empty_file_report(
                    inventory_row,
                    "empty_file",
                    "CSV file has zero bytes.",
                )
            )
            continue

        print(
            f"[{position}/{len(csv_rows)}] "
            f"Analysing {csv_path.name}"
        )

        report, timestamps = analyse_timestamp_file(
            csv_path,
            inventory_row,
            xml_record,
            axis_preference,
        )

        if metadata_status != "matched_by_sol_and_name":
            previous_notes = report.get("notes", "")
            report["notes"] = (
                previous_notes + " " if previous_notes else ""
            ) + f"Metadata matching method: {metadata_status}."

        file_reports.append(report)

        if timestamps and report["analysis_status"] == "analysed":

            sol_number = get_sol_number(
                inventory_row.get("sol_number")
            )

            if sol_number is None:
                sol_number = get_sol_number(
                    inventory_row.get("sol_folder")
                )

            if sol_number is None:
                report["notes"] += (
                    " File was not included in pair comparisons "
                    "because its Sol number could not be identified."
                )
                continue

            series_by_sol[sol_number].append({
                "product_code": str(
                    inventory_row.get("product_code") or ""
                ).strip(),
                "csv_file": csv_path.name,
                "timestamps": timestamps,
                "time_kind": report["time_kind"],
            })

    # Compare different products within each Sol.
    pair_reports = []

    for sol_number in sorted(series_by_sol):

        products = series_by_sol[sol_number]

        for first, second in combinations(products, 2):

            first_product = first["product_code"]
            second_product = second["product_code"]

            # Product-to-product comparison requires two known,
            # different product codes.
            if not first_product or not second_product:
                continue

            if first_product.casefold() == second_product.casefold():
                continue

            comparison = compare_timestamp_series(
                first["timestamps"],
                second["timestamps"],
                tolerance,
                first["time_kind"],
                second["time_kind"],
            )

            pair_reports.append({
                "sol_number": sol_number,
                "product_1": first_product,
                "file_1": first["csv_file"],
                "product_2": second_product,
                "file_2": second["csv_file"],
                **comparison,
            })

    return file_reports, pair_reports


# ---------------------------------------------------------
# Reports
# ---------------------------------------------------------

def write_csv(
    path: Path,
    rows: list[dict],
    columns: list[str],
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
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def build_summary(
    file_reports: list[dict],
    pair_reports: list[dict],
    tolerance: float,
) -> dict:

    analysed_files = [
        row for row in file_reports
        if row["analysis_status"] == "analysed"
    ]

    analysed_pairs = [
        row for row in pair_reports
        if row["comparison_status"] == "analysed"
    ]

    file_status_counts = Counter(
        row["analysis_status"]
        for row in file_reports
    )

    pair_status_counts = Counter(
        row["comparison_status"]
        for row in pair_reports
    )

    return {
        "analyzer": "MEDA Synchronization Analyzer",
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "tolerance": tolerance,
        "tolerance_interpretation": (
            "Applied to the selected time coordinate. It is not "
            "guaranteed to represent SI seconds for every time axis."
        ),
        "total_files": len(file_reports),
        "analysed_files": len(analysed_files),
        "unanalysed_files": (
            len(file_reports) - len(analysed_files)
        ),
        "file_status_counts": dict(file_status_counts),
        "total_product_pairs": len(pair_reports),
        "analysed_pairs": len(analysed_pairs),
        "pair_status_counts": dict(pair_status_counts),
        "pairs_with_matches": sum(
            row["matched_timestamps"] > 0
            for row in analysed_pairs
        ),
        "matching_method": (
            "Sorted two-pointer one-to-one matching. "
            "Each timestamp occurrence can participate in at most one match."
        ),
        "important_limitations": [
            "Products are compared only when they use the same time axis.",
            "No mission-specific time axis is converted to UTC.",
            "Tolerance is applied in the selected coordinate.",
            "Different products may have different sampling schedules.",
            "A timestamp match does not prove scientific equivalence.",
            "Temporal overlap does not establish complete measurement coverage.",
            "Duplicate timestamp occurrences are retained and matched individually.",
            "Files with missing or identical product codes are excluded from product-pair comparisons.",
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


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Compare timestamp synchronization between MEDA products."
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
        "--file-report",
        type=Path,
        default=DEFAULT_FILE_REPORT,
    )

    parser.add_argument(
        "--pair-report",
        type=Path,
        default=DEFAULT_PAIR_REPORT,
    )

    parser.add_argument(
        "--summary",
        type=Path,
        default=DEFAULT_SUMMARY,
    )

    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help=(
            "Maximum absolute difference in the selected time coordinate. "
            "Default: 1.0"
        ),
    )

    parser.add_argument(
        "--time-axis",
        nargs="+",
        default=list(DEFAULT_AXIS_PREFERENCE),
        help="Preferred time-axis order.",
    )

    return parser.parse_args()


def main() -> None:

    args = parse_args()

    if not math.isfinite(args.tolerance) or args.tolerance < 0:
        raise SystemExit(
            "Error: --tolerance must be finite and non-negative."
        )

    print("Loading file inventory...")
    inventory = load_inventory(args.inventory)

    print("Loading XML metadata...")
    metadata_records = load_metadata(args.metadata)

    print("Analyzing timestamp series...")

    file_reports, pair_reports = run_analysis(
        args.input,
        inventory,
        metadata_records,
        args.tolerance,
        tuple(args.time_axis),
    )

    summary = build_summary(
        file_reports,
        pair_reports,
        args.tolerance,
    )

    summary["input_directory"] = str(args.input)
    summary["inventory_file"] = str(args.inventory)
    summary["metadata_file"] = str(args.metadata)
    summary["file_report"] = str(args.file_report)
    summary["pair_report"] = str(args.pair_report)

    write_csv(
        args.file_report,
        file_reports,
        FILE_REPORT_COLUMNS,
    )

    write_csv(
        args.pair_report,
        pair_reports,
        PAIR_REPORT_COLUMNS,
    )

    save_summary(
        args.summary,
        summary,
    )

    csv_count = sum(
        1
        for row in inventory
        if str(row.get("extension") or "")
        .strip()
        .casefold()
        .lstrip(".") == "csv"
    )

    print("")
    print("Synchronization analysis completed.")
    print(f"CSV inventory entries: {csv_count}")
    print(f"File reports: {len(file_reports)}")
    print(f"Analysed files: {summary['analysed_files']}")
    print(f"Product pairs: {len(pair_reports)}")
    print(f"Analysed pairs: {summary['analysed_pairs']}")
    print(f"File report: {args.file_report.resolve()}")
    print(f"Pair report: {args.pair_report.resolve()}")
    print(f"Summary: {args.summary.resolve()}")


if __name__ == "__main__":
    main()
