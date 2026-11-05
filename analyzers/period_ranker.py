
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
    "timestamp_coverage": 0.25,
    "data_completeness": 0.20,
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

    result = defaultdict(lambda: {
        "files": 0,
        "rows": 0,
        "parsed_timestamps": 0,
        "missing_timestamps": 0,
        "timestamp_rates": [],
        "timestamp_intervals": [],
    })

    for row in rows:

        sol = sol_number(row.get("sol_number"))

        if sol is None:
            continue

        item = result[sol]

        item["files"] += 1

        total_rows = safe_int(row.get("total_rows"))
        parsed = safe_int(row.get("parsed_timestamps"))
        missing = safe_int(row.get("missing_timestamps"))

        if total_rows is not None:
            item["rows"] += total_rows

        if parsed is not None:
            item["parsed_timestamps"] += parsed

        if missing is not None:
            item["missing_timestamps"] += missing

        rate = safe_float(row.get("timestamp_parse_rate_percent"))

        if rate is not None:
            item["timestamp_rates"].append(rate)

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

        first_rate = safe_float(
            row.get("match_rate_first_percent")
        )

        second_rate = safe_float(
            row.get("match_rate_second_percent")
        )

        if first_rate is not None and second_rate is not None:
            item["match_rates"].append(
                (first_rate + second_rate) / 2
            )

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

    # Timestamp parsing:
    # This measures successfully parsed timestamp values,
    # not physical sensor uptime.
    parsed = coverage_data.get("parsed_timestamps", 0)
    missing = coverage_data.get("missing_timestamps", 0)

    timestamp_total = parsed + missing

    if timestamp_total > 0:
        timestamp_score = parsed / timestamp_total * 100
    else:
        timestamp_score = None

    # Data completeness:
    quality_total = quality_data.get("total_values", 0)
    quality_missing = quality_data.get("missing_values", 0)

    if quality_total > 0:
        completeness_score = (
            1 - quality_missing / quality_total
        ) * 100
    else:
        completeness_score = None

    # Quality indicator:
    # No undocumented flag values are interpreted.
    # This score only reflects the proportion of range-checked
    # numeric values that fall inside declared XML bounds.
    #
    # The quality analyzer currently does not report total
    # numeric values checked separately, so this score is
    # unavailable until that information is added.
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
        "quality_indicator_score": quality_score,
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
        "parsed_timestamps": parsed,
        "missing_timestamps": missing,
        "quality_fields_analysed": (
            quality_data.get("analysed_fields", 0)
        ),
        "quality_missing_values": quality_missing,
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
) -> dict:

    start, end = window
    sols = list(range(start, end + 1))

    metric_keys = {
        "file_availability": "file_availability_score",
        "timestamp_coverage": "timestamp_coverage_score",
        "data_completeness": "data_completeness_score",
        "quality_indicators": "quality_indicator_score",
        "synchronization": "synchronization_score",
    }

    metric_averages = {}
    reasons = []
    available_weight = 0.0
    weighted_total = 0.0

    for metric_name, field_name in metric_keys.items():

        values = [
            sol_metrics[sol][field_name]
            for sol in sols
            if sol in sol_metrics
            and sol_metrics[sol][field_name] is not None
        ]

        metric_value = average(values)
        metric_averages[metric_name] = metric_value

        if metric_value is None:
            continue

        weight = weights[metric_name]

        weighted_total += metric_value * weight
        available_weight += weight

    if available_weight > 0:
        score = weighted_total / available_weight
    else:
        score = None

    for metric_name, value in metric_averages.items():

        if value is None:
            reasons.append(
                f"{metric_name}: insufficient report data."
            )

        elif value >= 90:
            reasons.append(
                f"{metric_name}: strong observed indicator."
            )

        elif value >= 70:
            reasons.append(
                f"{metric_name}: moderate observed indicator."
            )

        else:
            reasons.append(
                f"{metric_name}: review recommended."
            )

    # A window should not be ranked confidently when too many
    # metrics are unavailable.
    available_metrics = sum(
        value is not None
        for value in metric_averages.values()
    )

    ranking_status = (
        "rankable"
        if available_metrics >= 2
        else "insufficient_data"
    )

    if ranking_status == "insufficient_data":
        score = None
        reasons.append(
            "Too few independent metrics are available for ranking."
        )

    return {
        "window_start_sol": start,
        "window_end_sol": end,
        "window_label": window_label(window),
        "ranking_status": ranking_status,
        "exploratory_score": (
            round(score, 3) if score is not None else None
        ),
        "available_metrics": available_metrics,
        "total_sols": len(sols),
        **{
            f"{key}_score": (
                round(value, 3)
                if value is not None else None
            )
            for key, value in metric_averages.items()
        },
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
        "exploratory_score",
        "available_metrics",
        "total_sols",
        "file_availability_score",
        "timestamp_coverage_score",
        "data_completeness_score",
        "quality_indicators_score",
        "synchronization_score",
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
            "Quality indicator score is currently unavailable.",
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

    expected_products = sorted({
        (row.get("product_code") or "").strip()
        for row in inventory_rows
        if row.get("product_code")
    })

    weights = normalize_weights({
        "file_availability": args.weight_files,
        "timestamp_coverage": args.weight_timestamps,
        "data_completeness": args.weight_completeness,
        "quality_indicators": args.weight_quality,
        "synchronization": args.weight_sync,
    })

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

    parser.add_argument("--weight-files", type=float, default=0.20)
    parser.add_argument("--weight-timestamps", type=float, default=0.25)
    parser.add_argument("--weight-completeness", type=float, default=0.20)
    parser.add_argument("--weight-quality", type=float, default=0.15)
    parser.add_argument("--weight-sync", type=float, default=0.20)

    args = parser.parse_args()

    if args.start_sol > args.end_sol:
        parser.error("start-sol cannot exceed end-sol.")

    if args.window_size < 1:
        parser.error("window-size must be at least 1.")

    weights = [
        args.weight_files,
        args.weight_timestamps,
        args.weight_completeness,
        args.weight_quality,
        args.weight_sync,
    ]

    if any(weight < 0 for weight in weights):
        parser.error("Ranking weights cannot be negative.")

    if sum(weights) <= 0:
        parser.error("At least one ranking weight must be positive.")

    return args


if __name__ == "__main__":
    run(parse_args())
