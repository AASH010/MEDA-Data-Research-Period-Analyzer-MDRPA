import copy

import pytest

from backend.analyzers.meda_common import (
    SOL_SECONDS,
    MISSING_TEXT,
    PARSERS,
    DEFAULT_AXIS_PREFERENCE,
    norm,
    parse_sclk,
    parse_lmst,
    parse_ltst,
    parse_iso,
    column_time_kind,
    ordered_fields,
    validate_field_metadata,
    pick_time_column,
    numeric_column_indexes,
)


# ---------------------------------------------------------------------
# Shared constants and normalization
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SCLK", "sclk"),
        ("UTC_TIME", "utctime"),
        ("Local Mean Solar Time", "localmeansolartime"),
        ("Field-Number_01", "fieldnumber01"),
        ("", ""),
        (None, ""),
        (0, "0"),
        (False, "false"),
    ],
)
def test_norm(value, expected):
    assert norm(value) == expected


def test_missing_text_is_immutable():
    assert "" in MISSING_TEXT
    assert "na" in MISSING_TEXT

    with pytest.raises(AttributeError):
        MISSING_TEXT.add("unknown")


def test_parser_registry_contains_supported_time_kinds():
    assert set(PARSERS) == {
        "sclk",
        "utc",
        "lmst",
        "ltst",
        "iso_naive",
    }

    for parser, description in PARSERS.values():
        assert callable(parser)
        assert isinstance(description, str)
        assert description


def test_default_axis_preference_is_defined():
    assert DEFAULT_AXIS_PREFERENCE == (
        "sclk",
        "utc",
        "lmst",
        "ltst",
        "iso_naive",
    )


# ---------------------------------------------------------------------
# SCLK parsing
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("12345.67", 12345.67),
        ("0", 0.0),
        ("-12.5", -12.5),
        (" 123.25 ", 123.25),
    ],
)
def test_parse_sclk_valid_values(value, expected):
    assert parse_sclk(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "invalid",
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_parse_sclk_invalid_values(value):
    assert parse_sclk(value) is None


# ---------------------------------------------------------------------
# LMST parsing
# ---------------------------------------------------------------------

def test_parse_lmst_valid_value():
    result = parse_lmst("00001M16:05:31.315")

    assert result is not None
    assert result > 0


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "invalid",
        "00001M25:05:31.315",
        "00001M12:60:00",
        "00001M12:30:60",
        "00001M12:30:-1",
    ],
)
def test_parse_lmst_invalid_values(value):
    assert parse_lmst(value) is None


def test_parse_lmst_sol_difference_uses_mars_sol_scale():
    first = parse_lmst("00001M00:00:00")
    second = parse_lmst("00002M00:00:00")

    assert first is not None
    assert second is not None
    assert second - first == pytest.approx(SOL_SECONDS)


def test_parse_lmst_rejects_extremely_large_sol_without_overflow():
    value = "9" * 400 + "M00:00:00"

    assert parse_lmst(value) is None


# ---------------------------------------------------------------------
# LTST parsing
# ---------------------------------------------------------------------

def test_parse_ltst_valid_value():
    result = parse_ltst("0001 15:28:01")

    assert result is not None
    assert result > 0


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "invalid",
        "0001 25:28:01",
        "0001 12:60:00",
        "0001 12:30:60",
    ],
)
def test_parse_ltst_invalid_values(value):
    assert parse_ltst(value) is None


def test_parse_ltst_sol_difference_uses_nominal_sol_scale():
    first = parse_ltst("0001 00:00:00")
    second = parse_ltst("0002 00:00:00")

    assert first is not None
    assert second is not None
    assert second - first == pytest.approx(SOL_SECONDS)


def test_parse_ltst_rejects_extremely_large_sol_without_overflow():
    value = "9" * 400 + " 00:00:00"

    assert parse_ltst(value) is None


# ---------------------------------------------------------------------
# ISO-8601 parsing
# ---------------------------------------------------------------------

def test_parse_iso_aware_utc_value():
    result = parse_iso("2025-01-01T12:00:00Z", True)

    assert result is not None


def test_parse_iso_aware_timezone_is_normalized_to_utc():
    utc_value = parse_iso("2025-01-01T12:00:00Z", True)
    offset_value = parse_iso("2025-01-01T14:00:00+02:00", True)

    assert utc_value is not None
    assert offset_value is not None
    assert utc_value == pytest.approx(offset_value)


def test_parse_iso_naive_value():
    result = parse_iso("2025-01-01T12:00:00", False)

    assert result is not None


def test_parse_iso_rejects_naive_value_when_aware_is_required():
    assert parse_iso("2025-01-01T12:00:00", True) is None


def test_parse_iso_rejects_aware_value_when_naive_is_required():
    assert parse_iso("2025-01-01T12:00:00Z", False) is None


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "invalid",
        "2025-99-99T12:00:00Z",
    ],
)
def test_parse_iso_invalid_values(value):
    assert parse_iso(value, True) is None


