import csv
import re
from collections import defaultdict, Counter
from pathlib import Path

report_path = Path("output_test/quality_field_report.csv")

if not report_path.exists():
    raise FileNotFoundError(report_path)

fields_by_category = defaultdict(set)
mapping_counts = Counter()

with report_path.open(
    "r",
    encoding="utf-8-sig",
    newline="",
) as file:

    reader = csv.DictReader(file)

    for row in reader:

        if row.get("analysis_status") != "analysed":
            continue

        category = row.get("field_type", "")
        field_name = row.get("field_name", "")

        if field_name:
            fields_by_category[category].add(field_name)

        notes = row.get("notes", "")

        match = re.search(
            r"Column mapping: ([^.]+)\.",
            notes,
        )

        if match:
            mapping_counts[match.group(1)] += 1


print("=" * 65)
print("QUALITY REPORT FIELD CLASSIFICATION")
print("=" * 65)

for category, names in sorted(fields_by_category.items()):

    print()
    print(f"### {category} ({len(names)} unique fields)")

    for name in sorted(names):
        print(f"  - {name}")


print()
print("=" * 65)
print("COLUMN MAPPING STATUS")
print("=" * 65)

for status, count in sorted(mapping_counts.items()):
    print(f"{status}: {count}")