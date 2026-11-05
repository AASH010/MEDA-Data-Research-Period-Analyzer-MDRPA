
"""
MEDA Period Ranker

Compares candidate Sol windows using available MEDA analysis reports.

This is an exploratory comparison tool, not a scientific validation
or certification tool.

Inputs:
    output/file_inventory.csv
    output/coverage_report.csv
    output/quality_field_report.csv
    output/synchronization_file_report.csv
    output/synchronization_pair_report.csv

Outputs:
    output/period_ranking.csv
    output/period_ranking_summary.json

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

DEFAULT_START_SOL = 107
DEFAULT_END_SOL = 250
DEFAULT_WINDOW_SIZE = 10

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

    if number is None:
        return None

    if not number.is_integer():
        return None

    return int(number)


def sol_number(value: Any) -> int | None:
    return safe_int(value)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def average(values: list[float]) -> float | None:
    if not values:
        return None

    return sum(values) / len(values)


def normalized_weights(weights: dict[str, float]) -> dict[str, float]:
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


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        print(f"WARNING: Report not found; treating as unavailable: {path}")
        return []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        if not reader.fieldnames:
            print(f"WARNING: Report has no header: {path}")
            return []

        return list(reader)


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

        product = str(row.get("product_code") or "").strip().upper()

        item = result[sol]
        item["inventory_entries"] += 1

        if extension == "csv":
            item["csv_files"] += 1

            if product:
                item["products"].add(product)

        elif extension == "xml":
            item["xml_files"] += 1

        pair_status = str(row.get("pair_status") or "").lower()

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
    })

    fields = (
        ("rows", "row_count"),
        ("parsed_timestamps", "parsed_timestamp_count"),
        ("missing_timestamps", "missing_timestamp_count"),
        ("invalid_timestamps", "invalid_timestamp_count"),
        ("numeric_values", "numeric_value_count"),
        ("numeric_missing", "numeric_missing_count"),
        ("numeric_invalid", "numeric_invalid_count"),
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

        if str(row.get("analysis_status") or "").lower() != "analysed":
            continue

        item["analysed_fields"] += 1

        minimum = safe_float(row.get("valid_minimum"))
        maximum = safe_float(row.get("valid_maximum"))

        # Only fields with at least one documented bound are
        # considered range-checked.
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

        if str(row.get("analysis_status") or "").lower() == "analysed":
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

        if str(row.get("comparison_status") or "").lower() != "analysed":
            continue

        item["analysed_pairs"] += 1

        rate = safe_float(row.get("match_rate_sparser_percent"))

        if rate is not None and 0 <= rate <= 100:
            item["match_rates"].append(rate)

        matched = safe_int(row.get("matched_timestamps"))

        if matched is not None and matched >= 0:
            item["matched_timestamps"] += matched

        # Current Synchronization Analyzer schema uses
        # 'overlap_duration', not 'overlap_duration_seconds'.
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
) -> dict:

    inventory_data = inventory.get(sol, {})
    coverage_data = coverage.get(sol, {})
    quality_data = quality.get(sol, {})
    sync_file_data = sync_files.get(sol, {})
    sync_pair_data = sync_pairs.get(sol, {})

    # File availability is unavailable unless the user explicitly
    # defines the expected product set.
    file_score = None

    if required_products:
        available_products = inventory_data.get("products", set())

        available = sum(
            product in available_products
            for product in required_products
        )

        file_score = available / len(required_products) * 100

    integrity_score, integrity_components = calculate_integrity(
        coverage_data,
        integrity_weights,
    )

    # Range indicator only uses documented XML bounds.
    checked = quality_data.get("range_checked_values", 0)

    quality_score = None

    if checked > 0:
        outside = (
            quality_data.get("below_minimum", 0)
            + quality_data.get("above_maximum", 0)
        )

        if 0 <= outside <= checked:
            quality_score = (checked - outside) / checked * 100

    # Mean of available analysed pair-level match rates.
    # Pair rates are not interpreted as a universal instrument
    # synchronization quality measure.
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
        "available_products": len(inventory_data.get("products", set())),
        "required_products": len(required_products or []),
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

        # Zero-weight metrics are diagnostic only.
        # They must not affect the final score, the metric count,
        # or the comparison-group signature.
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

    # Only positively weighted metrics define the comparison group.
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

    A rank in one comparison group must not be interpreted as
    directly comparable to a rank in another group.
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
        "required_products_explicitly_configured": bool(required_products),
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
            "File availability is unavailable unless required products are explicitly configured.",
            "Continuity is excluded because the current gap_total_seconds field is not a defensible missing-duration estimate.",
            "Quality flag meanings are not inferred.",
            "Quality indicator scores use only documented XML numerical bounds.",
            "Partial windows are listed but not ranked.",
            "Timestamp parsing success is not equivalent to sensor uptime.",
            "Numeric completeness is not equivalent to scientific validity.",
            "Synchronization scores are averages of available pair-level match rates and depend on sampling schedules and matching tolerance.",
            "Product availability does not establish measurement completeness.",
            "Candidate periods require further review before research use.",
        ],
    }


# ---------------------------------------------------------
# Main analysis
# ---------------------------------------------------------

def run(args) -> dict:

    print("Loading analysis reports...")

    inventory_rows = read_csv(Path(args.inventory))
    coverage_rows = read_csv(Path(args.coverage))
    quality_rows = read_csv(Path(args.quality))
    sync_file_rows = read_csv(Path(args.sync_files))
    sync_pair_rows = read_csv(Path(args.sync_pairs))

    print("Aggregating analyzer reports...")

    inventory = analyse_inventory(
        inventory_rows,
        args.start_sol,
        args.end_sol,
    )

    coverage = analyse_coverage(coverage_rows)
    quality = analyse_quality(quality_rows)
    sync_files = analyse_sync_files(sync_file_rows)
    sync_pairs = analyse_sync_pairs(sync_pair_rows)

    required_products = None

    if args.required_products is not None:
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

    print("Calculating per-Sol metrics...")

    sol_metrics = {}

    for sol in range(args.start_sol, args.end_sol + 1):
        sol_metrics[sol] = calculate_sol_metrics(
            sol,
            inventory,
            coverage,
            quality,
            sync_files,
            sync_pairs,
            required_products,
            integrity_weights,
        )

    windows = build_windows(
        args.start_sol,
        args.end_sol,
        args.window_size,
    )

    print("Evaluating candidate windows...")

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
        args.start_sol,
        args.end_sol,
        args.window_size,
        required_products,
        args.min_sol_fraction,
        args.min_metrics,
    )

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

    write_json(summary_path, summary)

    print("\nPeriod ranking completed.")
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

    parser.add_argument("--start-sol", type=int, default=DEFAULT_START_SOL)
    parser.add_argument("--end-sol", type=int, default=DEFAULT_END_SOL)
    parser.add_argument("--window-size", type=int, default=DEFAULT_WINDOW_SIZE)

    parser.add_argument("--min-sol-fraction", type=float, default=0.5)
    parser.add_argument("--min-metrics", type=int, default=3)

    parser.add_argument(
        "--required-products",
        nargs="*",
        default=None,
        help="Explicit product codes required for file availability scoring.",
    )

    parser.add_argument("--weight-files", type=float, default=0.20)
    parser.add_argument("--weight-integrity", type=float, default=0.45)
    parser.add_argument("--weight-quality", type=float, default=0.15)
    parser.add_argument("--weight-sync", type=float, default=0.20)

    parser.add_argument("--integrity-timestamps", type=float, default=1.0)
    parser.add_argument("--integrity-values", type=float, default=1.0)

    args = parser.parse_args()

    if args.start_sol < 0 or args.end_sol < 0:
        parser.error("Sol numbers cannot be negative.")

    if args.start_sol > args.end_sol:
        parser.error("Start Sol cannot exceed End Sol.")

    if args.window_size < 1:
        parser.error("Window size must be at least 1.")

    if not math.isfinite(args.min_sol_fraction):
        parser.error("min-sol-fraction must be finite.")

    if not 0 < args.min_sol_fraction <= 1:
        parser.error("min-sol-fraction must be greater than 0 and at most 1.")

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
        parser.error("At least one integrity component weight must be positive.")

    if args.required_products is not None:
        products = [
            product.strip()
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
    except (OSError, ValueError, csv.Error, json.JSONDecodeError) as error:
        raise SystemExit(f"ERROR: {error}")