# ---------------------------------------------------------------------
# Time column detection
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("SCLK", "sclk"),
        ("SCLK_START", "sclk"),
        ("SPACECRAFT_CLOCK", "sclk"),
        ("UTC_TIME", "utc"),
        ("LMST", "lmst"),
        ("LOCAL_MEAN_SOLAR_TIME", "lmst"),
        ("LTST", "ltst"),
        ("LOCAL_TRUE_SOLAR_TIME", "ltst"),
        ("TEMPERATURE", None),
        ("UNKNOWN_FIELD", None),
    ],
)
def test_column_time_kind(name, expected):
    assert column_time_kind(name) == expected


# ---------------------------------------------------------------------
# XML field ordering
# ---------------------------------------------------------------------

def test_ordered_fields_sorts_valid_field_numbers():
    fields = [
        {"name": "B", "field_number": "2"},
        {"name": "A", "field_number": "1"},
    ]

    result = ordered_fields(fields)

    assert [field["name"] for field in result] == ["A", "B"]


def test_ordered_fields_preserves_document_order_for_invalid_numbers():
    fields = [
        {"name": "C", "field_number": ""},
        {"name": "A", "field_number": "1"},
        {"name": "D", "field_number": "invalid"},
        {"name": "B", "field_number": "2"},
    ]

    result = ordered_fields(fields)

    assert [field["name"] for field in result] == [
        "A",
        "B",
        "C",
        "D",
    ]


@pytest.mark.parametrize(
    "field_number",
    [
        "0",
        "-1",
        "01",
        "1.0",
        "2.5",
        "invalid",
    ],
)
def test_ordered_fields_treats_noncanonical_numbers_as_invalid(
    field_number,
):
    fields = [
        {"name": "INVALID", "field_number": field_number},
        {"name": "VALID", "field_number": "2"},
    ]

    result = ordered_fields(fields)

    assert [field["name"] for field in result] == [
        "VALID",
        "INVALID",
    ]


def test_ordered_fields_preserves_order_for_equal_numbers():
    fields = [
        {"name": "A", "field_number": "1"},
        {"name": "B", "field_number": "1"},
    ]

    result = ordered_fields(fields)

    assert [field["name"] for field in result] == ["A", "B"]


def test_ordered_fields_ignores_non_dictionary_entries():
    fields = [
        {"name": "A", "field_number": "1"},
        None,
        "invalid",
        {"name": "B", "field_number": "2"},
    ]

    result = ordered_fields(fields)

    assert [field["name"] for field in result] == ["A", "B"]


def test_ordered_fields_rejects_non_list_input():
    assert ordered_fields(None) == []
    assert ordered_fields({}) == []


def test_ordered_fields_does_not_modify_input():
    fields = [
        {"name": "B", "field_number": "2"},
        {"name": "A", "field_number": "1"},
    ]

    original = copy.deepcopy(fields)

    ordered_fields(fields)

    assert fields == original


# ---------------------------------------------------------------------
# XML field metadata validation
# ---------------------------------------------------------------------

def test_validate_field_metadata_rejects_non_list_input():
    warnings = validate_field_metadata(None)

    assert len(warnings) == 1
    assert warnings[0]["code"] == "fields_not_a_list"
    assert warnings[0]["severity"] == "error"


def test_validate_field_metadata_detects_non_dictionary_entry():
    warnings = validate_field_metadata([None])

    assert any(
        warning["code"] == "field_entry_not_an_object"
        for warning in warnings
    )


def test_validate_field_metadata_detects_missing_name():
    warnings = validate_field_metadata([
        {
            "field_number": "1",
            "data_type": "real",
        }
    ])

    assert any(
        warning["code"] == "missing_field_name"
        for warning in warnings
    )


def test_validate_field_metadata_detects_missing_field_number():
    warnings = validate_field_metadata([
        {
            "name": "TEMP",
            "data_type": "real",
        }
    ])

    assert any(
        warning["code"] == "missing_field_number"
        and warning["severity"] == "warning"
        for warning in warnings
    )


@pytest.mark.parametrize(
    "field_number",
    [
        "0",
        "-1",
        "01",
        "2.5",
        "invalid",
    ],
)
def test_validate_field_metadata_detects_invalid_field_number(
    field_number,
):
    warnings = validate_field_metadata([
        {
            "name": "TEMP",
            "field_number": field_number,
            "data_type": "real",
        }
    ])

    assert any(
        warning["code"] == "invalid_field_number"
        for warning in warnings
    )


def test_validate_field_metadata_accepts_canonical_positive_number():
    warnings = validate_field_metadata([
        {
            "name": "TEMP",
            "field_number": "1",
            "data_type": "real",
        }
    ])

    assert not any(
        warning["code"] == "invalid_field_number"
        for warning in warnings
    )


