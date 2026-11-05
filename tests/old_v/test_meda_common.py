import sys
from pathlib import Path

# Add the project root to Python's import path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from analyzers.meda_common import (
    parse_sclk,
    parse_lmst,
    parse_ltst,
    parse_iso,
    column_time_kind,
    ordered_fields,
    pick_time_column,
)

# SCLK
assert parse_sclk("12345.67") == 12345.67
assert parse_sclk("NaN") is None
assert parse_sclk("Infinity") is None
assert parse_sclk("invalid") is None

# LMST
assert parse_lmst("00001M16:05:31.315") is not None
assert parse_lmst("00001M25:05:31.315") is None
assert parse_lmst("invalid") is None

# LTST
assert parse_ltst("0001 15:28:01") is not None
assert parse_ltst("0001 25:28:01") is None

# ISO
assert parse_iso("2025-01-01T12:00:00Z", True) is not None
assert parse_iso("2025-01-01T12:00:00", True) is None
assert parse_iso("2025-01-01T12:00:00", False) is not None

# Time field detection
assert column_time_kind("SCLK") == "sclk"
assert column_time_kind("UTC_TIME") == "utc"
assert column_time_kind("LMST") == "lmst"
assert column_time_kind("LTST") == "ltst"

# XML field ordering
fields = [
    {"name": "B", "field_number": "2"},
    {"name": "A", "field_number": "1"},
]

ordered = ordered_fields(fields)

assert ordered[0]["name"] == "A"
assert ordered[1]["name"] == "B"

# Time column selection
index, name, kind = pick_time_column([
    {"name": "TEMP", "field_number": "1"},
    {"name": "UTC_TIME", "field_number": "2"},
])

assert index == 1
assert name == "UTC_TIME"
assert kind == "utc"

print("All meda_common tests passed.")
