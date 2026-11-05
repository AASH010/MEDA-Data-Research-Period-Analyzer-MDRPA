
"""Shared helpers for MEDA time axes, XML-driven CSV columns,
and structural XML field-metadata validation.

Time handling is deliberately conservative:
- SCLK is parsed as a finite numeric coordinate, not converted to UTC.
- UTC ISO-8601 values are normalized to Unix seconds only when timezone-aware.
- LMST is represented on a linear Mars-sol coordinate.
- LTST is a nominal local-clock coordinate, not a precise elapsed-time scale.

Metadata validation is structural only:
- It detects missing or duplicated field names.
- It detects missing, invalid, or duplicated field numbers.
- It reports missing data types.
- It does not infer scientific meanings or silently repair source metadata.

Important:
Parsing a time value does not prove that its scientific interpretation
or conversion is valid. Callers must report the selected time axis and
the number of values that failed parsing.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional


# Mean Mars solar day in Earth seconds.
# Used as a coordinate scale for LMST, never as an Earth UTC conversion.
SOL_SECONDS = 88775.244

MISSING_TEXT = {
    "",
    "na",
    "n/a",
    "nan",
    "null",
    "none",
    "missing",
}

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


def norm(value) -> str:
    """Normalize a field or column name for comparisons."""
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value or "").lower(),
    )


def _finite_float(value) -> Optional[float]:
    """Convert a value to a finite float, otherwise return None."""
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(number):
        return None

    return number


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

    return (
        sol * SOL_SECONDS
        + hour * (SOL_SECONDS / 24.0)
        + minute * (SOL_SECONDS / 1440.0)
        + second * (SOL_SECONDS / 86400.0)
    )


def parse_lmst(text: str) -> Optional[float]:
    """Parse LMST into a linear Mars-sol coordinate.

    This is not a conversion to UTC.
    """
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

    Naive timestamps are not silently assumed to be UTC.
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

        # Keep naive values separate from UTC timestamps.
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

    # Spacecraft clock
    if (
        normalized == "sclk"
        or normalized.startswith("sclk")
        or "spacecraftclock" in normalized
    ):
        return "sclk"

    # UTC
    if "utc" in normalized:
        return "utc"

    # Local Mean Solar Time
    if normalized in {
        "lmst",
        "localmeansolartime",
        "startlocalmeansolartime",
        "marslocalmeansolartime",
    }:
        return "lmst"

    # Local True Solar Time
    if normalized in {
        "ltst",
        "localtruesolartime",
        "startlocaltruesolartime",
        "marslocaltruesolartime",
    }:
        return "ltst"

    return None


def ordered_fields(fields: list[dict]) -> list[dict]:
    """Order XML field definitions by field_number.

    If field_number is missing or invalid, preserve document order
    for those fields.
    """
    if not isinstance(fields, list):
        return []

    valid_fields = [
        field
        for field in fields
        if isinstance(field, dict)
    ]

    def sort_key(item):
        original_index, field = item

        try:
            field_number = int(field.get("field_number"))

            return (
                0,
                field_number,
                original_index,
            )

        except (TypeError, ValueError, OverflowError):
            return (
                1,
                original_index,
                original_index,
            )

    indexed = list(enumerate(valid_fields))

    return [
        field
        for _, field in sorted(
            indexed,
            key=sort_key,
        )
    ]


def validate_field_metadata(fields: list[dict]) -> list[dict]:
    """Return structural warnings for XML field metadata.

    Each warning contains:
        code: Stable machine-readable warning code.
        severity: "warning" or "error".
        field_index: Zero-based position in the original fields list.
        field_name: Original field name, if available.
        message: Human-readable explanation.

    This function does not modify fields and does not determine
    scientific validity or interpret flag semantics.

    Duplicate names are compared after norm() normalization.
    Field numbers must be positive integers and unique when present.
    Missing field numbers are warnings because document order may
    still be retained by ordered_fields().
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
        field_name = str(raw_name).strip() if raw_name is not None else ""

        if not field_name:
            warnings.append({
                "code": "missing_field_name",
                "severity": "error",
                "field_index": index,
                "field_name": "",
                "message": "Field definition has no usable name.",
            })
        else:
            names_by_key[norm(field_name)].append((index, field_name))

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
            try:
                number = int(str(raw_number).strip())

                # Reject values such as "2.5" rather than truncating.
                if str(raw_number).strip() not in {
                    str(number),
                    f"+{number}",
                }:
                    raise ValueError

                if number < 1:
                    raise ValueError

                numbers_by_value[number].append((index, field_name))

            except (TypeError, ValueError, OverflowError):
                warnings.append({
                    "code": "invalid_field_number",
                    "severity": "error",
                    "field_index": index,
                    "field_name": field_name,
                    "message": (
                        f"Field number {raw_number!r} is not "
                        "a positive integer."
                    ),
                })

        data_type = field.get("data_type")

        if data_type is None or not str(data_type).strip():
            warnings.append({
                "code": "missing_data_type",
                "severity": "warning",
                "field_index": index,
                "field_name": field_name,
                "message": "Field definition has no data type.",
            })

    # Report every member of a duplicate-name group.
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

    # Report every member of a duplicate field-number group.
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

    Returns (None, None, None) when no supported time field is found.

    Important:
    This function performs metadata/name-based discovery only.
    It does not validate actual CSV values.

    The caller must validate values with the selected parser and
    report invalid or missing timestamps.
    """
    if not isinstance(fields, list):
        return None, None, None

    ordered = ordered_fields(fields)

    by_kind = {}

    for index, field in enumerate(ordered):
        name = field.get("name") or ""

        kind = column_time_kind(name)

        if kind and kind not in by_kind:
            by_kind[kind] = (
                index,
                name,
            )

    for kind in preference:
        if kind in by_kind:
            index, name = by_kind[kind]

            return (
                index,
                name,
                kind,
            )

    return None, None, None


def numeric_column_indexes(
    fields: list[dict],
    skip: set[int],
) -> list[int]:
    """Return XML-declared numeric columns, excluding time columns."""
    if not isinstance(fields, list):
        return []

    skip = skip or set()

    result = []

    for index, field in enumerate(ordered_fields(fields)):
        if index in skip:
            continue

        name = field.get("name") or ""

        # Never treat recognized time axes as ordinary numeric data.
        if column_time_kind(name) is not None:
            continue

        data_type = str(
            field.get("data_type") or ""
        )

        if NUMERIC_TYPE_RE.search(data_type):
            result.append(index)

    return result
