from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .meda_common import validate_field_metadata
except ImportError:
    from meda_common import validate_field_metadata


SOL_PATTERN = re.compile(
    r"^SOL[_-]?0*(\d+)$",
    re.IGNORECASE,
)

PRODUCT_PATTERN = re.compile(
    r"(?:^|_)CAL_([A-Z0-9]+)(?:_|\.|$)",
    re.IGNORECASE,
)

FIELD_TAGS = {
    "field_delimited",
    "field_character",
    "field_binary",
    "field_bit",
}

QUALITY_KEYWORDS = re.compile(
    r"\b(quality|qual|flag|status|validity|confidence)\b",
    re.IGNORECASE,
)

TIME_KEYWORDS = re.compile(
    r"\b(time|date|utc|ltst|lmst|timestamp|sol|sclk)\b",
    re.IGNORECASE,
)

INTERESTING_ELEMENTS = [
    "logical_identifier",
    "version_id",
    "title",
    "product_class",
    "start_date_time",
    "stop_date_time",
    "time_coordinate",
    "investigation_name",
    "observing_system_name",
    "target_name",
]


# --------------------------------------------------
# XML Helpers
# --------------------------------------------------

def local_name(tag: str) -> str:
    """Remove the XML namespace from an element name."""

    if "}" in tag:
        return tag.rsplit("}", 1)[1]

    return tag


def element_to_dict(element: ET.Element) -> Any:
    """
    Convert an XML element into a JSON-compatible structure.

    Preserves attributes, nested elements, repeated elements,
    and element text.
    """

    result = {}

    for key, value in element.attrib.items():
        result[f"@{local_name(key)}"] = value

    for child in element:
        key = local_name(child.tag)
        value = element_to_dict(child)

        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]

            result[key].append(value)

        else:
            result[key] = value

    text = (element.text or "").strip()

    if text:
        if result:
            result["#text"] = text
        else:
            return text

    return result


def get_text(element: ET.Element | None) -> str | None:
    """Return combined text from an XML element."""

    if element is None:
        return None

    value = " ".join(
        part.strip()
        for part in element.itertext()
        if part.strip()
    )

    return value or None


def find_direct_child(
    element: ET.Element,
    child_name: str,
) -> ET.Element | None:
    """Find a direct child using its namespace-independent name."""

    for child in element:

        if local_name(child.tag).lower() == child_name.lower():
            return child

    return None


def find_direct_child_text(
    element: ET.Element,
    child_name: str,
) -> str | None:
    """Return text from a direct child."""

    return get_text(
        find_direct_child(element, child_name)
    )


def find_all_elements(
    root: ET.Element,
    element_name: str,
) -> list[ET.Element]:
    """Find all elements matching a local XML name."""

    return [
        element
        for element in root.iter()
        if local_name(element.tag).lower() == element_name.lower()
    ]


def find_first_text(
    root: ET.Element,
    element_name: str,
) -> str | None:
    """Return the first non-empty matching element text."""

    for element in find_all_elements(root, element_name):

        value = get_text(element)

        if value:
            return value

    return None


# --------------------------------------------------
# File and Product Identification
# --------------------------------------------------

def get_sol_number(folder_name: str) -> int | None:
    """Extract Sol number from SOL100, SOL_100, or SOL-100."""

    match = SOL_PATTERN.fullmatch(folder_name)

    return int(match.group(1)) if match else None


def get_product_code(filename: str) -> str | None:
    """Extract product code following CAL_."""

    match = PRODUCT_PATTERN.search(filename)

    return match.group(1).upper() if match else None


def find_sol_folder(path: Path) -> Path | None:
    """
    Find the nearest SOL directory in the file's parent hierarchy.

    Supports XML files located in nested subdirectories.
    """

    for parent in path.parents:

        if SOL_PATTERN.fullmatch(parent.name):
            return parent

    return None


def find_matching_csv(xml_path: Path) -> str | None:
    """
    Find a CSV counterpart in the same directory.

    Matching uses a case-insensitive filename stem.
    Ambiguous matches return None.
    """

    if not xml_path.parent.is_dir():
        return None

    try:
        matches = [
            path
            for path in xml_path.parent.iterdir()
            if path.is_file()
            and path.stem.casefold() == xml_path.stem.casefold()
            and path.suffix.lower() == ".csv"
        ]

    except OSError:
        return None

    if len(matches) == 1:
        return matches[0].name

    return None


