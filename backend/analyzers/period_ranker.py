
"""
MEDA Period Ranker

Compares candidate Sol windows using available MEDA analysis reports.

This is an exploratory comparison tool, not a scientific validation
or certification tool.

Python standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math

from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = Path("output")

DEFAULT_INVENTORY = DEFAULT_OUTPUT_DIR / "file_inventory.csv"
DEFAULT_COVERAGE = DEFAULT_OUTPUT_DIR / "coverage_report.csv"
DEFAULT_QUALITY = DEFAULT_OUTPUT_DIR / "quality_field_report.csv"
DEFAULT_SYNC_FILES = DEFAULT_OUTPUT_DIR / "synchronization_file_report.csv"
DEFAULT_SYNC_PAIRS = DEFAULT_OUTPUT_DIR / "synchronization_pair_report.csv"

DEFAULT_RANKING = DEFAULT_OUTPUT_DIR / "period_ranking.csv"
DEFAULT_SUMMARY = DEFAULT_OUTPUT_DIR / "period_ranking_summary.json"

DEFAULT_START_SOL = None
DEFAULT_END_SOL = None

DEFAULT_WINDOW_SIZE = 10

DEFAULT_REQUIRED_PRODUCTS = (
    "ATS",
    "PS",
    "RDS",
    "RHS",
    "TIRS",
    "WS",
)

OPTIONAL_PRODUCTS = ("ENG",)

METRIC_NAMES = (
    "file_availability",
    "data_integrity",
    "quality_indicators",
    "synchronization",
)

DEFAULT_WEIGHTS = {
    "file_availability": 0.20,
    "data_integrity": 0.45,
    "quality_indicators": 0.15,
    "synchronization": 0.20,
}

DEFAULT_INTEGRITY_WEIGHTS = {
    "timestamps": 1.0,
    "values": 1.0,
}


# ---------------------------------------------------------
# Input report schemas
# ---------------------------------------------------------

REPORT_REQUIRED_COLUMNS = {
    "inventory": {
        "sol_number",
        "extension",
        "product_code",
    },
    "coverage": {
        "sol_number",
        "row_count",
        "parsed_timestamp_count",
        "missing_timestamp_count",
        "invalid_timestamp_count",
        "numeric_value_count",
        "numeric_missing_count",
        "numeric_invalid_count",
    },
    "quality": {
        "sol_number",
        "field_type",
        "analysis_status",
        "numeric_count",
        "below_valid_minimum",
        "above_valid_maximum",
        "valid_minimum",
        "valid_maximum",
    },
    "sync_files": {
        "sol_number",
        "analysis_status",
        "parsed_timestamps",
    },
    "sync_pairs": {
        "sol_number",
        "comparison_status",
        "match_rate_sparser_percent",
        "matched_timestamps",
        "overlap_duration",
    },
}


# ---------------------------------------------------------
# General helpers
# ---------------------------------------------------------

def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        number = float(str(value).strip())
    except (TypeError, ValueError, OverflowError):
        return None

    return number if math.isfinite(number) else None


def safe_int(value: Any) -> int | None:
    number = safe_float(value)

    if number is None or not number.is_integer():
        return None

    return int(number)


def sol_number(value: Any) -> int | None:
    return safe_int(value)


def clamp(
    value: float,
    low: float = 0.0,
    high: float = 100.0,
) -> float:
    return max(low, min(high, value))


def average(values: list[float]) -> float | None:
    if not values:
        return None

    return sum(values) / len(values)


def normalized_weights(
    weights: dict[str, float],
) -> dict[str, float]:
    cleaned = {}

    for key, value in weights.items():
        number = safe_float(value)

        if number is None or number < 0:
            raise ValueError(
                f"Weight '{key}' must be finite and non-negative."
            )

        cleaned[key] = number

    total = sum(cleaned.values())

    if not math.isfinite(total) or total <= 0:
        raise ValueError("At least one weight must be positive.")

    return {
        key: value / total
        for key, value in cleaned.items()
    }



def read_csv(
    path: Path,
    required_columns: set[str] | None = None,
) -> list[dict]:
    """
    Read a CSV report and validate its header when requested.

    Header names are normalized before rows are returned.
    Missing reports are treated as unavailable reports.
    Existing reports with invalid headers raise ValueError.
    """
    path = Path(path)

    if not path.exists():
        print(
            "WARNING: Report not found; treating as unavailable: "
            f"{path}"
        )
        return []

    try:
        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            reader = csv.DictReader(handle)

            if not reader.fieldnames:
                raise ValueError(
                    f"Report has no header: {path}"
                )

            normalized_headers = [
                str(name).strip()
                for name in reader.fieldnames
                if name is not None
            ]

            if len(normalized_headers) != len(reader.fieldnames):
                raise ValueError(
                    f"Invalid empty header in report: {path}"
                )

            if (
                any(not name for name in normalized_headers)
                or len(set(normalized_headers)) != len(normalized_headers)
            ):
                raise ValueError(
                    f"Report contains empty or duplicate headers: {path}"
                )

            if required_columns:
                missing = sorted(
                    required_columns - set(normalized_headers)
                )

                if missing:
                    raise ValueError(
                        f"Invalid report schema in {path}. "
                        f"Missing required columns: {', '.join(missing)}"
                    )

            reader.fieldnames = normalized_headers

            return list(reader)

    except csv.Error as error:
        raise ValueError(
            f"Could not read CSV report {path}: {error}"
        ) from error


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            data,
            handle,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )


# ---------------------------------------------------------
# Automatic Sol range detection
# ---------------------------------------------------------

def discover_sol_numbers(
    *report_rows: list[dict],
) -> set[int]:
    """
    Collect valid Sol numbers from the union of supplied reports.
    """
    discovered = set()

    for rows in report_rows:
        for row in rows:
            sol = sol_number(row.get("sol_number"))

            if sol is not None and sol >= 0:
                discovered.add(sol)

    return discovered


def resolve_sol_range(
    requested_start: int | None,
    requested_end: int | None,
    discovered_sols: set[int],
) -> tuple[int, int, str]:

    if not discovered_sols:
        raise ValueError(
            "Cannot determine the Sol range: no valid Sol numbers "
            "were found in the supplied analyzer reports."
        )

    observed_start = min(discovered_sols)
    observed_end = max(discovered_sols)

    start_sol = (
        requested_start
        if requested_start is not None
        else observed_start
    )

    end_sol = (
        requested_end
        if requested_end is not None
        else observed_end
    )

    if requested_start is not None and requested_end is not None:
        source = "explicit_cli"
    elif requested_start is not None:
        source = "explicit_start_auto_end"
    elif requested_end is not None:
        source = "auto_start_explicit_end"
    else:
        source = "automatic_from_reports"

    if start_sol < 0 or end_sol < 0:
        raise ValueError("Sol numbers cannot be negative.")

    if start_sol > end_sol:
        raise ValueError("Start Sol cannot exceed End Sol.")

    return start_sol, end_sol, source


# ---------------------------------------------------------
# Candidate windows
# ---------------------------------------------------------

def build_windows(
    start_sol: int,
    end_sol: int,
    window_size: int,
) -> list[tuple[int, int]]:

    if start_sol < 0 or end_sol < 0:
        raise ValueError("Sol numbers cannot be negative.")

    if start_sol > end_sol:
        raise ValueError("Start Sol cannot exceed End Sol.")

    if window_size < 1:
        raise ValueError("Window size must be at least 1.")

    windows = []
    current = start_sol

    while current <= end_sol:
        window_end = min(
            current + window_size - 1,
            end_sol,
        )

        windows.append((current, window_end))
        current = window_end + 1

    return windows


def window_label(window: tuple[int, int]) -> str:
    return f"Sol {window[0]}-{window[1]}"


# ---------------------------------------------------------
# Inventory analysis
# ---------------------------------------------------------

def analyse_inventory(
    rows: list[dict],
    start_sol: int,
    end_sol: int,
) -> dict:

    result = defaultdict(lambda: {
        "products": set(),
        "csv_files": 0,
        "xml_files": 0,
        "inventory_entries": 0,
        "missing_pairs": 0,
    })

    for row in rows:
        sol = sol_number(row.get("sol_number"))

        if sol is None or not start_sol <= sol <= end_sol:
            continue

        extension = (
            str(row.get("extension") or "")
            .strip()
            .lower()
            .lstrip(".")
        )

        product = (
            str(row.get("product_code") or "")
            .strip()
            .upper()
        )

        item = result[sol]
        item["inventory_entries"] += 1

        if extension == "csv":
            item["csv_files"] += 1

            if product:
                item["products"].add(product)

        elif extension == "xml":
            item["xml_files"] += 1

        pair_status = str(
            row.get("pair_status") or ""
        ).lower()

        if "missing" in pair_status:
            item["missing_pairs"] += 1

    return result


# ---------------------------------------------------------
# Coverage analysis
# ---------------------------------------------------------

def analyse_coverage(rows: list[dict]) -> dict:

    result = defaultdict(lambda: {
        "files": 0,
        "rows": 0,
        "parsed_timestamps": 0,
        "missing_timestamps": 0,
        "invalid_timestamps": 0,
        "numeric_values": 0,
        "numeric_missing": 0,
        "numeric_invalid": 0,
        "special_error": 0,
        "special_saturated": 0,
        "special_unknown": 0,
        "special_not_applicable": 0,
        "special_ambiguous": 0,
    })

    fields = (
        ("rows", "row_count"),
        ("parsed_timestamps", "parsed_timestamp_count"),
        ("missing_timestamps", "missing_timestamp_count"),
        ("invalid_timestamps", "invalid_timestamp_count"),
        ("numeric_values", "numeric_value_count"),
        ("numeric_missing", "numeric_missing_count"),
        ("numeric_invalid", "numeric_invalid_count"),
        ("special_error", "special_error_count"),
        ("special_saturated", "special_saturated_count"),
        ("special_unknown", "special_unknown_count"),
        ("special_not_applicable", "special_not_applicable_count"),
        ("special_ambiguous", "special_ambiguous_count"),
    )

    for row in rows:
        sol = sol_number(row.get("sol_number"))

        if sol is None:
            continue

        item = result[sol]
        item["files"] += 1

        for target, column in fields:
            value = safe_int(row.get(column))

            if value is not None and value >= 0:
                item[target] += value

    return result

# ---------------------------------------------------------
# Quality analysis
# ---------------------------------------------------------

def analyse_quality(rows: list[dict]) -> dict:
    """
    Aggregate documented XML range-check information.

    Only field_type == range_check contributes to the range
    indicator. Other categories may describe the same field and
    must not duplicate its range statistics.
    """
    result = defaultdict(lambda: {
        "field_reports": 0,
        "analysed_fields": 0,
        "range_checked_fields": 0,
        "range_checked_values": 0,
        "below_minimum": 0,
        "above_maximum": 0,
    })

    for row in rows:
        sol = sol_number(row.get("sol_number"))

        if sol is None:
            continue

        item = result[sol]
        item["field_reports"] += 1

        if (
            str(row.get("analysis_status") or "")
            .strip()
            .casefold()
            != "analysed"
        ):
            continue

        item["analysed_fields"] += 1

        field_type = (
            str(row.get("field_type") or "")
            .strip()
            .casefold()
        )

        if field_type != "range_check":
            continue

        minimum = safe_float(row.get("valid_minimum"))
        maximum = safe_float(row.get("valid_maximum"))

        if minimum is None and maximum is None:
            continue

        numeric_count = safe_int(row.get("numeric_count"))
        below = safe_int(row.get("below_valid_minimum"))
        above = safe_int(row.get("above_valid_maximum"))

        if (
            numeric_count is None
            or below is None
            or above is None
            or numeric_count < 0
            or below < 0
            or above < 0
        ):
            continue

        # A row with impossible out-of-range counts is not used.
        if below + above > numeric_count:
            continue

        item["range_checked_fields"] += 1
        item["range_checked_values"] += numeric_count
        item["below_minimum"] += below
        item["above_maximum"] += above

    return result


# ---------------------------------------------------------
# Synchronization analysis
# ---------------------------------------------------------

def analyse_sync_files(rows: list[dict]) -> dict:

    result = defaultdict(lambda: {
        "files": 0,
        "analysed_files": 0,
        "parsed_timestamps": 0,
    })

    for row in rows:
        sol = sol_number(row.get("sol_number"))

        if sol is None:
            continue

        item = result[sol]
        item["files"] += 1

        if (
            str(row.get("analysis_status") or "")
            .strip()
            .casefold()
            == "analysed"
        ):
            item["analysed_files"] += 1

            count = safe_int(row.get("parsed_timestamps"))

            if count is not None and count >= 0:
                item["parsed_timestamps"] += count

    return result


def analyse_sync_pairs(rows: list[dict]) -> dict:

    result = defaultdict(lambda: {
        "pairs": 0,
        "analysed_pairs": 0,
        "match_rates": [],
        "matched_timestamps": 0,
        "overlap_durations": [],
    })

    for row in rows:
        sol = sol_number(row.get("sol_number"))

        if sol is None:
            continue

        item = result[sol]
        item["pairs"] += 1

        if (
            str(row.get("comparison_status") or "")
            .strip()
            .casefold()
            != "analysed"
        ):
            continue

        item["analysed_pairs"] += 1

        rate = safe_float(
            row.get("match_rate_sparser_percent")
        )

        if rate is not None and 0 <= rate <= 100:
            item["match_rates"].append(rate)

        matched = safe_int(row.get("matched_timestamps"))

        if matched is not None and matched >= 0:
            item["matched_timestamps"] += matched

        overlap = safe_float(row.get("overlap_duration"))

        if overlap is not None and overlap >= 0:
            item["overlap_durations"].append(overlap)

    return result


# ---------------------------------------------------------
# Per-Sol metric calculation
# ---------------------------------------------------------

def calculate_integrity(
    coverage_data: dict,
    integrity_weights: dict[str, float],
) -> tuple[float | None, dict]:

    parsed = coverage_data.get("parsed_timestamps", 0)
    missing_ts = coverage_data.get("missing_timestamps", 0)
    invalid_ts = coverage_data.get("invalid_timestamps", 0)

    numeric = coverage_data.get("numeric_values", 0)
    missing_numeric = coverage_data.get("numeric_missing", 0)
    invalid_numeric = coverage_data.get("numeric_invalid", 0)

    timestamp_total = parsed + missing_ts + invalid_ts
    numeric_total = numeric + missing_numeric + invalid_numeric

    components = {}
    weighted_sum = 0.0
    available_weight = 0.0

    if timestamp_total > 0:
        score = parsed / timestamp_total * 100
        components["timestamps"] = score

        weight = integrity_weights["timestamps"]

        if weight > 0:
            weighted_sum += score * weight
            available_weight += weight

    if numeric_total > 0:
        score = numeric / numeric_total * 100
        components["values"] = score

        weight = integrity_weights["values"]

        if weight > 0:
            weighted_sum += score * weight
            available_weight += weight

    if available_weight <= 0:
        return None, components

    return weighted_sum / available_weight, components


def calculate_sol_metrics(
    sol: int,
    inventory: dict,
    coverage: dict,
    quality: dict,
    sync_files: dict,
    sync_pairs: dict,
    required_products: list[str] | None,
    integrity_weights: dict[str, float],
    inventory_available: bool = True,
) -> dict:

    inventory_data = inventory.get(sol, {})
    coverage_data = coverage.get(sol, {})
    quality_data = quality.get(sol, {})
    sync_file_data = sync_files.get(sol, {})
    sync_pair_data = sync_pairs.get(sol, {})

    # Missing inventory report means unavailable, not zero availability.
    file_score = None
    available_products = inventory_data.get("products", set())

    available_required_products = 0

    if inventory_available and required_products:
        available_required_products = sum(
            product in available_products
            for product in required_products
        )

        file_score = (
            available_required_products / len(required_products) * 100
        )

    integrity_score, integrity_components = calculate_integrity(
        coverage_data,
        integrity_weights,
    )

    checked = quality_data.get("range_checked_values", 0)
    quality_score = None

    if checked > 0:
        outside = (
            quality_data.get("below_minimum", 0)
            + quality_data.get("above_maximum", 0)
        )

        if 0 <= outside <= checked:
            quality_score = (checked - outside) / checked * 100

    synchronization_score = average(
        sync_pair_data.get("match_rates", [])
    )

    return {
        "file_availability_score": file_score,
        "data_integrity_score": integrity_score,
        "integrity_timestamp_score": integrity_components.get("timestamps"),
        "integrity_value_score": integrity_components.get("values"),
        "quality_indicator_score": quality_score,
        "synchronization_score": synchronization_score,

        "available_products": len(available_products),
        "available_required_products": available_required_products,
        "required_products": len(required_products or []),
        "optional_products_present": sum(
            product in available_products
            for product in OPTIONAL_PRODUCTS
        ),

        "csv_files": inventory_data.get("csv_files", 0),
        "xml_files": inventory_data.get("xml_files", 0),
        "inventory_entries": inventory_data.get("inventory_entries", 0),
        "missing_pairs": inventory_data.get("missing_pairs", 0),

        "coverage_files": coverage_data.get("files", 0),
        "parsed_timestamps": coverage_data.get("parsed_timestamps", 0),
        "missing_timestamps": coverage_data.get("missing_timestamps", 0),
        "invalid_timestamps": coverage_data.get("invalid_timestamps", 0),

        "numeric_values": coverage_data.get("numeric_values", 0),
        "numeric_missing": coverage_data.get("numeric_missing", 0),
        "numeric_invalid": coverage_data.get("numeric_invalid", 0),

        # Special Constants: reporting only.
        # They do not directly affect the Data Integrity score.
        "special_error": coverage_data.get("special_error", 0),
        "special_saturated": coverage_data.get("special_saturated", 0),
        "special_unknown": coverage_data.get("special_unknown", 0),
        "special_not_applicable": coverage_data.get(
            "special_not_applicable", 0
        ),
        "special_ambiguous": coverage_data.get("special_ambiguous", 0),

        "analysed_field_reports": quality_data.get("analysed_fields", 0),
        "range_checked_fields": quality_data.get("range_checked_fields", 0),
        "range_checked_values": checked,

        "sync_files_analysed": sync_file_data.get("analysed_files", 0),
        "sync_pairs_analysed": sync_pair_data.get("analysed_pairs", 0),
        "matched_timestamps": sync_pair_data.get("matched_timestamps", 0),
        "sync_match_rate_pair_count": len(
            sync_pair_data.get("match_rates", [])
        ),
    }

# ---------------------------------------------------------
# Window aggregation
# ---------------------------------------------------------

def aggregate_window(
    window: tuple[int, int],
    sol_metrics: dict,
    weights: dict[str, float],
    window_size: int,
    min_sol_fraction: float,
    min_metrics: int,
) -> dict:

    start, end = window
    sols = list(range(start, end + 1))
    total_sols = len(sols)

    metric_fields = {
        "file_availability": "file_availability_score",
        "data_integrity": "data_integrity_score",
        "quality_indicators": "quality_indicator_score",
        "synchronization": "synchronization_score",
    }

    metric_scores = {}
    metric_sols = {}
    contributing_metrics = []

    weighted_total = 0.0
    available_weight = 0.0
    reasons = []

    minimum_sols = math.ceil(min_sol_fraction * total_sols)

    for metric_name, field_name in metric_fields.items():
        values = [
            sol_metrics[sol][field_name]
            for sol in sols
            if sol in sol_metrics
            and sol_metrics[sol].get(field_name) is not None
        ]

        metric_sols[metric_name] = len(values)

        if len(values) < minimum_sols or not values:
            metric_scores[metric_name] = None
            reasons.append(
                f"{metric_name}: unavailable "
                f"({len(values)}/{total_sols} Sols met the availability threshold)."
            )
            continue

        score = average(values)
        metric_scores[metric_name] = score

        if score is None:
            continue

        weight = weights[metric_name]

        if weight > 0:
            contributing_metrics.append(metric_name)
            weighted_total += score * weight
            available_weight += weight

        reasons.append(
            f"{metric_name}: {score:.2f}/100 "
            f"({len(values)}/{total_sols} Sols)."
        )

    score = None

    if available_weight > 0:
        score = weighted_total / available_weight

    is_partial = total_sols < window_size

    if len(contributing_metrics) < min_metrics:
        ranking_status = "insufficient_data"
        score = None

        reasons.append(
            f"Only {len(contributing_metrics)} positively weighted "
            f"metric(s) available; {min_metrics} required."
        )

    elif is_partial:
        ranking_status = "partial_window"
        score = None

        reasons.append(
            "Partial window is not ranked against full candidate windows."
        )

    else:
        ranking_status = "rankable"

    metric_signature = ",".join(contributing_metrics)

    result = {
        "rank": "",
        "comparison_group": metric_signature or "no_available_metrics",
        "window_start_sol": start,
        "window_end_sol": end,
        "window_label": window_label(window),
        "ranking_status": ranking_status,
        "is_partial_window": is_partial,
        "exploratory_score": (
            round(score, 3) if score is not None else None
        ),
        "available_metrics": len(contributing_metrics),
        "metrics_used": metric_signature,
        "total_sols": total_sols,
        "reasons": " | ".join(reasons),
    }

    for metric_name, value in metric_scores.items():
        result[f"{metric_name}_score"] = (
            round(value, 3) if value is not None else None
        )
        result[f"{metric_name}_sols"] = metric_sols[metric_name]

    return result


# ---------------------------------------------------------
# Ranking
# ---------------------------------------------------------

def rank_windows(rows: list[dict]) -> list[dict]:
    """
    Rank only windows with the exact same available metric signature.
    """
    groups = defaultdict(list)

    for row in rows:
        if row["ranking_status"] == "rankable":
            groups[row["comparison_group"]].append(row)

    for group_rows in groups.values():
        group_rows.sort(
            key=lambda row: (
                -row["exploratory_score"],
                row["window_start_sol"],
                row["window_end_sol"],
            )
        )

        for rank, row in enumerate(group_rows, start=1):
            row["rank"] = rank

    return rows


# ---------------------------------------------------------
# Output
# ---------------------------------------------------------

RANKING_COLUMNS = [
    "rank",
    "comparison_group",
    "window_start_sol",
    "window_end_sol",
    "window_label",
    "ranking_status",
    "is_partial_window",
    "exploratory_score",
    "available_metrics",
    "metrics_used",
    "total_sols",
    "file_availability_score",
    "data_integrity_score",
    "quality_indicators_score",
    "synchronization_score",
    "file_availability_sols",
    "data_integrity_sols",
    "quality_indicators_sols",
    "synchronization_sols",
    "reasons",
]


def write_ranking_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=RANKING_COLUMNS,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def build_summary(
    rows: list[dict],
    weights: dict,
    start_sol: int,
    end_sol: int,
    window_size: int,
    required_products: list[str] | None,
    required_products_source: str,
    min_sol_fraction: float,
    min_metrics: int,
) -> dict:

    rankable = [
        row for row in rows
        if row["ranking_status"] == "rankable"
    ]

    groups = defaultdict(list)

    for row in rankable:
        groups[row["comparison_group"]].append(row)

    best_by_group = {}

    for group_name, group_rows in groups.items():
        best_by_group[group_name] = max(
            group_rows,
            key=lambda row: row["exploratory_score"],
        )

    single_global_best = None

    if len(best_by_group) == 1:
        single_global_best = next(iter(best_by_group.values()))

    return {
        "analyzer": "MEDA Period Ranker",
        "ranking_type": "exploratory_comparative",
        "sol_range": {
            "start": start_sol,
            "end": end_sol,
        },
        "window_size": window_size,
        "total_candidate_windows": len(rows),
        "rankable_windows": len(rankable),
        "unrankable_windows": len(rows) - len(rankable),
        "comparison_group_count": len(groups),
        "ranking_weights": weights,
        "required_products": required_products,
        "required_products_source": required_products_source,
        "required_products_explicitly_configured": (
            required_products_source == "command_line"
        ),
        "optional_products": list(OPTIONAL_PRODUCTS),
        "min_sol_fraction": min_sol_fraction,
        "min_metrics": min_metrics,
        "best_ranked_window": single_global_best,
        "best_ranked_windows_by_comparison_group": best_by_group,
        "important_limitations": [
            "Scores are exploratory indicators, not scientific validation.",
            "Ranking weights are configurable and not scientifically calibrated.",
            "Unavailable metrics are excluded and remaining positive weights are renormalized.",
            "Zero-weight metrics do not contribute to scores or comparison groups.",
            "Windows are ranked only against windows with the same available positively weighted metric set.",
            "Ranks from different comparison groups are not directly comparable.",
            "File availability is calculated against the configured required product set.",
            "ENG is optional by default and does not affect the default file availability score.",
            "Continuity is excluded because the current gap_total_seconds field is not a defensible missing-duration estimate.",
            "Quality flag meanings are not inferred.",
            "Quality indicator scores use only documented XML numerical bounds.",
            "Partial windows are listed but not ranked.",
            "Timestamp parsing success is not equivalent to sensor uptime.",
            "Numeric completeness is not equivalent to scientific validity.",
            "Synchronization scores are averages of available pair-level match rates and depend on sampling schedules and matching tolerance.",
            "Product availability does not establish measurement completeness.",
            "Candidate periods require further review before research use.",
            "A missing inventory report makes file availability unavailable; it is not interpreted as zero product availability.",
            "Special Constants other than missing_constant and invalid_constant are reported separately and do not directly alter the Data Integrity score.",
            "Ambiguous Special Constant matches are excluded from numeric value, missing, and invalid counters.",
        ],
    }

# ---------------------------------------------------------
# Main analysis
# ---------------------------------------------------------

def run(args) -> dict:

    print("Loading analysis reports...")

    inventory_path = Path(args.inventory)

    inventory_available = inventory_path.is_file()

    inventory_rows = read_csv(
        inventory_path,
        REPORT_REQUIRED_COLUMNS["inventory"],
    )

    coverage_rows = read_csv(
        Path(args.coverage),
        REPORT_REQUIRED_COLUMNS["coverage"],
    )

    quality_rows = read_csv(
        Path(args.quality),
        REPORT_REQUIRED_COLUMNS["quality"],
    )

    sync_file_rows = read_csv(
        Path(args.sync_files),
        REPORT_REQUIRED_COLUMNS["sync_files"],
    )

    sync_pair_rows = read_csv(
        Path(args.sync_pairs),
        REPORT_REQUIRED_COLUMNS["sync_pairs"],
    )

    discovered_sols = discover_sol_numbers(
        inventory_rows,
        coverage_rows,
        quality_rows,
        sync_file_rows,
        sync_pair_rows,
    )

    if not discovered_sols:
        raise ValueError(
            "No valid Sol numbers were found in the supplied reports. "
            "Check the report paths and sol_number columns."
        )

    observed_start = min(discovered_sols)
    observed_end = max(discovered_sols)

    start_sol, end_sol, sol_range_source = resolve_sol_range(
        args.start_sol,
        args.end_sol,
        discovered_sols,
    )

    print("\nSol range configuration:")
    print(f"Observed report range: Sol {observed_start}-{observed_end}")
    print(f"Analysis range: Sol {start_sol}-{end_sol}")
    print(f"Range source: {sol_range_source}")

    print("\nAggregating analyzer reports...")

    inventory = analyse_inventory(
        inventory_rows,
        start_sol,
        end_sol,
    )

    coverage = analyse_coverage(coverage_rows)
    quality = analyse_quality(quality_rows)
    sync_files = analyse_sync_files(sync_file_rows)
    sync_pairs = analyse_sync_pairs(sync_pair_rows)

    if args.required_products is None:
        required_products = list(DEFAULT_REQUIRED_PRODUCTS)
        required_products_source = "default_configuration"
    else:
        products = {
            str(product).strip().upper()
            for product in args.required_products
            if str(product).strip()
        }

        if not products:
            raise ValueError(
                "When --required-products is supplied, "
                "at least one product code must be provided."
            )

        required_products = sorted(products)
        required_products_source = "command_line"

    print("\nProduct availability configuration:")
    print(f"Required products: {', '.join(required_products)}")
    print(f"Optional products: {', '.join(OPTIONAL_PRODUCTS)}")
    print(f"Configuration source: {required_products_source}")

    weights = normalized_weights({
        "file_availability": args.weight_files,
        "data_integrity": args.weight_integrity,
        "quality_indicators": args.weight_quality,
        "synchronization": args.weight_sync,
    })

    integrity_weights = normalized_weights({
        "timestamps": args.integrity_timestamps,
        "values": args.integrity_values,
    })

    print("\nCalculating per-Sol metrics...")

    sol_metrics = {}

    for sol in range(start_sol, end_sol + 1):
        sol_metrics[sol] = calculate_sol_metrics(
            sol,
            inventory,
            coverage,
            quality,
            sync_files,
            sync_pairs,
            required_products,
            integrity_weights,
            inventory_available=inventory_available,
        )

    windows = build_windows(
        start_sol,
        end_sol,
        args.window_size,
    )

    print("\nEvaluating candidate windows...")

    ranking_rows = []

    for window in windows:
        ranking_rows.append(
            aggregate_window(
                window,
                sol_metrics,
                weights,
                args.window_size,
                args.min_sol_fraction,
                args.min_metrics,
            )
        )

    rank_windows(ranking_rows)

    output_path = Path(args.output)
    summary_path = Path(args.summary)

    write_ranking_csv(output_path, ranking_rows)

    summary = build_summary(
        ranking_rows,
        weights,
        start_sol,
        end_sol,
        args.window_size,
        required_products,
        required_products_source,
        args.min_sol_fraction,
        args.min_metrics,
    )

    summary["sol_range_detection"] = {
        "source": sol_range_source,
        "observed_start": observed_start,
        "observed_end": observed_end,
        "observed_sol_count": len(discovered_sols),
        "analysis_start": start_sol,
        "analysis_end": end_sol,
        "automatic_detection_used": (
            args.start_sol is None or args.end_sol is None
        ),
    }

    summary["sol_metrics"] = {
        str(sol): metrics
        for sol, metrics in sol_metrics.items()
    }

    summary["input_reports"] = {
        "inventory": args.inventory,
        "coverage": args.coverage,
        "quality": args.quality,
        "sync_files": args.sync_files,
        "sync_pairs": args.sync_pairs,
    }

    summary["input_report_availability"] = {
        "inventory": inventory_available,
        "coverage": Path(args.coverage).is_file(),
        "quality": Path(args.quality).is_file(),
        "sync_files": Path(args.sync_files).is_file(),
        "sync_pairs": Path(args.sync_pairs).is_file(),
    }

    write_json(summary_path, summary)

    print("\nPeriod ranking completed.")
    print(f"Observed Sol range: {observed_start}-{observed_end}")
    print(f"Analysis Sol range: {start_sol}-{end_sol}")
    print(f"Range source: {sol_range_source}")
    print(f"Required products: {len(required_products)}")
    print(f"Candidate windows: {len(ranking_rows)}")
    print(f"Rankable windows: {summary['rankable_windows']}")
    print(f"Comparison groups: {summary['comparison_group_count']}")
    print(f"Ranking CSV: {output_path}")
    print(f"Summary JSON: {summary_path}")

    if summary["best_ranked_window"]:
        best = summary["best_ranked_window"]

        print(
            "Top candidate: "
            f"{best['window_label']} "
            f"(score: {best['exploratory_score']})"
        )

    elif summary["best_ranked_windows_by_comparison_group"]:
        print(
            "Top candidates are available in separate comparison groups; "
            "see the summary JSON."
        )

    else:
        print("No candidate window met the ranking requirements.")

    return summary


# ---------------------------------------------------------
# Command-line interface
# ---------------------------------------------------------

def parse_args():

    parser = argparse.ArgumentParser(
        description="Compare candidate MEDA Sol periods."
    )

    parser.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    parser.add_argument("--coverage", default=str(DEFAULT_COVERAGE))
    parser.add_argument("--quality", default=str(DEFAULT_QUALITY))
    parser.add_argument("--sync-files", default=str(DEFAULT_SYNC_FILES))
    parser.add_argument("--sync-pairs", default=str(DEFAULT_SYNC_PAIRS))

    parser.add_argument("--output", default=str(DEFAULT_RANKING))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))

    parser.add_argument(
        "--start-sol",
        type=int,
        default=DEFAULT_START_SOL,
        help="First Sol to analyse. Defaults to automatic detection.",
    )

    parser.add_argument(
        "--end-sol",
        type=int,
        default=DEFAULT_END_SOL,
        help="Last Sol to analyse. Defaults to automatic detection.",
    )

    parser.add_argument(
        "--window-size",
        type=int,
        default=DEFAULT_WINDOW_SIZE,
    )

    parser.add_argument("--min-sol-fraction", type=float, default=0.5)
    parser.add_argument("--min-metrics", type=int, default=3)

    parser.add_argument(
        "--required-products",
        nargs="*",
        default=None,
        help=(
            "Override the default required product codes "
            "(ATS PS RDS RHS TIRS WS). ENG is optional by default."
        ),
    )

    parser.add_argument("--weight-files", type=float, default=0.20)
    parser.add_argument("--weight-integrity", type=float, default=0.45)
    parser.add_argument("--weight-quality", type=float, default=0.15)
    parser.add_argument("--weight-sync", type=float, default=0.20)

    parser.add_argument("--integrity-timestamps", type=float, default=1.0)
    parser.add_argument("--integrity-values", type=float, default=1.0)

    args = parser.parse_args()

    if args.start_sol is not None and args.start_sol < 0:
        parser.error("Start Sol cannot be negative.")

    if args.end_sol is not None and args.end_sol < 0:
        parser.error("End Sol cannot be negative.")

    if (
        args.start_sol is not None
        and args.end_sol is not None
        and args.start_sol > args.end_sol
    ):
        parser.error("Start Sol cannot exceed End Sol.")

    if args.window_size < 1:
        parser.error("Window size must be at least 1.")

    if not math.isfinite(args.min_sol_fraction):
        parser.error("min-sol-fraction must be finite.")

    if not 0 < args.min_sol_fraction <= 1:
        parser.error(
            "min-sol-fraction must be greater than 0 and at most 1."
        )

    if not 1 <= args.min_metrics <= len(METRIC_NAMES):
        parser.error(
            f"min-metrics must be between 1 and {len(METRIC_NAMES)}."
        )

    weight_values = [
        args.weight_files,
        args.weight_integrity,
        args.weight_quality,
        args.weight_sync,
        args.integrity_timestamps,
        args.integrity_values,
    ]

    if any(
        not math.isfinite(value) or value < 0
        for value in weight_values
    ):
        parser.error("All weights must be finite and non-negative.")

    if sum(weight_values[:4]) <= 0:
        parser.error("At least one ranking weight must be positive.")

    if sum(weight_values[4:]) <= 0:
        parser.error(
            "At least one integrity component weight must be positive."
        )

    if args.required_products is not None:
        products = [
            product.strip().upper()
            for product in args.required_products
            if product.strip()
        ]

        if not products:
            parser.error(
                "--required-products requires at least one product code."
            )

        args.required_products = products

    return args


if __name__ == "__main__":
    try:
        run(parse_args())
    except (
        OSError,
        ValueError,
        csv.Error,
        json.JSONDecodeError,
    ) as error:
        raise SystemExit(f"ERROR: {error}")