def test_validate_field_metadata_detects_missing_data_type():
    warnings = validate_field_metadata([
        {
            "name": "TEMP",
            "field_number": "1",
        }
    ])

    assert any(
        warning["code"] == "missing_data_type"
        and warning["severity"] == "warning"
        for warning in warnings
    )


def test_validate_field_metadata_detects_duplicate_normalized_names():
    warnings = validate_field_metadata([
        {
            "name": "TEMP_VALUE",
            "field_number": "1",
            "data_type": "real",
        },
        {
            "name": "temp-value",
            "field_number": "2",
            "data_type": "real",
        },
    ])

    duplicates = [
        warning
        for warning in warnings
        if warning["code"] == "duplicate_field_name"
    ]

    assert len(duplicates) == 2
    assert all(
        warning["severity"] == "error"
        for warning in duplicates
    )


def test_validate_field_metadata_detects_duplicate_field_numbers():
    warnings = validate_field_metadata([
        {
            "name": "TEMP",
            "field_number": "1",
            "data_type": "real",
        },
        {
            "name": "PRESSURE",
            "field_number": "1",
            "data_type": "real",
        },
    ])

    duplicates = [
        warning
        for warning in warnings
        if warning["code"] == "duplicate_field_number"
    ]

    assert len(duplicates) == 2


def test_validate_field_metadata_does_not_modify_input():
    fields = [
        {
            "name": "TEMP",
            "field_number": "1",
        },
        {
            "name": "TEMP",
            "field_number": "2",
            "data_type": "real",
        },
    ]

    original = copy.deepcopy(fields)

    validate_field_metadata(fields)

    assert fields == original


# ---------------------------------------------------------------------
# Time column selection
# ---------------------------------------------------------------------

def test_pick_time_column_selects_default_preferred_axis():
    fields = [
        {"name": "UTC_TIME", "field_number": "1"},
        {"name": "SCLK", "field_number": "2"},
    ]

    index, name, kind = pick_time_column(fields)

    assert index == 1
    assert name == "SCLK"
    assert kind == "sclk"


def test_pick_time_column_respects_custom_preference():
    fields = [
        {"name": "SCLK", "field_number": "1"},
        {"name": "UTC_TIME", "field_number": "2"},
    ]

    index, name, kind = pick_time_column(
        fields,
        preference=("utc", "sclk"),
    )

    assert index == 1
    assert name == "UTC_TIME"
    assert kind == "utc"


def test_pick_time_column_returns_none_when_no_supported_axis_exists():
    fields = [
        {"name": "TEMP", "field_number": "1"},
        {"name": "PRESSURE", "field_number": "2"},
    ]

    assert pick_time_column(fields) == (None, None, None)


def test_pick_time_column_rejects_non_list_input():
    assert pick_time_column(None) == (None, None, None)


def test_pick_time_column_index_matches_ordered_fields():
    fields = [
        {"name": "TEMP", "field_number": "3"},
        {"name": "SCLK", "field_number": "1"},
        {"name": "UTC_TIME", "field_number": "2"},
    ]

    index, name, kind = pick_time_column(fields)

    ordered = ordered_fields(fields)

    assert index == 0
    assert ordered[index]["name"] == name
    assert name == "SCLK"
    assert kind == "sclk"


# ---------------------------------------------------------------------
# Numeric column indexes
# ---------------------------------------------------------------------

def test_numeric_column_indexes_excludes_time_columns():
    fields = [
        {
            "name": "UTC_TIME",
            "field_number": "1",
            "data_type": "integer",
        },
        {
            "name": "TEMP",
            "field_number": "2",
            "data_type": "real",
        },
        {
            "name": "LMST",
            "field_number": "3",
            "data_type": "real",
        },
        {
            "name": "LABEL",
            "field_number": "4",
            "data_type": "character",
        },
    ]

    assert numeric_column_indexes(fields, set()) == [1]


def test_numeric_column_indexes_respects_skip_indexes():
    fields = [
        {
            "name": "TEMP",
            "field_number": "1",
            "data_type": "real",
        },
        {
            "name": "PRESSURE",
            "field_number": "2",
            "data_type": "numeric",
        },
    ]

    assert numeric_column_indexes(fields, {0}) == [1]


def test_numeric_column_indexes_uses_ordered_field_indexes():
    fields = [
        {
            "name": "PRESSURE",
            "field_number": "2",
            "data_type": "real",
        },
        {
            "name": "TEMP",
            "field_number": "1",
            "data_type": "real",
        },
    ]

    assert numeric_column_indexes(fields) == [0, 1]

    ordered = ordered_fields(fields)

    assert [field["name"] for field in ordered] == [
        "TEMP",
        "PRESSURE",
    ]


def test_numeric_column_indexes_returns_empty_for_non_list_input():
    assert numeric_column_indexes(None, set()) == []


def test_numeric_column_indexes_supports_omitted_skip_argument():
    fields = [
        {
            "name": "TEMP",
            "field_number": "1",
            "data_type": "real",
        },
    ]

    assert numeric_column_indexes(fields) == [0]