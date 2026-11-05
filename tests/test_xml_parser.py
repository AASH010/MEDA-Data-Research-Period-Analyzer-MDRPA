import json
import sys
import xml.etree.ElementTree as ET

from pathlib import Path

import pytest

from backend.analyzers import xml_parser


# --------------------------------------------------
# Test Helpers
# --------------------------------------------------

def create_xml(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def sample_xml() -> str:
    return """
    <Product>
        <logical_identifier>urn:example:meda:product</logical_identifier>
        <title>Example MEDA Product</title>

        <Table_Character>
            <records>10</records>
            <record_length>24</record_length>
            <field_delimiter>,</field_delimiter>

            <Field_Delimited>
                <name>temperature</name>
                <field_number>1</field_number>
                <data_type>ASCII_Real</data_type>
                <description>Air temperature measurement</description>
                <unit>degC</unit>
                <Special_Constants>
                    <valid_minimum>-100</valid_minimum>
                    <valid_maximum>100</valid_maximum>
                </Special_Constants>
            </Field_Delimited>

            <Field_Delimited>
                <name>UTC_time</name>
                <field_number>2</field_number>
                <data_type>ASCII_Real</data_type>
                <description>Observation timestamp</description>
            </Field_Delimited>

            <Field_Delimited>
                <name>quality_flag</name>
                <field_number>3</field_number>
                <data_type>ASCII_Integer</data_type>
                <description>Quality status flag</description>
            </Field_Delimited>
        </Table_Character>
    </Product>
    """


# --------------------------------------------------
# Shared Identification Helpers
# --------------------------------------------------

@pytest.mark.parametrize(
    ("folder_name", "expected"),
    [
        ("SOL100", 100),
        ("SOL_0100", 100),
        ("SOL-100", 100),
        ("sol100", 100),
        ("SOL000", 0),
        ("DATA100", None),
        ("SOL", None),
        ("SOL_ABC", None),
        ("", None),
    ],
)
def test_get_sol_number(folder_name, expected):
    assert xml_parser.get_sol_number(folder_name) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        (
            "WE__0100________CAL_ATS________________P01.XML",
            "ATS",
        ),
        ("WE__0100__CAL_PS_DATA.XML", "PS"),
        ("unknown.xml", None),
    ],
)
def test_get_product_code(filename, expected):
    assert xml_parser.get_product_code(filename) == expected


def test_identification_helpers_match_shared_discovery_helpers():
    from backend.analyzers import file_discovery

    names = [
        "SOL100",
        "SOL_0100",
        "SOL-100",
        "INVALID",
    ]

    filenames = [
        "WE__0100________CAL_ATS________________P01.XML",
        "unknown.xml",
    ]

    for name in names:
        assert (
            xml_parser.get_sol_number(name)
            == file_discovery.get_sol_number(name)
        )

    for filename in filenames:
        assert (
            xml_parser.get_product_code(filename)
            == file_discovery.get_product_code(filename)
        )


# --------------------------------------------------
# XML Helper Tests
# --------------------------------------------------

def test_local_name_removes_namespace():
    assert (
        xml_parser.local_name("{http://example.com}Product")
        == "Product"
    )


def test_local_name_without_namespace():
    assert xml_parser.local_name("Product") == "Product"


def test_get_text_returns_combined_text():
    element = ET.fromstring(
        "<description> Air <part>temperature</part> </description>"
    )

    assert xml_parser.get_text(element) == "Air temperature"


def test_get_text_returns_none_for_missing_element():
    assert xml_parser.get_text(None) is None


def test_find_direct_child_ignores_namespace():
    root = ET.fromstring(
        """
        <Product xmlns="http://example.com">
            <name>Example</name>
        </Product>
        """
    )

    child = xml_parser.find_direct_child(root, "name")

    assert child is not None
    assert xml_parser.get_text(child) == "Example"


