"""Shared utilities used by the MEDA backend analyzers.

This module provides shared time-axis parsing, XML field ordering,
field metadata validation, numeric-column discovery, and special
constant classification.

It is a utility module, not an independent pipeline stage:
- It does not discover or open input files.
- It does not write reports.
- It does not define project input/output paths.
- It does not execute analyzers or orchestrate the pipeline.

Time handling is deliberately conservative:
- SCLK is a numeric coordinate, not UTC.
- UTC ISO-8601 values require timezone information.
- LMST is represented as a linear Mars-sol coordinate.
- LTST is a nominal local-clock coordinate, not precise elapsed SI time.

Metadata validation is structural only. It does not determine
scientific validity or interpret quality-flag semantics.

Special Constants are treated as read-only metadata:
- Their documented categories and values are preserved.
- Values can be matched against CSV cells for classification.
- No category is automatically converted into another category.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional


# Mean Mars solar day in Earth seconds.
# Used only as a coordinate scale for LMST/LTST.
SOL_SECONDS = 88775.244

# Shared by coverage, synchronization, and quality analyzers.
# Immutable to prevent accidental modification by a consumer.
MISSING_TEXT = frozenset({
    "",
    "na",
    "n/a",
    "nan",
    "null",
    "none",
    "missing",
})

LMST_RE = re.compile(
    r"^(?:SOL[-_ ]*)?(\d+)M(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)$",
    re.IGNORECASE,
)

LTST_RE = re.compile(
    r"^(?:SOL[-_ ]*)?(\d+)\s+(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)$",
    re.IGNORECASE,
)

NUMERIC_TYPE_RE = re.compile(
    r"(real|integer|numeric)",
    re.IGNORECASE,
)

# A special constant is identified by its documented XML key.
# New categories can be supported without changing this list.
SPECIAL_CONSTANT_SUFFIX = "_constant"


def norm(value) -> str:
    """Normalize a field or column name for comparisons."""
    if value is None:
        value = ""

    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value).lower(),
    )


def _finite_float(value) -> Optional[float]:
    """Convert a value to a finite float, otherwise return None."""
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError, OverflowError):
        return None

    return number if math.isfinite(number) else None


def _normalized_special_value(value) -> Optional[str]:
    """Return a normalized textual representation of a special value."""
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    return text.casefold()


def _numeric_special_value(value) -> Optional[Decimal]:
    """Convert a value to a finite Decimal for safe numeric matching."""
    if value is None or isinstance(value, bool):
        return None

    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None

    if not number.is_finite():
        return None

    return number


def _collect_special_constant_text_values(value) -> set[str]:
    """Collect textual values from one Special Constant definition.

    XML metadata may represent a value as:
        "-999"

    Or as a dictionary containing:
        {"#text": "-999"}

    Attributes are deliberately ignored because they describe metadata,
    not the special constant's actual value.
    """
    values = set()

    if value is None:
        return values

    if isinstance(value, str):
        text = value.strip()

        if text:
            values.add(text)

        return values

    if isinstance(value, (int, float, Decimal)):
        text = str(value).strip()

        if text:
            values.add(text)

        return values

    if isinstance(value, list):
        for item in value:
            values.update(
                _collect_special_constant_text_values(item)
            )

        return values

    if isinstance(value, dict):
        # Prefer the explicit XML element text when available.
        if "#text" in value:
            values.update(
                _collect_special_constant_text_values(
                    value["#text"]
                )
            )

        # Support nested representations while ignoring XML attributes.
        for key, nested_value in value.items():
            if key == "#text" or str(key).startswith("@"):
                continue

            values.update(
                _collect_special_constant_text_values(nested_value)
            )

        return values

    return values


def get_special_constant_values(field: dict) -> dict[str, frozenset[str]]:
    """Extract documented Special Constant values from one XML field.

    The returned mapping uses the original metadata category names,
    for example:
        {
            "missing_constant": frozenset({"-999"}),
            "invalid_constant": frozenset({"-998"}),
        }

    The source field and its nested metadata are never modified.

    This function performs metadata extraction only. It does not decide
    how a category affects Data Integrity or Quality Analyzer scores.
    """
    if not isinstance(field, dict):
        return {}

    special_constants = field.get("special_constants")

    if not isinstance(special_constants, (dict, list)):
        return {}

    definitions = (
        special_constants
        if isinstance(special_constants, list)
        else [special_constants]
    )

    collected = defaultdict(set)

    for definition in definitions:
        if not isinstance(definition, dict):
            continue

        for key, value in definition.items():
            category = str(key).strip().casefold()

            if not category.endswith(SPECIAL_CONSTANT_SUFFIX):
                continue

            values = _collect_special_constant_text_values(value)

            if values:
                collected[category].update(values)

    return {
        category: frozenset(values)
        for category, values in collected.items()
    }


def classify_special_constant(
    raw_value,
    field: dict,
) -> Optional[str]:
    """Classify a raw CSV value using the field's XML Special Constants.

    Matching rules:
        1. Case-insensitive exact textual matching.
        2. Numeric equivalence for finite numeric values.

    Examples:
        XML value "-999" matches CSV "-999".
        XML value "-999" matches CSV "-999.0".
        XML value "-999" matches CSV "-9.99e2".

    Return values:
        - The documented category, e.g. "missing_constant".
        - "ambiguous_special_constant" if the same value is documented
          under more than one category.
        - None if the value does not match a documented category.

    This function does not convert categories into Missing or Invalid.
    The caller must apply the project's explicit classification policy.
    """
    if raw_value is None:
        return None

    documented = get_special_constant_values(field)

    if not documented:
        return None

    raw_text = _normalized_special_value(raw_value)

    if raw_text is None:
        return None

    raw_number = _numeric_special_value(raw_value)

    matched_categories = set()

    for category, documented_values in documented.items():
        for documented_value in documented_values:
            documented_text = _normalized_special_value(
                documented_value
            )

            if documented_text == raw_text:
                matched_categories.add(category)
                break

            documented_number = _numeric_special_value(
                documented_value
            )

            if (
                raw_number is not None
                and documented_number is not None
                and raw_number == documented_number
            ):
                matched_categories.add(category)
                break

    if not matched_categories:
        return None

    if len(matched_categories) > 1:
        return "ambiguous_special_constant"

    return next(iter(matched_categories))


def parse_sclk(text: str) -> Optional[float]:
    """Parse a numeric SCLK coordinate without assigning UTC meaning."""
    return _finite_float(text)


def _parse_sol_clock(match) -> Optional[float]:
    """Convert a parsed Sol/clock value into a nominal linear coordinate."""
    if match is None:
        return None

    sol_text, hour_text, minute_text, second_text = match.groups()

    try:
        sol = int(sol_text)
        hour = int(hour_text)
        minute = int(minute_text)
        second = float(second_text)
    except (TypeError, ValueError, OverflowError):
        return None

    if sol < 0:
        return None

    if not 0 <= hour <= 23:
        return None

    if not 0 <= minute <= 59:
        return None

    if not math.isfinite(second) or not 0 <= second < 60:
        return None

    try:
        coordinate = (
            sol * SOL_SECONDS
            + hour * (SOL_SECONDS / 24.0)
            + minute * (SOL_SECONDS / 1440.0)
            + second * (SOL_SECONDS / 86400.0)
        )
    except (OverflowError, ValueError):
        return None

    if not math.isfinite(coordinate):
        return None

    return coordinate


def parse_lmst(text: str) -> Optional[float]:
    """Parse LMST into a linear Mars-sol coordinate, not UTC."""
    if text is None:
        return None

    match = LMST_RE.fullmatch(str(text).strip())
    return _parse_sol_clock(match)


def parse_ltst(text: str) -> Optional[float]:
    """Parse LTST into a nominal Sol/local-clock coordinate.

    LTST is true solar time. Its clock does not advance uniformly
    relative to elapsed SI time.

    The returned value may support exploratory ordering, but must not
    be interpreted as precise elapsed seconds or converted to UTC.
    """
    if text is None:
        return None

    match = LTST_RE.fullmatch(str(text).strip())
    return _parse_sol_clock(match)


def parse_iso(
    text: str,
    want_aware: bool,
) -> Optional[float]:
    """Parse ISO-8601 while preserving timezone-awareness semantics.

    If want_aware=True:
        Only timezone-aware values are accepted and normalized to UTC.

    If want_aware=False:
        Only timezone-naive values are accepted.

    Naive timestamps are never silently assumed to be UTC.
    """
    if text is None:
        return None

    value = str(text).strip()

    if not value:
        return None

    if value[-1:] in ("Z", "z"):
        value = value[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError, OverflowError):
        return None

    is_aware = (
        parsed.tzinfo is not None
        and parsed.utcoffset() is not None
    )

    if is_aware != want_aware:
        return None

    try:
        if is_aware:
            return parsed.astimezone(timezone.utc).timestamp()

        # Naive timestamps remain a separate coordinate.
        return (
            parsed - datetime(1970, 1, 1)
        ).total_seconds()

    except (ValueError, OverflowError, OSError):
        return None


# Time kind -> (parser, coordinate description)
PARSERS = {
    "sclk": (
        parse_sclk,
        "SCLK numeric coordinate (not UTC)",
    ),
    "utc": (
        lambda value: parse_iso(value, True),
        "UTC epoch seconds",
    ),
    "lmst": (
        parse_lmst,
        "linear LMST sol coordinate (not UTC)",
    ),
    "ltst": (
        parse_ltst,
        "nominal LTST coordinate (not elapsed SI seconds)",
    ),
    "iso_naive": (
        lambda value: parse_iso(value, False),
        "naive ISO coordinate (timezone unspecified)",
    ),
}

DEFAULT_AXIS_PREFERENCE = (
    "sclk",
    "utc",
    "lmst",
    "ltst",
    "iso_naive",
)


def column_time_kind(name: str) -> Optional[str]:
    """Identify a supported time axis from a field/column name."""
    normalized = norm(name)

    if (
        normalized == "sclk"
        or normalized.startswith("sclk")
        or "spacecraftclock" in normalized
    ):
        return "sclk"

    if "utc" in normalized:
        return "utc"

    if normalized in {
        "lmst",
        "localmeansolartime",
        "startlocalmeansolartime",
        "marslocalmeansolartime",
    }:
        return "lmst"

    if normalized in {
        "ltst",
        "localtruesolartime",
        "startlocaltruesolartime",
        "marslocaltruesolartime",
    }:
        return "ltst"

    return None


def _positive_field_number(value) -> Optional[int]:
    """Return a canonical positive integer field number, if valid.

    Accepted examples:
        1
        "1"
        "+1"

    Rejected examples:
        0
        "-1"
        "01"
        "1.0"
        "2.5"
        "invalid"
    """
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    try:
        number = int(text)
    except (TypeError, ValueError, OverflowError):
        return None

    if number < 1:
        return None

    if text not in {str(number), f"+{number}"}:
        return None

    return number


def ordered_fields(fields: list[dict]) -> list[dict]:
    """Order XML fields by valid field_number.

    Fields with missing or invalid numbers retain their relative
    document order and follow fields with valid numbers.

    Non-dictionary entries are ignored. The input is not modified.
    """
    if not isinstance(fields, list):
        return []

    valid_fields = [
        field
        for field in fields
        if isinstance(field, dict)
    ]

    indexed = list(enumerate(valid_fields))

    def sort_key(item):
        original_index, field = item
        field_number = _positive_field_number(
            field.get("field_number")
        )

        if field_number is None:
            return 1, original_index, original_index

        return 0, field_number, original_index

    return [
        field
        for _, field in sorted(indexed, key=sort_key)
    ]


def validate_field_metadata(fields: list[dict]) -> list[dict]:
    """Return structural warnings for XML field metadata.

    Each warning contains:
        code: Stable machine-readable warning code.
        severity: "warning" or "error".
        field_index: Zero-based position in the original fields list.
        field_name: Original field name, if available.
        message: Human-readable explanation.

    Duplicate names are compared after norm() normalization.
    Field numbers must be positive canonical integers and unique
    when present. Missing field numbers are warnings because
    ordered_fields() retains document order as a fallback.

    This function does not modify the supplied metadata.
    """
    if not isinstance(fields, list):
        return [{
            "code": "fields_not_a_list",
            "severity": "error",
            "field_index": None,
            "field_name": "",
            "message": "XML field metadata must be provided as a list.",
        }]

    warnings = []
    names_by_key = defaultdict(list)
    numbers_by_value = defaultdict(list)

    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            warnings.append({
                "code": "field_entry_not_an_object",
                "severity": "error",
                "field_index": index,
                "field_name": "",
                "message": "Field metadata entry is not an object.",
            })
            continue

        raw_name = field.get("name")
        field_name = (
            str(raw_name).strip()
            if raw_name is not None
            else ""
        )

        if not field_name:
            warnings.append({
                "code": "missing_field_name",
                "severity": "error",
                "field_index": index,
                "field_name": "",
                "message": "Field definition has no usable name.",
            })
        else:
            names_by_key[norm(field_name)].append(
                (index, field_name)
            )

        raw_number = field.get("field_number")

        if raw_number is None or str(raw_number).strip() == "":
            warnings.append({
                "code": "missing_field_number",
                "severity": "warning",
                "field_index": index,
                "field_name": field_name,
                "message": (
                    "Field number is missing; document order "
                    "will be preserved as a fallback."
                ),
            })
        else:
            number = _positive_field_number(raw_number)

            if number is None:
                warnings.append({
                    "code": "invalid_field_number",
                    "severity": "error",
                    "field_index": index,
                    "field_name": field_name,
                    "message": (
                        f"Field number {raw_number!r} is not "
                        "a positive canonical integer."
                    ),
                })
            else:
                numbers_by_value[number].append(
                    (index, field_name)
                )

        data_type = field.get("data_type")

        if data_type is None or not str(data_type).strip():
            warnings.append({
                "code": "missing_data_type",
                "severity": "warning",
                "field_index": index,
                "field_name": field_name,
                "message": "Field definition has no data type.",
            })

    # Report every member of each duplicate-name group.
    for entries in names_by_key.values():
        if len(entries) > 1:
            duplicate_names = ", ".join(
                f"{name!r} (field index {index})"
                for index, name in entries
            )

            for index, name in entries:
                warnings.append({
                    "code": "duplicate_field_name",
                    "severity": "error",
                    "field_index": index,
                    "field_name": name,
                    "message": (
                        "Field name is duplicated after normalization: "
                        f"{duplicate_names}."
                    ),
                })

    # Report every member of each duplicate field-number group.
    for number, entries in numbers_by_value.items():
        if len(entries) > 1:
            for index, name in entries:
                warnings.append({
                    "code": "duplicate_field_number",
                    "severity": "error",
                    "field_index": index,
                    "field_name": name,
                    "message": (
                        f"Field number {number} is assigned to "
                        f"{len(entries)} field definitions."
                    ),
                })

    return warnings


def pick_time_column(
    fields: list[dict],
    preference=DEFAULT_AXIS_PREFERENCE,
):
    """Return (column_index, column_name, kind).

    The index refers to the ordered_fields() result, not the
    original XML list position.

    Returns (None, None, None) when no supported time field exists.

    This function performs metadata/name-based discovery only.
    It does not validate actual CSV values.
    """
    if not isinstance(fields, list):
        return None, None, None

    ordered = ordered_fields(fields)
    by_kind = {}

    for index, field in enumerate(ordered):
        name = field.get("name") or ""
        kind = column_time_kind(name)

        if kind and kind not in by_kind:
            by_kind[kind] = (index, name)

    for kind in preference:
        if kind in by_kind:
            index, name = by_kind[kind]
            return index, name, kind

    return None, None, None


def numeric_column_indexes(
    fields: list[dict],
    skip: set[int] | None = None,
) -> list[int]:
    """Return XML-declared numeric column indexes.

    Indexes refer to ordered_fields(fields). Recognized time columns
    are excluded even if their XML data_type is numeric.
    """
    if not isinstance(fields, list):
        return []

    skip = skip or set()
    result = []

    for index, field in enumerate(ordered_fields(fields)):
        if index in skip:
            continue

        name = field.get("name") or ""

        if column_time_kind(name) is not None:
            continue

        data_type = str(field.get("data_type") or "")

        if NUMERIC_TYPE_RE.search(data_type):
            result.append(index)

    return result