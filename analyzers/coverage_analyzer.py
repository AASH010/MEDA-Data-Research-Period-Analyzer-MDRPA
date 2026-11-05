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

try:
    from .meda_common import (
        DEFAULT_AXIS_PREFERENCE,
        MISSING_TEXT,
        PARSERS,
        norm,
        numeric_column_indexes,
        ordered_fields,
        pick_time_column,
    )
except ImportError:
    from meda_common import (
        DEFAULT_AXIS_PREFERENCE,
        MISSING_TEXT,
        PARSERS,
        norm,
        numeric_column_indexes,
        ordered_fields,
        pick_time_column,
    )



SOL_PATTERN = re.compile(r"^sol[_-]?0*(\d+)$", re.IGNORECASE)

PRODUCT_PATTERN = re.compile(
    r"(?:^|_)CAL_([A-Z0-9]+)(?:_|\.|$)",
    re.IGNORECASE,
)

REPORT_COLUMNS = [
    "sol_number",
    "sol_folder",
    "product_code",
    "filename",
    "file_size_bytes",
    "row_count",
    "time_field",
    "time_kind",
    "first_time",
    "last_time",
    "span_seconds",
    "parsed_timestamp_count",
    "missing_timestamp_count",
    "invalid_timestamp_count",
    "duplicate_timestamp_count",
    "out_of_order_count",
    "median_step_seconds",
    "gap_count",
    "largest_gap_seconds",
    "gap_total_seconds",
    "numeric_value_count",
    "numeric_missing_count",
    "numeric_invalid_count",
    "measurement_coverage_status",
    "column_mapping_status",
    "notes",
]


# --------------------------------------------------
# Identification helpers
# --------------------------------------------------

def get_sol_number(folder_name: str) -> int | None:
    match = SOL_PATTERN.match(str(folder_name))
    return int(match.group(1)) if match else None


def get_product_code(filename: str) -> str | None:
    match = PRODUCT_PATTERN.search(str(filename))
    return match.group(1).upper() if match else None


def normalize_name(value: str) -> str:
    return norm(value)


def safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return number if math.isfinite(number) else None


# --------------------------------------------------
# Load previous stage reports
# --------------------------------------------------

def load_file_inventory(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"File inventory not found: {path}")

    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        return list(csv.DictReader(file))