def test_find_direct_child_is_direct_only():
    root = ET.fromstring(
        """
        <Product>
            <Container>
                <name>Nested</name>
            </Container>
        </Product>
        """
    )

    assert xml_parser.find_direct_child(root, "name") is None


def test_find_all_elements_ignores_namespace():
    root = ET.fromstring(
        """
        <Product xmlns="http://example.com">
            <name>First</name>
            <Container>
                <name>Second</name>
            </Container>
        </Product>
        """
    )

    elements = xml_parser.find_all_elements(root, "name")

    assert len(elements) == 2


def test_find_first_text_returns_first_non_empty_value():
    root = ET.fromstring(
        """
        <Product>
            <title></title>
            <title>Second title</title>
            <title>Third title</title>
        </Product>
        """
    )

    assert (
        xml_parser.find_first_text(root, "title")
        == "Second title"
    )


def test_element_to_dict_preserves_attributes_and_repeated_elements():
    root = ET.fromstring(
        """
        <Product id="123">
            <name>First</name>
            <name>Second</name>
            <description lang="en">Example</description>
        </Product>
        """
    )

    result = xml_parser.element_to_dict(root)

    assert result["@id"] == "123"
    assert result["name"] == ["First", "Second"]
    assert result["description"]["@lang"] == "en"
    assert result["description"]["#text"] == "Example"


# --------------------------------------------------
# SOL Folder and CSV Matching
# --------------------------------------------------

def test_find_sol_folder_in_nested_directory(tmp_path):
    sol_dir = tmp_path / "SOL100"
    nested_dir = sol_dir / "nested"
    nested_dir.mkdir(parents=True)

    xml_path = nested_dir / "sample.xml"
    xml_path.touch()

    assert xml_parser.find_sol_folder(xml_path) == sol_dir


def test_find_sol_folder_returns_nearest_nested_sol(tmp_path):
    outer_sol = tmp_path / "SOL100"
    inner_sol = outer_sol / "SOL101"
    inner_sol.mkdir(parents=True)

    xml_path = inner_sol / "sample.xml"
    xml_path.touch()

    assert xml_parser.find_sol_folder(xml_path) == inner_sol


def test_find_sol_folder_returns_none_without_sol_ancestor(tmp_path):
    directory = tmp_path / "ordinary"
    directory.mkdir()

    xml_path = directory / "sample.xml"
    xml_path.touch()

    assert xml_parser.find_sol_folder(xml_path) is None


def test_find_matching_csv(tmp_path):
    xml_path = tmp_path / "sample.XML"
    csv_path = tmp_path / "sample.csv"

    xml_path.touch()
    csv_path.touch()

    assert xml_parser.find_matching_csv(xml_path) == "sample.csv"


def test_find_matching_csv_path(tmp_path):
    xml_path = tmp_path / "sample.xml"
    csv_path = tmp_path / "sample.csv"

    xml_path.touch()
    csv_path.touch()

    assert (
        xml_parser.find_matching_csv_path(xml_path)
        == str(csv_path)
    )


def test_csv_matching_is_case_insensitive(tmp_path):
    xml_path = tmp_path / "SAMPLE.XML"
    csv_path = tmp_path / "sample.CSV"

    xml_path.touch()
    csv_path.touch()

    assert xml_parser.find_matching_csv(xml_path) == "sample.CSV"


def test_csv_matching_returns_none_when_missing(tmp_path):
    xml_path = tmp_path / "sample.xml"
    xml_path.touch()

    assert xml_parser.find_matching_csv(xml_path) is None
    assert xml_parser.find_matching_csv_path(xml_path) is None


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Case-only filename differences are not supported by default on Windows.",
)
def test_csv_matching_returns_none_when_ambiguous(tmp_path):
    xml_path = tmp_path / "sample.xml"
    xml_path.touch()

    (tmp_path / "sample.csv").touch()
    (tmp_path / "sample.CSV").touch()

    assert xml_parser.find_matching_csv(xml_path) is None
    assert xml_parser.find_matching_csv_path(xml_path) is None

