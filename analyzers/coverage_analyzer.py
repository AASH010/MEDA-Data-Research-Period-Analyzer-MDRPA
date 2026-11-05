from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from meda_common import (
    DEFAULT_AXIS_PREFERENCE,
    MISSING_TEXT,
    PARSERS,
    norm,
    numeric_column_indexes,
    ordered_fields,
    pick_time_column,
)


SOL_PATTERN = re.compile(
    r"^sol[_-]?0*(\d+)$",
    re.IGNORECASE,
)

PRODUCT_PATTERN = re.compile(
    r"(?:^|_)CAL_([A-Z0-9]+)(?:_|\.|$)",
    re.IGNORECASE,
)

TIME_KEYWORDS = re.compile(
    r"\b(time|date|utc|ltst|lmst|timestamp)\b",
    re.IGNORECASE,
)

REPORT_COLUMNS = [
    "sol_number", "sol_folder", "product_code", "filename",
    "file_size_bytes", "row_count", "time_field", "time_kind",
    "first_time", "last_time", "span_seconds",
    "parsed_timestamp_count", "missing_timestamp_count",
    "invalid_timestamp_count", "duplicate_timestamp_count",
    "out_of_order_count", "median_step_seconds", "gap_count",
    "largest_gap_seconds", "gap_total_seconds", "numeric_value_count",
    "numeric_missing_count", "numeric_invalid_count",
    "measurement_coverage_status", "notes",
]


# --------------------------------------------------
# Basic Helpers
# --------------------------------------------------

def get_sol_number(folder_name: str) -> int | None:
    match = SOL_PATTERN.match(folder_name)

    return int(match.group(1)) if match else None


def get_product_code(filename: str) -> str | None:
    match = PRODUCT_PATTERN.search(filename)

    return match.group(1).upper() if match else None


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def parse_timestamp(value: str | None) -> datetime | None:
    """
    Parse common ISO-style timestamps.

    Numeric mission-specific time values are not interpreted
    without an explicit time-system definition.
    """

    if not value:
        return None

    value = value.strip()

    if not value:
        return None

    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)

    except ValueError:
        pass

    formats = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    return None


def format_timestamp(value: datetime | None) -> str:
    if value is None:
        return ""

    return value.isoformat()


# --------------------------------------------------
# Load Previous Stage Outputs
# --------------------------------------------------

def load_file_inventory(path: Path) -> list[dict]:

    if not path.exists():
        raise FileNotFoundError(
            f"File inventory not found: {path}"
        )

    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        return list(csv.DictReader(file))