def load_metadata_inventory(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Metadata inventory not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("Metadata inventory must contain a JSON object.")

    if not isinstance(data.get("records", []), list):
        raise ValueError("Metadata inventory 'records' must be a list.")

    return data


# --------------------------------------------------
# Metadata indexing
# --------------------------------------------------

def build_metadata_index(metadata: dict) -> dict:
    """
    Index XML records by Sol and filename.

    Filename matching is retained for compatibility with the
    current inventory format. Relative paths are also indexed
    when available.
    """

    index = defaultdict(list)

    for record in metadata.get("records", []):
        sol = str(record.get("sol_folder") or "").casefold()
        source_file = str(record.get("source_file") or "").casefold()

        if sol and source_file:
            index[("name", sol, source_file)].append(record)

        relative_path = record.get("relative_path")

        if relative_path:
            normalized_path = str(relative_path).replace("\\", "/").casefold()
            index[("path", normalized_path)].append(record)

    return index


def find_xml_record(
    csv_record: dict,
    metadata_index: dict,
) -> dict | None:
    """Find an unambiguous XML record for one CSV inventory record."""

    sol = str(csv_record.get("sol_folder") or "").casefold()
    filename = str(csv_record.get("filename") or "")

    xml_name = Path(filename).stem + ".xml"

    matches = metadata_index.get(
        ("name", sol, xml_name.casefold()),
        [],
    )

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        return None

    relative_path = csv_record.get("relative_path")

    if relative_path:
        relative = Path(str(relative_path))
        xml_relative = str(relative.with_suffix(".xml"))
        xml_relative = xml_relative.replace("\\", "/").casefold()

        matches = metadata_index.get(("path", xml_relative), [])

        if len(matches) == 1:
            return matches[0]

    return None


# --------------------------------------------------
# CSV path resolution
# --------------------------------------------------

def resolve_csv_path(
    input_dir: Path,
    inventory_record: dict,
) -> Path | None:
    """
    Resolve a CSV using its relative path when available.

    Filename-only fallback is accepted only when unique inside
    the declared Sol directory.
    """

    relative_path = inventory_record.get("relative_path")

    if relative_path:
        candidate = input_dir / Path(relative_path)

        if candidate.is_file():
            return candidate

    sol_folder = str(inventory_record.get("sol_folder") or "")
    filename = str(inventory_record.get("filename") or "")

    if not sol_folder or not filename:
        return None

    sol_dir = input_dir / sol_folder

    if not sol_dir.is_dir():
        return None

    direct = sol_dir / filename

    if direct.is_file():
        return direct

    matches = [
        path
        for path in sol_dir.rglob("*")
        if path.is_file()
        and path.name.casefold() == filename.casefold()
    ]

    return matches[0] if len(matches) == 1 else None


# --------------------------------------------------
# CSV column mapping
# --------------------------------------------------

def build_column_mapping(
    header: list[str] | None,
    fields: list[dict],
    has_header,
) -> tuple[dict[int, int] | None, str, bool]:
    """
    Return:
        mapping: XML field index -> CSV column index
        status: mapping status
        skip_first_row: whether the first CSV row is a header

    If the XML does not establish header presence, only an exact
    normalized header match is treated as a header automatically.
    """

    field_names = [str(field.get("name") or "") for field in fields]
    normalized_fields = [normalize_name(name) for name in field_names]

    if not field_names or any(not name for name in normalized_fields):
        return None, "invalid_xml_field_names", False

    if len(set(normalized_fields)) != len(normalized_fields):
        return None, "duplicate_xml_field_names", False

    if has_header is False:
        return (
            {index: index for index in range(len(fields))},
            "positional_no_header",
            False,
        )

    if header is None:
        if has_header is True:
            return None, "header_missing", False

        return (
            {index: index for index in range(len(fields))},
            "positional_header_unknown",
            False,
        )

    normalized_header = [normalize_name(value) for value in header]

    if len(set(normalized_header)) != len(normalized_header):
        return None, "duplicate_csv_header_names", False

    # Exact field/header match.
    if normalized_header == normalized_fields:
        return (
            {index: index for index in range(len(fields))},
            "header_exact_match",
            True,
        )

    # Header order may differ, but all XML fields must map uniquely.
    header_positions = {
        name: index
        for index, name in enumerate(normalized_header)
        if name
    }

    if all(name in header_positions for name in normalized_fields):
        mapping = {
            xml_index: header_positions[field_name]
            for xml_index, field_name in enumerate(normalized_fields)
        }

        return mapping, "header_reordered_mapped", True

    if has_header is True:
        return None, "header_mapping_ambiguous", True

    # has_header is unknown. Do not discard a possible first data row.
    return (
        {index: index for index in range(len(fields))},
        "positional_header_unknown",
        False,
    )


# --------------------------------------------------
# CSV analysis
# --------------------------------------------------

def analyze_csv(
    csv_path: Path,
    xml_record: dict | None,
    axis_preference=DEFAULT_AXIS_PREFERENCE,
    gap_factor: float = 2.5,
) -> dict:

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
        "column_mapping_status": "not_assessed",
        "notes": [],
    }

    if not math.isfinite(gap_factor) or gap_factor <= 1:
        raise ValueError("gap_factor must be finite and greater than 1.")

    if not xml_record:
        result["measurement_coverage_status"] = "no_xml_metadata"
        result["column_mapping_status"] = "no_xml_metadata"
        result["notes"].append("No matching XML metadata record.")
        return result

    if xml_record.get("parse_status") == "failed":
        result["measurement_coverage_status"] = "xml_parse_failed"
        result["column_mapping_status"] = "xml_parse_failed"
        result["notes"].append(
            str(xml_record.get("parse_error") or "XML parsing failed.")
        )
        return result

    fields = ordered_fields(xml_record.get("fields") or [])

    if not fields:
        result["measurement_coverage_status"] = "no_xml_fields"
        result["column_mapping_status"] = "no_xml_fields"
        result["notes"].append("XML contains no usable field definitions.")
        return result

    time_idx, time_name, kind = pick_time_column(
        fields,
        axis_preference,
    )

    result["time_field"] = time_name or ""
    result["time_kind"] = kind or ""

    parser = PARSERS[kind][0] if kind else None

    skip = {time_idx} if time_idx is not None else set()
    numeric_indexes = numeric_column_indexes(fields, skip)

    seen_timestamps = set()
    positive_steps = []

    previous_timestamp = None
    minimum_timestamp = None
    maximum_timestamp = None

    first_raw = ""
    last_raw = ""

    try:
        with csv_path.open(
            "r",
            newline="",
            encoding="utf-8-sig",
        ) as file:

            reader = csv.reader(file)

            first_row = next(reader, None)

            if first_row is None:
                result["measurement_coverage_status"] = "empty_file"
                result["column_mapping_status"] = "not_available"
                return result

            mapping, mapping_status, skip_header = build_column_mapping(
                first_row,
                fields,
                xml_record.get("has_header"),
            )

            result["column_mapping_status"] = mapping_status

            if mapping is None:
                result["measurement_coverage_status"] = (
                    "column_mapping_ambiguous"
                )
                result["notes"].append(
                    "CSV columns could not be mapped safely to XML fields."
                )
                return result

            if mapping_status == "header_reordered_mapped":
                result["notes"].append(
                    "CSV header order differs from XML; columns mapped by name."
                )

            if mapping_status == "positional_header_unknown":
                result["notes"].append(
                    "XML does not establish header presence; positional mapping used."
                )

            rows = reader

            if not skip_header:
                rows = iter([first_row, *reader])

            for row in rows:

                if not row or not any(value.strip() for value in row):
                    continue

                result["row_count"] += 1

                # Numeric measurements
                for xml_index in numeric_indexes:
                    csv_index = mapping.get(xml_index)

                    if csv_index is None or csv_index >= len(row):
                        result["numeric_missing_count"] += 1
                        continue

                    raw = row[csv_index].strip()

                    if raw.casefold() in MISSING_TEXT:
                        result["numeric_missing_count"] += 1
                        continue

                    number = safe_float(raw)

                    if number is None:
                        result["numeric_invalid_count"] += 1
                    else:
                        result["numeric_value_count"] += 1

                # Time analysis
                if time_idx is None or parser is None:
                    continue

                time_csv_index = mapping.get(time_idx)

                if time_csv_index is None or time_csv_index >= len(row):
                    result["missing_timestamp_count"] += 1
                    continue

                raw_time = row[time_csv_index].strip()

                if raw_time.casefold() in MISSING_TEXT:
                    result["missing_timestamp_count"] += 1
                    continue

                try:
                    timestamp = parser(raw_time)
                except (TypeError, ValueError, OverflowError):
                    timestamp = None

                if timestamp is None:
                    result["invalid_timestamp_count"] += 1
                    continue

                # The shared parsers are expected to return numeric
                # coordinates for the selected axis.
                timestamp = safe_float(timestamp)

                if timestamp is None:
                    result["invalid_timestamp_count"] += 1
                    continue

                result["parsed_timestamp_count"] += 1

                if timestamp in seen_timestamps:
                    result["duplicate_timestamp_count"] += 1
                else:
                    seen_timestamps.add(timestamp)

                if previous_timestamp is not None:
                    step = timestamp - previous_timestamp

                    if step < 0:
                        result["out_of_order_count"] += 1
                    elif step > 0:
                        positive_steps.append(step)

                previous_timestamp = timestamp

                if minimum_timestamp is None or timestamp < minimum_timestamp:
                    minimum_timestamp = timestamp
                    first_raw = raw_time

                if maximum_timestamp is None or timestamp > maximum_timestamp:
                    maximum_timestamp = timestamp
                    last_raw = raw_time

    except (OSError, UnicodeError, csv.Error) as error:
        result["measurement_coverage_status"] = "read_failed"
        result["notes"].append(str(error))
        return result

    # Temporal span is based on the minimum and maximum parsed
    # coordinates, not on the first and last CSV rows.
    if minimum_timestamp is not None:
        result["first_time"] = first_raw
        result["last_time"] = last_raw
        result["span_seconds"] = round(
            maximum_timestamp - minimum_timestamp,
            6,
        )

    # Gap threshold is based on the median positive adjacent step.
    if positive_steps:
        median_step = statistics.median(positive_steps)
        threshold = gap_factor * median_step

        gaps = [
            step for step in positive_steps
            if step > threshold
        ]

        result["median_step_seconds"] = round(median_step, 6)
        result["gap_count"] = len(gaps)

        if gaps:
            result["largest_gap_seconds"] = round(max(gaps), 6)
            result["gap_total_seconds"] = round(sum(gaps), 6)
        else:
            result["largest_gap_seconds"] = 0
            result["gap_total_seconds"] = 0

    if time_idx is None:
        result["measurement_coverage_status"] = "time_field_not_detected"
        result["notes"].append(
            "No supported time field was detected from XML metadata."
        )

    elif result["parsed_timestamp_count"] == 0:
        result["measurement_coverage_status"] = "timestamps_not_interpreted"
        result["notes"].append(
            "No values could be interpreted on the selected time axis."
        )

    elif result["row_count"] == 0:
        result["measurement_coverage_status"] = "no_data_rows"

    else:
        result["measurement_coverage_status"] = "timestamp_analysis_available"

    if kind and kind != "utc":
        result["notes"].append(
            f"Time axis: {PARSERS[kind][1]}. No UTC conversion was performed."
        )

    if result["out_of_order_count"]:
        result["notes"].append(
            "Out-of-order timestamps were detected; gap calculations "
            "use positive adjacent steps only."
        )

    result["notes"].append(
        "Gap totals are sums of detected timestamp intervals, not estimates "
        "of missing measurement duration."
    )

    return result


