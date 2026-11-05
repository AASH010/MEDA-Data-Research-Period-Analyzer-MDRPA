
from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET

from pathlib import Path
from datetime import datetime, timezone


SOL_PATTERN = re.compile(r"^sol[_-]?0*(\d+)$", re.IGNORECASE)

PRODUCT_PATTERN = re.compile(
    r"(?:^|_)CAL_([A-Z0-9]+)(?:_|\.|$)",
    re.IGNORECASE,
)

FIELD_TAG_PATTERN = re.compile(
    r"^Field_",
    re.IGNORECASE,
)

QUALITY_KEYWORDS = re.compile(
    r"\b(quality|qual|flag|status|validity|confidence)\b",
    re.IGNORECASE,
)

TIME_KEYWORDS = re.compile(
    r"\b(time|date|utc|ltst|lmst|timestamp|sol)\b",
    re.IGNORECASE,
)


# --------------------------------------------------
# XML Helpers
# --------------------------------------------------

def local_name(tag: str) -> str:
    """Remove the XML namespace from an element or attribute name."""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]

    return tag


def element_to_dict(element: ET.Element):
    """
    Convert an XML element into a JSON-compatible structure.

    Preserves:
    - Element names
    - Attributes
    - Text
    - Nested elements
    - Repeated elements
    """

    result = {}

    # Preserve attributes
    for key, value in element.attrib.items():
        result[f"@{local_name(key)}"] = value

    # Preserve child elements
    for child in element:
        key = local_name(child.tag)
        value = element_to_dict(child)

        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]

            result[key].append(value)

        else:
            result[key] = value

    # Preserve text
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


def find_direct_child_text(
    element: ET.Element,
    child_name: str,
) -> str | None:
    """Find text from a direct child using its local XML name."""
    for child in element:
        if local_name(child.tag).lower() == child_name.lower():
            return get_text(child)

    return None


def find_all_elements(
    root: ET.Element,
    element_name: str,
) -> list[ET.Element]:
    """Find all elements matching a local name."""
    return [
        element
        for element in root.iter()
        if local_name(element.tag).lower() == element_name.lower()
    ]


# --------------------------------------------------
# File and Product Identification
# --------------------------------------------------

def get_sol_number(folder_name: str) -> int | None:
    match = SOL_PATTERN.match(folder_name)

    if not match:
        return None

    return int(match.group(1))


def get_product_code(filename: str) -> str | None:
    match = PRODUCT_PATTERN.search(filename)

    if not match:
        return None

    return match.group(1).upper()


def find_matching_csv(xml_path: Path) -> str | None:
    """Find a CSV file with the same filename stem."""
    parent = xml_path.parent

    matches = [
        path
        for path in parent.iterdir()
        if path.is_file()
        and path.stem.casefold() == xml_path.stem.casefold()
        and path.suffix.lower() == ".csv"
    ]

    if len(matches) == 1:
        return matches[0].name

    return None


# --------------------------------------------------
# Metadata Extraction
# --------------------------------------------------

def extract_field_metadata(root: ET.Element) -> list[dict]:
    """
    Extract PDS4 table field definitions.

    This does not interpret the scientific meaning of
    quality flags or determine whether values are valid.
    """

    fields = []

    for element in root.iter():

        tag = local_name(element.tag)

        if not FIELD_TAG_PATTERN.match(tag):
            continue

        field = {
            "xml_element_type": tag,
            "name": find_direct_child_text(element, "name"),
            "field_number": find_direct_child_text(
                element, "field_number"
            ),
            "data_type": find_direct_child_text(
                element, "data_type"
            ),
            "description": find_direct_child_text(
                element, "description"
            ),
            "unit": find_direct_child_text(
                element, "unit"
            ),
            "field_length": find_direct_child_text(
                element, "field_length"
            ),
            "field_location": find_direct_child_text(
                element, "field_location"
            ),
            "scaling_factor": find_direct_child_text(
                element, "scaling_factor"
            ),
            "value_offset": find_direct_child_text(
                element, "value_offset"
            ),
            "valid_minimum": find_direct_child_text(
                element, "valid_minimum"
            ),
            "valid_maximum": find_direct_child_text(
                element, "valid_maximum"
            ),
            "special_constants": [],
        }

        # Capture all special constants attached to this field.
        for child in element:
            if local_name(child.tag).lower() == "special_constants":
                field["special_constants"].append(
                    element_to_dict(child)
                )

        # Remove empty optional values.
        field = {
            key: value
            for key, value in field.items()
            if value is not None and value != []
        }

        fields.append(field)

    return fields


