from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


# Examples:
# SOL100
# SOL_0100
SOL_FOLDER_PATTERN = re.compile(r"^SOL[_-]?0*(\d+)$", re.IGNORECASE)

# Example NASA filename:
# WE__0100___________CAL_ATS_________________P01.CSV
FILENAME_SOL_PATTERN = re.compile(
    r"^[A-Z0-9]+__0*(\d+)__",
    re.IGNORECASE,
)

# Extracts ATS from CAL_ATS, PS from CAL_PS, etc.
PRODUCT_PATTERN = re.compile(
    r"(?:^|_)CAL_([A-Z0-9]+)(?:_|\.|$)",
    re.IGNORECASE,
)

SUPPORTED_EXTENSIONS = {".csv", ".xml"}

OUTPUT_COLUMNS = [
    "sol_folder",
    "sol_number",
    "filename",
    "extension",
    "product_code",
    "file_size_bytes",
    "matching_file",
    "pair_status",
    "issues",
]


def get_sol_number(folder_name: str) -> int | None:
    """Extract the Sol number from a folder name such as SOL100."""
    match = SOL_FOLDER_PATTERN.match(folder_name)
    return int(match.group(1)) if match else None


def get_filename_sol(filename: str) -> int | None:
    """Extract the Sol number encoded in a NASA filename."""
    match = FILENAME_SOL_PATTERN.match(filename)
    return int(match.group(1)) if match else None


def get_product_code(filename: str) -> str | None:
    """Extract the product code following CAL_ in the filename."""
    match = PRODUCT_PATTERN.search(filename)
    return match.group(1).upper() if match else None


def discover_files(input_dir: Path) -> list[dict]:
    """Scan Sol folders and create one inventory record per file."""
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_dir}")

    records = []

    sol_folders = sorted(
        path for path in input_dir.iterdir()
        if path.is_dir() and SOL_FOLDER_PATTERN.match(path.name)
    )

    for sol_folder in sol_folders:
        sol_number = get_sol_number(sol_folder.name)

        # Search recursively in case a Sol folder contains subfolders.
        files = sorted(path for path in sol_folder.rglob("*") if path.is_file())

        # Group files by filename stem, ignoring letter case.
        files_by_stem = defaultdict(list)

        for file_path in files:
            files_by_stem[file_path.stem.casefold()].append(file_path)

        # Count CSV/XML files for each product within this Sol.
        product_extension_counts = Counter()

        for file_path in files:
            extension = file_path.suffix.lower()
            product_code = get_product_code(file_path.name)

            if extension in SUPPORTED_EXTENSIONS and product_code:
                product_extension_counts[(product_code, extension)] += 1

        for file_path in files:
            extension = file_path.suffix.lower()
            product_code = get_product_code(file_path.name)
            filename_sol = get_filename_sol(file_path.name)

            issues = []

            if extension not in SUPPORTED_EXTENSIONS:
                issues.append("unsupported_file_type")

            if product_code is None:
                issues.append("product_code_not_detected")

            if filename_sol is None:
                issues.append("sol_number_not_detected_in_filename")
            elif filename_sol != sol_number:
                issues.append("sol_number_mismatch")

            matching_file = ""
            pair_status = "not_applicable"

            if extension in SUPPORTED_EXTENSIONS:
                stem_files = files_by_stem[file_path.stem.casefold()]
                expected_extension = ".xml" if extension == ".csv" else ".csv"

                matching_files = [
                    item for item in stem_files
                    if item.suffix.lower() == expected_extension
                ]

                same_type_files = [
                    item for item in stem_files
                    if item.suffix.lower() == extension
                ]

                if len(same_type_files) > 1:
                    issues.append("duplicate_filename_case_variant")

                if len(matching_files) == 1:
                    matching_file = matching_files[0].name
                    pair_status = "matched"
                elif len(matching_files) > 1:
                    pair_status = "multiple_matching_files"
                    issues.append("multiple_counterpart_files")
                else:
                    pair_status = "missing_xml" if extension == ".csv" else "missing_csv"
                    issues.append(pair_status)

                if product_code:
                    count = product_extension_counts[(product_code, extension)]
                    if count > 1:
                        issues.append("multiple_files_for_product_and_type")

            records.append({
                "sol_folder": sol_folder.name,
                "sol_number": sol_number,
                "filename": file_path.name,
                "extension": extension,
                "product_code": product_code or "",
                "file_size_bytes": file_path.stat().st_size,
                "matching_file": matching_file,
                "pair_status": pair_status,
                "issues": ";".join(sorted(set(issues))),
            })

    return records


def write_inventory(records: list[dict], output_file: Path) -> None:
    """Write the discovered file inventory to a CSV report."""
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover and inventory MEDA Sol files."
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=Path("input"),
        help="Directory containing SOL folders. Default: input",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/file_inventory.csv"),
        help="Output inventory CSV path.",
    )

    args = parser.parse_args()

    records = discover_files(args.input)
    write_inventory(records, args.output)

    print(f"Files discovered: {len(records)}")
    print(f"Inventory saved to: {args.output.resolve()}")


if __name__ == "__main__":
    main()