"""MEDA input-file discovery and inventory generation.

This module is a reusable backend analysis component.

Pipeline-facing functions:
    discover_files(input_dir) -> list[dict]
    write_inventory(records, output_file) -> None

The caller supplies input and output paths explicitly.
The CLI is retained for backward compatibility and standalone use.

Discovery rules:
- Only files inside recognized SOL directories are inventoried.
- Nested SOL directories own their files.
- CSV/XML pairing requires the same directory and case-insensitive stem.
- Unsupported files are retained in the inventory with an issue.
- File availability describes filesystem availability only.
  It does not establish data completeness or scientific validity.
"""


from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path





# Supported Sol directory names:
# SOL100, SOL_0100, SOL-100
SOL_FOLDER_PATTERN = re.compile(
    r"^SOL[_-]?0*(\d+)$",
    re.IGNORECASE,
)

# Typical MEDA filename prefix:
# WE__0100___________CAL_ATS...
FILENAME_SOL_PATTERN = re.compile(
    r"^[A-Z0-9]+__0*(\d+)__",
    re.IGNORECASE,
)

# Product code follows CAL_:
# CAL_ATS, CAL_PS, etc.
PRODUCT_PATTERN = re.compile(
    r"(?:^|_)CAL_([A-Z0-9]+)(?:_|\.|$)",
    re.IGNORECASE,
)

SUPPORTED_EXTENSIONS = frozenset({
    ".csv",
    ".xml",
})


OUTPUT_COLUMNS = [
    "sol_folder",
    "sol_number",
    "filename",
    "relative_path",
    "extension",
    "product_code",
    "file_size_bytes",
    "file_status",
    "is_empty",
    "matching_file",
    "matching_relative_path",
    "pair_status",
    "issues",
]


def get_sol_number(folder_name: str) -> int | None:
    """Extract a Sol number from a directory name."""
    if not isinstance(folder_name, str):
        return None

    match = SOL_FOLDER_PATTERN.fullmatch(folder_name)

    if not match:
        return None

    try:
        return int(match.group(1))
    except (ValueError, OverflowError):
        return None


def get_filename_sol(filename: str) -> int | None:
    """Extract the Sol number encoded in a MEDA filename."""
    if not isinstance(filename, str):
        return None

    match = FILENAME_SOL_PATTERN.match(filename)

    if not match:
        return None

    try:
        return int(match.group(1))
    except (ValueError, OverflowError):
        return None


def get_product_code(filename: str) -> str | None:
    """Extract the product code following CAL_."""
    if not isinstance(filename, str):
        return None

    match = PRODUCT_PATTERN.search(filename)

    return match.group(1).upper() if match else None


def _relative(path: Path, root: Path) -> str:
    """Return a platform-independent relative path."""
    return path.relative_to(root).as_posix()


def _sort_path(path: Path, root: Path) -> tuple[str, str]:
    """Provide deterministic case-insensitive path ordering."""
    relative = _relative(path, root)

    return relative.casefold(), relative


def _sol_ancestor(
    path: Path,
    input_dir: Path,
) -> Path | None:
    """Find the nearest SOL directory containing the file.

    The search stops at input_dir. A nested SOL directory owns its
    files instead of assigning them to an outer SOL directory.
    """
    for parent in path.parents:
        if parent == input_dir:
            break

        if SOL_FOLDER_PATTERN.fullmatch(parent.name):
            return parent

    return None


def _file_status(file_size: int | None) -> str:
    """Classify filesystem availability without inferring data quality."""
    if file_size is None:
        return "unavailable"

    if file_size == 0:
        return "empty"

    return "available"


def _file_issues(
    extension: str,
    product_code: str | None,
    filename_sol: int | None,
    sol_number: int,
    file_status: str,
) -> list[str]:
    """Build filesystem and filename diagnostics for one file."""
    issues = []

    if extension not in SUPPORTED_EXTENSIONS:
        issues.append("unsupported_file_type")

    if product_code is None:
        issues.append("product_code_not_detected")

    if filename_sol is None:
        issues.append("sol_number_not_detected_in_filename")

    elif filename_sol != sol_number:
        issues.append("sol_number_mismatch")

    if file_status == "empty":
        issues.append("empty_file")

    elif file_status == "unavailable":
        issues.append("file_stat_unavailable")

    return issues


def _pair_file(
    file_path: Path,
    root: Path,
    files_by_identity: dict,
    extension: str,
) -> tuple[str, str, str, list[str]]:
    """Determine the counterpart and pairing diagnostics."""
    matching_file = ""
    matching_relative_path = ""
    pair_status = "not_applicable"
    issues = []

    if extension not in SUPPORTED_EXTENSIONS:
        return (
            matching_file,
            matching_relative_path,
            pair_status,
            issues,
        )

    identity = (
        _relative(file_path.parent, root).casefold(),
        file_path.stem.casefold(),
    )

    same_stem_files = files_by_identity[identity]

    expected_extension = (
        ".xml"
        if extension == ".csv"
        else ".csv"
    )

    same_type_files = [
        path
        for path in same_stem_files
        if path.suffix.lower() == extension
    ]

    counterpart_files = [
        path
        for path in same_stem_files
        if path.suffix.lower() == expected_extension
    ]

    # Detect duplicate files of the same type.
    if len(same_type_files) > 1:
        filenames = [
            path.name
            for path in same_type_files
        ]

        if len({
            name.casefold()
            for name in filenames
        }) < len(filenames):
            issues.append("duplicate_filename_case_variant")

        else:
            issues.append("duplicate_file_identity")

    # Determine counterpart status.
    if len(counterpart_files) == 1:
        counterpart = counterpart_files[0]

        matching_file = counterpart.name
        matching_relative_path = _relative(
            counterpart,
            root,
        )

        pair_status = "matched"

    elif len(counterpart_files) > 1:
        pair_status = "multiple_matching_files"
        issues.append("multiple_counterpart_files")

    else:
        pair_status = (
            "missing_xml"
            if extension == ".csv"
            else "missing_csv"
        )

        issues.append(pair_status)

    return (
        matching_file,
        matching_relative_path,
        pair_status,
        issues,
    )


