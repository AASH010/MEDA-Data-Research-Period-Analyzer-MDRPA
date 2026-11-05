from __future__ import annotations

import argparse
import csv
import json
import math
import statistics

from collections import defaultdict
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path

try:
    from .file_discovery import (
        SOL_FOLDER_PATTERN as SOL_PATTERN,
        PRODUCT_PATTERN,
        get_sol_number as _shared_get_sol_number,
        get_product_code as _shared_get_product_code,
    )
except ImportError:
    from file_discovery import (
        SOL_FOLDER_PATTERN as SOL_PATTERN,
        PRODUCT_PATTERN,
        get_sol_number as _shared_get_sol_number,
        get_product_code as _shared_get_product_code,
    )

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
    """Preserve the public helper while reusing file_discovery."""
    return _shared_get_sol_number(folder_name)


def get_product_code(filename: str) -> str | None:
    """Preserve the public helper while reusing file_discovery."""
    return _shared_get_product_code(filename)


def normalize_name(value: str) -> str:
    return norm(value)


def safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def safe_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    return number if math.isfinite(number) else None


def _normalize_relative_path(value) -> str:
    """Normalize a relative path for platform-independent matching."""
    if value is None:
        return ""

    return (
        str(value)
        .replace("\\", "/")
        .casefold()
    )


# --------------------------------------------------
# Load previous stage reports
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

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "Metadata inventory must contain a JSON object."
        )

    if not isinstance(data.get("records", []), list):
        raise ValueError(
            "Metadata inventory 'records' must be a list."
        )

    return data


# --------------------------------------------------
# Metadata indexing
# --------------------------------------------------

def build_metadata_index(metadata: dict) -> dict:
    """
    Index XML records by relative path and by Sol/filename.

    source_relative_path is the current XML parser field.
    relative_path remains supported for backward compatibility.

    When both path fields contain the same normalized path,
    the same record is indexed only once for that path.
    """

    index = defaultdict(list)

    for record in metadata.get("records", []):
        sol = str(
            record.get("sol_folder") or ""
        ).casefold()

        source_file = str(
            record.get("source_file") or ""
        ).casefold()

        if sol and source_file:
            index[("name", sol, source_file)].append(record)

        indexed_paths = set()

        for path_field in (
            "source_relative_path",
            "relative_path",
        ):
            normalized_path = _normalize_relative_path(
                record.get(path_field)
            )

            if not normalized_path:
                continue

            if normalized_path in indexed_paths:
                continue

            indexed_paths.add(normalized_path)

            index[("path", normalized_path)].append(record)

    return index