def find_matching_csv_path(xml_path: Path) -> str | None:
    """Return the full path of a unique CSV counterpart."""

    matching_name = find_matching_csv(xml_path)

    if matching_name is None:
        return None

    return str(xml_path.parent / matching_name)


# --------------------------------------------------
# Metadata Extraction
# --------------------------------------------------

def extract_field_metadata(root: ET.Element) -> list[dict]:
    """
    Extract PDS4 field definitions.

    This function extracts documented metadata only.
    It does not interpret quality flags or scientific validity.
    """

    fields = []

    for element in root.iter():

        tag = local_name(element.tag)

        if tag.lower() not in FIELD_TAGS:
            continue

        special_constants = [
            child
            for child in element
            if local_name(child.tag).lower() == "special_constants"
        ]

        def extract_limit(name: str) -> str | None:

            direct_value = find_direct_child_text(
                element,
                name,
            )

            if direct_value is not None:
                return direct_value

            for special in special_constants:

                value = find_direct_child_text(
                    special,
                    name,
                )

                if value is not None:
                    return value

            return None

        field = {
            "xml_element_type": tag,

            "name": find_direct_child_text(
                element,
                "name",
            ),

            "field_number": find_direct_child_text(
                element,
                "field_number",
            ),

            "data_type": find_direct_child_text(
                element,
                "data_type",
            ),

            "description": find_direct_child_text(
                element,
                "description",
            ),

            "unit": find_direct_child_text(
                element,
                "unit",
            ),

            "field_length": find_direct_child_text(
                element,
                "field_length",
            ),

            "field_location": find_direct_child_text(
                element,
                "field_location",
            ),

            "scaling_factor": find_direct_child_text(
                element,
                "scaling_factor",
            ),

            "value_offset": find_direct_child_text(
                element,
                "value_offset",
            ),

            "valid_minimum": extract_limit(
                "valid_minimum",
            ),

            "valid_maximum": extract_limit(
                "valid_maximum",
            ),

            "special_constants": [
                element_to_dict(special)
                for special in special_constants
            ],
        }

        # Remove absent optional metadata.
        field = {
            key: value
            for key, value in field.items()
            if value is not None and value != []
        }

        fields.append(field)

    return fields


# --------------------------------------------------
# Candidate Field Classification
# --------------------------------------------------

def classify_candidate_fields(fields: list[dict]) -> dict:
    """
    Identify possible time and quality-related fields.

    These are keyword-based candidates, not scientific
    classifications or interpretations.
    """

    time_candidates = []
    quality_candidates = []

    for field in fields:

        searchable_text = " ".join(
            str(field.get(key, ""))
            for key in (
                "name",
                "description",
                "data_type",
            )
        )

        searchable_text = re.sub(
            r"[^a-zA-Z0-9]+",
            " ",
            searchable_text,
        )

        if TIME_KEYWORDS.search(searchable_text):
            if field.get("name"):
                time_candidates.append(field["name"])

        if QUALITY_KEYWORDS.search(searchable_text):
            if field.get("name"):
                quality_candidates.append(field["name"])

    return {
        "time_field_candidates": sorted(
            set(time_candidates)
        ),

        "quality_field_candidates": sorted(
            set(quality_candidates)
        ),
    }


# --------------------------------------------------
# Product Metadata
# --------------------------------------------------

def extract_product_metadata(root: ET.Element) -> dict:
    """Extract selected product identification metadata."""

    metadata = {}

    for element_name in INTERESTING_ELEMENTS:

        elements = find_all_elements(
            root,
            element_name,
        )

        values = [
            get_text(element)
            for element in elements
            if get_text(element)
        ]

        if values:
            metadata[element_name] = values

    return metadata


