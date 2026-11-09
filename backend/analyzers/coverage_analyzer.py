from __future__ import annotations

import argparse
import csv
import json
import math
import numbers
import os
import statistics
import sys

from array import array
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path, PurePosixPath

try:
    from .file_discovery import (  # noqa: F401
        SOL_FOLDER_PATTERN as SOL_PATTERN,
        PRODUCT_PATTERN,
        get_sol_number as _shared_get_sol_number,
        get_product_code as _shared_get_product_code,
    )
except ImportError:
    from file_discovery import (  # noqa: F401
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
        classify_special_constant,
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
        classify_special_constant,
        norm,
        numeric_column_indexes,
        ordered_fields,
        pick_time_column,
    )


DEFAULT_GAP_FACTOR = 2.5

# Worker selection ("optimized" mode).
OPTIMIZED_WORKERS = "optimized"
MAX_OPTIMIZED_WORKERS = 8
MIN_TASKS_FOR_PARALLEL = 4

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
    "special_error_count",
    "special_saturated_count",
    "special_unknown_count",
    "special_not_applicable_count",
    "special_ambiguous_count",
    "measurement_coverage_status",
    "column_mapping_status",
    "notes",
]

# Human readable notes attached to the non-trivial mapping modes.
MAPPING_NOTES = {
    "header_reordered_mapped": (
        "CSV header order differs from XML; "
        "columns mapped by name."
    ),
    "header_positional_duplicate_xml_names": (
        "XML contains duplicate field names. "
        "Positional mapping was accepted because column "
        "counts match, CSV header names are unique, and "
        "all non-duplicated XML fields match their header "
        "positions. Duplicate XML fields were mapped "
        "by position without modifying source metadata."
    ),
    "header_positional_ws_aliases": (
        "WS CSV header contains two validated field-name "
        "aliases at positions 15 and 16. All other XML "
        "field names match their CSV header positions. "
        "Positional mapping was used without modifying "
        "the original XML metadata."
    ),
    "positional_header_unknown": (
        "XML does not establish header presence; "
        "positional mapping used."
    ),
}


# --------------------------------------------------
# Identification and validation helpers
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


def validate_gap_factor(value) -> float:
    """
    Return gap_factor as a float or raise ValueError.

    Accepts only real numbers (bool and strings are rejected) that
    are finite and strictly greater than 1.
    """

    if (
        isinstance(value, bool)
        or not isinstance(value, numbers.Real)
        or not math.isfinite(value)
        or value <= 1
    ):
        raise ValueError(
            "gap_factor must be finite and greater than 1."
        )

    return float(value)


def _normalize_relative_path(value) -> str:
    """
    Normalize a relative path for platform-independent matching.

    Backslashes become slashes, duplicate separators, "." segments
    and trailing separators are collapsed, and the result is
    case-folded. Empty values and "." normalize to "".
    """

    if value is None:
        return ""

    text = str(value).replace("\\", "/")

    if not text.strip():
        return ""

    normalized = PurePosixPath(text).as_posix()

    return "" if normalized == "." else normalized.casefold()


def _safe_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except (OSError, ValueError):
        return False


def _safe_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except (OSError, ValueError):
        return False


def _lexically_within(base: Path, candidate: Path) -> bool:
    """
    True when candidate stays inside base after lexical
    normalization. Blocks "..", and absolute paths that escape
    the input directory. Symlinks are intentionally not resolved.
    """

    base_path = os.path.abspath(base)
    candidate_path = os.path.abspath(candidate)

    try:
        return (
            os.path.commonpath([base_path, candidate_path])
            == base_path
        )
    except ValueError:
        # Different drives (Windows) or mixed absolute/relative.
        return False


# --------------------------------------------------
# Load previous stage reports
# --------------------------------------------------

