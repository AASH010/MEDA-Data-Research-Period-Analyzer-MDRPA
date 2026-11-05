
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from analyzers.file_discovery import (
    discover_files,
    get_filename_sol,
    get_product_code,
    get_sol_number,
)


class TestFileDiscovery(unittest.TestCase):

    def test_sol_folder_parser(self):
        self.assertEqual(get_sol_number("SOL100"), 100)
        self.assertEqual(get_sol_number("SOL_0100"), 100)
        self.assertIsNone(get_sol_number("DATA100"))

    def test_filename_sol_parser(self):
        self.assertEqual(
            get_filename_sol(
                "WE__0100___________CAL_ATS_________________P01.CSV"
            ),
            100,
        )

    def test_product_code_parser(self):
        self.assertEqual(
            get_product_code(
                "WE__0100___________CAL_ATS_________________P01.CSV"
            ),
            "ATS",
        )

    def test_recursive_discovery_and_pairing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sol = root / "SOL100"
            nested = sol / "nested"

            nested.mkdir(parents=True)

            filename = (
                "WE__0100___________CAL_ATS_________________P01"
            )

            (nested / f"{filename}.CSV").write_text(
                "time,value\n1,2\n",
                encoding="utf-8",
            )
            (nested / f"{filename}.XML").write_text(
                "<Product></Product>",
                encoding="utf-8",
            )

            records = discover_files(root)

            self.assertEqual(len(records), 2)

            csv_record = next(
                item for item in records
                if item["extension"] == ".csv"
            )

            self.assertEqual(csv_record["pair_status"], "matched")
            self.assertEqual(
                csv_record["matching_file"],
                f"{filename}.XML",
            )
            self.assertEqual(
                csv_record["relative_path"],
                f"SOL100/nested/{filename}.CSV",
            )

    def test_empty_file_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sol = root / "SOL100"
            sol.mkdir()

            filename = (
                "WE__0100___________CAL_ATS_________________P01.CSV"
            )
            (sol / filename).write_text("", encoding="utf-8")

            records = discover_files(root)

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["file_status"], "empty")
            self.assertIn("empty_file", records[0]["issues"])

    def test_same_stem_in_different_subfolders(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sol = root / "SOL100"

            folder_a = sol / "A"
            folder_b = sol / "B"

            folder_a.mkdir(parents=True)
            folder_b.mkdir(parents=True)

            stem = (
                "WE__0100___________CAL_ATS_________________P01"
            )

            (folder_a / f"{stem}.CSV").write_text(
                "a,b\n1,2\n",
                encoding="utf-8",
            )
            (folder_b / f"{stem}.XML").write_text(
                "<Product></Product>",
                encoding="utf-8",
            )

            records = discover_files(root)

            self.assertEqual(len(records), 2)

            csv_record = next(
                item for item in records
                if item["extension"] == ".csv"
            )

            self.assertEqual(csv_record["pair_status"], "missing_xml")


if __name__ == "__main__":
    unittest.main()