def discover_files(input_dir: Path) -> list[dict]:
    """Recursively inventory files inside SOL directories.

    Args:
        input_dir:
            Dataset directory containing SOL folders.

    Returns:
        One inventory record per discovered file.

    Raises:
        FileNotFoundError:
            The supplied input directory does not exist.
        NotADirectoryError:
            The supplied input path is not a directory.

    CSV/XML pairing requires the same directory and
    case-insensitive filename stem.

    This prevents incorrect pairing between files
    located in different subdirectories.

    The function does not write files or choose an output path.
    """
    input_dir = Path(input_dir).expanduser()

    if not input_dir.exists():
        raise FileNotFoundError(
            f"Input directory does not exist: {input_dir}"
        )

    if not input_dir.is_dir():
        raise NotADirectoryError(
            f"Input path is not a directory: {input_dir}"
        )

    root = input_dir.resolve()

    # Discover SOL directories recursively.
    sol_folders = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_dir()
            and SOL_FOLDER_PATTERN.fullmatch(path.name)
        ),
        key=lambda path: _sort_path(path, root),
    )

    records = []

    for sol_folder in sol_folders:
        sol_number = get_sol_number(sol_folder.name)

        # A recognized SOL folder always produces a valid number.
        # Keep this guard to avoid generating incomplete records
        # if the folder-name parser is changed in the future.
        if sol_number is None:
            continue

        # Avoid assigning nested SOL files to an outer SOL.
        files = [
            path
            for path in sol_folder.rglob("*")
            if path.is_file()
            and _sol_ancestor(path, root) == sol_folder
        ]

        files.sort(
            key=lambda path: _sort_path(path, root)
        )

        # Group files by relative parent directory and filename stem.
        files_by_identity = defaultdict(list)

        # Count product files by product code and extension.
        product_extension_counts = Counter()

        for file_path in files:
            relative_parent = _relative(
                file_path.parent,
                root,
            ).casefold()

            identity = (
                relative_parent,
                file_path.stem.casefold(),
            )

            files_by_identity[identity].append(file_path)

            extension = file_path.suffix.lower()
            product_code = get_product_code(file_path.name)

            if (
                extension in SUPPORTED_EXTENSIONS
                and product_code
            ):
                product_extension_counts[
                    (product_code, extension)
                ] += 1

        # Build one inventory record per file.
        for file_path in files:
            extension = file_path.suffix.lower()

            product_code = get_product_code(
                file_path.name
            )

            filename_sol = get_filename_sol(
                file_path.name
            )

            relative_path = _relative(
                file_path,
                root,
            )

            # Get file size safely.
            try:
                file_size = file_path.stat().st_size
            except OSError:
                file_size = None

            file_status = _file_status(file_size)

            issues = _file_issues(
                extension=extension,
                product_code=product_code,
                filename_sol=filename_sol,
                sol_number=sol_number,
                file_status=file_status,
            )

            (
                matching_file,
                matching_relative_path,
                pair_status,
                pair_issues,
            ) = _pair_file(
                file_path=file_path,
                root=root,
                files_by_identity=files_by_identity,
                extension=extension,
            )

            issues.extend(pair_issues)

            # Detect multiple files for the same product/type
            # within the current Sol directory.
            if (
                extension in SUPPORTED_EXTENSIONS
                and product_code
                and product_extension_counts[
                    (product_code, extension)
                ] > 1
            ):
                issues.append(
                    "multiple_files_for_product_and_type"
                )

            records.append({
                "sol_folder": sol_folder.name,
                "sol_number": sol_number,
                "filename": file_path.name,
                "relative_path": relative_path,
                "extension": extension,
                "product_code": product_code or "",
                "file_size_bytes": (
                    file_size
                    if file_size is not None
                    else ""
                ),
                "file_status": file_status,
                "is_empty": (
                    file_size == 0
                    if file_size is not None
                    else ""
                ),
                "matching_file": matching_file,
                "matching_relative_path": matching_relative_path,
                "pair_status": pair_status,
                "issues": ";".join(
                    sorted(set(issues))
                ),
            })

    return records


def write_inventory(
    records: list[dict],
    output_file: Path,
) -> None:
    """Write inventory records to a CSV report.

    The output path is supplied by the caller. This allows the
    future pipeline/run manager to direct the artifact into the
    active run's output directory without changing this analyzer.
    """
    output_file = Path(output_file).expanduser()

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=OUTPUT_COLUMNS,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    """Retain the standalone CLI for backward compatibility."""
    parser = argparse.ArgumentParser(
        description="Discover and inventory MEDA Sol files."
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=Path("input"),
        help="Directory containing SOL folders.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/file_inventory.csv"),
        help="Output inventory CSV path.",
    )

    args = parser.parse_args()

    records = discover_files(args.input)

    write_inventory(
        records,
        args.output,
    )

    print(
        f"Files discovered: {len(records)}"
    )

    print(
        f"Inventory saved to: {args.output.resolve()}"
    )


if __name__ == "__main__":
    main()