def test_parse_xml_performs_csv_lookup_once(tmp_path, monkeypatch):
    sol_dir = tmp_path / "SOL100"
    sol_dir.mkdir()

    xml_path = create_xml(
        sol_dir / "sample.xml",
        "<Product/>",
    )

    calls = []

    def fake_lookup(path):
        calls.append(path)
        return "sample.csv", str(path.parent / "sample.csv")

    monkeypatch.setattr(
        xml_parser,
        "_find_matching_csv_details",
        fake_lookup,
    )

    record = xml_parser.parse_xml_file(xml_path)

    assert len(calls) == 1
    assert record["matching_csv"] == "sample.csv"
    assert record["matching_csv_path"] == str(
        sol_dir / "sample.csv"
    )


# --------------------------------------------------
# Metadata Extraction
# --------------------------------------------------

def test_extract_field_metadata():
    root = ET.fromstring(sample_xml())

    fields = xml_parser.extract_field_metadata(root)

    assert len(fields) == 3

    temperature = fields[0]

    assert temperature["name"] == "temperature"
    assert temperature["data_type"] == "ASCII_Real"
    assert temperature["unit"] == "degC"
    assert temperature["valid_minimum"] == "-100"
    assert temperature["valid_maximum"] == "100"


def test_extract_field_metadata_supports_xml_namespace():
    root = ET.fromstring(
        """
        <Product xmlns="http://example.com">
            <Table_Character>
                <Field_Delimited>
                    <name>temperature</name>
                    <data_type>ASCII_Real</data_type>
                </Field_Delimited>
            </Table_Character>
        </Product>
        """
    )

    fields = xml_parser.extract_field_metadata(root)

    assert len(fields) == 1
    assert fields[0]["name"] == "temperature"


def test_extract_field_metadata_omits_absent_optional_values():
    root = ET.fromstring(
        """
        <Product>
            <Field_Delimited>
                <name>temperature</name>
            </Field_Delimited>
        </Product>
        """
    )

    fields = xml_parser.extract_field_metadata(root)

    assert len(fields) == 1
    assert fields[0] == {
        "xml_element_type": "Field_Delimited",
        "name": "temperature",
    }


def test_extract_product_metadata():
    root = ET.fromstring(sample_xml())

    metadata = xml_parser.extract_product_metadata(root)

    assert metadata["title"] == ["Example MEDA Product"]
    assert metadata["logical_identifier"] == [
        "urn:example:meda:product"
    ]


def test_extract_table_metadata():
    root = ET.fromstring(sample_xml())

    metadata = xml_parser.extract_table_metadata(root)

    assert metadata["record_count"] == "10"
    assert metadata["record_length"] == "24"
    assert metadata["field_delimiter"] == ","
    assert len(metadata["table_elements"]) == 1


def test_extract_table_metadata_without_table():
    root = ET.fromstring("<Product/>")

    metadata = xml_parser.extract_table_metadata(root)

    assert metadata["table_elements"] == []
    assert metadata["record_count"] is None
    assert metadata["field_delimiter"] is None


# --------------------------------------------------
# Candidate Classification
# --------------------------------------------------

def test_candidate_field_classification():
    fields = [
        {
            "name": "UTC_time",
            "description": "Observation time",
        },
        {
            "name": "quality_flag",
            "description": "Quality status",
        },
        {
            "name": "temperature",
            "description": "Air temperature",
        },
    ]

    result = xml_parser.classify_candidate_fields(fields)

    assert "UTC_time" in result["time_field_candidates"]
    assert "quality_flag" in result["quality_field_candidates"]


def test_candidate_classification_deduplicates_and_sorts():
    fields = [
        {"name": "UTC_time", "description": "timestamp"},
        {"name": "UTC_time", "description": "observation time"},
        {"name": "LMST", "description": "local time"},
    ]

    result = xml_parser.classify_candidate_fields(fields)

    assert result["time_field_candidates"] == [
        "LMST",
        "UTC_time",
    ]


