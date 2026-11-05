
import sys
import tempfile
import unittest

from pathlib import Path
from xml.etree import ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from analyzers.xml_parser import (
    get_sol_number,
    get_product_code,
    find_sol_folder,
    find_matching_csv,
    extract_field_metadata,
    classify_candidate_fields,
    parse_xml_file,
    discover_xml_files,
)


class TestXMLParser(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        self.sol_dir = self.root / "SOL100"
        self.sol_dir.mkdir()

        self.sub_dir = self.sol_dir / "nested"
        self.sub_dir.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_xml(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_get_sol_number(self):
        self.assertEqual(get_sol_number("SOL100"), 100)
        self.assertEqual(get_sol_number("SOL_0100"), 100)
        self.assertEqual(get_sol_number("SOL-100"), 100)
        self.assertIsNone(get_sol_number("DATA100"))

    def test_get_product_code(self):
        self.assertEqual(
            get_product_code(
                "WE__0100________CAL_ATS________________P01.XML"
            ),
            "ATS",
        )

        self.assertIsNone(
            get_product_code("unknown.xml")
        )

    def test_find_sol_folder_in_nested_directory(self):
        xml_path = self.sub_dir / "sample.xml"
        xml_path.touch()

        self.assertEqual(
            find_sol_folder(xml_path),
            self.sol_dir,
        )

    def test_find_matching_csv(self):
        xml_path = self.sub_dir / "sample.XML"
        csv_path = self.sub_dir / "sample.csv"

        xml_path.touch()
        csv_path.touch()

        self.assertEqual(
            find_matching_csv(xml_path),
            "sample.csv",
        )

    def test_extract_field_metadata(self):
        xml = """
        <Product>
            <Table_Character>
                <Field_Delimited>
                    <name>temperature</name>
                    <field_number>1</field_number>
                    <data_type>ASCII_Real</data_type>
                    <unit>degC</unit>
                    <Special_Constants>
                        <valid_minimum>-100</valid_minimum>
                        <valid_maximum>100</valid_maximum>
                    </Special_Constants>
                </Field_Delimited>
            </Table_Character>
        </Product>
        """

        root = ET.fromstring(xml)
        fields = extract_field_metadata(root)

        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]["name"], "temperature")
        self.assertEqual(fields[0]["data_type"], "ASCII_Real")
        self.assertEqual(fields[0]["unit"], "degC")
        self.assertEqual(fields[0]["valid_minimum"], "-100")
        self.assertEqual(fields[0]["valid_maximum"], "100")

    def test_candidate_field_classification(self):
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

        result = classify_candidate_fields(fields)

        self.assertIn(
            "UTC_time",
            result["time_field_candidates"],
        )

        self.assertIn(
            "quality_flag",
            result["quality_field_candidates"],
        )

    def test_parse_xml_does_not_assume_header(self):
        xml_path = self.sub_dir / "sample.xml"

        self.create_xml(
            xml_path,
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

        record = parse_xml_file(xml_path)

        self.assertEqual(record["parse_status"], "success")
        self.assertIsNone(record["has_header"])
        self.assertEqual(
            record["header_status"],
            "not_determined_from_label",
        )

    def test_parse_invalid_xml(self):
        xml_path = self.sub_dir / "invalid.xml"
        self.create_xml(xml_path, "<Product>")

        record = parse_xml_file(xml_path)

        self.assertEqual(record["parse_status"], "failed")
        self.assertIsNotNone(record["parse_error"])

    def test_discover_xml_files_recursively(self):
        xml_path = self.sub_dir / "sample.xml"
        self.create_xml(xml_path, "<Product/>")

        discovered = discover_xml_files(self.root)

        normalized_xml_path = xml_path.resolve()
        normalized_discovered = {
        path.resolve()
        for path in discovered
        }

        self.assertIn(normalized_xml_path, normalized_discovered)

    def test_nested_sol_is_not_claimed_by_parent(self):
        nested_sol = self.sol_dir / "SOL101"
        nested_sol.mkdir()

        xml_path = nested_sol / "sample.xml"
        self.create_xml(xml_path, "<Product/>")

        self.assertEqual(
            find_sol_folder(xml_path),
            nested_sol,
        )


if __name__ == "__main__":
    unittest.main()