# --------------------------------------------------
# Analyze inventory
# --------------------------------------------------

def analyze_coverage(
    input_dir: Path,
    inventory_records: list[dict],
    metadata: dict,
) -> list[dict]:

    metadata_index = build_metadata_index(metadata)
    reports = []

    for record in inventory_records:

        if str(record.get("extension") or "").lower() != ".csv":
            continue

        sol_folder = str(record.get("sol_folder") or "")
        filename = str(record.get("filename") or "")

        sol_number = safe_int(
            record.get("sol_number"),
            get_sol_number(sol_folder) or -1,
        )

        if sol_number < 0:
            sol_number = None

        product_code = (
            record.get("product_code")
            or get_product_code(filename)
            or ""
        )

        report = {
            "sol_number": sol_number,
            "sol_folder": sol_folder,
            "product_code": product_code,
            "filename": filename,
            "file_size_bytes": record.get("file_size_bytes", ""),
            "row_count": 0,
            "measurement_coverage_status": "not_analyzed",
            "column_mapping_status": "not_analyzed",
            "notes": "",
        }

        xml_record = find_xml_record(record, metadata_index)
        csv_path = resolve_csv_path(input_dir, record)

        if csv_path is None:
            report["measurement_coverage_status"] = "file_not_found"
            report["notes"] = "CSV file could not be resolved on disk."
            reports.append(report)
            continue

        if csv_path.stat().st_size == 0:
            report["measurement_coverage_status"] = "empty_file"
            report["notes"] = "CSV file has zero bytes."
            reports.append(report)
            continue

        analysis = analyze_csv(csv_path, xml_record)

        for key, value in analysis.items():
            if key == "notes":
                report[key] = "; ".join(value)
            else:
                report[key] = value

        reports.append(report)

    return reports