def find_xml_record(
    csv_record: dict,
    metadata_index: dict,
) -> dict | None:
    """
    Find an unambiguous XML record for one CSV inventory record.

    Matching order:
        1. Relative-path matching.
        2. Unique Sol/filename fallback.

    Ambiguous matches are rejected instead of selecting an
    arbitrary XML record.
    """

    relative_path = csv_record.get("relative_path")

    if relative_path:
        normalized_csv_path = _normalize_relative_path(
            relative_path
        )

        xml_relative_path = _normalize_relative_path(
            Path(normalized_csv_path).with_suffix(".xml")
        )

        path_matches = metadata_index.get(
            ("path", xml_relative_path),
            [],
        )

        if len(path_matches) == 1:
            return path_matches[0]

        if len(path_matches) > 1:
            return None

    sol = str(
        csv_record.get("sol_folder") or ""
    ).casefold()

    filename = str(
        csv_record.get("filename") or ""
    )

    if not sol or not filename:
        return None

    xml_name = Path(filename).stem + ".xml"

    matches = metadata_index.get(
        ("name", sol, xml_name.casefold()),
        [],
    )

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

    sol_folder = str(
        inventory_record.get("sol_folder") or ""
    )

    filename = str(
        inventory_record.get("filename") or ""
    )

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

    Supported mapping modes:
        - Exact header matching.
        - Strict positional mapping for duplicate XML names.
        - Validated WS header aliases.
        - Unique reordered header mapping.

    Original XML field names are never modified.
    """

    field_names = [
        str(field.get("name") or "")
        for field in fields
    ]

    normalized_fields = [
        normalize_name(name)
        for name in field_names
    ]

    if (
        not field_names
        or any(not name for name in normalized_fields)
    ):
        return None, "invalid_xml_field_names", False

    positional_mapping = {
        index: index
        for index in range(len(fields))
    }

    if has_header is False:
        return (
            positional_mapping,
            "positional_no_header",
            False,
        )

    if header is None:
        if has_header is True:
            return None, "header_missing", False

        return (
            positional_mapping,
            "positional_header_unknown",
            False,
        )

    normalized_header = [
        normalize_name(value)
        for value in header
    ]

    if any(not name for name in normalized_header):
        return None, "invalid_csv_header_names", False

    if len(set(normalized_header)) != len(normalized_header):
        return None, "duplicate_csv_header_names", False

    if len(normalized_header) != len(normalized_fields):
        if has_header is True:
            return None, "header_column_count_mismatch", True

        return (
            positional_mapping,
            "positional_header_unknown",
            False,
        )

    # Exact field/header match.
    if normalized_header == normalized_fields:
        return (
            positional_mapping,
            "header_exact_match",
            True,
        )

    # Detect duplicate XML field names.
    positions_by_name = defaultdict(list)

    for index, name in enumerate(normalized_fields):
        positions_by_name[name].append(index)

    duplicate_groups = {
        name: positions
        for name, positions in positions_by_name.items()
        if len(positions) > 1
    }

    if duplicate_groups:
        duplicate_positions = {
            index
            for positions in duplicate_groups.values()
            for index in positions
        }

        # All non-duplicated XML fields must match the CSV
        # header at exactly the same positions.
        for index, xml_name in enumerate(normalized_fields):
            if index in duplicate_positions:
                continue

            if normalized_header[index] != xml_name:
                if has_header is True:
                    return (
                        None,
                        "duplicate_xml_field_mapping_ambiguous",
                        True,
                    )

                return (
                    positional_mapping,
                    "positional_header_unknown",
                    False,
                )

        # The CSV header must distinguish duplicate XML positions.
        for positions in duplicate_groups.values():
            duplicate_header_names = [
                normalized_header[index]
                for index in positions
            ]

            if len(set(duplicate_header_names)) != len(
                duplicate_header_names
            ):
                return (
                    None,
                    "duplicate_xml_field_mapping_ambiguous",
                    True,
                )

        return (
            positional_mapping,
            "header_positional_duplicate_xml_names",
            True,
        )

    # Strictly validated WS header aliases.
    # These aliases are based on the observed WS files.
    # Only positions 15 and 16 may differ.
    # All other fields and the total column count must match.
    ws_header_aliases = {
        normalize_name("BOOM1_ALG_IN_STABLE_STATE"):
            normalize_name("BOOM1_ALG_STATE_STABLE"),

        normalize_name("BOOM2_ALG_IN_STABLE_STATE"):
            normalize_name("BOOM2_ALG_STATE_STABLE"),
    }

    if len(fields) == 18:
        differences = [
            index
            for index, (xml_name, csv_name)
            in enumerate(zip(normalized_fields, normalized_header))
            if xml_name != csv_name
        ]

        if differences == [15, 16]:
            aliases_match = all(
                ws_header_aliases.get(normalized_fields[index])
                == normalized_header[index]
                for index in differences
            )

            if aliases_match:
                return (
                    positional_mapping,
                    "header_positional_ws_aliases",
                    True,
                )

    # Header order may differ, but every XML field must map
    # uniquely to one CSV header.
    header_positions = {
        name: index
        for index, name in enumerate(normalized_header)
    }

    if all(
        name in header_positions
        for name in normalized_fields
    ):
        mapping = {
            xml_index: header_positions[field_name]
            for xml_index, field_name
            in enumerate(normalized_fields)
        }

        return (
            mapping,
            "header_reordered_mapped",
            True,
        )

    if has_header is True:
        return None, "header_mapping_ambiguous", True

    # Do not discard a possible first data row when header
    # presence cannot be established safely.
    return (
        positional_mapping,
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

    if (
        not math.isfinite(gap_factor)
        or gap_factor <= 1
    ):
        raise ValueError(
            "gap_factor must be finite and greater than 1."
        )

    if not xml_record:
        result["measurement_coverage_status"] = "no_xml_metadata"
        result["column_mapping_status"] = "no_xml_metadata"

        result["notes"].append(
            "No matching XML metadata record."
        )

        return result

    if xml_record.get("parse_status") == "failed":
        result["measurement_coverage_status"] = "xml_parse_failed"
        result["column_mapping_status"] = "xml_parse_failed"

        result["notes"].append(
            str(
                xml_record.get("parse_error")
                or "XML parsing failed."
            )
        )

        return result

    fields = ordered_fields(
        xml_record.get("fields") or []
    )

    if not fields:
        result["measurement_coverage_status"] = "no_xml_fields"
        result["column_mapping_status"] = "no_xml_fields"

        result["notes"].append(
            "XML contains no usable field definitions."
        )

        return result

    # Preserve structural metadata warnings.
    # Deduplicate identical messages without modifying
    # the original metadata warning records.
    metadata_warnings = (
        xml_record.get("metadata_warnings") or []
    )

    seen_metadata_warning_messages = set()

    for warning in metadata_warnings:
        if not isinstance(warning, dict):
            continue

        code = str(warning.get("code") or "unknown")
        message = str(warning.get("message") or code)

        warning_key = (code, message)

        if warning_key in seen_metadata_warning_messages:
            continue

        seen_metadata_warning_messages.add(warning_key)

        result["notes"].append(
            f"XML metadata warning [{code}]: {message}"
        )

    time_idx, time_name, kind = pick_time_column(
        fields,
        axis_preference,
    )

    result["time_field"] = time_name or ""
    result["time_kind"] = kind or ""

    parser = PARSERS[kind][0] if kind else None

    skip = (
        {time_idx}
        if time_idx is not None
        else set()
    )

    numeric_indexes = numeric_column_indexes(
        fields,
        skip,
    )

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

            mapping, mapping_status, skip_header = (
                build_column_mapping(
                    first_row,
                    fields,
                    xml_record.get("has_header"),
                )
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
                    "CSV header order differs from XML; "
                    "columns mapped by name."
                )

            elif (
                mapping_status
                == "header_positional_duplicate_xml_names"
            ):
                result["notes"].append(
                    "XML contains duplicate field names. "
                    "Positional mapping was accepted because column "
                    "counts match, CSV header names are unique, and "
                    "all non-duplicated XML fields match their header "
                    "positions. Duplicate XML fields were mapped "
                    "by position without modifying source metadata."
                )

            elif (
                mapping_status
                == "header_positional_ws_aliases"
            ):
                result["notes"].append(
                    "WS CSV header contains two validated field-name "
                    "aliases at positions 15 and 16. All other XML "
                    "field names match their CSV header positions. "
                    "Positional mapping was used without modifying "
                    "the original XML metadata."
                )

            elif mapping_status == "positional_header_unknown":
                result["notes"].append(
                    "XML does not establish header presence; "
                    "positional mapping used."
                )

            # Stream rows without materializing the entire CSV.
            if skip_header:
                rows = reader
            else:
                rows = chain((first_row,), reader)

            for row in rows:

                if not row or not any(
                    value.strip()
                    for value in row
                ):
                    continue

                result["row_count"] += 1

                # Numeric measurements.
                for xml_index in numeric_indexes:
                    csv_index = mapping.get(xml_index)

                    if (
                        csv_index is None
                        or csv_index >= len(row)
                    ):
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

                # Time analysis.
                if time_idx is None or parser is None:
                    continue

                time_csv_index = mapping.get(time_idx)

                if (
                    time_csv_index is None
                    or time_csv_index >= len(row)
                ):
                    result["missing_timestamp_count"] += 1
                    continue

                raw_time = row[time_csv_index].strip()

                if raw_time.casefold() in MISSING_TEXT:
                    result["missing_timestamp_count"] += 1
                    continue

                try:
                    timestamp = parser(raw_time)
                except (
                    TypeError,
                    ValueError,
                    OverflowError,
                ):
                    timestamp = None

                if timestamp is None:
                    result["invalid_timestamp_count"] += 1
                    continue

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

                if (
                    minimum_timestamp is None
                    or timestamp < minimum_timestamp
                ):
                    minimum_timestamp = timestamp
                    first_raw = raw_time

                if (
                    maximum_timestamp is None
                    or timestamp > maximum_timestamp
                ):
                    maximum_timestamp = timestamp
                    last_raw = raw_time

    except (
        OSError,
        UnicodeError,
        csv.Error,
    ) as error:
        result["measurement_coverage_status"] = "read_failed"
        result["notes"].append(str(error))
        return result

    # Temporal span is based on minimum and maximum parsed
    # coordinates, not the first and last CSV rows.
    if minimum_timestamp is not None:
        result["first_time"] = first_raw
        result["last_time"] = last_raw

        result["span_seconds"] = round(
            maximum_timestamp - minimum_timestamp,
            6,
        )

    # Gap threshold uses the median positive adjacent step.
    if positive_steps:
        median_step = statistics.median(positive_steps)
        threshold = gap_factor * median_step

        gaps = [
            step
            for step in positive_steps
            if step > threshold
        ]

        result["median_step_seconds"] = round(
            median_step,
            6,
        )

        result["gap_count"] = len(gaps)

        if gaps:
            result["largest_gap_seconds"] = round(
                max(gaps),
                6,
            )

            result["gap_total_seconds"] = round(
                sum(gaps),
                6,
            )
        else:
            result["largest_gap_seconds"] = 0
            result["gap_total_seconds"] = 0

    if time_idx is None:
        result["measurement_coverage_status"] = (
            "time_field_not_detected"
        )

        result["notes"].append(
            "No supported time field was detected from XML metadata."
        )

    elif result["parsed_timestamp_count"] == 0:
        result["measurement_coverage_status"] = (
            "timestamps_not_interpreted"
        )

        result["notes"].append(
            "No values could be interpreted on the selected time axis."
        )

    elif result["row_count"] == 0:
        result["measurement_coverage_status"] = "no_data_rows"

    else:
        result["measurement_coverage_status"] = (
            "timestamp_analysis_available"
        )

    if kind and kind != "utc":
        result["notes"].append(
            f"Time axis: {PARSERS[kind][1]}. "
            "No UTC conversion was performed."
        )

    if result["out_of_order_count"]:
        result["notes"].append(
            "Out-of-order timestamps were detected; gap calculations "
            "use positive adjacent steps only."
        )

    result["notes"].append(
        "Gap totals are sums of detected timestamp intervals, "
        "not estimates of missing measurement duration."
    )

    return result


# --------------------------------------------------
# Analyze inventory
# --------------------------------------------------

def analyze_coverage(
    input_dir: Path,
    inventory_records: list[dict],
    metadata: dict,
    gap_factor: float = 2.5,
) -> list[dict]:

    metadata_index = build_metadata_index(metadata)
    reports = []

    for record in inventory_records:

        if (
            str(record.get("extension") or "").lower()
            != ".csv"
        ):
            continue

        sol_folder = str(
            record.get("sol_folder") or ""
        )

        filename = str(
            record.get("filename") or ""
        )

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
            "file_size_bytes": record.get(
                "file_size_bytes",
                "",
            ),
            "row_count": 0,
            "measurement_coverage_status": "not_analyzed",
            "column_mapping_status": "not_analyzed",
            "notes": "",
        }

        xml_record = find_xml_record(
            record,
            metadata_index,
        )

        csv_path = resolve_csv_path(
            input_dir,
            record,
        )

        if csv_path is None:
            report["measurement_coverage_status"] = "file_not_found"
            report["notes"] = (
                "CSV file could not be resolved on disk."
            )

            reports.append(report)
            continue

        if csv_path.stat().st_size == 0:
            report["measurement_coverage_status"] = "empty_file"
            report["notes"] = "CSV file has zero bytes."

            reports.append(report)
            continue

        analysis = analyze_csv(
            csv_path,
            xml_record,
            gap_factor=gap_factor,
        )

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

    best_start = best_end = values[0]
    current_start = current_end = values[0]

    for sol in values[1:]:
        if sol == current_end + 1:
            current_end = sol
        else:
            if (
                current_end - current_start
                > best_end - best_start
            ):
                best_start, best_end = (
                    current_start,
                    current_end,
                )

            current_start = current_end = sol

    if (
        current_end - current_start
        > best_end - best_start
    ):
        best_start, best_end = (
            current_start,
            current_end,
        )

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
            "longest_consecutive_sol_range": (
                longest_consecutive_range(present_sols)
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
            extrasaction="ignore",
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
        help=(
            "A gap is an adjacent positive time step greater than "
            "this factor multiplied by the median positive step."
        ),
    )

    args = parser.parse_args()

    if args.start_sol > args.end_sol:
        parser.error(
            "--start-sol must not exceed --end-sol"
        )

    if (
        not math.isfinite(args.gap_factor)
        or args.gap_factor <= 1
    ):
        parser.error(
            "--gap-factor must be finite and greater than 1"
        )

    print("Loading file inventory...")
    inventory = load_file_inventory(args.inventory)

    print("Loading XML metadata...")
    metadata = load_metadata_inventory(args.metadata)

    print("Analyzing CSV files...")
    reports = analyze_coverage(
        args.input,
        inventory,
        metadata,
        gap_factor=args.gap_factor,
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
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "analysis_range": {
            "start_sol": args.start_sol,
            "end_sol": args.end_sol,
        },
        "csv_files_analyzed": len(reports),
        "products": product_summaries,
        "gap_definition": {
            "factor": args.gap_factor,
            "rule": (
                "An adjacent positive timestamp step is classified "
                "as a gap when it exceeds gap_factor multiplied by "
                "the median positive adjacent step."
            ),
            "gap_total_seconds": (
                "Sum of detected gap intervals; not an estimate of "
                "missing measurement duration."
            ),
        },
        "interpretation_notes": [
            "File presence, row counts and timestamp parsing do not establish scientific validity.",
            "CSV columns are mapped using XML field names when a header is available.",
            "Duplicate XML field names may use validated positional mapping only when all non-duplicated fields match their CSV header positions and the CSV header uniquely distinguishes the duplicate positions.",
            "The known WS header aliases are accepted only at their validated positions and only when all other field names and the total column count match.",
            "Ambiguous column mappings are not used for measurement calculations.",
            "XML metadata warnings are preserved in the per-file coverage notes.",
            "Time axes are analyzed in their own coordinate systems and are not automatically converted to UTC.",
            "LMST and LTST numeric coordinates depend on the shared parser conventions and require validation against authoritative MEDA documentation.",
            "Product presence is not equivalent to continuous temporal coverage.",
        ],
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