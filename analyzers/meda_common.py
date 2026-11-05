
"""Shared helpers for MEDA time axes and XML-driven CSV columns.

Time handling is deliberately conservative:
- SCLK is parsed as a finite numeric coordinate, not converted to UTC.
- UTC ISO-8601 values are normalized to Unix seconds only when timezone-aware.
- LMST is represented on a linear Mars-sol coordinate.
- LTST is a nominal local-clock coordinate, not a precise elapsed-time scale.

Important:
Parsing a time value does not prove that its scientific interpretation
or conversion is valid. Callers must report the selected time axis and
the number of values that failed parsing.
"""

from __future__ import annotations

import math
import re
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