def extract_table_metadata(root: ET.Element) -> dict:
    """
    Extract available table layout metadata.

    No assumption is made that the CSV contains a header row.
    """

    table_tags = {
        "table_character",
        "table_delimited",
        "table_binary",
        "table_binary2",
    }

    table_elements = [
        element
        for element in root.iter()
        if local_name(element.tag).lower() in table_tags
    ]

    result = {
        "table_elements": [],
        "record_count": None,
        "record_length": None,
        "records_per_file": None,
        "field_delimiter": None,
        "record_delimiter": None,
    }

    for table in table_elements:

        table_info = {
            "element_type": local_name(table.tag),
            "records": find_direct_child_text(
                table,
                "records",
            ),
            "record_length": find_direct_child_text(
                table,
                "record_length",
            ),
            "records_per_file": find_direct_child_text(
                table,
                "records_per_file",
            ),
            "field_delimiter": find_direct_child_text(
                table,
                "field_delimiter",
            ),
            "record_delimiter": find_direct_child_text(
                table,
                "record_delimiter",
            ),
        }

        result["table_elements"].append(table_info)

        for key in (
            "record_count",
            "record_length",
            "records_per_file",
            "field_delimiter",
            "record_delimiter",
        ):

            source_key = (
                "records"
                if key == "record_count"
                else key
            )

            if result[key] is None and table_info[source_key] is not None:
                result[key] = table_info[source_key]

    return result


# --------------------------------------------------
# XML Parser
# --------------------------------------------------

def parse_xml_file(
    xml_path: Path,
    input_root: Path | None = None,
    include_full_xml: bool = False,
) -> dict:
    """
    Parse one XML file and return a metadata record.

    Structural metadata warnings are reported separately.
    Original XML metadata is never automatically modified.
    """

    xml_path = Path(xml_path)

    sol_folder_path = find_sol_folder(xml_path)

    sol_folder = (
        sol_folder_path.name
        if sol_folder_path is not None
        else None
    )

    sol_number = (
        get_sol_number(sol_folder)
        if sol_folder is not None
        else None
    )

    product_code = get_product_code(xml_path.name)

    source_relative_path = None

    if input_root is not None:

        try:
            source_relative_path = xml_path.resolve().relative_to(
                Path(input_root).resolve()
            ).as_posix()

        except ValueError:
            source_relative_path = None

    record = {
        "source_file": xml_path.name,
        "source_path": str(xml_path),
        "source_relative_path": source_relative_path,
        "sol_folder": sol_folder,
        "sol_number": sol_number,
        "product_code": product_code,

        "matching_csv": find_matching_csv(xml_path),
        "matching_csv_path": find_matching_csv_path(xml_path),

        "parse_status": "success",
        "parse_error": None,

        "product_metadata": {},
        "table_metadata": {},

        "field_count": 0,
        "fields": [],

        "metadata_warnings": [],

        # Header presence is not inferred from a generic XML Header element.
        "has_header": None,
        "header_status": "not_determined_from_label",

        "field_delimiter": None,

        "candidate_fields": {
            "time_field_candidates": [],
            "quality_field_candidates": [],
        },

        "full_xml": None,
    }

    try:

        tree = ET.parse(xml_path)
        root = tree.getroot()

        fields = extract_field_metadata(root)

        record["product_metadata"] = extract_product_metadata(
            root
        )

        record["table_metadata"] = extract_table_metadata(
            root
        )

        record["field_count"] = len(fields)
        record["fields"] = fields

        # Structural validation only.
        # No scientific interpretation or automatic correction.
        record["metadata_warnings"] = validate_field_metadata(
            fields
        )

        record["field_delimiter"] = record[
            "table_metadata"
        ].get("field_delimiter")

        record["candidate_fields"] = classify_candidate_fields(
            fields
        )

        if include_full_xml:
            record["full_xml"] = {
                local_name(root.tag): element_to_dict(root)
            }

    except (ET.ParseError, OSError, ValueError) as error:

        record["parse_status"] = "failed"
        record["parse_error"] = str(error)

    return record


# --------------------------------------------------
# Metadata Warning Summary
# --------------------------------------------------

