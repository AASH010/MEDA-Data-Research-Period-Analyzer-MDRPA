from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import statistics

from array import array
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import chain, combinations, islice
from pathlib import Path, PurePosixPath
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
    except (TypeError, ValueError, OverflowError):
        return default


def get_sol_number(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        pass

    match = SOL_PATTERN.match(str(value).strip())

    return int(match.group(1)) if match else None


def inventory_sol_number(inventory_row: dict) -> int | None:
    """
    Sol number of an inventory row: sol_number first,
    sol_folder as the fallback.
    """
    sol_number = get_sol_number(
        inventory_row.get("sol_number")
    )

    if sol_number is None:
        sol_number = get_sol_number(
            inventory_row.get("sol_folder")
        )

    return sol_number


def portable_path(value: Any) -> str:
    """
    Normalize Windows and POSIX separators.

    This does not change path case because filesystem path
    identity and metadata matching have different requirements.
    """
    return str(value or "").strip().replace("\\", "/")


def normalize_path(value: Any) -> str:
    """
    Normalize separators and case for metadata path matching.

    Metadata path matching remains case-insensitive, preserving
    the analyzer's existing matching behavior.
    """
    return portable_path(value).casefold()


def portable_stem(value: Any) -> str:
    """
    Extract a filename stem consistently across Windows and POSIX.

    pathlib.Path on POSIX does not treat backslashes as separators.
    PurePosixPath works after portable separator normalization.
    """
    return PurePosixPath(
        portable_path(value)
    ).stem.casefold()


def file_identity(path: Path) -> str:
    """
    Return a normalized identity for an existing file path.

    os.path.normcase applies the host platform's path normalization:
    - Windows: case-insensitive path normalization.
    - POSIX: preserves case-sensitive path distinctions.

    resolve() also normalizes relative path components and symlinks.
    """
    return os.path.normcase(
        str(path.resolve())
    )


def is_missing(value: Any) -> bool:
    return (
        value is None
        or str(value).strip().casefold() in MISSING_TEXT
    )


def get_metadata_relative_path(record: dict) -> str:
    """
    Prefer the XML parser's source_relative_path.

    Keep relative_path as a compatibility fallback for
    older metadata records.
    """
    return str(
        record.get("source_relative_path")
        or record.get("relative_path")
        or ""
    ).strip()


def get_inventory_relative_path(record: dict) -> str:
    return str(
        record.get("relative_path")
        or record.get("source_relative_path")
        or ""
    ).strip()


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
    Keep all metadata matches.

    Do not silently overwrite records that share a filename stem
    or relative path.
    """

    by_sol_name = defaultdict(list)
    by_stem = defaultdict(list)
    by_path = defaultdict(list)

    for record in records:
        source_file = str(
            record.get("source_file") or ""
        ).strip()

        if not source_file:
            continue

        stem = portable_stem(source_file)
        sol_number = metadata_sol_number(record)

        if sol_number is not None:
            by_sol_name[(sol_number, stem)].append(record)

        by_stem[stem].append(record)

        relative_path = get_metadata_relative_path(record)

        if relative_path:
            by_path[
                normalize_path(relative_path)
            ].append(record)

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
    ).strip()

    if not filename:
        return None, "missing_inventory_filename"

    stem = portable_stem(filename)

    # Priority 1: exact relative path.
    relative_path = get_inventory_relative_path(
        inventory_row
    )

    if relative_path:
        csv_relative = PurePosixPath(
            portable_path(relative_path)
        )

        xml_relative = normalize_path(
            csv_relative.with_suffix(".xml")
        )

        matches = index["by_path"].get(
            xml_relative,
            [],
        )

        if len(matches) == 1:
            return matches[0], "matched_by_relative_path"

        if len(matches) > 1:
            return None, "ambiguous_metadata_path"

    # Priority 2: Sol number + filename stem.
    sol_number = inventory_sol_number(inventory_row)

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

class FileIndex:
    """
    Lazy filename index of the input tree.

    The tree is walked at most once (on the first fallback lookup)
    instead of once per CSV file. The index stores traversal paths
    grouped by case-folded filename; every candidate is still
    validated by resolve_csv_path's safe_file() at lookup time, so
    symlink and path-traversal rules are unchanged.
    """

    def __init__(self) -> None:
        self._root: Path | None = None
        self._by_name: dict[str, list[Path]] | None = None

    def candidates(
        self,
        root: Path,
        filename: str,
    ) -> list[Path]:

        if self._by_name is None or self._root != root:
            by_name = defaultdict(list)

            for path in root.rglob("*"):
                by_name[path.name.casefold()].append(path)

            self._by_name = by_name
            self._root = root

        return self._by_name.get(filename.casefold(), [])


def resolve_csv_path(
    input_root: Path,
    inventory_row: dict,
    file_index: FileIndex | None = None,
) -> Path | None:
    """
    Resolve an inventory CSV path strictly inside input_root.

    Relative path has priority. Filename fallback is accepted only
    when it resolves uniquely inside the input root.

    Symbolic links and path traversal outside input_root are rejected.

    file_index is optional. Passing one shared FileIndex avoids
    re-walking the input tree for every file.
    """
    try:
        root = Path(input_root).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None

    if not root.is_dir():
        return None

    if file_index is None:
        file_index = FileIndex()

    def safe_file(candidate: Path) -> Path | None:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            return None

        return resolved if resolved.is_file() else None

    filename = portable_path(
        inventory_row.get("filename")
    )

    if not filename:
        return None

    filename = PurePosixPath(filename).name

    if not filename:
        return None

    relative_path = get_inventory_relative_path(
        inventory_row
    )

    if relative_path:
        candidate = root / Path(
            portable_path(relative_path)
        )

        resolved = safe_file(candidate)

        if resolved is not None:
            return resolved

    sol_folder = portable_path(
        inventory_row.get("sol_folder")
    )

    if sol_folder:
        sol_directory = None

        try:
            candidate_directory = (
                root / Path(sol_folder)
            ).resolve()
            candidate_directory.relative_to(root)

            if candidate_directory.is_dir():
                sol_directory = candidate_directory
        except (OSError, RuntimeError, ValueError):
            pass

        if sol_directory is not None:
            direct = safe_file(sol_directory / filename)

            if direct is not None:
                return direct

            matches = []

            for path in file_index.candidates(root, filename):
                try:
                    path.relative_to(sol_directory)
                except ValueError:
                    continue

                resolved = safe_file(path)

                if resolved is not None:
                    matches.append(resolved)

            if len(matches) == 1:
                return matches[0]

            if len(matches) > 1:
                return None

    matches = []

    for path in file_index.candidates(root, filename):
        resolved = safe_file(path)

        if resolved is not None:
            matches.append(resolved)

    return matches[0] if len(matches) == 1 else None


# ---------------------------------------------------------
# CSV column mapping
# ---------------------------------------------------------

def build_column_mapping(
    first_row: list[str],
    fields: list[dict],
    has_header: Any,
) -> tuple[dict[int, int] | None, bool, str]:
    """
    Build a safe XML-field-to-CSV-column mapping.

    Supported mapping strategies:

    1. Exact header match.
    2. Reordered unique headers.
    3. Validated RHS duplicate XML names using positional mapping.
    4. Validated WS aliases at the exact known positions.
    5. Positional mapping only when XML explicitly states
       that the CSV has no header.

    Unknown header status is not treated as proof of a
    headerless CSV.
    """

    if not fields:
        return None, False, "no_xml_fields"

    field_names = [
        norm(field.get("name") or "")
        for field in fields
    ]

    if any(not name for name in field_names):
        return None, False, "invalid_xml_field_names"

    header_names = [
        norm(value)
        for value in first_row
    ]

    if not header_names:
        return None, False, "empty_csv_header"

    if len(header_names) != len(field_names):
        return None, False, "column_count_mismatch"

    # CSV header names must be unique for name-based mapping.
    if len(set(header_names)) != len(header_names):
        return None, False, "duplicate_csv_header_names"

    field_counts = Counter(field_names)
    has_duplicate_xml_names = any(
        count > 1
        for count in field_counts.values()
    )

    # Exact header match.
    if header_names == field_names:
        return (
            {index: index for index in range(len(fields))},
            True,
            "header_exact_match",
        )

    # -----------------------------------------------------
    # WS-specific aliases.
    #
    # Expected alias names are normalized using the same
    # function as XML and CSV field names.
    # Exactly 18 fields are required.
    # Only positions 15 and 16 may differ.
    # -----------------------------------------------------

    if (
        len(fields) == 18
        and not has_duplicate_xml_names
    ):
        expected_aliases = {
            15: (
                norm("BOOM1_ALG_IN_STABLE_STATE"),
                norm("BOOM1_ALG_STATE_STABLE"),
            ),
            16: (
                norm("BOOM2_ALG_IN_STABLE_STATE"),
                norm("BOOM2_ALG_STATE_STABLE"),
            ),
        }

        differences = [
            index
            for index, (xml_name, csv_name)
            in enumerate(zip(field_names, header_names))
            if xml_name != csv_name
        ]

        aliases_match = (
            set(differences) == {15, 16}
            and all(
                (
                    field_names[index],
                    header_names[index],
                ) == expected_aliases[index]
                for index in differences
            )
        )

        if aliases_match:
            return (
                {index: index for index in range(len(fields))},
                True,
                "header_positional_ws_aliases",
            )

    # -----------------------------------------------------
    # RHS duplicate XML names.
    #
    # Safe positional mapping requires:
    # - same XML and CSV column count;
    # - unique CSV header names;
    # - every non-duplicate XML field matches the CSV
    #   header at the same position;
    # - duplicate XML-name positions have distinct,
    #   non-empty CSV header names.
    #
    # This does not rename or modify XML source metadata.
    # -----------------------------------------------------

    if has_duplicate_xml_names:
        duplicate_positions = {
            name: [
                index
                for index, candidate in enumerate(field_names)
                if candidate == name
            ]
            for name, count in field_counts.items()
            if count > 1
        }

        all_duplicate_indices = {
            index
            for positions in duplicate_positions.values()
            for index in positions
        }

        non_duplicate_positions_match = all(
            field_names[index] == header_names[index]
            for index in range(len(fields))
            if index not in all_duplicate_indices
        )

        duplicate_headers_are_distinct = all(
            len({
                header_names[index]
                for index in positions
            }) == len(positions)
            and all(
                header_names[index]
                for index in positions
            )
            for positions in duplicate_positions.values()
        )

        if (
            non_duplicate_positions_match
            and duplicate_headers_are_distinct
        ):
            return (
                {index: index for index in range(len(fields))},
                True,
                "header_positional_duplicate_xml_names",
            )

        return (
            None,
            False,
            "duplicate_xml_names_mapping_ambiguous",
        )

    # -----------------------------------------------------
    # Reordered unique headers.
    # -----------------------------------------------------

    positions = {
        name: index
        for index, name in enumerate(header_names)
    }

    if all(name in positions for name in field_names):
        mapping = {
            xml_index: positions[name]
            for xml_index, name in enumerate(field_names)
        }

        return mapping, True, "header_reordered_mapped"

    # Explicitly declared header but no safe mapping.
    if has_header is True:
        return None, False, "header_mapping_ambiguous"

    # Partial match: cannot safely decide whether the first
    # row is a header or data.
    if set(field_names).intersection(header_names):
        return None, False, "partial_header_match"

    # Unknown header status is not sufficient evidence
    # for positional no-header mapping.
    if has_header is None:
        return None, False, "header_status_unknown"

    # Positional mapping is allowed only when XML explicitly
    # declares that the CSV has no header.
    if has_header is False:
        return (
            {index: index for index in range(len(fields))},
            False,
            "positional_no_header",
        )

    return None, False, "header_mapping_ambiguous"


# ---------------------------------------------------------
# File-level report helpers
# ---------------------------------------------------------

def empty_file_report(
    inventory_row: dict,
    status: str,
    notes: str,
) -> dict:

    return {
        "sol_number": inventory_sol_number(inventory_row),
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


# ---------------------------------------------------------
# File-level timestamp analysis
# ---------------------------------------------------------

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

    fields = ordered_fields(
        xml_record.get("fields") or []
    )

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

    timestamps: list[float] = []
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

            # Stream rows without expanding the complete reader.
            rows = reader

            if not skip_header:
                rows = chain((first_row,), reader)

            # Local bindings for the hot loop.
            append = timestamps.append
            missing_text = MISSING_TEXT
            isfinite = math.isfinite
            parse = time_parser

            for row in rows:

                # Equivalent to: not any(str(v).strip() for v in row)
                if not row or not "".join(row).strip():
                    continue

                total_rows += 1

                if csv_time_index >= len(row):
                    missing_count += 1
                    continue

                raw_value = row[csv_time_index].strip()

                if raw_value.casefold() in missing_text:
                    missing_count += 1
                    continue

                try:
                    parsed_value = parse(raw_value)
                except (
                    TypeError,
                    ValueError,
                    OverflowError,
                ):
                    parsed_value = None

                if parsed_value is None:
                    invalid_count += 1
                    continue

                # Inlined safe_float().
                try:
                    timestamp = float(parsed_value)
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

                if (
                    previous_timestamp is not None
                    and timestamp < previous_timestamp
                ):
                    out_of_order_count += 1

                previous_timestamp = timestamp
                append(timestamp)

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

    # If no decreasing step was seen, the list is already sorted;
    # skip the extra sorted copy.
    if out_of_order_count:
        sorted_timestamps = sorted(timestamps)
    else:
        sorted_timestamps = timestamps

    # One pass over the sorted values:
    # - a strictly positive step is recorded;
    # - an equal neighbour is a duplicate occurrence
    #   (identical to sum(count - 1) over a Counter).
    positive_steps = array("d")
    add_step = positive_steps.append
    duplicate_count = 0

    previous = sorted_timestamps[0]

    for current in islice(sorted_timestamps, 1, None):
        if current > previous:
            add_step(current - previous)
        else:
            duplicate_count += 1

        previous = current

    median_step = (
        round(statistics.median(positive_steps), 6)
        if positive_steps
        else ""
    )

    notes = [
        f"Column mapping: {mapping_status}."
    ]

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
        "parsed_timestamps": len(sorted_timestamps),
        "missing_timestamps": missing_count,
        "invalid_timestamps": invalid_count,
        "duplicate_timestamps": duplicate_count,
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

def _match_range(
    first,
    i: int,
    i_end: int,
    second,
    j: int,
    j_end: int,
    tolerance: float,
) -> tuple[int, array]:
    """
    Two-pointer one-to-one matching over sorted slices
    first[i:i_end] and second[j:j_end], without copying them.

    Each timestamp occurrence can participate in at most
    one match. Duplicate timestamps remain separate observations.

    Inputs must already be sorted in ascending order.
    """

    differences = array("d")
    add_difference = differences.append
    matched = 0

    while i < i_end and j < j_end:

        a = first[i]
        b = second[j]

        absolute_difference = abs(a - b)

        if absolute_difference <= tolerance:
            matched += 1
            add_difference(absolute_difference)
            i += 1
            j += 1

        elif a < b:
            i += 1

        else:
            j += 1

    return matched, differences


def match_one_to_one(
    first: list[float],
    second: list[float],
    tolerance: float,
) -> tuple[int, list[float]]:
    """
    Match timestamp occurrences one-to-one.

    Each timestamp occurrence can participate in at most
    one match. Duplicate timestamps remain separate observations.

    Inputs are sorted locally to make this public function safe
    when called directly with unsorted timestamp lists.

    The two-pointer strategy produces a maximum-cardinality
    matching for sorted one-dimensional values under a fixed
    absolute tolerance.
    """

    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError(
            "Tolerance must be finite and non-negative."
        )

    first = sorted(first)
    second = sorted(second)

    matched, differences = _match_range(
        first,
        0,
        len(first),
        second,
        0,
        len(second),
        tolerance,
    )

    return matched, list(differences)


def _compare_sorted_series(
    first,
    second,
    tolerance: float,
    kind_first: str,
    kind_second: str,
) -> dict:
    """
    Same as compare_timestamp_series, but the caller guarantees
    that both sequences are already sorted ascending.
    """

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

    if not len(first) or not len(second):
        result["comparison_status"] = "empty_series"
        result["notes"] = "At least one timestamp series is empty."
        return result

    overlap_start = max(first[0], second[0])
    overlap_end = min(first[-1], second[-1])

    if overlap_start > overlap_end:
        result["comparison_status"] = "no_temporal_overlap"
        result["notes"] = "The timestamp series do not overlap."
        return result

    # Observations inside the common closed interval, located by
    # binary search instead of copying filtered lists.
    first_lo = bisect_left(first, overlap_start)
    first_hi = bisect_right(first, overlap_end)

    second_lo = bisect_left(second, overlap_start)
    second_hi = bisect_right(second, overlap_end)

    matched, differences = _match_range(
        first,
        first_lo,
        first_hi,
        second,
        second_lo,
        second_hi,
        tolerance,
    )

    first_count = first_hi - first_lo
    second_count = second_hi - second_lo

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

    if len(differences):
        # statistics.mean is kept on purpose: it is exactly rounded,
        # so reports stay identical to the previous version.
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


def compare_timestamp_series(
    first: list[float],
    second: list[float],
    tolerance: float,
    kind_first: str,
    kind_second: str,
) -> dict:
    """
    Public entry point. Accepts unsorted input and sorts copies,
    retaining every duplicate occurrence.
    """

    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError(
            "Tolerance must be finite and non-negative."
        )

    return _compare_sorted_series(
        sorted(first),
        sorted(second),
        tolerance,
        kind_first,
        kind_second,
    )


# ---------------------------------------------------------
# Full analysis
# ---------------------------------------------------------

def _process_csv_row(
    position: int,
    total: int,
    inventory_row: dict,
    input_root: Path,
    file_index: FileIndex,
    metadata_index: dict,
    processed_paths: set,
    axis_preference,
    file_reports: list[dict],
    series_by_sol: dict,
) -> None:
    """
    Analyse one inventory CSV row.

    Appends exactly one report to file_reports (or none for a
    duplicate path) and, for analysed files with a known Sol,
    stores the compact timestamp series in series_by_sol.
    """

    csv_path = resolve_csv_path(
        input_root,
        inventory_row,
        file_index,
    )

    if csv_path is None:
        file_reports.append(
            empty_file_report(
                inventory_row,
                "file_not_found_or_ambiguous",
                "CSV path could not be resolved uniquely.",
            )
        )
        return

    # resolve_csv_path already returns a resolved path.
    resolved_path = os.path.normcase(str(csv_path))

    if resolved_path in processed_paths:
        return

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
        return

    try:
        file_size = csv_path.stat().st_size
    except OSError as error:
        file_reports.append(
            empty_file_report(
                inventory_row,
                "file_stat_error",
                str(error),
            )
        )
        return

    if file_size == 0:
        file_reports.append(
            empty_file_report(
                inventory_row,
                "empty_file",
                "CSV file has zero bytes.",
            )
        )
        return

    print(
        f"[{position}/{total}] "
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
            previous_notes + " "
            if previous_notes
            else ""
        ) + f"Metadata matching method: {metadata_status}."

    file_reports.append(report)

    if (
        timestamps
        and report["analysis_status"] == "analysed"
    ):

        sol_number = inventory_sol_number(inventory_row)

        if sol_number is None:
            report["notes"] += (
                " File was not included in pair comparisons "
                "because its Sol number could not be identified."
            )
            return

        series_by_sol[sol_number].append({
            "product_code": str(
                inventory_row.get("product_code") or ""
            ).strip(),
            "csv_file": csv_path.name,
            # Compact contiguous doubles; already sorted.
            "timestamps": array("d", timestamps),
            "time_kind": report["time_kind"],
        })


def _compare_sol_products(
    sol_number: int,
    products: list[dict],
    tolerance: float,
) -> list[dict]:
    """Compare every pair of different products within one Sol."""

    pair_reports = []

    for first, second in combinations(products, 2):

        first_product = first["product_code"]
        second_product = second["product_code"]

        # Pair comparisons require two known, different products.
        if not first_product or not second_product:
            continue

        if first_product.casefold() == second_product.casefold():
            continue

        comparison = _compare_sorted_series(
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

    return pair_reports


def run_analysis(
    input_root: Path,
    inventory: list[dict],
    metadata_records: list[dict],
    tolerance: float,
    axis_preference=DEFAULT_AXIS_PREFERENCE,
) -> tuple[list[dict], list[dict]]:

    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError(
            "Tolerance must be finite and non-negative."
        )

    metadata_index = build_metadata_index(metadata_records)

    csv_rows = [
        row for row in inventory
        if str(row.get("extension") or "")
        .strip()
        .casefold()
        .lstrip(".") == "csv"
    ]

    total = len(csv_rows)

    print(f"CSV inventory entries: {total}")

    # Last position of each Sol in the inventory. Once the last
    # file of a Sol is processed its series are compared and freed,
    # so peak memory is one Sol instead of the whole dataset.
    last_position_by_sol = {}

    for position, inventory_row in enumerate(
        csv_rows,
        start=1,
    ):
        sol_number = inventory_sol_number(inventory_row)

        if sol_number is not None:
            last_position_by_sol[sol_number] = position

    file_index = FileIndex()
    file_reports = []
    pair_reports = []
    series_by_sol = defaultdict(list)
    processed_paths = set()

    for position, inventory_row in enumerate(
        csv_rows,
        start=1,
    ):

        _process_csv_row(
            position,
            total,
            inventory_row,
            input_root,
            file_index,
            metadata_index,
            processed_paths,
            axis_preference,
            file_reports,
            series_by_sol,
        )

        sol_number = inventory_sol_number(inventory_row)

        if (
            sol_number is not None
            and last_position_by_sol.get(sol_number) == position
        ):
            products = series_by_sol.pop(sol_number, None)

            if products:
                pair_reports.extend(
                    _compare_sol_products(
                        sol_number,
                        products,
                        tolerance,
                    )
                )

    # Every Sol is flushed at its last inventory position, so
    # series_by_sol is empty here.

    # Original order: ascending Sol, original pair order inside a Sol.
    # list.sort is stable, so the per-Sol order is preserved.
    pair_reports.sort(key=lambda row: row["sol_number"])

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
    start_sol: int | None = None,
    end_sol: int | None = None,
) -> dict:
    """
    Build a synchronization summary for the full dataset or
    an inclusive SOL range.

    With no bounds, all report rows are summarized (legacy behavior).
    If one bound is omitted, only the supplied bound is applied.

    The input reports are never modified.
    """

    if start_sol is not None:
        if isinstance(start_sol, bool) or not isinstance(start_sol, int):
            raise TypeError("start_sol must be an integer or None.")
        if start_sol < 0:
            raise ValueError("start_sol must be non-negative.")

    if end_sol is not None:
        if isinstance(end_sol, bool) or not isinstance(end_sol, int):
            raise TypeError("end_sol must be an integer or None.")
        if end_sol < 0:
            raise ValueError("end_sol must be non-negative.")

    if (
        start_sol is not None
        and end_sol is not None
        and start_sol > end_sol
    ):
        raise ValueError(
            "start_sol must be less than or equal to end_sol."
        )

    if start_sol is not None or end_sol is not None:
        file_reports = [
            row for row in file_reports
            if isinstance(row.get("sol_number"), int)
            and not isinstance(row.get("sol_number"), bool)
            and (
                start_sol is None
                or row["sol_number"] >= start_sol
            )
            and (
                end_sol is None
                or row["sol_number"] <= end_sol
            )
        ]

        pair_reports = [
            row for row in pair_reports
            if isinstance(row.get("sol_number"), int)
            and not isinstance(row.get("sol_number"), bool)
            and (
                start_sol is None
                or row["sol_number"] >= start_sol
            )
            and (
                end_sol is None
                or row["sol_number"] <= end_sol
            )
        ]

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

    mapping_status_counts = Counter()

    for row in analysed_files:
        match = re.search(
            r"Column mapping: ([^.]+)\.",
            str(row.get("notes") or ""),
        )

        if match:
            mapping_status_counts[match.group(1)] += 1

    return {
        "analyzer": "MEDA Synchronization Analyzer",
        "start_sol": start_sol,
        "end_sol": end_sol,
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
        "mapping_status_counts": dict(mapping_status_counts),
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
            "Unknown CSV header status is not treated as proof of a headerless file.",
            "RHS duplicate XML names are mapped positionally only when all non-duplicate positions match.",
            "WS aliases are accepted only at the two explicitly validated field positions.",
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
    print(
        f"Mapping statuses: {summary['mapping_status_counts']}"
    )
    print(f"File report: {args.file_report.resolve()}")
    print(f"Pair report: {args.pair_report.resolve()}")
    print(f"Summary: {args.summary.resolve()}")


if __name__ == "__main__":
    main()
    