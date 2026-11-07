from __future__ import annotations

import argparse
import csv
import json
import math
import re

from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import chain
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

TOP_VALUE_LIMIT = 20
VALUE_TRACKING_LIMIT = 5000

SOL_PATTERN = re.compile(
    r"^sol[\_-]?0*(\d+)$",
    re.IGNORECASE,
)

QUALITY_TERMS = {
    "quality",
    "qual",
    "validity",
    "confidence",
}

FLAG_TERMS = {
    "flag",
    "flags",
    "status",
    "state",
}

OPERATIONAL_TERMS = {
    "operational",
    "operation",
    "mode",
    "active",
    "enabled",
    "stable",
    "stability",
    "deployment",
    "deployed",
    "mechanism",
    "algorithm",
    "heater",
    "motor",
    "boom",
}

UNCERTAINTY_TERMS = {
    "uncertainty",
    "uncertainties",
    "unc",
    "sigma",
    "precision",
    "standard",
    "deviation",
    "error",
}

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

# Validated aliases: exact positions and exactly 18 fields only.
WS_VALIDATED_ALIASES = {
    15: (
        "BOOM1_ALG_IN_STABLE_STATE",
        "BOOM1_ALG_STATE_STABLE",
    ),
    16: (
        "BOOM2_ALG_IN_STABLE_STATE",
        "BOOM2_ALG_STATE_STABLE",
    ),
}

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
    """Use the shared MEDA field-name normalization."""
    return norm(value)


def tokenize(value: Any) -> set[str]:
    return set(
        TOKEN_PATTERN.findall(
            str(value or "").casefold()
        )
    )


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
    except (TypeError, ValueError, OverflowError):
        return default


def get_sol_number(value: Any) -> int | None:
    """
    Accept either a numeric Sol value or a SOL folder name.

    Kept as a public helper for compatibility with callers.
    """
    if value is None:
        return None

    try:
        number = int(value)
        return number if number >= 0 else None
    except (TypeError, ValueError, OverflowError):
        pass

    match = SOL_PATTERN.fullmatch(str(value).strip())

    if not match:
        return None

    try:
        return int(match.group(1))
    except (ValueError, OverflowError):
        return None


def get_product_code(filename: str) -> str:
    """
    Extract a product code from a MEDA filename.

    The empty-string return is retained for compatibility
    with the current quality report schema.
    """
    match = re.search(
        r"(?:^|_)CAL_([A-Z0-9]+)(?:_|\.|$)",
        str(filename or ""),
        re.IGNORECASE,
    )

    return match.group(1).upper() if match else ""


def normalize_relative_path(value: Any) -> str:
    """
    Normalize path separators and case for matching.

    This is a comparison key only. It does not modify actual paths.
    """
    if value is None:
        return ""

    return (
        str(value)
        .replace("\\", "/")
        .strip("/")
        .casefold()
    )


def relative_xml_path(csv_relative_path: Any) -> str:
    """Convert an inventory CSV relative path to its XML counterpart."""
    if not csv_relative_path:
        return ""

    normalized = str(csv_relative_path).replace("\\", "/")

    try:
        xml_path = Path(normalized).with_suffix(".xml")
    except (TypeError, ValueError):
        return ""

    return normalize_relative_path(xml_path.as_posix())


def relative_csv_path(value: Any) -> Path | None:
    """Convert an inventory relative path into a platform path."""
    if not value:
        return None

    normalized = str(value).replace("\\", "/")

    try:
        return Path(normalized)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------
# Bounded frequency tracking
# --------------------------------------------------