def build_metadata_warning_summary(records: list[dict]) -> dict:
    """
    Summarize structural metadata warnings across XML records.

    Warning counts are not scientific quality scores.
    """

    severity_counts = Counter()
    code_counts = Counter()

    files_with_warnings = 0
    total_warnings = 0

    for record in records:

        warnings = record.get("metadata_warnings", [])

        if warnings:
            files_with_warnings += 1

        for warning in warnings:

            severity = warning.get(
                "severity",
                "unknown",
            )

            code = warning.get(
                "code",
                "unknown",
            )

            severity_counts[severity] += 1
            code_counts[code] += 1
            total_warnings += 1

    return {
        "files_with_metadata_warnings": files_with_warnings,
        "total_metadata_warnings": total_warnings,

        "metadata_warning_severity_counts": dict(
            sorted(severity_counts.items())
        ),

        "metadata_warning_code_counts": dict(
            sorted(code_counts.items())
        ),

        "interpretation": (
            "Structural metadata findings only. "
            "They do not establish measurement quality "
            "or scientific validity."
        ),
    }


# --------------------------------------------------
# Directory Processing
# --------------------------------------------------

def discover_xml_files(input_dir: Path) -> list[Path]:
    """
    Recursively find XML files inside SOL directories.

    Supports nested SOL directories and nested subdirectories.
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

    sol_folders = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_dir()
            and SOL_PATTERN.fullmatch(path.name)
        ),
        key=lambda path: path.as_posix().casefold(),
    )

    xml_files = []

    for sol_folder in sol_folders:

        for xml_path in sol_folder.rglob("*"):

            if not xml_path.is_file():
                continue

            if xml_path.suffix.lower() != ".xml":
                continue

            # A nested SOL folder belongs to itself, not its parent.
            if find_sol_folder(xml_path) != sol_folder:
                continue

            xml_files.append(xml_path)

    return sorted(
        xml_files,
        key=lambda path: path.as_posix().casefold(),
    )


def build_metadata_inventory(
    input_dir: Path,
    include_full_xml: bool = False,
) -> dict:
    """Build a metadata inventory from discovered XML files."""

    input_dir = Path(input_dir).expanduser()

    xml_files = discover_xml_files(input_dir)

    records = []

    for index, xml_path in enumerate(xml_files, start=1):

        print(
            f"[{index}/{len(xml_files)}] Parsing: "
            f"{xml_path.name}"
        )

        records.append(
            parse_xml_file(
                xml_path,
                input_root=input_dir,
                include_full_xml=include_full_xml,
            )
        )

    successful = sum(
        record["parse_status"] == "success"
        for record in records
    )

    failed = len(records) - successful

    metadata_warning_summary = build_metadata_warning_summary(
        records
    )

    return {
        "tool": "MEDA Data Research & Period Analyzer",
        "module": "XML Parser",

        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "input_directory": str(input_dir.resolve()),

        "summary": {
            "xml_files_discovered": len(xml_files),
            "successfully_parsed": successful,
            "failed_to_parse": failed,

            **metadata_warning_summary,
        },

        "records": records,
    }


# --------------------------------------------------
# Output
# --------------------------------------------------

def save_json(
    data: dict,
    output_file: Path,
) -> None:
    """Save metadata inventory as UTF-8 JSON."""

    output_file = Path(output_file).expanduser()

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_file.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False,
        )


# --------------------------------------------------
# Main
# --------------------------------------------------

def main() -> None:

    parser = argparse.ArgumentParser(
        description="Parse MEDA PDS4 XML metadata files."
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
        default=Path("output/metadata_inventory.json"),
        help="JSON output file.",
    )

    parser.add_argument(
        "--include-full-xml",
        action="store_true",
        help="Include the complete XML tree in the JSON output.",
    )

    args = parser.parse_args()

    print("Starting MEDA XML Parser...")

    inventory = build_metadata_inventory(
        args.input,
        include_full_xml=args.include_full_xml,
    )

    save_json(
        inventory,
        args.output,
    )

    summary = inventory["summary"]

    print("")
    print("XML parsing completed.")

    print(
        f"Discovered: {summary['xml_files_discovered']}"
    )

    print(
        f"Successful: {summary['successfully_parsed']}"
    )

    print(
        f"Failed: {summary['failed_to_parse']}"
    )

    print(
        "Files with metadata warnings: "
        f"{summary['files_with_metadata_warnings']}"
    )

    print(
        "Total metadata warnings: "
        f"{summary['total_metadata_warnings']}"
    )

    print(
        "Metadata warning severity counts: "
        f"{summary['metadata_warning_severity_counts']}"
    )

    print(
        f"Output: {args.output.resolve()}"
    )


if __name__ == "__main__":
    main()