def classify_candidate_fields(fields: list[dict]) -> dict:
    """
    Identify possible time and quality-related fields.

    These are candidates only. No scientific interpretation
    is made here.
    """

    time_candidates = []
    quality_candidates = []

    for field in fields:

        searchable_text = " ".join(
            str(field.get(key, ""))
            for key in ("name", "description", "data_type")
        )

        if TIME_KEYWORDS.search(searchable_text):
            time_candidates.append(field.get("name"))

        if QUALITY_KEYWORDS.search(searchable_text):
            quality_candidates.append(field.get("name"))

    return {
        "time_field_candidates": sorted(
            set(name for name in time_candidates if name)
        ),
        "quality_field_candidates": sorted(
            set(name for name in quality_candidates if name)
        ),
    }


def extract_product_metadata(root: ET.Element) -> dict:
    """Extract basic product identification metadata."""

    metadata = {}

    interesting_elements = [
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

    for element_name in interesting_elements:

        elements = find_all_elements(root, element_name)

        values = [
            get_text(element)
            for element in elements
            if get_text(element)
        ]

        if values:
            metadata[element_name] = values

    return metadata


# --------------------------------------------------
# XML Parser
# --------------------------------------------------

def parse_xml_file(xml_path: Path) -> dict:
    """Parse one XML file and return its metadata record."""

    sol_folder = xml_path.parent.name
    sol_number = get_sol_number(sol_folder)

    product_code = get_product_code(xml_path.name)

    record = {
        "source_file": xml_path.name,
        "source_path": str(xml_path),
        "sol_folder": sol_folder,
        "sol_number": sol_number,
        "product_code": product_code,
        "matching_csv": find_matching_csv(xml_path),
        "parse_status": "success",
        "parse_error": None,
    }

    try:

        tree = ET.parse(xml_path)
        root = tree.getroot()

        fields = extract_field_metadata(root)

        record["product_metadata"] = extract_product_metadata(root)

        record["field_count"] = len(fields)
        record["fields"] = fields

        record["candidate_fields"] = classify_candidate_fields(
            fields
        )

        # Preserve the complete XML document structure.
        record["full_xml"] = {
            local_name(root.tag): element_to_dict(root)
        }

    except (ET.ParseError, OSError, ValueError) as error:

        record["parse_status"] = "failed"
        record["parse_error"] = str(error)

        record["product_metadata"] = {}
        record["field_count"] = 0
        record["fields"] = []
        record["candidate_fields"] = {
            "time_field_candidates": [],
            "quality_field_candidates": [],
        }
        record["full_xml"] = None

    return record


# --------------------------------------------------
# Directory Processing
# --------------------------------------------------

def discover_xml_files(input_dir: Path) -> list[Path]:
    """Find XML files inside SOL folders."""

    if not input_dir.exists():
        raise FileNotFoundError(
            f"Input directory does not exist: {input_dir}"
        )

    if not input_dir.is_dir():
        raise NotADirectoryError(
            f"Input path is not a directory: {input_dir}"
        )

    xml_files = []

    for sol_folder in sorted(input_dir.iterdir()):

        if not sol_folder.is_dir():
            continue

        if not SOL_PATTERN.match(sol_folder.name):
            continue

        for xml_path in sol_folder.rglob("*"):

            if (
                xml_path.is_file()
                and xml_path.suffix.lower() == ".xml"
            ):
                xml_files.append(xml_path)

    return sorted(xml_files)


def build_metadata_inventory(
    input_dir: Path,
) -> dict:

    xml_files = discover_xml_files(input_dir)

    records = []

    for index, xml_path in enumerate(xml_files, start=1):

        print(
            f"[{index}/{len(xml_files)}] Parsing: "
            f"{xml_path.name}"
        )

        records.append(parse_xml_file(xml_path))

    successful = sum(
        record["parse_status"] == "success"
        for record in records
    )

    failed = len(records) - successful

    return {
        "tool": "MEDA Research Tool",
        "module": "XML Parser",
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "input_directory": str(input_dir),
        "summary": {
            "xml_files_discovered": len(xml_files),
            "successfully_parsed": successful,
            "failed_to_parse": failed,
        },
        "records": records,
    }


# --------------------------------------------------
# Output
# --------------------------------------------------

def save_json(data: dict, output_file: Path) -> None:

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

def main():

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

    args = parser.parse_args()

    print("Starting MEDA XML Parser...")

    inventory = build_metadata_inventory(args.input)

    save_json(inventory, args.output)

    summary = inventory["summary"]

    print("")
    print("XML parsing completed.")
    print(f"Discovered: {summary['xml_files_discovered']}")
    print(f"Successful: {summary['successfully_parsed']}")
    print(f"Failed: {summary['failed_to_parse']}")
    print(f"Output: {args.output.resolve()}")


if __name__ == "__main__":
    main()
