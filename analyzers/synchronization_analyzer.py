
"""
MEDA Synchronization Analyzer

Compares timestamp coverage between MEDA CSV products within each Sol.

Supported timestamp format:
- ISO 8601 date/time strings, including optional fractional seconds.
- Timezone-aware timestamps are normalized to UTC.
- Timezone-naive timestamps remain naive and are not compared
  against timezone-aware timestamps.

No mission-specific numeric time conversion is assumed.
Python standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import re

from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Optional


DEFAULT_INPUT = Path("input")
DEFAULT_INVENTORY = Path("output/file_inventory.csv")
DEFAULT_METADATA = Path("output/metadata_inventory.json")

DEFAULT_FILE_REPORT = Path("output/synchronization_file_report.csv")
DEFAULT_PAIR_REPORT = Path("output/synchronization_pair_report.csv")
DEFAULT_SUMMARY = Path("output/synchronization_summary.json")

DEFAULT_TOLERANCE_SECONDS = 1.0

TIME_KEYWORDS = (
    "time",
    "date",
    "utc",
    "timestamp",
    "datetime",
    "sol_time",
    "ltst",
)


# ---------------------------------------------------------
# General helpers
# ---------------------------------------------------------

def normalise_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def parse_iso_timestamp(value: Any) -> Optional[datetime]:
    """Parse ISO 8601 timestamps without guessing other formats."""

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    if text.lower() in {"na", "n/a", "nan", "null", "none"}:
        return None

    # Support UTC suffix Z.
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)

        # Normalize timezone-aware timestamps to UTC.
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc)

        return parsed

    except ValueError:
        return None


def timestamp_to_seconds(value: datetime) -> float:
    """Convert a parsed timestamp to a comparable numeric value."""

    if value.tzinfo is not None:
        return value.timestamp()

    # Naive timestamps use a naive reference epoch.
    # They must not be compared with timezone-aware timestamps.
    reference = datetime(1970, 1, 1)
    return (value - reference).total_seconds()


def load_inventory(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Inventory not found: {path}")

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def load_metadata(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Metadata not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        for key in ("records", "products", "metadata", "files"):
            value = data.get(key)

            if isinstance(value, list):
                return [
                    item for item in value
                    if isinstance(item, dict)
                ]

    raise ValueError("Unsupported metadata JSON structure.")


def build_metadata_index(records: list[dict]) -> dict[str, dict]:
    index = {}

    for record in records:
        source_file = record.get("source_file")

        if source_file:
            key = normalise_name(Path(source_file).stem)
            index[key] = record

    return index


def resolve_csv_path(
    input_root: Path,
    inventory_row: dict,
) -> Optional[Path]:

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

    matches = list(input_root.rglob(filename))

    if len(matches) == 1:
        return matches[0]

    return None


# ---------------------------------------------------------
# Metadata time field discovery
# ---------------------------------------------------------

def extract_candidate_names(value: Any) -> list[str]:
    """Extract field names from candidate_fields metadata."""

    names = []

    if isinstance(value, str):
        names.append(value)

    elif isinstance(value, list):
        for item in value:
            names.extend(extract_candidate_names(item))

    elif isinstance(value, dict):
        for key in ("name", "field_name", "field"):
            candidate = value.get(key)

            if isinstance(candidate, str):
                names.append(candidate)

    return names


def discover_time_candidates(
    metadata_record: dict,
) -> list[str]:

    candidates = []

    for name in extract_candidate_names(
        metadata_record.get("candidate_fields", [])
    ):
        if name not in candidates:
            candidates.append(name)

    fields = metadata_record.get("fields", [])

    if isinstance(fields, list):
        for field in fields:

            if not isinstance(field, dict):
                continue

            name = field.get("name")

            if not name:
                continue

            searchable = (
                str(name) + " " +
                str(field.get("description", ""))
            ).lower()

            if any(keyword in searchable for keyword in TIME_KEYWORDS):
                if name not in candidates:
                    candidates.append(name)

    return candidates


# ---------------------------------------------------------
# CSV timestamp extraction
# ---------------------------------------------------------

def analyse_timestamp_file(
    csv_path: Path,
    candidate_names: list[str],
    sol_number: str,
    product_code: str,
) -> dict:

    base_result = {
        "sol_number": sol_number,
        "product_code": product_code,
        "csv_file": csv_path.name,
        "selected_time_field": "",
        "analysis_status": "",
        "total_rows": 0,
        "parsed_timestamps": 0,
        "missing_timestamps": 0,
        "invalid_timestamps": 0,
        "duplicate_timestamps": 0,
        "first_timestamp": "",
        "last_timestamp": "",
        "timezone_type": "",
        "notes": "",
    }

    try:
        with csv_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
            errors="replace",
        ) as handle:

            reader = csv.DictReader(handle)

            if not reader.fieldnames:
                base_result["analysis_status"] = "no_header"
                base_result["notes"] = "CSV header unavailable."
                return base_result

            # Match metadata candidates against actual CSV columns.
            column_lookup = {
                normalise_name(column): column
                for column in reader.fieldnames
                if column
            }

            matched_columns = []

            for candidate in candidate_names:
                actual = column_lookup.get(
                    normalise_name(candidate)
                )

                if actual and actual not in matched_columns:
                    matched_columns.append(actual)

            if not matched_columns:
                base_result["analysis_status"] = "no_time_field"
                base_result["notes"] = (
                    "No metadata time candidate matched a CSV column."
                )
                return base_result

            # Select the candidate with the greatest number
            # of successfully parsed timestamps.
            best_column = None
            best_timestamps = []
            best_missing = 0
            best_invalid = 0

            for column in matched_columns:

                timestamps = []
                missing = 0
                invalid = 0

                handle.seek(0)
                test_reader = csv.DictReader(handle)

                for row in test_reader:
                    value = row.get(column)

                    if value is None or not str(value).strip():
                        missing += 1
                        continue

                    parsed = parse_iso_timestamp(value)

                    if parsed is None:
                        invalid += 1
                    else:
                        timestamps.append(parsed)

                if len(timestamps) > len(best_timestamps):
                    best_column = column
                    best_timestamps = timestamps
                    best_missing = missing
                    best_invalid = invalid

            if best_column is None or not best_timestamps:
                base_result["analysis_status"] = "no_parseable_timestamps"
                base_result["notes"] = (
                    "No candidate column contained parseable ISO timestamps."
                )
                return base_result

            # Read total rows for the selected field.
            handle.seek(0)
            final_reader = csv.DictReader(handle)

            total_rows = sum(1 for _ in final_reader)

            duplicate_count = (
                len(best_timestamps) - len(set(best_timestamps))
            )

            best_timestamps.sort()

            timezone_types = {
                "aware" if item.tzinfo is not None else "naive"
                for item in best_timestamps
            }

            timezone_type = (
                next(iter(timezone_types))
                if len(timezone_types) == 1
                else "mixed"
            )

            base_result.update({
                "selected_time_field": best_column,
                "analysis_status": "analysed",
                "total_rows": total_rows,
                "parsed_timestamps": len(best_timestamps),
                "missing_timestamps": best_missing,
                "invalid_timestamps": best_invalid,
                "duplicate_timestamps": duplicate_count,
                "first_timestamp": best_timestamps[0].isoformat(),
                "last_timestamp": best_timestamps[-1].isoformat(),
                "timezone_type": timezone_type,
                "notes": "",
            })

            return base_result, best_timestamps

    except Exception as exc:
        base_result["analysis_status"] = "read_error"
        base_result["notes"] = str(exc)
        return base_result


# ---------------------------------------------------------
# Pairwise synchronization
# ---------------------------------------------------------

def compare_timestamp_series(
    first: list[datetime],
    second: list[datetime],
    tolerance_seconds: float,
) -> dict:

    result = {
        "comparison_status": "analysed",
        "timezone_compatible": False,
        "overlap_start": "",
        "overlap_end": "",
        "overlap_duration_seconds": None,
        "first_count": len(first),
        "second_count": len(second),
        "matched_timestamps": 0,
        "first_unmatched": len(first),
        "second_unmatched": len(second),
        "match_rate_first_percent": 0.0,
        "match_rate_second_percent": 0.0,
        "mean_match_difference_seconds": None,
        "max_match_difference_seconds": None,
    }

    if not first or not second:
        result["comparison_status"] = "empty_series"
        return result

    first_aware = first[0].tzinfo is not None
    second_aware = second[0].tzinfo is not None

    if first_aware != second_aware:
        result["comparison_status"] = "incompatible_timezones"
        return result

    result["timezone_compatible"] = True

    first_seconds = sorted(
        timestamp_to_seconds(item) for item in first
    )

    second_seconds = sorted(
        timestamp_to_seconds(item) for item in second
    )

    overlap_start = max(
        first_seconds[0],
        second_seconds[0],
    )

    overlap_end = min(
        first_seconds[-1],
        second_seconds[-1],
    )

    if overlap_start > overlap_end:
        result["comparison_status"] = "no_temporal_overlap"
        return result

    result["overlap_start"] = datetime_from_seconds(
        overlap_start, first_aware
    )

    result["overlap_end"] = datetime_from_seconds(
        overlap_end, first_aware
    )

    result["overlap_duration_seconds"] = (
        overlap_end - overlap_start
    )

    # Restrict matching to the common time interval.
    a = [
        value for value in first_seconds
        if overlap_start <= value <= overlap_end
    ]

    b = [
        value for value in second_seconds
        if overlap_start <= value <= overlap_end
    ]

    # Greedy one-to-one matching using two pointers.
    i = 0
    j = 0
    differences = []

    while i < len(a) and j < len(b):

        difference = a[i] - b[j]
        absolute_difference = abs(difference)

        if absolute_difference <= tolerance_seconds:
            differences.append(absolute_difference)
            i += 1
            j += 1

        elif difference < 0:
            i += 1

        else:
            j += 1

    matched = len(differences)

    result["matched_timestamps"] = matched
    result["first_unmatched"] = len(a) - matched
    result["second_unmatched"] = len(b) - matched

    if a:
        result["match_rate_first_percent"] = round(
            matched / len(a) * 100, 3
        )

    if b:
        result["match_rate_second_percent"] = round(
            matched / len(b) * 100, 3
        )

    if differences:
        result["mean_match_difference_seconds"] = round(
            sum(differences) / len(differences), 6
        )

        result["max_match_difference_seconds"] = round(
            max(differences), 6
        )

    return result


def datetime_from_seconds(
    value: float,
    timezone_aware: bool,
) -> str:

    if timezone_aware:
        return datetime.fromtimestamp(
            value,
            tz=timezone.utc,
        ).isoformat()

    reference = datetime(1970, 1, 1)

    from datetime import timedelta

    return (reference + timedelta(seconds=value)).isoformat()


# ---------------------------------------------------------
# Report generation
# ---------------------------------------------------------

def write_csv(path: Path, rows: list[dict], columns: list[str]):

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
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

    return {
        "analyzer": "MEDA Synchronization Analyzer",
        "tolerance_seconds": tolerance,
        "total_files": len(file_reports),
        "analysed_files": len(analysed_files),
        "unanalysed_files": len(file_reports) - len(analysed_files),
        "total_product_pairs": len(pair_reports),
        "analysed_pairs": len(analysed_pairs),
        "pairs_without_temporal_overlap": sum(
            row["comparison_status"] == "no_temporal_overlap"
            for row in pair_reports
        ),
        "pairs_with_incompatible_timezones": sum(
            row["comparison_status"] == "incompatible_timezones"
            for row in pair_reports
        ),
        "pairs_with_matches": sum(
            row.get("matched_timestamps", 0) > 0
            for row in analysed_pairs
        ),
        "important_limitations": [
            "Only ISO 8601 timestamps are parsed.",
            "Numeric mission-specific time formats are not converted.",
            "Timezone-aware and timezone-naive series are not compared.",
            "Matching is one-to-one within the configured tolerance.",
            "A timestamp match does not prove scientific equivalence.",
            "Different MEDA products may have different sampling schedules.",
            "Temporal overlap does not establish complete measurement coverage.",
        ],
    }


# ---------------------------------------------------------
# Main execution
# ---------------------------------------------------------

def run(args: argparse.Namespace):

    input_root = Path(args.input)
    inventory_path = Path(args.inventory)
    metadata_path = Path(args.metadata)

    print("Loading inventory...")
    inventory = load_inventory(inventory_path)

    print("Loading XML metadata...")
    metadata_records_list = load_metadata(metadata_path)
    metadata_index = build_metadata_index(metadata_records_list)

    csv_rows = [
        row for row in inventory
        if (row.get("extension") or "").lower().lstrip(".") == "csv"
    ]

    file_reports = []
    series_by_sol = defaultdict(list)
    processed_files = set()

    print(f"CSV entries found: {len(csv_rows)}")

    for index, item in enumerate(csv_rows, start=1):

        csv_path = resolve_csv_path(input_root, item)

        if csv_path is None:
            continue

        resolved = str(csv_path.resolve())

        if resolved in processed_files:
            continue

        processed_files.add(resolved)

        metadata_record = metadata_index.get(
            normalise_name(csv_path.stem)
        )

        if metadata_record is None:
            continue

        candidates = discover_time_candidates(metadata_record)

        sol_number = item.get("sol_number", "")
        product_code = item.get("product_code", "")

        print(
            f"[{index}/{len(csv_rows)}] "
            f"Analysing {csv_path.name}"
        )

        result = analyse_timestamp_file(
            csv_path,
            candidates,
            sol_number,
            product_code,
        )

        if isinstance(result, tuple):
            file_report, timestamps = result
            file_reports.append(file_report)

            if timestamps:
                series_by_sol[str(sol_number)].append({
                    "product_code": product_code,
                    "csv_file": csv_path.name,
                    "timestamps": timestamps,
                })

        else:
            file_reports.append(result)

    # Compare every available product pair within each Sol.
    pair_reports = []

    for sol_number, products in series_by_sol.items():

        for first, second in combinations(products, 2):

            comparison = compare_timestamp_series(
                first["timestamps"],
                second["timestamps"],
                args.tolerance,
            )

            pair_reports.append({
                "sol_number": sol_number,
                "product_1": first["product_code"],
                "file_1": first["csv_file"],
                "product_2": second["product_code"],
                "file_2": second["csv_file"],
                **comparison,
            })

    file_columns = [
        "sol_number",
        "product_code",
        "csv_file",
        "selected_time_field",
        "analysis_status",
        "total_rows",
        "parsed_timestamps",
        "missing_timestamps",
        "invalid_timestamps",
        "duplicate_timestamps",
        "first_timestamp",
        "last_timestamp",
        "timezone_type",
        "notes",
    ]

    pair_columns = [
        "sol_number",
        "product_1",
        "file_1",
        "product_2",
        "file_2",
        "comparison_status",
        "timezone_compatible",
        "overlap_start",
        "overlap_end",
        "overlap_duration_seconds",
        "first_count",
        "second_count",
        "matched_timestamps",
        "first_unmatched",
        "second_unmatched",
        "match_rate_first_percent",
        "match_rate_second_percent",
        "mean_match_difference_seconds",
        "max_match_difference_seconds",
    ]

    write_csv(
        Path(args.file_report),
        file_reports,
        file_columns,
    )

    write_csv(
        Path(args.pair_report),
        pair_reports,
        pair_columns,
    )

    summary = build_summary(
        file_reports,
        pair_reports,
        args.tolerance,
    )

    summary["input_directory"] = str(input_root)
    summary["file_report"] = args.file_report
    summary["pair_report"] = args.pair_report

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(
            summary,
            handle,
            indent=2,
            ensure_ascii=False,
        )

    print("\nSynchronization analysis completed.")
    print(f"Files analysed: {summary['analysed_files']}")
    print(f"Product pairs: {summary['total_product_pairs']}")
    print(f"Analysed pairs: {summary['analysed_pairs']}")
    print(f"File report: {args.file_report}")
    print(f"Pair report: {args.pair_report}")
    print(f"Summary: {args.summary}")


def parse_args():

    parser = argparse.ArgumentParser(
        description="Compare MEDA product timestamp synchronization."
    )

    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
    )

    parser.add_argument(
        "--inventory",
        default=str(DEFAULT_INVENTORY),
    )

    parser.add_argument(
        "--metadata",
        default=str(DEFAULT_METADATA),
    )

    parser.add_argument(
        "--file-report",
        default=str(DEFAULT_FILE_REPORT),
    )

    parser.add_argument(
        "--pair-report",
        default=str(DEFAULT_PAIR_REPORT),
    )

    parser.add_argument(
        "--summary",
        default=str(DEFAULT_SUMMARY),
    )

    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE_SECONDS,
        help="Timestamp matching tolerance in seconds.",
    )

    args = parser.parse_args()

    if args.tolerance < 0:
        parser.error("--tolerance must be zero or greater.")

    return args


if __name__ == "__main__":
    run(parse_args())