class BoundedValueCounter:
    """
    Space-Saving frequency tracker.

    Memory is bounded by the configured capacity.

    Top-value counts are approximate if capacity is reached.
    Distinct count is a lower bound when distinct tracking is capped.
    """

    def __init__(
        self,
        capacity: int = VALUE_TRACKING_LIMIT,
    ):
        if not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be a positive integer.")

        self.capacity = capacity
        self.counts: dict[str, int] = {}
        self.seen_values: set[str] = set()
        self.distinct_tracking_capped = False

    def add(self, value: str) -> None:
        if value not in self.seen_values:
            if len(self.seen_values) < self.capacity:
                self.seen_values.add(value)
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

    def top_values(
        self,
        limit: int = TOP_VALUE_LIMIT,
    ) -> dict:
        if limit < 0:
            raise ValueError("limit cannot be negative.")

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
    path = Path(path)

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
    path = Path(path)

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
# Metadata indexing and matching
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
    Build metadata indexes without silently overwriting duplicates.

    Indexes:
      - Sol folder + XML filename
      - source_relative_path
      - legacy relative_path
      - XML filename stem

    Both relative-path fields are indexed independently.
    A record is not inserted twice under the same normalized path.
    """
    by_sol_name = defaultdict(list)
    by_path = defaultdict(list)
    by_stem = defaultdict(list)

    records = metadata.get("records", [])

    if not isinstance(records, list):
        records = []

    for record in records:
        if not isinstance(record, dict):
            continue

        source_file = str(record.get("source_file") or "")

        if not source_file:
            continue

        normalized_source = source_file.replace("\\", "/")

        source_name = Path(normalized_source).name.casefold()
        stem = Path(normalized_source).stem.casefold()
        sol = metadata_sol(record)

        if sol:
            by_sol_name[(sol, source_name)].append(record)

        by_stem[stem].append(record)

        indexed_paths = set()

        for path_field in (
            "source_relative_path",
            "relative_path",
        ):
            normalized_path = normalize_relative_path(
                record.get(path_field)
            )

            if not normalized_path:
                continue

            if normalized_path in indexed_paths:
                continue

            indexed_paths.add(normalized_path)
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
    """
    Find an XML record for an inventory CSV row.

    Matching priority:
      1. Unique relative path match
      2. Unique Sol + filename match
      3. Unique filename stem

    Relative paths are preferred because they can distinguish
    nested files that share the same filename.
    """
    filename = str(inventory_row.get("filename") or "")

    if not filename:
        return None, "missing_inventory_filename"

    filename_path = Path(filename.replace("\\", "/"))
    xml_name = (filename_path.stem + ".xml").casefold()

    # 1. Prefer an exact relative-path match.
    relative_path = inventory_row.get("relative_path")

    if relative_path:
        xml_relative = relative_xml_path(relative_path)

        if xml_relative:
            matches = index["by_path"].get(xml_relative, [])

            if len(matches) == 1:
                return matches[0], "matched_by_relative_path"

            if len(matches) > 1:
                return None, "ambiguous_metadata_path"

    # 2. Fall back to Sol + filename.
    sol_folder = str(
        inventory_row.get("sol_folder") or ""
    ).casefold()

    if sol_folder:
        matches = index["by_sol_name"].get(
            (sol_folder, xml_name),
            [],
        )

        if len(matches) == 1:
            return matches[0], "matched_by_sol_and_name"

        if len(matches) > 1:
            return None, "ambiguous_metadata_match"

    # 3. Fall back to a unique filename stem.
    stem = filename_path.stem.casefold()
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
    """
    Resolve an inventory CSV path without allowing access outside
    the input root, including through symbolic links.

    Relative path has priority. Filename fallback is accepted only
    when it resolves uniquely inside the input root.
    """
    input_root = Path(input_root).expanduser().resolve()

    def safe_file(candidate: Path) -> Path | None:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(input_root)
        except (OSError, RuntimeError, ValueError):
            return None

        return resolved if resolved.is_file() else None

    relative_path = relative_csv_path(
        inventory_row.get("relative_path")
    )

    if relative_path is not None:
        candidate = safe_file(input_root / relative_path)

        if candidate is not None:
            return candidate

    filename = str(
        inventory_row.get("filename") or ""
    )

    sol_folder = str(
        inventory_row.get("sol_folder") or ""
    )

    if not filename:
        return None

    filename_path = Path(filename.replace("\\", "/"))
    filename = filename_path.name

    if sol_folder:
        sol_directory = input_root / sol_folder

        try:
            resolved_sol_directory = sol_directory.resolve()
            resolved_sol_directory.relative_to(input_root)
        except (OSError, RuntimeError, ValueError):
            resolved_sol_directory = None

        if (
            resolved_sol_directory is not None
            and resolved_sol_directory.is_dir()
        ):
            direct = safe_file(
                resolved_sol_directory / filename
            )

            if direct is not None:
                return direct

            matches = []

            for path in resolved_sol_directory.rglob("*"):
                if (
                    path.is_file()
                    and path.name.casefold() == filename.casefold()
                ):
                    safe_path = safe_file(path)

                    if safe_path is not None:
                        matches.append(safe_path)

            if len(matches) == 1:
                return matches[0]

            if len(matches) > 1:
                return None

    if not input_root.is_dir():
        return None

    matches = []

    for path in input_root.rglob("*"):
        if (
            path.is_file()
            and path.name.casefold() == filename.casefold()
        ):
            safe_path = safe_file(path)

            if safe_path is not None:
                matches.append(safe_path)

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


def field_search_tokens(field: dict) -> set[str]:
    searchable = " ".join(
        str(field.get(key) or "")
        for key in (
            "name",
            "description",
            "unit",
        )
    )

    return tokenize(searchable)


def field_is_quality_candidate(field: dict) -> bool:
    """
    Identify explicit quality-related candidates.

    This is keyword-based candidate selection only.
    It does not interpret undocumented flag values.
    """
    tokens = field_search_tokens(field)

    return bool(tokens.intersection(QUALITY_TERMS))


def field_is_operational_context_candidate(
    field: dict,
) -> bool:
    """
    Identify possible operational/context flags separately.
    """
    tokens = field_search_tokens(field)

    has_flag_term = bool(
        tokens.intersection(FLAG_TERMS)
    )

    has_operational_term = bool(
        tokens.intersection(OPERATIONAL_TERMS)
    )

    has_quality_term = bool(
        tokens.intersection(QUALITY_TERMS)
    )

    return (
        has_flag_term
        and not has_quality_term
        and (
            has_operational_term
            or bool(tokens.intersection({"status", "state"}))
        )
    )


def field_is_uncertainty_candidate(field: dict) -> bool:
    """
    Identify uncertainty-related fields by documented wording.

    No uncertainty values are interpreted or recalculated.
    """
    tokens = field_search_tokens(field)

    return bool(
        tokens.intersection(UNCERTAINTY_TERMS)
    )


def get_field_bounds(
    field: dict,
) -> tuple[float | None, float | None]:
    minimum = safe_float(
        field.get("valid_minimum")
    )

    maximum = safe_float(
        field.get("valid_maximum")
    )

    return minimum, maximum


def field_has_range(field: dict) -> bool:
    minimum, maximum = get_field_bounds(field)

    return (
        minimum is not None
        or maximum is not None
    )


def select_field_categories(
    fields: list[dict],
) -> list[tuple[int, dict, list[str]]]:
    """
    Select descriptive analysis categories.

    A field may belong to multiple categories.
    No category is treated as a scientific quality verdict.
    """
    selected = []

    for index, field in enumerate(fields):
        categories = []

        if field_is_quality_candidate(field):
            categories.append("quality_field_candidate")

        if field_is_operational_context_candidate(field):
            categories.append(
                "operational_context_flag_candidate"
            )

        if field_is_uncertainty_candidate(field):
            categories.append("measurement_uncertainty")

        if field_has_range(field):
            categories.append("range_check")

        if categories:
            selected.append(
                (index, field, categories)
            )

    return selected


# --------------------------------------------------
# CSV header and XML field mapping
# --------------------------------------------------

def build_column_mapping(
    first_row: list[str] | None,
    fields: list[dict],
    has_header: Any,
) -> tuple[dict[int, int] | None, bool, str]:
    """
    Map XML field positions to CSV column positions.

    Supported modes:
      - Exact header match
      - Reordered unique header
      - Validated duplicate XML-name positional mapping
      - Validated WS aliases at exact positions
      - Positional mapping when XML explicitly declares no header

    Ambiguous mappings are rejected.
    """
    field_names = [
        normalize_name(field.get("name") or "")
        for field in fields
    ]

    if (
        not field_names
        or any(not name for name in field_names)
    ):
        return None, False, "invalid_xml_field_names"

    # XML explicitly declares a headerless CSV.
    if has_header is False:
        return (
            {
                index: index
                for index in range(len(fields))
            },
            False,
            "headerless_positional_mapping",
        )

    if first_row is None:
        return None, False, "invalid_csv_header_names"

    header_names = [
        normalize_name(value)
        for value in first_row
    ]

    if not header_names or any(
        not name for name in header_names
    ):
        return None, False, "invalid_csv_header_names"

    if len(header_names) != len(field_names):
        return None, False, "column_count_mismatch"

    if len(set(header_names)) != len(header_names):
        return None, False, "duplicate_csv_header_names"

    # Exact positional header match.
    if header_names == field_names:
        return (
            {
                index: index
                for index in range(len(fields))
            },
            True,
            "header_exact_match",
        )

    # Detect duplicate XML field-name groups.
    duplicate_groups = defaultdict(list)

    for index, name in enumerate(field_names):
        duplicate_groups[name].append(index)

    duplicate_groups = {
        name: positions
        for name, positions in duplicate_groups.items()
        if len(positions) > 1
    }

    # Validated positional mapping for duplicate XML names.
    if duplicate_groups:
        safe_positional_match = True

        for index, xml_name in enumerate(field_names):
            if xml_name in duplicate_groups:
                continue

            if header_names[index] != xml_name:
                safe_positional_match = False
                break

        if safe_positional_match:
            for positions in duplicate_groups.values():
                csv_names = [
                    header_names[index]
                    for index in positions
                ]

                if len(set(csv_names)) != len(csv_names):
                    safe_positional_match = False
                    break

        if safe_positional_match:
            return (
                {
                    index: index
                    for index in range(len(fields))
                },
                True,
                "header_positional_duplicate_xml_names",
            )

        return (
            None,
            False,
            "duplicate_xml_names_mapping_ambiguous",
        )

    # Validated WS aliases.
    if len(fields) == 18:
        alias_positions = set(WS_VALIDATED_ALIASES)

        differences = {
            index
            for index, (xml_name, csv_name)
            in enumerate(zip(field_names, header_names))
            if xml_name != csv_name
        }

        if differences == alias_positions:
            aliases_match = True

            for index, (xml_alias, csv_alias) in (
                WS_VALIDATED_ALIASES.items()
            ):
                if field_names[index] != normalize_name(xml_alias):
                    aliases_match = False
                    break

                if header_names[index] != normalize_name(csv_alias):
                    aliases_match = False
                    break

            other_positions_match = all(
                field_names[index] == header_names[index]
                for index in range(len(fields))
                if index not in alias_positions
            )

            if aliases_match and other_positions_match:
                return (
                    {
                        index: index
                        for index in range(len(fields))
                    },
                    True,
                    "header_positional_ws_aliases",
                )

    # Reordered unique header.
    header_positions = {
        name: index
        for index, name in enumerate(header_names)
    }

    if all(
        name in header_positions
        for name in field_names
    ):
        mapping = {
            xml_index: header_positions[field_name]
            for xml_index, field_name
            in enumerate(field_names)
        }

        return (
            mapping,
            True,
            "header_reordered_mapped",
        )

    if has_header is True:
        return (
            None,
            False,
            "header_mapping_mismatch",
        )

    matching_names = (
        set(field_names)
        .intersection(set(header_names))
    )

    if matching_names:
        return (
            None,
            False,
            "partial_header_match",
        )

    return (
        None,
        False,
        "header_status_unknown",
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

    sol_number = get_sol_number(
        inventory_row.get("sol_number")
    )

    if sol_number is None:
        sol_number = get_sol_number(sol_folder)

    product_code = (
        inventory_row.get("product_code")
        or get_product_code(filename)
    )

    row = {
        "sol_number": (
            sol_number
            if sol_number is not None
            else ""
        ),
        "sol_folder": sol_folder,
        "product_code": product_code or "",
        "csv_file": filename,
        "field_name": (
            field.get("name", "")
            if field
            else ""
        ),
        "field_type": category,
        "metadata_description": (
            field_description(field)
            if field
            else ""
        ),
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
        "distinct_values_lower_bound": (
            counter.distinct_lower_bound()
        ),
        "distinct_count_capped": (
            counter.distinct_tracking_capped
        ),
        "below_valid_minimum": (
            stats["below_valid_minimum"]
        ),
        "above_valid_maximum": (
            stats["above_valid_maximum"]
        ),
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
    csv_path = Path(csv_path)

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
                (
                    "No candidate fields or XML-declared "
                    "valid ranges were found."
                ),
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

            mapping, skip_first_row, mapping_status = (
                build_column_mapping(
                    first_row,
                    fields,
                    xml_record.get("has_header"),
                )
            )

            if mapping is None:
                return [
                    make_report_row(
                        inventory_row,
                        None,
                        None,
                        "file_status",
                        mapping_status,
                        (
                            "CSV columns could not be mapped "
                            "safely to XML fields."
                        ),
                    )
                ]

            field_stats = []

            for field_index, field, categories in selected:
                for category in categories:
                    field_stats.append({
                        "field_index": field_index,
                        "field": field,
                        "stats": new_field_stats(
                            field,
                            category,
                        ),
                    })

            malformed_rows = 0

            if skip_first_row:
                rows_iterator = reader
            else:
                rows_iterator = chain(
                    (first_row,),
                    reader,
                )

            # Process incrementally; do not load the full CSV into memory.
            for row in rows_iterator:
                if (
                    not row
                    or not any(
                        str(value).strip()
                        for value in row
                    )
                ):
                    continue

                if len(row) != len(fields):
                    malformed_rows += 1

                for item in field_stats:
                    field_index = item["field_index"]
                    csv_index = mapping.get(field_index)

                    value = (
                        row[csv_index]
                        if (
                            csv_index is not None
                            and csv_index < len(row)
                        )
                        else None
                    )

                    update_field_stats(
                        item["stats"],
                        value,
                    )

            report_rows = []

            for item in field_stats:
                stats = item["stats"]
                category = stats["category"]

                notes = [
                    f"Column mapping: {mapping_status}."
                ]

                if (
                    stats["minimum"] is not None
                    or stats["maximum"] is not None
                ):
                    notes.append(
                        "Range checks use XML-declared valid limits only."
                    )

                if category == "quality_field_candidate":
                    notes.append(
                        "Keyword-based quality candidate only; "
                        "flag meanings are not interpreted."
                    )

                elif category == "operational_context_flag_candidate":
                    notes.append(
                        "Possible operational/context field; "
                        "not treated as a measurement quality flag."
                    )

                elif category == "measurement_uncertainty":
                    notes.append(
                        "Uncertainty-related field candidate; "
                        "values are reported without reinterpretation."
                    )

                if stats["value_counter"].distinct_tracking_capped:
                    notes.append(
                        "Distinct-value tracking reached its configured "
                        "memory limit; the reported distinct count "
                        "is a lower bound."
                    )

                if malformed_rows:
                    notes.append(
                        f"{malformed_rows} rows had a column count "
                        "different from the XML field count."
                    )

                if category == "range_check":
                    notes.append(
                        "Values outside documented limits are flagged "
                        "for review, not automatically classified "
                        "as scientifically invalid."
                    )

                report_rows.append(
                    make_report_row(
                        inventory_row,
                        item["field"],
                        stats,
                        category,
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
    input_root = Path(input_root).expanduser()

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

    print(
        f"CSV inventory entries: {len(csv_records)}"
    )

    for position, inventory_row in enumerate(
        csv_records,
        start=1,
    ):
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

        resolved_path = str(
            csv_path.resolve()
        ).casefold()

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
# Save reports
# --------------------------------------------------

def write_report(
    path: Path,
    rows: list[dict],
) -> None:
    path = Path(path)

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


# --------------------------------------------------
# Summary
# --------------------------------------------------

def build_summary(
    rows: list[dict],
    start_sol: int | None = None,
    end_sol: int | None = None,
) -> dict:
    """
    Build a quality summary for the full dataset or an inclusive SOL range.

    With no bounds, all report rows are summarized (legacy behavior).
    If one bound is omitted, only the supplied bound is applied.
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
        raise ValueError("start_sol must be less than or equal to end_sol.")

    if start_sol is not None or end_sol is not None:
        rows = [
            row
            for row in rows
            if isinstance(row.get("sol_number"), int)
            and not isinstance(row.get("sol_number"), bool)
            and (start_sol is None or row["sol_number"] >= start_sol)
            and (end_sol is None or row["sol_number"] <= end_sol)
        ]

    analysed = [
        row
        for row in rows
        if row.get("analysis_status") == "analysed"
    ]

    quality_rows = [
        row
        for row in analysed
        if row.get("field_type") == "quality_field_candidate"
    ]

    operational_rows = [
        row
        for row in analysed
        if row.get("field_type")
        == "operational_context_flag_candidate"
    ]

    uncertainty_rows = [
        row
        for row in analysed
        if row.get("field_type") == "measurement_uncertainty"
    ]

    range_rows = [
        row
        for row in analysed
        if row.get("field_type") == "range_check"
    ]

    statuses = Counter(
        row.get("analysis_status", "unknown")
        for row in rows
    )

    mapping_statuses = Counter()

    for row in analysed:
        notes = str(row.get("notes") or "")

        match = re.search(
            r"Column mapping: ([^.]+)\.",
            notes,
        )

        if match:
            mapping_statuses[match.group(1)] += 1

    return {
        "analyzer": "MEDA Quality Analyzer",
        "start_sol": start_sol,
        "end_sol": end_sol,

        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "report_row_count": len(rows),

        "analysed_field_reports": len(analysed),

        # Backward-compatible summary key.
        "quality_field_reports": len(quality_rows),

        "quality_field_candidate_reports": len(quality_rows),

        "operational_context_flag_candidate_reports": (
            len(operational_rows)
        ),

        "measurement_uncertainty_reports": (
            len(uncertainty_rows)
        ),

        "range_check_reports": len(range_rows),

        "file_status_reports": sum(
            row.get("field_type") == "file_status"
            for row in rows
        ),

        "analysis_status_counts": dict(statuses),

        "column_mapping_status_counts": dict(
            mapping_statuses
        ),

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
            (
                "Quality-related fields are keyword-based candidates; "
                "undocumented flag meanings are not inferred."
            ),
            (
                "Operational/context flags are reported separately "
                "from quality-related candidates."
            ),
            (
                "Measurement uncertainty fields are reported separately "
                "and are not converted into a quality score."
            ),
            (
                "Values outside XML-declared limits are flagged for review, "
                "not automatically classified as scientifically invalid."
            ),
            (
                "Special constants are not automatically treated "
                "as missing values."
            ),
            (
                "A field may appear in more than one report category "
                "when it meets multiple independent selection rules."
            ),
            (
                "Distinct-value tracking is bounded in memory. "
                "When capped, the reported distinct count is a lower bound."
            ),
            (
                "Duplicate XML names and known WS aliases are mapped "
                "only under narrowly validated positional conditions."
            ),
            (
                "Ambiguous column mappings are not used for measurement "
                "calculations."
            ),
            (
                "This analyzer does not determine overall instrument health "
                "or scientific suitability of a period."
            ),
        ],
    }


def save_summary(
    path: Path,
    summary: dict,
) -> None:
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
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
# CLI
# --------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze MEDA quality-related candidates, "
            "operational/context fields, uncertainty fields, "
            "and XML-declared measurement ranges."
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

    print(
        "Analyzing quality candidates, operational/context "
        "fields, uncertainty fields and documented ranges..."
    )

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

    print(
        f"Report rows: {len(reports)}"
    )

    print(
        "Analysed field reports: "
        f"{summary['analysed_field_reports']}"
    )

    print(
        "Quality field candidate reports: "
        f"{summary['quality_field_candidate_reports']}"
    )

    print(
        "Operational/context flag candidate reports: "
        f"{summary['operational_context_flag_candidate_reports']}"
    )

    print(
        "Measurement uncertainty reports: "
        f"{summary['measurement_uncertainty_reports']}"
    )

    print(
        "Range check reports: "
        f"{summary['range_check_reports']}"
    )

    print(
        f"CSV report: {args.output.resolve()}"
    )

    print(
        f"JSON summary: {args.summary.resolve()}"
    )


if __name__ == "__main__":
    main()