def load_file_inventory(path: Path) -> list[dict]:
    if not path.is_file():
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
    if not path.is_file():
        raise FileNotFoundError(
            f"Metadata inventory not found: {path}"
        )

    try:
        with path.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Metadata inventory is not valid JSON: {path} ({error})"
        ) from error

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
    Non-dict records are ignored.
    """

    index = defaultdict(list)

    for record in metadata.get("records", []):
        if not isinstance(record, dict):
            continue

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

            if (
                not normalized_path
                or normalized_path in indexed_paths
            ):
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

    normalized_csv_path = _normalize_relative_path(
        csv_record.get("relative_path")
    )

    if normalized_csv_path:
        try:
            xml_relative_path = (
                PurePosixPath(normalized_csv_path)
                .with_suffix(".xml")
                .as_posix()
            )
        except ValueError:
            xml_relative_path = ""

        if xml_relative_path:
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

    return matches[0] if len(matches) == 1 else None


# --------------------------------------------------
# CSV path resolution
# --------------------------------------------------

def _files_by_casefolded_name(sol_dir: Path) -> dict[str, list[Path]]:
    """
    All files below sol_dir, grouped by case-folded filename.

    os.walk is used because it silently skips unreadable
    directories instead of aborting the whole run.
    """

    by_name = defaultdict(list)

    for root, _dirs, files in os.walk(sol_dir):
        for name in files:
            path = Path(root) / name

            if _safe_is_file(path):
                by_name[name.casefold()].append(path)

    return by_name


def resolve_csv_path(
    input_dir: Path,
    inventory_record: dict,
    sol_dir_cache: dict | None = None,
) -> Path | None:
    """
    Resolve a CSV using its relative path when available.

    Security: candidates that escape input_dir (absolute paths,
    "..") are rejected. Backslashes in relative_path are treated
    as separators so Windows-generated inventories work on POSIX.

    Filename-only fallback is accepted only when unique inside
    the declared Sol directory.

    sol_dir_cache is optional. When one dict is shared between
    calls, each Sol directory is walked at most once instead of
    once per file.
    """

    relative_path = inventory_record.get("relative_path")

    if relative_path:
        candidate = input_dir / str(relative_path).replace("\\", "/")

        if (
            _lexically_within(input_dir, candidate)
            and _safe_is_file(candidate)
        ):
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

    if (
        not _lexically_within(input_dir, sol_dir)
        or not _safe_is_dir(sol_dir)
    ):
        return None

    direct = sol_dir / filename

    if _lexically_within(sol_dir, direct) and _safe_is_file(direct):
        return direct

    if sol_dir_cache is None:
        by_name = _files_by_casefolded_name(sol_dir)
    else:
        by_name = sol_dir_cache.get(sol_dir)

        if by_name is None:
            by_name = _files_by_casefolded_name(sol_dir)
            sol_dir_cache[sol_dir] = by_name

    matches = by_name.get(filename.casefold(), [])

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

    When the XML does not establish header presence
    (has_header is None) and the first row cannot be proven to be
    a header, positional mapping is used and the row is kept as
    data instead of rejecting the whole file.

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

    unknown = (
        positional_mapping,
        "positional_header_unknown",
        False,
    )

    if has_header is False:
        return (
            positional_mapping,
            "positional_no_header",
            False,
        )

    if header is None:
        if has_header is True:
            return None, "header_missing", False

        return unknown

    normalized_header = [
        normalize_name(value)
        for value in header
    ]

    if any(not name for name in normalized_header):
        if has_header is True:
            return None, "invalid_csv_header_names", False

        return unknown

    if len(set(normalized_header)) != len(normalized_header):
        if has_header is True:
            return None, "duplicate_csv_header_names", False

        return unknown

    if len(normalized_header) != len(normalized_fields):
        if has_header is True:
            return None, "header_column_count_mismatch", True

        return unknown

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

    duplicate_positions = {
        index
        for positions in positions_by_name.values()
        if len(positions) > 1
        for index in positions
    }

    if duplicate_positions:
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

                return unknown

        # CSV header names were already verified to be unique, so
        # duplicated XML positions always carry distinct names.
        return (
            positional_mapping,
            "header_positional_duplicate_xml_names",
            True,
        )

    # Strictly validated WS header aliases.
    # Only positions 15 and 16 may differ; all other fields and
    # the total column count must match.
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

        if differences == [15, 16] and all(
            ws_header_aliases.get(normalized_fields[index])
            == normalized_header[index]
            for index in differences
        ):
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
    return unknown
# --------------------------------------------------
# CSV analysis
# --------------------------------------------------

def _new_result() -> dict:
    return {
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
        "special_error_count": 0,
        "special_saturated_count": 0,
        "special_unknown_count": 0,
        "special_not_applicable_count": 0,
        "special_ambiguous_count": 0,
        "measurement_coverage_status": "not_assessed",
        "column_mapping_status": "not_assessed",
        "notes": [],
    }


def _metadata_warning_notes(xml_record: dict) -> list[str]:
    """
    Structural metadata warnings as note strings. Identical
    (code, message) pairs are emitted once; the original warning
    records are never modified.
    """

    warnings = xml_record.get("metadata_warnings") or []

    if not isinstance(warnings, (list, tuple)):
        return []

    notes = []
    seen = set()

    for warning in warnings:
        if not isinstance(warning, dict):
            continue

        code = str(warning.get("code") or "unknown")
        message = str(warning.get("message") or code)

        if (code, message) in seen:
            continue

        seen.add((code, message))
        notes.append(f"XML metadata warning [{code}]: {message}")

    return notes


def _is_blank_row(row: list[str]) -> bool:
    return not row or not "".join(row).strip()


def analyze_csv(
    csv_path: Path,
    xml_record: dict | None,
    axis_preference=DEFAULT_AXIS_PREFERENCE,
    gap_factor: float = DEFAULT_GAP_FACTOR,
) -> dict:

    gap_factor = validate_gap_factor(gap_factor)

    result = _new_result()

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

    result["notes"].extend(_metadata_warning_notes(xml_record))

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

    analyze_time = (
        time_idx is not None
        and parser is not None
    )

    # ---------------------------------------------
    # Hot-loop state.
    #
    # Counters are plain local integers (fast locals) and are
    # copied into `result` in the `finally` block below, which
    # also runs for every early return, so partial counts are
    # preserved.
    #
    # Memory: parsed timestamps are kept in a compact array of
    # C doubles (8 bytes each) instead of a Python set of floats
    # (~10x larger). Duplicates are derived afterwards:
    #   - no out-of-order rows -> duplicates are adjacent, so the
    #     number of zero-length steps is exact (no set needed);
    #   - otherwise -> parsed_count - number of distinct values.
    # ---------------------------------------------

    row_count = 0
    parsed_count = 0
    missing_count = 0
    invalid_count = 0
    out_of_order_count = 0
    zero_steps = 0

    numeric_value_count = 0
    numeric_missing_count = 0
    numeric_invalid_count = 0

    special_error_count = 0
    special_saturated_count = 0
    special_unknown_count = 0
    special_not_applicable_count = 0
    special_ambiguous_count = 0

    timestamps = array("d")
    positive_steps = array("d")

    # NaN makes the first step comparison neutral (neither
    # < 0 nor > 0), which replaces an `is not None` test per row.
    previous_timestamp = math.nan

    # Every parsed timestamp is finite, so +/-inf sentinels behave
    # exactly like an "is None" initial state.
    minimum_timestamp = math.inf
    maximum_timestamp = -math.inf

    first_raw = ""
    last_raw = ""

    try:
        with csv_path.open(
            "r",
            newline="",
            encoding="utf-8-sig",
            buffering=1024 * 1024,
        ) as file:

            reader = csv.reader(file)

            # Leading blank lines must not be mistaken for a header.
            first_row = next(reader, None)

            while first_row is not None and _is_blank_row(first_row):
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

            mapping_note = MAPPING_NOTES.get(mapping_status)

            if mapping_note:
                result["notes"].append(mapping_note)

            # Resolve column positions once, not once per row.
            numeric_csv_indexes = []
            unmapped_numeric_columns = 0

            for xml_index in numeric_indexes:
                csv_index = mapping.get(xml_index)

                if csv_index is None:
                    unmapped_numeric_columns += 1
                else:
                    numeric_csv_indexes.append(
                        (csv_index, fields[xml_index])
                    )

            time_csv_index = (
                mapping.get(time_idx)
                if analyze_time
                else None
            )

            # Stream rows without materializing the entire CSV.
            if skip_header:
                rows = reader
            else:
                rows = chain((first_row,), reader)

            # Local bindings.
            missing_text = MISSING_TEXT
            isfinite = math.isfinite
            parse = parser
            add_timestamp = timestamps.append
            add_step = positive_steps.append

            for row in rows:

                # Equivalent to: not any(v.strip() for v in row)
                if not row or not "".join(row).strip():
                    continue

                row_count += 1
                row_length = len(row)

                # Numeric measurements.
                numeric_missing_count += unmapped_numeric_columns

                for csv_index, field in numeric_csv_indexes:
                    if csv_index >= row_length:
                        numeric_missing_count += 1
                        continue

                    raw = row[csv_index].strip()

                    # XML Special Constants are metadata classifications.
                    # They are never added to the numeric measurement values.
                    special_category = classify_special_constant(
                        raw,
                        field,
                    )

                    if special_category == "missing_constant":
                        numeric_missing_count += 1
                        continue

                    if special_category == "invalid_constant":
                        numeric_invalid_count += 1
                        continue

                    if special_category == "error_constant":
                        special_error_count += 1
                        continue

                    if special_category == "saturated_constant":
                        special_saturated_count += 1
                        continue

                    if special_category == "unknown_constant":
                        special_unknown_count += 1
                        continue

                    if special_category == "not_applicable_constant":
                        special_not_applicable_count += 1
                        continue

                    if special_category == "ambiguous_special_constant":
                        special_ambiguous_count += 1
                        continue

                    if raw.casefold() in missing_text:
                        numeric_missing_count += 1
                        continue

                    try:
                        number = float(raw)
                    except (
                        TypeError,
                        ValueError,
                        OverflowError,
                    ):
                        numeric_invalid_count += 1
                        continue

                    if isfinite(number):
                        numeric_value_count += 1
                    else:
                        numeric_invalid_count += 1

                # Time analysis.
                if not analyze_time:
                    continue

                if (
                    time_csv_index is None
                    or time_csv_index >= row_length
                ):
                    missing_count += 1
                    continue

                raw_time = row[time_csv_index].strip()

                if raw_time.casefold() in missing_text:
                    missing_count += 1
                    continue

                try:
                    timestamp = parse(raw_time)
                except (
                    TypeError,
                    ValueError,
                    OverflowError,
                ):
                    timestamp = None

                if timestamp is None:
                    invalid_count += 1
                    continue

                try:
                    timestamp = float(timestamp)
                except (
                    TypeError,
                    ValueError,
                    OverflowError,
                ):
                    invalid_count += 1
                    continue

                if not isfinite(timestamp):
                    invalid_count += 1
                    continue

                parsed_count += 1
                add_timestamp(timestamp)

                step = timestamp - previous_timestamp

                if step < 0:
                    out_of_order_count += 1
                elif step > 0:
                    add_step(step)
                elif step == 0:
                    zero_steps += 1

                previous_timestamp = timestamp

                if timestamp < minimum_timestamp:
                    minimum_timestamp = timestamp
                    first_raw = raw_time

                if timestamp > maximum_timestamp:
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

    finally:
        result["row_count"] = row_count
        result["parsed_timestamp_count"] = parsed_count
        result["missing_timestamp_count"] = missing_count
        result["invalid_timestamp_count"] = invalid_count

        if out_of_order_count == 0:
            result["duplicate_timestamp_count"] = zero_steps
        else:
            result["duplicate_timestamp_count"] = (
                parsed_count - len(set(timestamps))
            )

        result["out_of_order_count"] = out_of_order_count
        result["numeric_value_count"] = numeric_value_count
        result["numeric_missing_count"] = numeric_missing_count
        result["numeric_invalid_count"] = numeric_invalid_count

        result["special_error_count"] = special_error_count
        result["special_saturated_count"] = special_saturated_count
        result["special_unknown_count"] = special_unknown_count
        result["special_not_applicable_count"] = (
            special_not_applicable_count
        )
        result["special_ambiguous_count"] = special_ambiguous_count

    # Temporal span is based on minimum and maximum parsed
    # coordinates, not the first and last CSV rows.
    if parsed_count:
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

    if row_count == 0:
        # Header-only file (or only blank lines after the header).
        result["measurement_coverage_status"] = "no_data_rows"

        result["notes"].append(
            "CSV contains no data rows."
        )

    elif time_idx is None:
        result["measurement_coverage_status"] = (
            "time_field_not_detected"
        )

        result["notes"].append(
            "No supported time field was detected from XML metadata."
        )

    elif parsed_count == 0:
        result["measurement_coverage_status"] = (
            "timestamps_not_interpreted"
        )

        result["notes"].append(
            "No values could be interpreted on the selected time axis."
        )

    else:
        result["measurement_coverage_status"] = (
            "timestamp_analysis_available"
        )

    if kind and kind != "utc":
        result["notes"].append(
            f"Time axis: {PARSERS[kind][1]}. "
            "No UTC conversion was performed."
        )

    if out_of_order_count:
        result["notes"].append(
            "Out-of-order timestamps were detected; gap calculations "
            "use positive adjacent steps only."
        )

    result["notes"].append(
        "Gap totals are sums of detected timestamp intervals, "
        "not estimates of missing measurement duration."
    )

    return result
def analyze_csv_safely(
    csv_path: Path,
    xml_record: dict | None,
    gap_factor: float = DEFAULT_GAP_FACTOR,
) -> dict:
    """
    analyze_csv that never lets one bad file abort a whole run.

    An invalid gap_factor is a caller error and still raises.
    Any unexpected error while analyzing the file is converted
    into an ``analysis_failed`` result.
    """

    gap_factor = validate_gap_factor(gap_factor)

    try:
        return analyze_csv(
            csv_path,
            xml_record,
            gap_factor=gap_factor,
        )
    except Exception as error:  # noqa: BLE001 - deliberate isolation
        result = _new_result()
        result["measurement_coverage_status"] = "analysis_failed"
        result["column_mapping_status"] = "analysis_failed"
        result["notes"].append(
            f"Unexpected analysis error: "
            f"{type(error).__name__}: {error}"
        )
        return result


# --------------------------------------------------
# Analyze inventory
# --------------------------------------------------

def _analyze_task(task: tuple) -> dict:
    """
    Process-pool entry point (must be a module-level function).

    task = (csv_path, xml_record, gap_factor)
    """
    csv_path, xml_record, gap_factor = task

    return analyze_csv_safely(
        csv_path,
        xml_record,
        gap_factor=gap_factor,
    )


def _apply_analysis(report: dict, analysis: dict) -> None:
    for key, value in analysis.items():
        if key == "notes":
            report[key] = "; ".join(value)
        else:
            report[key] = value


def choose_workers(
    requested,
    task_count: int,
    cpu_count: int | None = None,
) -> int:
    """
    Resolve a ``workers`` setting into a concrete process count.

    requested:
        An int >= 1 (explicit) or the string "optimized".
    task_count:
        Number of CSV files that may be analyzed.
    cpu_count:
        Override for os.cpu_count() (useful for tests).

    Rules:
        - explicit n  -> min(n, task_count), never below 1;
        - "optimized" -> 1 for fewer than MIN_TASKS_FOR_PARALLEL
          files, otherwise min(cpus - 1, MAX_OPTIMIZED_WORKERS,
          task_count), never below 1.

    Pure function: no I/O and no side effects.
    """

    if (
        isinstance(task_count, bool)
        or not isinstance(task_count, int)
        or task_count < 0
    ):
        raise ValueError("task_count must be an integer >= 0.")

    message = "workers must be an integer >= 1 or 'optimized'."

    if isinstance(requested, str):
        if requested.strip().casefold() != OPTIMIZED_WORKERS:
            raise ValueError(message)

        if task_count < MIN_TASKS_FOR_PARALLEL:
            return 1

        cpus = cpu_count if cpu_count is not None else (os.cpu_count() or 1)

        return max(
            1,
            min(cpus - 1, MAX_OPTIMIZED_WORKERS, task_count),
        )

    if (
        isinstance(requested, bool)
        or not isinstance(requested, int)
        or requested < 1
    ):
        raise ValueError(message)

    return max(1, min(requested, task_count))


def _record_extension(record: dict, filename: str) -> str:
    """Extension from the inventory, else from the filename."""

    extension = str(
        record.get("extension") or Path(filename).suffix or ""
    ).strip().lower()

    if extension and not extension.startswith("."):
        extension = "." + extension

    return extension


def count_csv_records(inventory_records: list[dict]) -> int:
    """Number of inventory records that describe a CSV file."""

    return sum(
        1
        for record in inventory_records
        if _record_extension(
            record,
            str(record.get("filename") or ""),
        ) == ".csv"
    )


def analyze_coverage(
    input_dir: Path,
    inventory_records: list[dict],
    metadata: dict,
    gap_factor: float = DEFAULT_GAP_FACTOR,
    workers: int = 1,
) -> list[dict]:
    """
    Analyze every CSV in the inventory.

    workers=1 (default) runs sequentially in this process.
    workers>1 analyzes files in a process pool. Files are
    independent and the results are small, so the output
    (content and order) is identical to the sequential run.
    A failure inside one file never aborts the run.
    """

    if (
        isinstance(workers, bool)
        or not isinstance(workers, int)
        or workers < 1
    ):
        raise ValueError("workers must be an integer >= 1.")

    gap_factor = validate_gap_factor(gap_factor)

    metadata_index = build_metadata_index(metadata)
    sol_dir_cache = {}

    reports = []
    pending = []

    for record in inventory_records:
        filename = str(
            record.get("filename") or ""
        )

        if _record_extension(record, filename) != ".csv":
            continue

        sol_folder = str(
            record.get("sol_folder") or ""
        )

        # Sol 0 is a valid Sol: do not use `or` to pick a default.
        folder_sol = get_sol_number(sol_folder)

        sol_number = safe_int(
            record.get("sol_number"),
            -1 if folder_sol is None else folder_sol,
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

        csv_path = resolve_csv_path(
            input_dir,
            record,
            sol_dir_cache,
        )

        if csv_path is None:
            report["measurement_coverage_status"] = "file_not_found"
            report["notes"] = (
                "CSV file could not be resolved on disk."
            )

            reports.append(report)
            continue

        try:
            size = csv_path.stat().st_size
        except OSError as error:
            report["measurement_coverage_status"] = "read_failed"
            report["notes"] = str(error)

            reports.append(report)
            continue

        if report["file_size_bytes"] in ("", None):
            report["file_size_bytes"] = size

        if size == 0:
            report["measurement_coverage_status"] = "empty_file"
            report["notes"] = "CSV file has zero bytes."

            reports.append(report)
            continue

        xml_record = find_xml_record(
            record,
            metadata_index,
        )

        if workers == 1:
            _apply_analysis(
                report,
                analyze_csv_safely(
                    csv_path,
                    xml_record,
                    gap_factor=gap_factor,
                ),
            )
        else:
            pending.append(
                (report, (csv_path, xml_record, gap_factor))
            )

        reports.append(report)

    if pending:
        chunk_size = max(1, len(pending) // (workers * 4))

        try:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                analyses = executor.map(
                    _analyze_task,
                    [task for _, task in pending],
                    chunksize=chunk_size,
                )

                for (report, _), analysis in zip(pending, analyses):
                    _apply_analysis(report, analysis)
        except (BrokenProcessPool, OSError, NotImplementedError):
            # The pool could not start or died (restricted
            # environment, frozen build...). Fall back to the
            # sequential path; _apply_analysis overwrites any
            # partially applied results.
            for report, task in pending:
                _apply_analysis(report, _analyze_task(task))

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
    """
    Build product summaries using only reports inside the
    inclusive Sol range.

    Reports outside the requested range do not contribute to
    product counts, row totals, timestamp totals, or present Sols.
    """

    products = defaultdict(list)

    for report in reports:
        product = report.get("product_code")
        sol = report.get("sol_number")

        # Reject booleans explicitly because bool is an int subclass.
        if (
            not product
            or not isinstance(sol, int)
            or isinstance(sol, bool)
            or sol < start_sol
            or sol > end_sol
            or safe_int(report.get("row_count")) <= 0
        ):
            continue

        products[product].append(report)

    summaries = {}

    for product, records in sorted(products.items()):

        present_set = {
            record["sol_number"]
            for record in records
        }

        present_sols = sorted(present_set)

        missing_sols = [
            sol
            for sol in range(start_sol, end_sol + 1)
            if sol not in present_set
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
            "total_numeric_missing": sum(
                safe_int(record.get("numeric_missing_count"))
                for record in records
            ),
            "total_numeric_invalid": sum(
                safe_int(record.get("numeric_invalid_count"))
                for record in records
            ),
            "total_special_error": sum(
                safe_int(record.get("special_error_count"))
                for record in records
            ),
            "total_special_saturated": sum(
                safe_int(record.get("special_saturated_count"))
                for record in records
            ),
            "total_special_unknown": sum(
                safe_int(record.get("special_unknown_count"))
                for record in records
            ),
            "total_special_not_applicable": sum(
                safe_int(record.get("special_not_applicable_count"))
                for record in records
            ),
            "total_special_ambiguous": sum(
                safe_int(record.get("special_ambiguous_count"))
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

def _write_atomically(output_file: Path, write, **open_kwargs) -> None:
    """
    Write to ``<name>.tmp`` and then replace the target, so a crash
    or serialization error never leaves a truncated report and never
    destroys a previous good one.
    """

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = output_file.with_name(output_file.name + ".tmp")

    try:
        with temporary.open("w", **open_kwargs) as file:
            write(file)

        os.replace(temporary, output_file)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass

        raise


def save_coverage_csv(
    reports: list[dict],
    output_file: Path,
) -> None:

    def write(file) -> None:
        writer = csv.DictWriter(
            file,
            fieldnames=REPORT_COLUMNS,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(reports)

    _write_atomically(
        output_file,
        write,
        newline="",
        encoding="utf-8-sig",
    )


def save_summary_json(
    summary: dict,
    output_file: Path,
) -> None:

    def write(file) -> None:
        json.dump(
            summary,
            file,
            indent=4,
            ensure_ascii=False,
        )

    _write_atomically(
        output_file,
        write,
        encoding="utf-8",
    )


# --------------------------------------------------
# Main
# --------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
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
        default=DEFAULT_GAP_FACTOR,
        help=(
            "A gap is an adjacent positive time step greater than "
            "this factor multiplied by the median positive step."
        ),
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "Number of worker processes for CSV analysis "
            "(0 = one per CPU). Results are identical for any "
            "value. Default: 1"
        ),
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.start_sol > args.end_sol:
        parser.error(
            "--start-sol must not exceed --end-sol"
        )

    try:
        gap_factor = validate_gap_factor(args.gap_factor)
    except ValueError:
        parser.error(
            "--gap-factor must be finite and greater than 1"
        )

    if args.workers < 0:
        parser.error(
            "--workers must be 0 (auto) or greater"
        )

    try:
        print("Loading file inventory...")
        inventory = load_file_inventory(args.inventory)

        # --workers 0 means "optimized": pick from CPU and file count.
        csv_count = count_csv_records(inventory)

        workers = (
            args.workers
            if args.workers
            else choose_workers(OPTIMIZED_WORKERS, csv_count)
        )

        print("Loading XML metadata...")
        metadata = load_metadata_inventory(args.metadata)

        print("Analyzing CSV files...")
        reports = analyze_coverage(
            args.input,
            inventory,
            metadata,
            gap_factor=gap_factor,
            workers=workers,
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
            "coverage_status_counts": dict(
                sorted(
                    Counter(
                        report.get("measurement_coverage_status")
                        for report in reports
                    ).items()
                )
            ),
            "products": product_summaries,
            "gap_definition": {
                "factor": gap_factor,
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
                "XML Special Constants are used only to classify matching CSV values; the metadata definitions themselves are never treated as measurement values.",
                "Values matching missing_constant and invalid_constant contribute to the corresponding numeric counters.",
                "Error, saturated, unknown, and not-applicable special values are counted separately and are not counted as valid numeric measurements.",
                "Values matching multiple special-constant categories are counted as ambiguous and are excluded from the numeric value, missing, and invalid counters.",
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
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print("")
    print("Coverage analysis completed.")
    print(f"CSV files analyzed: {len(reports)}")
    print(f"Products found: {len(product_summaries)}")
    print(f"Coverage report: {args.output.resolve()}")
    print(f"Coverage summary: {args.summary.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())