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
import statistics

from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Optional

from meda_common import (
    DEFAULT_AXIS_PREFERENCE,
    MISSING_TEXT,
    PARSERS,
    ordered_fields,
    pick_time_column,
)


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
    xml_record: dict,
    sol_number: str,
    product_code: str,
    axis_preference=DEFAULT_AXIS_PREFERENCE,
) -> tuple[dict, list[float]]:
    """Always returns (file_report, sorted_seconds)."""

    report = {
        "sol_number": sol_number,
        "product_code": product_code,
        "csv_file": csv_path.name,
        "selected_time_field": "",
        "time_kind": "",
        "analysis_status": "",
        "total_rows": 0,
        "parsed_timestamps": 0,
        "missing_timestamps": 0,
        "invalid_timestamps": 0,
        "duplicate_timestamps": 0,
        "median_step_seconds": "",
        "first_timestamp": "",
        "last_timestamp": "",
        "notes": "",
    }

    fields = ordered_fields(xml_record.get("fields") or [])
    idx, name, kind = pick_time_column(fields, axis_preference)

    if idx is None:
        report["analysis_status"] = "no_time_field"
        report["notes"] = "No supported time column (SCLK/UTC/LMST/LTST)."
        return report, []

    report["selected_time_field"] = name
    report["time_kind"] = kind
    parser = PARSERS[kind][0]
    seconds = []

    try:
        with csv_path.open(
            "r", encoding="utf-8-sig", newline="", errors="replace"
        ) as handle:
            reader = csv.reader(handle)

            if xml_record.get("has_header"):
                next(reader, None)

            for row in reader:
                if not row or not any(v.strip() for v in row):
                    continue

                report["total_rows"] += 1
                raw = row[idx].strip() if idx < len(row) else ""

                if raw.lower() in MISSING_TEXT:
                    report["missing_timestamps"] += 1
                    continue

                value = parser(raw)

                if value is None:
                    report["invalid_timestamps"] += 1
                else:
                    seconds.append(value)

    except Exception as exc:
        report["analysis_status"] = "read_error"
        report["notes"] = str(exc)
        return report, []

    if not seconds:
        report["analysis_status"] = "no_parseable_timestamps"
        return report, []

    seconds.sort()
    steps = [b - a for a, b in zip(seconds, seconds[1:]) if b > a]

    report.update({
        "analysis_status": "analysed",
        "parsed_timestamps": len(seconds),
        "duplicate_timestamps": len(seconds) - len(set(seconds)),
        "median_step_seconds": (
            round(statistics.median(steps), 6) if steps else ""
        ),
        "first_timestamp": seconds[0],
        "last_timestamp": seconds[-1],
    })

    return report, seconds


def count_within_tolerance(
    source: list[float],
    reference: list[float],
    tolerance: float,
) -> tuple[int, list[float]]:
    """Count source values having a reference value within tolerance."""

    count = 0
    diffs = []

    for x in source:
        k = bisect_left(reference, x)
        best = min(
            (abs(x - reference[j]) for j in (k - 1, k) if 0 <= j < len(reference)),
            default=None,
        )

        if best is not None and best <= tolerance:
            count += 1
            diffs.append(best)

    return count, diffs


def compare_timestamp_series(
    first: list[float],
    second: list[float],
    tolerance_seconds: float,
    kind_first: str,
    kind_second: str,
) -> dict:

    result = {
        "comparison_status": "analysed",
        "time_kind": kind_first,
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
        "match_rate_sparser_percent": 0.0,
        "sampling_note": "",
        "mean_match_difference_seconds": None,
        "max_match_difference_seconds": None,
    }

    if not first or not second:
        result["comparison_status"] = "empty_series"
        return result

    if kind_first != kind_second:
        result["comparison_status"] = "incompatible_time_axes"
        return result

    start = max(first[0], second[0])
    end = min(first[-1], second[-1])

    if start > end:
        result["comparison_status"] = "no_temporal_overlap"
        return result

    result["overlap_start"] = start
    result["overlap_end"] = end
    result["overlap_duration_seconds"] = end - start

    a = [v for v in first if start <= v <= end]
    b = [v for v in second if start <= v <= end]

    # Nearest-neighbour matching: each timestamp is compared with the
    # closest timestamp of the other series (no drift when the two
    # products are sampled at different rates).
    count_a, diffs_a = count_within_tolerance(a, b, tolerance_seconds)
    count_b, diffs_b = count_within_tolerance(b, a, tolerance_seconds)

    # Matches are counted from the sparser series' point of view.
    matched, diffs = (
        (count_a, diffs_a) if len(a) <= len(b) else (count_b, diffs_b)
    )

    result["matched_timestamps"] = matched
    result["first_unmatched"] = len(a) - count_a
    result["second_unmatched"] = len(b) - count_b

    if a:
        result["match_rate_first_percent"] = round(count_a / len(a) * 100, 3)

    if b:
        result["match_rate_second_percent"] = round(count_b / len(b) * 100, 3)

    sparser = min(len(a), len(b))

    if sparser:
        # Relative to the sparser series, so a different sampling rate
        # is not reported as a synchronization problem.
        result["match_rate_sparser_percent"] = round(
            matched / sparser * 100, 3
        )

    if a and b and max(len(a), len(b)) > 1.2 * min(len(a), len(b)):
        result["sampling_note"] = (
            "Series have different sampling densities; use "
            "match_rate_sparser_percent."
        )

    if diffs:
        result["mean_match_difference_seconds"] = round(
            sum(diffs) / len(diffs), 6
        )
        result["max_match_difference_seconds"] = round(max(diffs), 6)

    return result


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
        "pairs_with_incompatible_time_axes": sum(
            row["comparison_status"] == "incompatible_time_axes"
            for row in pair_reports
        ),
        "pairs_with_matches": sum(
            row.get("matched_timestamps", 0) > 0
            for row in analysed_pairs
        ),
        "important_limitations": [
            "Series are compared only on the same time axis (default SCLK).",
            "No axis is converted to UTC.",
            "Matching is nearest-neighbour within the configured tolerance.",
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

        sol_number = item.get("sol_number", "")
        product_code = item.get("product_code", "")

        print(
            f"[{index}/{len(csv_rows)}] "
            f"Analysing {csv_path.name}"
        )

        file_report, seconds = analyse_timestamp_file(
            csv_path,
            metadata_record,
            sol_number,
            product_code,
            tuple(args.time_axis),
        )

        file_reports.append(file_report)

        if seconds:
            series_by_sol[str(sol_number)].append({
                "product_code": product_code,
                "csv_file": csv_path.name,
                "timestamps": seconds,
                "time_kind": file_report["time_kind"],
            })

    # Compare every available product pair within each Sol.
    pair_reports = []

    for sol_number, products in series_by_sol.items():

        for first, second in combinations(products, 2):

            comparison = compare_timestamp_series(
                first["timestamps"],
                second["timestamps"],
                args.tolerance,
                first["time_kind"],
                second["time_kind"],
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
        "time_kind",
        "median_step_seconds",
        "notes",
    ]

    pair_columns = [
        "sol_number",
        "product_1",
        "file_1",
        "product_2",
        "file_2",
        "comparison_status",
        "time_kind",
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
        "match_rate_sparser_percent",
        "sampling_note",
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
        "--time-axis",
        nargs="+",
        default=list(DEFAULT_AXIS_PREFERENCE),
        choices=list(PARSERS),
        help="Time axis preference order (default: sclk first).",
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