def load_metadata_inventory(path: Path) -> dict:

    if not path.exists():
        raise FileNotFoundError(
            f"Metadata inventory not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


# --------------------------------------------------
# Metadata Time Field Detection
# --------------------------------------------------

# --------------------------------------------------
# CSV Analysis
# --------------------------------------------------

def resolve_csv_path(
    input_dir: Path,
    sol_folder: str,
    filename: str,
) -> Path | None:

    sol_dir = input_dir / sol_folder

    if not sol_dir.exists():
        return None

    direct_path = sol_dir / filename

    if direct_path.is_file():
        return direct_path

    matches = [
        path
        for path in sol_dir.rglob("*")
        if path.is_file()
        and path.name.casefold() == filename.casefold()
    ]

    return matches[0] if len(matches) == 1 else None


def build_metadata_index(metadata: dict) -> dict:
    """Map (sol_folder, xml filename) -> XML record (fields, has_header)."""
    index = {}

    for record in metadata.get("records", []):
        key = (
            record.get("sol_folder", "").casefold(),
            record.get("source_file", "").casefold(),
        )
        index[key] = record

    return index


def analyze_csv(
    csv_path: Path,
    xml_record: dict | None,
    axis_preference=DEFAULT_AXIS_PREFERENCE,
    gap_factor: float = 2.5,
) -> dict:
    """Single streaming pass: time axis, gaps and numeric completeness."""

    result = {
        "row_count": 0,
        "time_field": "",
        "time_kind": "",
        "first_time": "",
        "last_time": "",
        "span_seconds": "",
        "parsed_timestamp_count": 0,
        "missing_timestamp_count": 0,
        "invalid_timestamp_count": 0,
        "duplicate_timestamp_count": 0,
        "out_of_order_count": 0,
        "median_step_seconds": "",
        "gap_count": 0,
        "largest_gap_seconds": "",
        "gap_total_seconds": "",
        "numeric_value_count": 0,
        "numeric_missing_count": 0,
        "numeric_invalid_count": 0,
        "measurement_coverage_status": "not_assessed",
        "notes": [],
    }

    if not xml_record or not xml_record.get("fields"):
        result["measurement_coverage_status"] = "no_xml_fields"
        result["notes"].append("No XML field definitions for this CSV.")
        return result

    fields = ordered_fields(xml_record["fields"])
    names = [f.get("name") or "" for f in fields]
    has_header = xml_record.get("has_header")

    time_idx, time_name, kind = pick_time_column(fields, axis_preference)
    skip = {time_idx} if time_idx is not None else set()
    numeric_idx = numeric_column_indexes(fields, skip)

    parser = PARSERS[kind][0] if kind else None
    result["time_field"] = time_name or ""
    result["time_kind"] = kind or ""

    steps = []
    prev = None
    first_val = last_val = None
    first_raw = last_raw = ""

    try:
        with csv_path.open("r", newline="", encoding="utf-8-sig") as file:
            reader = csv.reader(file)

            if has_header:
                header = next(reader, None)

                if header is None:
                    result["measurement_coverage_status"] = "empty_file"
                    return result

                if [norm(h) for h in header] != [norm(n) for n in names]:
                    result["notes"].append(
                        "CSV header differs from XML field order."
                    )

            for row in reader:

                if not row or not any(v.strip() for v in row):
                    continue

                result["row_count"] += 1

                for i in numeric_idx:
                    raw = row[i].strip() if i < len(row) else ""

                    if raw.lower() in MISSING_TEXT:
                        result["numeric_missing_count"] += 1
                        continue

                    try:
                        ok = math.isfinite(float(raw))
                    except ValueError:
                        ok = False

                    if ok:
                        result["numeric_value_count"] += 1
                    else:
                        result["numeric_invalid_count"] += 1

                if time_idx is None:
                    continue

                raw = row[time_idx].strip() if time_idx < len(row) else ""

                if raw.lower() in MISSING_TEXT:
                    result["missing_timestamp_count"] += 1
                    continue

                value = parser(raw)

                if value is None:
                    result["invalid_timestamp_count"] += 1
                    continue

                result["parsed_timestamp_count"] += 1

                if prev is not None:
                    step = value - prev

                    if step < 0:
                        result["out_of_order_count"] += 1
                    elif step == 0:
                        result["duplicate_timestamp_count"] += 1
                    else:
                        steps.append(step)

                prev = value

                if first_val is None or value < first_val:
                    first_val, first_raw = value, raw

                if last_val is None or value > last_val:
                    last_val, last_raw = value, raw

    except (OSError, UnicodeError, csv.Error) as error:
        result["measurement_coverage_status"] = "read_failed"
        result["notes"].append(str(error))
        return result

    if steps:
        median_step = statistics.median(steps)
        gaps = [s for s in steps if s > gap_factor * median_step]
        result["median_step_seconds"] = round(median_step, 6)
        result["gap_count"] = len(gaps)
        result["largest_gap_seconds"] = round(max(steps), 6)
        result["gap_total_seconds"] = round(sum(gaps), 6)

    if first_val is not None:
        result["first_time"] = first_raw
        result["last_time"] = last_raw
        result["span_seconds"] = round(last_val - first_val, 3)

    if time_idx is None:
        result["measurement_coverage_status"] = "time_field_not_detected"
        result["notes"].append("No supported time column (SCLK/UTC/LMST/LTST).")
    elif result["parsed_timestamp_count"] == 0:
        result["measurement_coverage_status"] = "timestamps_not_interpreted"
        result["notes"].append("No values parsed for the selected time column.")
    elif result["row_count"] == 0:
        result["measurement_coverage_status"] = "no_data_rows"
    else:
        result["measurement_coverage_status"] = "timestamp_analysis_available"

    if kind and kind != "utc":
        result["notes"].append(
            f"Time axis is {PARSERS[kind][1]}; not converted to UTC."
        )

    return result


# --------------------------------------------------
# Analyze Inventory
# --------------------------------------------------

def analyze_coverage(
    input_dir: Path,
    inventory_records: list[dict],
    metadata: dict,
) -> list[dict]:

    metadata_index = build_metadata_index(metadata)

    reports = []

    for record in inventory_records:

        if record.get("extension", "").lower() != ".csv":
            continue

        sol_folder = record.get("sol_folder", "")
        filename = record.get("filename", "")

        sol_number = get_sol_number(sol_folder)

        product_code = (
            record.get("product_code")
            or get_product_code(filename)
        )

        report = {
            "sol_number": sol_number,
            "sol_folder": sol_folder,
            "product_code": product_code or "",
            "filename": filename,
            "file_size_bytes": record.get("file_size_bytes", ""),
            "row_count": 0,
            "measurement_coverage_status": "not_analyzed",
            "notes": "",
        }

        metadata_key = (
            sol_folder.casefold(),
            filename.rsplit(".", 1)[0].casefold() + ".xml",
        )

        xml_record = metadata_index.get(metadata_key)

        csv_path = resolve_csv_path(
            input_dir,
            sol_folder,
            filename,
        )

        if csv_path is None:

            report["measurement_coverage_status"] = (
                "file_not_found"
            )

            report["notes"] = "CSV file not found on disk."

        else:

            analysis = analyze_csv(csv_path, xml_record)

            for key, value in analysis.items():

                if key == "notes":
                    report[key] = "; ".join(value)

                else:
                    report[key] = value

        reports.append(report)

    return reports


# --------------------------------------------------
# Product and Sol Summary
# --------------------------------------------------

def longest_consecutive_range(
    sol_numbers: list[int],
) -> dict:

    if not sol_numbers:
        return {
            "start_sol": None,
            "end_sol": None,
            "length_sols": 0,
        }

    values = sorted(set(sol_numbers))

    best_start = values[0]
    best_end = values[0]

    current_start = values[0]
    current_end = values[0]

    for sol in values[1:]:

        if sol == current_end + 1:

            current_end = sol

        else:

            if current_end - current_start > best_end - best_start:
                best_start = current_start
                best_end = current_end

            current_start = sol
            current_end = sol

    if current_end - current_start > best_end - best_start:
        best_start = current_start
        best_end = current_end

    return {
        "start_sol": best_start,
        "end_sol": best_end,
        "length_sols": best_end - best_start + 1,
    }


def build_product_summary(
    reports: list[dict],
    start_sol: int,
    end_sol: int,
) -> dict:

    products = defaultdict(list)

    for report in reports:

        product = report.get("product_code")

        sol = report.get("sol_number")

        if (
            product
            and sol is not None
            and int(report.get("row_count") or 0) > 0
        ):
            products[product].append(report)

    summaries = {}

    for product, records in sorted(products.items()):

        present_sols = sorted({
            record["sol_number"]
            for record in records
            if record["sol_number"] is not None
        })

        missing_sols = [
            sol
            for sol in range(start_sol, end_sol + 1)
            if sol not in present_sols
        ]

        consecutive = longest_consecutive_range(
            present_sols
        )

        summaries[product] = {
            "csv_file_count": len(records),
            "sols_with_csv_files": len(present_sols),
            "sols_without_csv_files": len(missing_sols),
            "present_sols": present_sols,
            "missing_sols": missing_sols,
            "longest_consecutive_file_presence": consecutive,
            "total_rows": sum(
                int(record.get("row_count") or 0)
                for record in records
            ),
            "total_numeric_values": sum(
                int(record.get("numeric_value_count") or 0)
                for record in records
            ),
            "total_parsed_timestamps": sum(
                int(record.get("parsed_timestamp_count") or 0)
                for record in records
            ),
        }

    return summaries


# --------------------------------------------------
# Save Reports
# --------------------------------------------------

def save_coverage_csv(
    reports: list[dict],
    output_file: Path,
) -> None:

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=REPORT_COLUMNS,
        )

        writer.writeheader()
        writer.writerows(reports)