# --------------------------------------------------
# Sol range helpers
# --------------------------------------------------

def longest_consecutive_range(sol_numbers: list[int]) -> dict:
    if not sol_numbers:
        return {
            "start_sol": None,
            "end_sol": None,
            "length_sols": 0,
        }

    values = sorted(set(sol_numbers))

    best_start = best_end = values[0]
    current_start = current_end = values[0]

    for sol in values[1:]:
        if sol == current_end + 1:
            current_end = sol
        else:
            if current_end - current_start > best_end - best_start:
                best_start, best_end = current_start, current_end

            current_start = current_end = sol

    if current_end - current_start > best_end - best_start:
        best_start, best_end = current_start, current_end

    return {
        "start_sol": best_start,
        "end_sol": best_end,
        "length_sols": best_end - best_start + 1,
    }


# --------------------------------------------------
# Product summary
# --------------------------------------------------

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
            and safe_int(report.get("row_count")) > 0
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

        summaries[product] = {
            "csv_file_count": len(records),
            "sols_with_rows": len(present_sols),
            "sols_without_rows": len(missing_sols),
            "present_sols": present_sols,
            "missing_sols": missing_sols,
            "longest_consecutive_sol_range": longest_consecutive_range(
                present_sols
            ),
            "total_rows": sum(
                safe_int(record.get("row_count"))
                for record in records
            ),
            "total_numeric_values": sum(
                safe_int(record.get("numeric_value_count"))
                for record in records
            ),
            "total_parsed_timestamps": sum(
                safe_int(record.get("parsed_timestamp_count"))
                for record in records
            ),
            "files_with_available_timestamp_analysis": sum(
                record.get("measurement_coverage_status")
                == "timestamp_analysis_available"
                for record in records
            ),
        }

    return summaries