def test_candidate_classification_does_not_invent_field_names():
    fields = [
        {
            "description": "Observation time",
            "data_type": "ASCII_Real",
        }
    ]

    result = xml_parser.classify_candidate_fields(fields)

    assert result["time_field_candidates"] == []
    assert result["quality_field_candidates"] == []


# --------------------------------------------------
# Single XML Parsing
# --------------------------------------------------

def test_parse_xml_file_success(tmp_path):
    xml_path = create_xml(
        tmp_path / "SOL100" / "sample.xml",
        sample_xml(),
    )

    record = xml_parser.parse_xml_file(
        xml_path,
        input_root=tmp_path,
    )

    assert record["parse_status"] == "success"
    assert record["parse_error"] is None
    assert record["sol_folder"] == "SOL100"
    assert record["sol_number"] == 100
    assert record["field_count"] == 3
    assert record["source_relative_path"] == "SOL100/sample.xml"


def test_parse_xml_does_not_assume_header(tmp_path):
    xml_path = create_xml(
        tmp_path / "SOL100" / "sample.xml",
        """
        <Product>
            <Header>
                <name>Example</name>
            </Header>
            <Table_Character>
                <records>10</records>
            </Table_Character>
        </Product>
        """,
    )

    record = xml_parser.parse_xml_file(xml_path)

    assert record["parse_status"] == "success"
    assert record["has_header"] is None
    assert (
        record["header_status"]
        == "not_determined_from_label"
    )


def test_parse_invalid_xml(tmp_path):
    xml_path = create_xml(
        tmp_path / "SOL100" / "invalid.xml",
        "<Product>",
    )

    record = xml_parser.parse_xml_file(xml_path)

    assert record["parse_status"] == "failed"
    assert record["parse_error"] is not None


def test_parse_missing_xml_file_returns_failed_record(tmp_path):
    xml_path = tmp_path / "SOL100" / "missing.xml"

    record = xml_parser.parse_xml_file(xml_path)

    assert record["parse_status"] == "failed"
    assert record["parse_error"] is not None


def test_parse_xml_full_tree_is_omitted_by_default(tmp_path):
    xml_path = create_xml(
        tmp_path / "SOL100" / "sample.xml",
        "<Product><title>Example</title></Product>",
    )

    record = xml_parser.parse_xml_file(xml_path)

    assert record["full_xml"] is None


def test_parse_xml_can_include_full_tree(tmp_path):
    xml_path = create_xml(
        tmp_path / "SOL100" / "sample.xml",
        """
        <Product id="123">
            <title>Example</title>
        </Product>
        """,
    )

    record = xml_parser.parse_xml_file(
        xml_path,
        include_full_xml=True,
    )

    assert record["full_xml"] is not None
    assert "Product" in record["full_xml"]
    assert record["full_xml"]["Product"]["@id"] == "123"


def test_parse_xml_metadata_warnings_are_structural(tmp_path):
    xml_path = create_xml(
        tmp_path / "SOL100" / "sample.xml",
        sample_xml(),
    )

    record = xml_parser.parse_xml_file(xml_path)

    assert isinstance(record["metadata_warnings"], list)

    # This field contains structural findings only.
    assert "quality_score" not in record
    assert "scientific_validity" not in record


# --------------------------------------------------
# Metadata Warning Summary
# --------------------------------------------------