def save_summary_json(
    summary: dict,
    output_file: Path,
) -> None:

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_file.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            summary,
            file,
            indent=4,
            ensure_ascii=False,
        )


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="Analyze MEDA product and Sol coverage."
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=Path("input"),
    )

    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("output/file_inventory.csv"),
    )

    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("output/metadata_inventory.json"),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/coverage_report.csv"),
    )

    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("output/coverage_summary.json"),
    )

    parser.add_argument(
        "--start-sol",
        type=int,
        default=107,
    )

    parser.add_argument(
        "--end-sol",
        type=int,
        default=250,
    )

    args = parser.parse_args()

    if args.start_sol > args.end_sol:
        parser.error("--start-sol must not exceed --end-sol")

    print("Loading file inventory...")

    inventory = load_file_inventory(args.inventory)

    print("Loading XML metadata...")

    metadata = load_metadata_inventory(args.metadata)

    print("Analyzing CSV files...")

    reports = analyze_coverage(
        args.input,
        inventory,
        metadata,
    )

    print("Building product summaries...")

    product_summaries = build_product_summary(
        reports,
        args.start_sol,
        args.end_sol,
    )

    summary = {
        "tool": "MEDA Research Tool",
        "module": "Coverage Analyzer",
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "analysis_range": {
            "start_sol": args.start_sol,
            "end_sol": args.end_sol,
        },
        "csv_files_analyzed": len(reports),
        "products": product_summaries,
        "interpretation_note": (
            "File presence and row counts do not establish "
            "continuous or scientifically valid measurements. "
            "Timestamp interpretation depends on XML metadata "
            "and supported time formats."
        ),
    }

    save_coverage_csv(
        reports,
        args.output,
    )

    save_summary_json(
        summary,
        args.summary,
    )

    print("")
    print("Coverage analysis completed.")
    print(f"CSV files analyzed: {len(reports)}")
    print(f"Products found: {len(product_summaries)}")
    print(f"Coverage report: {args.output.resolve()}")
    print(f"Coverage summary: {args.summary.resolve()}")


if __name__ == "__main__":
    main()