# --------------------------------------------------
# Save reports
# --------------------------------------------------

def save_coverage_csv(
    reports: list[dict],
    output_file: Path,
) -> None:

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=REPORT_COLUMNS,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(reports)


def save_summary_json(
    summary: dict,
    output_file: Path,
) -> None:

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as file:
        json.dump(
            summary,
            file,
            indent=4,
            ensure_ascii=False,
        )


# --------------------------------------------------
# Main
# --------------------------------------------------

def main() -> None:

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

    parser.add_argument(
        "--gap-factor",
        type=float,
        default=2.5,
        help="A gap is an adjacent positive time step greater than "
             "this factor multiplied by the median positive step.",
    )

    args = parser.parse_args()

    if args.start_sol > args.end_sol:
        parser.error("--start-sol must not exceed --end-sol")

    if not math.isfinite(args.gap_factor) or args.gap_factor <= 1:
        parser.error("--gap-factor must be finite and greater than 1")

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
        "tool": "MEDA Data Research & Period Analyzer",
        "module": "Coverage Analyzer",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_range": {
            "start_sol": args.start_sol,
            "end_sol": args.end_sol,
        },
        "csv_files_analyzed": len(reports),
        "products": product_summaries,
        "gap_definition": {
            "factor": args.gap_factor,
            "rule": (
                "An adjacent positive timestamp step is classified as "
                "a gap when it exceeds gap_factor multiplied by the "
                "median positive adjacent step."
            ),
            "gap_total_seconds": (
                "Sum of detected gap intervals; not an estimate of "
                "missing measurement duration."
            ),
        },
        "interpretation_notes": [
            "File presence, row counts and timestamp parsing do not establish scientific validity.",
            "CSV columns are mapped using XML field names when a header is available.",
            "Ambiguous column mappings are not used for measurement calculations.",
            "Time axes are analyzed in their own coordinate systems and are not automatically converted to UTC.",
            "LMST and LTST numeric coordinates depend on the shared parser conventions and require validation against authoritative MEDA documentation.",
            "Product presence is not equivalent to continuous temporal coverage.",
        ],
    }

    save_coverage_csv(reports, args.output)
    save_summary_json(summary, args.summary)

    print("")
    print("Coverage analysis completed.")
    print(f"CSV files analyzed: {len(reports)}")
    print(f"Products found: {len(product_summaries)}")
    print(f"Coverage report: {args.output.resolve()}")
    print(f"Coverage summary: {args.summary.resolve()}")


if __name__ == "__main__":
    main()
