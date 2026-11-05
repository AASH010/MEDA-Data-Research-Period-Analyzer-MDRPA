"""Shared helpers: time-axis parsing and XML-driven CSV column mapping."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Optional

SOL_SECONDS = 88775.244  # mean solar day length in seconds

MISSING_TEXT = {"", "na", "n/a", "nan", "null", "none", "missing"}

LMST_RE = re.compile(r"^(\d+)M(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)$", re.I)
LTST_RE = re.compile(r"^(\d+)\s+(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)$")

NUMERIC_TYPE_RE = re.compile(r"(real|integer|numeric)", re.I)


def norm(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def parse_sclk(text: str) -> Optional[float]:
    try:
        v = float(text)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def _sol_clock(match) -> float:
    sol, hh, mm, ss = match.groups()
    return int(sol) * SOL_SECONDS + int(hh) * 3600 + int(mm) * 60 + float(ss)


def parse_lmst(text: str) -> Optional[float]:
    m = LMST_RE.match(text)
    return _sol_clock(m) if m else None


def parse_ltst(text: str) -> Optional[float]:
    m = LTST_RE.match(text)
    return _sol_clock(m) if m else None


def parse_iso(text: str, want_aware: bool) -> Optional[float]:
    t = text.strip()
    if t[-1:] in "Zz":
        t = t[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        return None
    if (d.tzinfo is not None) != want_aware:
        return None  # never mix aware and naive timestamps
    if want_aware:
        return d.astimezone(timezone.utc).timestamp()
    return (d - datetime(1970, 1, 1)).total_seconds()


# kind -> (parser, human unit)
PARSERS = {
    "sclk": (parse_sclk, "SCLK seconds"),
    "utc": (lambda t: parse_iso(t, True), "UTC epoch seconds"),
    "lmst": (parse_lmst, "LMST seconds (sol*88775.244 + time of sol)"),
    "ltst": (parse_ltst, "LTST seconds (sol*88775.244 + time of sol)"),
    "iso_naive": (lambda t: parse_iso(t, False), "naive ISO seconds"),
}

DEFAULT_AXIS_PREFERENCE = ("sclk", "utc", "lmst", "ltst", "iso_naive")


def column_time_kind(name: str) -> Optional[str]:
    n = norm(name)
    if n == "sclk" or n.startswith("sclk"):
        return "sclk"
    if "utc" in n:
        return "utc"
    if n == "lmst":
        return "lmst"
    if n == "ltst":
        return "ltst"
    return None


def ordered_fields(fields: list[dict]) -> list[dict]:
    """Order fields by XML field_number (falls back to document order)."""
    def key(item):
        idx, f = item
        try:
            return (0, int(f.get("field_number")), idx)
        except (TypeError, ValueError):
            return (1, 0, idx)
    return [f for _, f in sorted(enumerate(fields), key=key)]


def pick_time_column(fields: list[dict], preference=DEFAULT_AXIS_PREFERENCE):
    """Return (column_index, column_name, kind) or (None, None, None)."""
    by_kind = {}
    for i, f in enumerate(fields):
        kind = column_time_kind(f.get("name") or "")
        if kind and kind not in by_kind:
            by_kind[kind] = (i, f["name"])
    for kind in preference:
        if kind in by_kind:
            return by_kind[kind][0], by_kind[kind][1], kind
    return None, None, None


def numeric_column_indexes(fields: list[dict], skip: set[int]) -> list[int]:
    return [
        i for i, f in enumerate(fields)
        if i not in skip
        and column_time_kind(f.get("name") or "") is None
        and NUMERIC_TYPE_RE.search(str(f.get("data_type") or ""))
    ]