def test_build_metadata_warning_summary():
    records = [
        {
            "metadata_warnings": [
                {"severity": "warning", "code": "missing_name"},
                {"severity": "error", "code": "duplicate_number"},
            ]
        },
        {
            "metadata_warnings": [
                {"severity": "warning", "code": "missing_name"},
            ]
        },
        {
            "metadata_warnings": [],
        },
    ]

    summary = xml_parser.build_metadata_warning_summary(records)

    assert summary["files_with_metadata_warnings"] == 2
    assert summary["total_metadata_warnings"] == 3

    assert summary["metadata_warning_severity_counts"] == {
        "error": 1,
        "warning": 2,
    }

    assert summary["metadata_warning_code_counts"] == {
        "duplicate_number": 1,
        "missing_name": 2,
    }

    assert "scientific validity" in summary["interpretation"]


def test_build_metadata_warning_summary_empty_records():
    summary = xml_parser.build_metadata_warning_summary([])

    assert summary["files_with_metadata_warnings"] == 0
    assert summary["total_metadata_warnings"] == 0
    assert summary["metadata_warning_severity_counts"] == {}
    assert summary["metadata_warning_code_counts"] == {}


# --------------------------------------------------
# Shared Discovery Integration
# --------------------------------------------------

def test_discover_xml_files_uses_shared_discovery(tmp_path):
    sol_dir = tmp_path / "SOL100"
    nested_dir = sol_dir / "nested"
    nested_dir.mkdir(parents=True)

    xml_path = create_xml(
        nested_dir / "sample.xml",
        "<Product/>",
    )

    create_xml(
        nested_dir / "sample.csv",
        "1,2,3",
    )

    discovered = xml_parser.discover_xml_files(tmp_path)

    assert discovered == [xml_path]


def test_discover_xml_files_excludes_files_outside_sol(tmp_path):
    sol_dir = tmp_path / "SOL100"
    sol_dir.mkdir()

    valid_xml = create_xml(
        sol_dir / "valid.xml",
        "<Product/>",
    )

    create_xml(
        tmp_path / "outside.xml",
        "<Product/>",
    )

    assert xml_parser.discover_xml_files(tmp_path) == [valid_xml]


def test_discover_xml_files_respects_nested_sol_ownership(tmp_path):
    outer_sol = tmp_path / "SOL100"
    inner_sol = outer_sol / "SOL101"
    inner_sol.mkdir(parents=True)

    outer_xml = create_xml(
        outer_sol / "outer.xml",
        "<Product/>",
    )

    inner_xml = create_xml(
        inner_sol / "inner.xml",
        "<Product/>",
    )

    discovered = xml_parser.discover_xml_files(tmp_path)

    assert outer_xml in discovered
    assert inner_xml in discovered
    assert len(discovered) == 2


def test_discover_xml_files_is_deterministic(tmp_path):
    sol_dir = tmp_path / "SOL100"
    sol_dir.mkdir()

    create_xml(sol_dir / "z.xml", "<Product/>")
    create_xml(sol_dir / "a.xml", "<Product/>")
    create_xml(sol_dir / "m.xml", "<Product/>")

    first = xml_parser.discover_xml_files(tmp_path)
    second = xml_parser.discover_xml_files(tmp_path)

    assert first == second
    assert [path.name for path in first] == [
        "a.xml",
        "m.xml",
        "z.xml",
    ]


def test_discover_xml_files_rejects_missing_directory(tmp_path):
    missing = tmp_path / "missing"

    with pytest.raises(FileNotFoundError):
        xml_parser.discover_xml_files(missing)


