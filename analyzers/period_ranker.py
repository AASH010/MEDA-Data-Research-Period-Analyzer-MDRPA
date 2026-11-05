"""
MEDA Period Ranker

Ranks candidate Sol periods using available MEDA analysis reports.

This is an exploratory ranking tool, not a scientific quality verdict.

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

from collections import defaultdict
from pathlib import Path
from typing import Optional


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

# Initial exploratory weights.
# These weights are configurable and are not scientifically validated.
DEFAULT_WEIGHTS = {
    "file_availability": 0.20,
    "data_integrity": 0.45,
    "quality_indicators": 0.15,
    "synchronization": 0.20,
}


# ---------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------

def read_csv(path: Path) -> list[dict]:

    if not path.exists():
        print(f"WARNING: Report not found: {path}")
        return []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        return list(csv.DictReader(handle))


def safe_float(value) -> Optional[float]:

    if value is None:
        return None

    try:
        result = float(str(value).strip())

        if result != result:
            return None

        return result

    except (TypeError, ValueError):
        return None


def safe_int(value) -> Optional[int]:

    number = safe_float(value)

    if number is None:
        return None

    return int(number)


def sol_number(value) -> Optional[int]:

    if value is None:
        return None

    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def clamp(value: float, low=0.0, high=100.0) -> float:

    return max(low, min(high, value))


def average(values: list[float]) -> Optional[float]:

    if not values:
        return None

    return sum(values) / len(values)


def normalize_weights(weights: dict) -> dict:

    positive = {
        key: max(0.0, float(value))
        for key, value in weights.items()
    }

    total = sum(positive.values())

    if total <= 0:
        raise ValueError("At least one ranking weight must be positive.")

    return {
        key: value / total
        for key, value in positive.items()
    }


INTEGRITY_PARTS = (
    ("timestamps", "ts_good", "ts_total"),
    ("values", "val_good", "val_total"),
    ("continuity", "cont_good", "cont_total"),
)


def integrity_from_totals(totals: dict, integrity_weights: dict):
    """Weighted mean of the integrity components that have data.

    Returns (score or None, {component: score}).
    """
    components = {}
    accumulated = 0.0
    weight_sum = 0.0

    for name, good_key, total_key in INTEGRITY_PARTS:
        total = totals.get(total_key, 0)

        if total > 0:
            value = totals.get(good_key, 0) / total * 100
            components[name] = value
            accumulated += value * integrity_weights[name]
            weight_sum += integrity_weights[name]

    score = accumulated / weight_sum if weight_sum > 0 else None
    return score, components


def load_json(path: Path) -> dict:

    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------
# Window handling
# ---------------------------------------------------------

def build_windows(
    start_sol: int,
    end_sol: int,
    window_size: int,
) -> list[tuple[int, int]]:

    if start_sol > end_sol:
        raise ValueError("Start Sol cannot exceed end Sol.")

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


def find_window(
    sol: int,
    windows: list[tuple[int, int]],
) -> Optional[tuple[int, int]]:

    for start, end in windows:

        if start <= sol <= end:
            return start, end

    return None


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
        "expected_sols": set(),
        "sols_with_files": set(),
        "csv_sols": set(),
        "xml_sols": set(),
        "products": set(),
        "missing_pairs": 0,
        "inventory_entries": 0,
    })

    all_sols = set(range(start_sol, end_sol + 1))

    for row in rows:

        sol = sol_number(row.get("sol_number"))

        if sol is None or sol not in all_sols:
            continue

        extension = (
            row.get("extension") or ""
        ).lower().lstrip(".")

        product = (row.get("product_code") or "").strip()

        if not product:
            continue

        item = result[sol]

        item["inventory_entries"] += 1
        item["sols_with_files"].add(sol)

        if extension == "csv":
            item["products"].add(product)

        if extension == "csv":
            item["csv_sols"].add(sol)

        elif extension == "xml":
            item["xml_sols"].add(sol)

        pair_status = (
            row.get("pair_status") or ""
        ).lower()

        if "missing" in pair_status:
            item["missing_pairs"] += 1

    return result


# ---------------------------------------------------------
# Coverage analysis
# ---------------------------------------------------------

def analyse_coverage(rows: list[dict]) -> dict:
    """Read the Coverage Analyzer report (row_count, *_timestamp_count, numeric_*)."""

    result = defaultdict(lambda: {
        "files": 0,
        "rows": 0,
        "parsed_timestamps": 0,
        "missing_timestamps": 0,
        "invalid_timestamps": 0,
        "numeric_values": 0,
        "numeric_missing": 0,
        "numeric_invalid": 0,
        "span_seconds": 0.0,
        "gap_seconds": 0.0,
    })

    for row in rows:

        sol = sol_number(row.get("sol_number"))

        if sol is None:
            continue

        item = result[sol]
        item["files"] += 1
        item["span_seconds"] += safe_float(row.get("span_seconds")) or 0.0
        item["gap_seconds"] += safe_float(row.get("gap_total_seconds")) or 0.0

        for target, column in (
            ("rows", "row_count"),
            ("parsed_timestamps", "parsed_timestamp_count"),
            ("missing_timestamps", "missing_timestamp_count"),
            ("invalid_timestamps", "invalid_timestamp_count"),
            ("numeric_values", "numeric_value_count"),
            ("numeric_missing", "numeric_missing_count"),
            ("numeric_invalid", "numeric_invalid_count"),
        ):
            item[target] += safe_int(row.get(column)) or 0

    return result


# ---------------------------------------------------------
# Quality analysis
# ---------------------------------------------------------

def analyse_quality(rows: list[dict]) -> dict:

    result = defaultdict(lambda: {
        "field_reports": 0,
        "analysed_fields": 0,
        "total_values": 0,
        "missing_values": 0,
        "below_minimum": 0,
        "above_maximum": 0,
        "range_checked_fields": 0,
        "range_checked_values": 0,
    })

    for row in rows:

        sol = sol_number(row.get("sol_number"))

        if sol is None:
            continue

        item = result[sol]

        item["field_reports"] += 1

        if row.get("analysis_status") != "analysed":
            continue

        item["analysed_fields"] += 1

        total = safe_int(row.get("total_rows")) or 0
        missing = safe_int(row.get("missing_count")) or 0

        item["total_values"] += total
        item["missing_values"] += missing

        below = safe_int(row.get("below_valid_minimum")) or 0
        above = safe_int(row.get("above_valid_maximum")) or 0

        item["below_minimum"] += below
        item["above_maximum"] += above

        minimum = safe_float(row.get("valid_minimum"))
        maximum = safe_float(row.get("valid_maximum"))

        if minimum is not None or maximum is not None:
            item["range_checked_fields"] += 1
            item["range_checked_values"] += (
                safe_int(row.get("numeric_count")) or 0
            )

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

        if row.get("analysis_status") == "analysed":
            item["analysed_files"] += 1

            item["parsed_timestamps"] += (
                safe_int(row.get("parsed_timestamps")) or 0
            )

    return result


def analyse_sync_pairs(rows: list[dict]) -> dict:

    result = defaultdict(lambda: {
        "pairs": 0,
        "analysed_pairs": 0,
        "overlap_durations": [],
        "match_rates": [],
        "matched_timestamps": 0,
    })

    for row in rows:

        sol = sol_number(row.get("sol_number"))

        if sol is None:
            continue

        item = result[sol]

        item["pairs"] += 1

        if row.get("comparison_status") != "analysed":
            continue

        item["analysed_pairs"] += 1

        overlap = safe_float(
            row.get("overlap_duration_seconds")
        )

        if overlap is not None:
            item["overlap_durations"].append(overlap)

        rate = safe_float(row.get("match_rate_sparser_percent"))

        if rate is not None:
            item["match_rates"].append(rate)

        item["matched_timestamps"] += (
            safe_int(row.get("matched_timestamps")) or 0
        )

    return result


# ---------------------------------------------------------
# Per-Sol metric calculation
# ---------------------------------------------------------

def calculate_sol_metrics(
    sol: int,
    inventory: dict,
    coverage: dict,
    quality: dict,
    sync_files: dict,
    sync_pairs: dict,
    expected_products: list[str],
    integrity_weights: dict,
) -> dict:

    inventory_data = inventory.get(sol, {})
    coverage_data = coverage.get(sol, {})
    quality_data = quality.get(sol, {})
    sync_file_data = sync_files.get(sol, {})
    sync_pair_data = sync_pairs.get(sol, {})

    # File availability:
    # This is product-Sol availability, not measurement completeness.
    if expected_products:

        available = sum(
            product in inventory_data.get("products", set())
            for product in expected_products
        )

        file_score = (
            available / len(expected_products) * 100
        )

    else:

        file_score = None

    # Timestamp parsing (pooled counts, not an average of averages).
    ts_good = coverage_data.get("parsed_timestamps", 0)
    ts_total = (
        ts_good
        + coverage_data.get("missing_timestamps", 0)
        + coverage_data.get("invalid_timestamps", 0)
    )

    timestamp_score = ts_good / ts_total * 100 if ts_total else None

    # Completeness over ALL numeric columns declared in the XML.
    val_good = coverage_data.get("numeric_values", 0)
    val_total = (
        val_good
        + coverage_data.get("numeric_missing", 0)
        + coverage_data.get("numeric_invalid", 0)
    )

    completeness_score = (
        val_good / val_total * 100 if val_total else None
    )

    # Continuity: share of the recorded time span not lost to gaps.
    span = coverage_data.get("span_seconds", 0.0)
    gap = min(coverage_data.get("gap_seconds", 0.0), span)

    integrity_totals = {
        "ts_good": ts_good,
        "ts_total": ts_total,
        "val_good": val_good,
        "val_total": val_total,
        "cont_good": span - gap,
        "cont_total": span,
    }

    integrity_score, _ = integrity_from_totals(
        integrity_totals, integrity_weights
    )

    # Quality indicator: share of range-checked numeric values inside
    # XML-declared bounds. None when the XML declares no bounds.
    checked = quality_data.get("range_checked_values", 0)

    if checked > 0:
        outside = (
            quality_data.get("below_minimum", 0)
            + quality_data.get("above_maximum", 0)
        )
        quality_score = (1 - outside / checked) * 100
    else:
        quality_score = None

    # Synchronization:
    rates = sync_pair_data.get("match_rates", [])

    synchronization_score = average(rates)

    if synchronization_score is None:
        synchronization_score = None

    return {
        "file_availability_score": (
            round(file_score, 3)
            if file_score is not None else None
        ),
        "timestamp_coverage_score": (
            round(timestamp_score, 3)
            if timestamp_score is not None else None
        ),
        "data_completeness_score": (
            round(clamp(completeness_score), 3)
            if completeness_score is not None else None
        ),
        "quality_indicator_score": (
            round(clamp(quality_score), 3)
            if quality_score is not None else None
        ),
        "data_integrity_score": (
            round(integrity_score, 3)
            if integrity_score is not None else None
        ),
        **integrity_totals,
        "synchronization_score": (
            round(clamp(synchronization_score), 3)
            if synchronization_score is not None else None
        ),
        "available_products": len(
            inventory_data.get("products", set())
        ),
        "expected_products": len(expected_products),
        "csv_sols_present": len(
            inventory_data.get("csv_sols", set())
        ),
        "xml_sols_present": len(
            inventory_data.get("xml_sols", set())
        ),
        "parsed_timestamps": ts_good,
        "missing_timestamps": ts_total - ts_good,
        "quality_fields_analysed": (
            quality_data.get("analysed_fields", 0)
        ),
        "quality_missing_values": val_total - val_good,
        "range_checked_fields": (
            quality_data.get("range_checked_fields", 0)
        ),
        "sync_pairs_analysed": (
            sync_pair_data.get("analysed_pairs", 0)
        ),
        "matched_timestamps": (
            sync_pair_data.get("matched_timestamps", 0)
        ),
    }


# ---------------------------------------------------------
# Window aggregation and ranking
# ---------------------------------------------------------

def aggregate_window(
    window: tuple[int, int],
    sol_metrics: dict,
    weights: dict,
    window_size: int,
    min_sol_fraction: float = 0.5,
    min_metrics: int = 3,
    integrity_weights: dict | None = None,
) -> dict:

    integrity_weights = integrity_weights or {
        "timestamps": 1.0, "values": 1.0, "continuity": 1.0,
    }
    integrity_components: dict = {}

    start, end = window
    sols = list(range(start, end + 1))
    total_sols = len(sols)

    # (metric name, per-Sol score field, pooled (good, total) fields or None)
    metric_defs = [
        ("file_availability", "file_availability_score", None),
        ("data_integrity", "data_integrity_score", "integrity"),
        ("quality_indicators", "quality_indicator_score", None),
        ("synchronization", "synchronization_score", None),
    ]

    metric_averages = {}
    contributing = {}
    reasons = []
    available_weight = 0.0
    weighted_total = 0.0

    for metric_name, field_name, pooled in metric_defs:

        present = [
            sol for sol in sols
            if sol in sol_metrics
            and sol_metrics[sol][field_name] is not None
        ]

        contributing[metric_name] = len(present)

        # Too few Sols carry this metric: treat it as unavailable
        # instead of letting a single good Sol represent the window.
        if len(present) < min_sol_fraction * total_sols or not present:
            metric_averages[metric_name] = None
            continue

        if pooled == "integrity":
            # Pool raw counts/seconds across Sols, then combine components.
            totals = {
                key: sum(sol_metrics[s][key] for s in present)
                for _, good_key, total_key in INTEGRITY_PARTS
                for key in (good_key, total_key)
            }
            metric_value, integrity_components = integrity_from_totals(
                totals, integrity_weights
            )
        else:
            metric_value = average([
                sol_metrics[s][field_name] for s in present
            ])

        metric_averages[metric_name] = metric_value

        if metric_value is None:
            continue

        weight = weights[metric_name]
        weighted_total += metric_value * weight
        available_weight += weight

    score = weighted_total / available_weight if available_weight > 0 else None

    for metric_name, value in metric_averages.items():

        n = contributing[metric_name]

        if value is None:
            reasons.append(
                f"{metric_name}: unavailable ({n}/{total_sols} Sols had data)."
            )
        elif value >= 90:
            reasons.append(f"{metric_name}: strong observed indicator ({n}/{total_sols} Sols).")
        elif value >= 70:
            reasons.append(f"{metric_name}: moderate observed indicator ({n}/{total_sols} Sols).")
        else:
            reasons.append(f"{metric_name}: review recommended ({n}/{total_sols} Sols).")

    used = [k for k, v in metric_averages.items() if v is not None]
    is_partial = total_sols < window_size

    if len(used) < min_metrics:
        ranking_status = "insufficient_data"
        score = None
        reasons.append(
            f"Only {len(used)} metric(s) available; at least {min_metrics} required."
        )
    elif is_partial:
        ranking_status = "partial_window"
        reasons.append(
            f"Window has {total_sols} Sols (< {window_size}); not ranked against full windows."
        )
    else:
        ranking_status = "rankable"

    return {
        "window_start_sol": start,
        "window_end_sol": end,
        "window_label": window_label(window),
        "ranking_status": ranking_status,
        "is_partial_window": is_partial,
        "exploratory_score": round(score, 3) if score is not None else None,
        "available_metrics": len(used),
        "metrics_used": ",".join(used),
        "total_sols": total_sols,
        **{
            f"integrity_{name}_score": round(value, 3)
            for name, value in integrity_components.items()
        },
        **{
            f"{key}_score": round(value, 3) if value is not None else None
            for key, value in metric_averages.items()
        },
        **{f"{key}_sols": n for key, n in contributing.items()},
        "reasons": " | ".join(reasons),
    }


def rank_windows(rows: list[dict]) -> list[dict]:

    rankable = [
        row for row in rows
        if row["ranking_status"] == "rankable"
    ]

    rankable.sort(
        key=lambda row: row["exploratory_score"],
        reverse=True,
    )

    for rank, row in enumerate(rankable, start=1):
        row["rank"] = rank

    for row in rows:

        if row["ranking_status"] != "rankable":
            row["rank"] = ""

    return rows


# ---------------------------------------------------------
# Output
# ---------------------------------------------------------

def write_ranking_csv(path: Path, rows: list[dict]):

    columns = [
        "rank",
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
        "integrity_timestamps_score",
        "integrity_values_score",
        "integrity_continuity_score",
        "quality_indicators_score",
        "synchronization_score",
        "file_availability_sols",
        "data_integrity_sols",
        "quality_indicators_sols",
        "synchronization_sols",
        "reasons",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def build_summary(
    rows: list[dict],
    weights: dict,
    start_sol: int,
    end_sol: int,
) -> dict:

    ranked = [
        row for row in rows
        if row["ranking_status"] == "rankable"
    ]

    best = ranked[0] if ranked else None

    return {
        "analyzer": "MEDA Period Ranker",
        "sol_range": {
            "start": start_sol,
            "end": end_sol,
        },
        "total_candidate_windows": len(rows),
        "rankable_windows": len(ranked),
        "unrankable_windows": len(rows) - len(ranked),
        "ranking_weights": weights,
        "best_ranked_window": best,
        "important_limitations": [
            "Scores are exploratory indicators, not scientific validation.",
            "Weights are configurable and not scientifically calibrated.",
            "Unavailable metrics are excluded and remaining weights are renormalized.",
            "Quality flag meanings are not inferred.",
            "Quality indicator score exists only where the XML declares valid_minimum/valid_maximum.",
            "Partial windows are listed but not ranked.",
            "data_integrity merges timestamp validity, numeric-value validity and continuity (gap time); it is not a scientific quality score.",
            "Timestamp parsing success is not equivalent to sensor uptime.",
            "Product availability does not establish measurement completeness.",
            "Synchronization match rates depend on sampling schedules and tolerance.",
            "Candidate windows should be reviewed before selecting final data.",
        ],
    }


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def run(args):

    print("Loading analysis reports...")

    inventory_rows = read_csv(Path(args.inventory))
    coverage_rows = read_csv(Path(args.coverage))
    quality_rows = read_csv(Path(args.quality))
    sync_file_rows = read_csv(Path(args.sync_files))
    sync_pair_rows = read_csv(Path(args.sync_pairs))

    print("Aggregating reports...")

    inventory = analyse_inventory(
        inventory_rows,
        args.start_sol,
        args.end_sol,
    )

    coverage = analyse_coverage(coverage_rows)
    quality = analyse_quality(quality_rows)
    sync_files = analyse_sync_files(sync_file_rows)
    sync_pairs = analyse_sync_pairs(sync_pair_rows)

    expected_products = args.required_products or sorted({
        (row.get("product_code") or "").strip()
        for row in inventory_rows
        if row.get("product_code")
    })

    weights = normalize_weights({
        "file_availability": args.weight_files,
        "data_integrity": args.weight_integrity,
        "quality_indicators": args.weight_quality,
        "synchronization": args.weight_sync,
    })

    integrity_weights = {
        "timestamps": args.integrity_timestamps,
        "values": args.integrity_values,
        "continuity": args.integrity_continuity,
    }

    print("Calculating Sol metrics...")

    sol_metrics = {}

    for sol in range(args.start_sol, args.end_sol + 1):

        sol_metrics[sol] = calculate_sol_metrics(
            sol,
            inventory,
            coverage,
            quality,
            sync_files,
            sync_pairs,
            expected_products,
            integrity_weights,
        )

    print("Building candidate windows...")

    windows = build_windows(
        args.start_sol,
        args.end_sol,
        args.window_size,
    )

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
                integrity_weights,
            )
        )

    ranking_rows = rank_windows(ranking_rows)

    output_path = Path(args.output)
    summary_path = Path(args.summary)

    write_ranking_csv(output_path, ranking_rows)

    summary = build_summary(
        ranking_rows,
        weights,
        args.start_sol,
        args.end_sol,
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

    summary_path.parent.mkdir(parents=True, exist_ok=True)

    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(
            summary,
            handle,
            indent=2,
            ensure_ascii=False,
        )

    print("\nPeriod ranking completed.")
    print(f"Candidate windows: {len(ranking_rows)}")
    print(f"Rankable windows: {summary['rankable_windows']}")
    print(f"Ranking CSV: {output_path}")
    print(f"Summary JSON: {summary_path}")

    if summary["best_ranked_window"]:
        print(
            "Top candidate: "
            + summary["best_ranked_window"]["window_label"]
        )


def parse_args():

    parser = argparse.ArgumentParser(
        description="Rank candidate MEDA Sol periods."
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
    parser.add_argument("--required-products", nargs="*", default=None)

    parser.add_argument("--weight-files", type=float, default=0.20)
    parser.add_argument("--weight-integrity", type=float, default=0.45)
    parser.add_argument("--integrity-timestamps", type=float, default=1.0)
    parser.add_argument("--integrity-values", type=float, default=1.0)
    parser.add_argument("--integrity-continuity", type=float, default=1.0)
    parser.add_argument("--weight-quality", type=float, default=0.15)
    parser.add_argument("--weight-sync", type=float, default=0.20)

    args = parser.parse_args()

    if args.start_sol > args.end_sol:
        parser.error("start-sol cannot exceed end-sol.")

    if args.window_size < 1:
        parser.error("window-size must be at least 1.")

    weights = [
        args.weight_files,
        args.weight_integrity,
        args.weight_quality,
        args.weight_sync,
    ]

    weights += [
        args.integrity_timestamps,
        args.integrity_values,
        args.integrity_continuity,
    ]

    if any(weight < 0 for weight in weights):
        parser.error("Ranking weights cannot be negative.")

    if sum(weights) <= 0:
        parser.error("At least one ranking weight must be positive.")

    return args


if __name__ == "__main__":
    run(parse_args())