def test_discover_xml_files_rejects_file_path(tmp_path):
    file_path = tmp_path / "not_a_directory"
    file_path.write_text("data", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        xml_parser.discover_xml_files(file_path)


def test_discover_xml_files_delegates_to_discover_files(
    tmp_path,
    monkeypatch,
):
    sol_dir = tmp_path / "SOL100"
    sol_dir.mkdir()

    xml_path = create_xml(
        sol_dir / "sample.xml",
        "<Product/>",
    )

    calls = []

    def fake_discover_files(input_dir):
        calls.append(input_dir)

        return [
            {
                "relative_path": "SOL100/sample.xml",
                "extension": ".xml",
            },
            {
                "relative_path": "SOL100/sample.csv",
                "extension": ".csv",
            },
        ]

    monkeypatch.setattr(
        xml_parser,
        "discover_files",
        fake_discover_files,
    )

    result = xml_parser.discover_xml_files(tmp_path)

    assert calls == [tmp_path]
    assert result == [xml_path]


# --------------------------------------------------
# Metadata Inventory
# --------------------------------------------------

def test_build_metadata_inventory(tmp_path):
    create_xml(
        tmp_path / "SOL100" / "sample.xml",
        sample_xml(),
    )

    inventory = xml_parser.build_metadata_inventory(tmp_path)

    assert inventory["tool"] == (
        "MEDA Data Research & Period Analyzer"
    )
    assert inventory["module"] == "XML Parser"

    assert inventory["summary"]["xml_files_discovered"] == 1
    assert inventory["summary"]["successfully_parsed"] == 1
    assert inventory["summary"]["failed_to_parse"] == 0

    assert len(inventory["records"]) == 1
    assert inventory["records"][0]["parse_status"] == "success"


def test_build_metadata_inventory_counts_invalid_xml(tmp_path):
    create_xml(
        tmp_path / "SOL100" / "valid.xml",
        "<Product/>",
    )

    create_xml(
        tmp_path / "SOL100" / "invalid.xml",
        "<Product>",
    )

    inventory = xml_parser.build_metadata_inventory(tmp_path)

    assert inventory["summary"]["xml_files_discovered"] == 2
    assert inventory["summary"]["successfully_parsed"] == 1
    assert inventory["summary"]["failed_to_parse"] == 1


def test_build_metadata_inventory_empty_dataset(tmp_path):
    inventory = xml_parser.build_metadata_inventory(tmp_path)

    assert inventory["summary"]["xml_files_discovered"] == 0
    assert inventory["summary"]["successfully_parsed"] == 0
    assert inventory["summary"]["failed_to_parse"] == 0
    assert inventory["records"] == []


def test_build_metadata_inventory_can_include_full_xml(tmp_path):
    create_xml(
        tmp_path / "SOL100" / "sample.xml",
        "<Product><title>Example</title></Product>",
    )

    inventory = xml_parser.build_metadata_inventory(
        tmp_path,
        include_full_xml=True,
    )

    assert inventory["records"][0]["full_xml"] is not None


def test_inventory_summary_contains_warning_summary_fields(tmp_path):
    create_xml(
        tmp_path / "SOL100" / "sample.xml",
        "<Product/>",
    )

    inventory = xml_parser.build_metadata_inventory(tmp_path)

    summary = inventory["summary"]

    assert "files_with_metadata_warnings" in summary
    assert "total_metadata_warnings" in summary
    assert "metadata_warning_severity_counts" in summary
    assert "metadata_warning_code_counts" in summary


# --------------------------------------------------
# JSON Output
# --------------------------------------------------

def test_save_json_creates_parent_directories(tmp_path):
    output_file = tmp_path / "nested" / "output" / "inventory.json"

    xml_parser.save_json(
        {"records": []},
        output_file,
    )

    assert output_file.is_file()

    loaded = json.loads(
        output_file.read_text(encoding="utf-8")
    )

    assert loaded == {"records": []}


def test_save_json_preserves_unicode(tmp_path):
    output_file = tmp_path / "inventory.json"

    xml_parser.save_json(
        {"title": "معلومات MEDA"},
        output_file,
    )

    content = output_file.read_text(encoding="utf-8")

    assert "معلومات MEDA" in content


def test_save_json_writes_valid_json(tmp_path):
    output_file = tmp_path / "inventory.json"

    data = {
        "summary": {
            "xml_files_discovered": 2,
        },
        "records": [
            {"source_file": "one.xml"},
            {"source_file": "two.xml"},
        ],
    }

    xml_parser.save_json(data, output_file)

    assert json.loads(
        output_file.read_text(encoding="utf-8")
    ) == data