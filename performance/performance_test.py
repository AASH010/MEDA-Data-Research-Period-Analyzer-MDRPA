from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import threading
import time

from datetime import datetime, timezone
from pathlib import Path

from backend.pipeline.analysis_pipeline import AnalysisPipeline
from backend.pipeline.pipeline_validator import PipelineConfig
from backend.run_manager.run_manager import RunManager


try:
    import psutil
except ImportError:
    psutil = None

'''
project/
└── performance/
    ├── performance_test.py
    ├── performance_dataset/
    │   ├── sol_0100/
    │   ├── sol_0101/
    │   └── ...
    ├── performance_sample/
    │   └── sol_0100/
    └── performance_test_runs/
        ├── runs/
        │   └── run_range(100-100)_001/
        └── reports/
'''

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PERFORMANCE_ROOT = PROJECT_ROOT / "performance"

DEFAULT_DATASET = PERFORMANCE_ROOT / "performance_dataset"
DEFAULT_SAMPLE = PERFORMANCE_ROOT / "performance_sample"
DEFAULT_OUTPUT = PERFORMANCE_ROOT / "performance_test_runs"

SOL_DIRECTORY_PATTERN = re.compile(r"^sol_(\d+)$", re.IGNORECASE)

# These are the artifacts declared by the current pipeline executor.
# Keep this list synchronized with pipeline_executor.py if its outputs
# intentionally change in a future project revision.
REQUIRED_OUTPUT_ARTIFACTS = (
    "file_inventory.csv",
    "metadata_inventory.json",
    "coverage_report.csv",
    "coverage_summary.json",
    "coverage_range_summary.json",
    "quality_field_report.csv",
    "quality_summary.json",
    "quality_range_summary.json",
    "synchronization_file_report.csv",
    "synchronization_pair_report.csv",
    "synchronization_summary.json",
    "synchronization_range_summary.json",
    "period_ranking.csv",
    "period_ranking_summary.json",
    "period_ranking_full.csv",
    "period_ranking_full_summary.json",
)


class MemoryMonitor:
    """Sample process RSS and track approximate per-stage peak memory."""

    def __init__(self, interval: float = 0.1):
        self.interval = interval
        self.process = None
        self.baseline_bytes = None
        self.peak_bytes = None
        self._stage_name = None
        self._stage_start_bytes = None
        self._stage_peak_bytes = None
        self._stage_measurements = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def _rss(self):
        if self.process is None:
            return None

        try:
            return self.process.memory_info().rss
        except (psutil.Error, OSError):
            return None

    def start(self):
        if psutil is None:
            return

        self.process = psutil.Process()
        self.baseline_bytes = self._rss()
        self.peak_bytes = self.baseline_bytes

        self._thread = threading.Thread(
            target=self._sample,
            name="performance-memory-monitor",
            daemon=True,
        )
        self._thread.start()

    def _sample(self):
        while not self._stop.wait(self.interval):
            current = self._rss()
            if current is None:
                continue

            with self._lock:
                self.peak_bytes = max(self.peak_bytes or current, current)

                if self._stage_name is not None:
                    self._stage_peak_bytes = max(
                        self._stage_peak_bytes or current,
                        current,
                    )

    def begin_stage(self, stage_name: str):
        current = self._rss()
        if current is None:
            return

        with self._lock:
            self._stage_name = stage_name
            self._stage_start_bytes = current
            self._stage_peak_bytes = current
            self.peak_bytes = max(self.peak_bytes or current, current)

    def end_stage(self, stage_name: str):
        current = self._rss()

        with self._lock:
            if self._stage_name != stage_name:
                return

            start_bytes = self._stage_start_bytes
            peak_bytes = self._stage_peak_bytes

            if current is not None:
                peak_bytes = max(peak_bytes or current, current)
                self.peak_bytes = max(self.peak_bytes or current, current)

            if start_bytes is not None and peak_bytes is not None:
                self._stage_measurements[stage_name] = {
                    "available": True,
                    "start_rss_mb": self.to_mb(start_bytes),
                    "end_rss_mb": self.to_mb(current),
                    "peak_rss_mb": self.to_mb(peak_bytes),
                    "peak_increase_mb": self.to_mb(
                        max(0, peak_bytes - start_bytes)
                    ),
                }
            else:
                self._stage_measurements[stage_name] = {
                    "available": False,
                    "reason": "RSS measurement unavailable.",
                }

            self._stage_name = None
            self._stage_start_bytes = None
            self._stage_peak_bytes = None

    def stop(self):
        if self._thread is not None:
            self._stop.set()
            self._thread.join()

        current = self._rss()
        if current is not None:
            with self._lock:
                self.peak_bytes = max(self.peak_bytes or current, current)

    @staticmethod
    def to_mb(value):
        if value is None:
            return None
        return round(value / (1024 * 1024), 2)

    def stage_report(self, stage_name: str):
        if psutil is None:
            return {
                "available": False,
                "reason": "psutil is not installed.",
            }

        return self._stage_measurements.get(
            stage_name,
            {
                "available": False,
                "reason": "Stage memory measurement was not recorded.",
            },
        )

    def report(self):
        if psutil is None or self.baseline_bytes is None:
            return {
                "available": False,
                "reason": "psutil is not installed or RSS is unavailable.",
                "stages": self._stage_measurements,
            }

        current = self._rss()

        return {
            "available": True,
            "baseline_rss_mb": self.to_mb(self.baseline_bytes),
            "current_rss_mb": self.to_mb(current),
            "peak_rss_mb": self.to_mb(self.peak_bytes),
            "peak_increase_mb": self.to_mb(
                max(0, self.peak_bytes - self.baseline_bytes)
            ),
            "stages": self._stage_measurements,
        }


def snapshot_input(input_dir: Path) -> dict:
    """Record file size and modification time without changing input files."""
    snapshot = {}

    for path in sorted(input_dir.rglob("*")):
        if not path.is_file():
            continue

        relative = path.relative_to(input_dir).as_posix()
        stat = path.stat()

        snapshot[relative] = {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }

    return snapshot


def compare_snapshots(before: dict, after: dict) -> dict:
    """Describe input-file metadata changes between two snapshots."""
    before_names = set(before)
    after_names = set(after)

    added = sorted(after_names - before_names)
    removed = sorted(before_names - after_names)
    size_changed = []
    mtime_changed = []

    for relative_path in sorted(before_names & after_names):
        old = before[relative_path]
        new = after[relative_path]

        if old["size"] != new["size"]:
            size_changed.append(relative_path)
        if old["mtime_ns"] != new["mtime_ns"]:
            mtime_changed.append(relative_path)

    return {
        "added": added,
        "removed": removed,
        "size_changed": size_changed,
        "mtime_changed": mtime_changed,
        "changed": bool(added or removed or size_changed or mtime_changed),
        "file_count_before": len(before),
        "file_count_after": len(after),
    }


def discover_sol_directories(dataset_dir: Path) -> dict[int, Path]:
    """Return SOL-number to directory mapping for recognized SOL folders."""
    sol_directories = {}

    for path in dataset_dir.iterdir():
        if not path.is_dir():
            continue

        match = SOL_DIRECTORY_PATTERN.fullmatch(path.name)
        if match is None:
            continue

        sol_number = int(match.group(1))
        if sol_number in sol_directories:
            raise ValueError(
                f"Duplicate SOL directory number {sol_number}: "
                f"{sol_directories[sol_number].name} and {path.name}"
            )

        sol_directories[sol_number] = path

    return sol_directories


def prepare_sample(
    dataset_dir: Path,
    sample_dir: Path,
    start_sol: int,
    end_sol: int,
) -> tuple[int, int, int]:
    """Rebuild the one shared performance_sample folder for the requested range."""
    if not dataset_dir.is_dir():
        raise NotADirectoryError(
            f"Performance dataset does not exist: {dataset_dir}"
        )

    if start_sol < 0 or end_sol < start_sol:
        raise ValueError("Invalid SOL range.")

    dataset_dir = dataset_dir.resolve()
    sample_dir = sample_dir.resolve()

    if (
        sample_dir == dataset_dir
        or sample_dir in dataset_dir.parents
        or dataset_dir in sample_dir.parents
    ):
        raise ValueError(
            "The sample directory must be separate from the original dataset."
        )

    available = discover_sol_directories(dataset_dir)
    if not available:
        raise ValueError(
            f"No folders matching sol_NNNN were found in {dataset_dir}"
        )

    requested_numbers = list(range(start_sol, end_sol + 1))
    missing_numbers = [
        number for number in requested_numbers
        if number not in available
    ]

    if missing_numbers:
        raise FileNotFoundError(
            "The requested SOL range contains missing folders: "
            + ", ".join(str(number) for number in missing_numbers)
        )

    # Rebuild the same sample directory. The source dataset is never deleted
    # or modified by this operation.
    if sample_dir.exists():
        shutil.rmtree(sample_dir)

    sample_dir.mkdir(parents=True, exist_ok=False)

    for sol_number in requested_numbers:
        source_folder = available[sol_number]
        shutil.copytree(
            source_folder,
            sample_dir / source_folder.name,
        )

    copied_files = [
        path for path in sample_dir.rglob("*") if path.is_file()
    ]
    csv_count = sum(path.suffix.lower() == ".csv" for path in copied_files)
    xml_count = sum(path.suffix.lower() == ".xml" for path in copied_files)

    if csv_count == 0 or xml_count == 0:
        raise ValueError(
            "The prepared sample must contain both CSV and XML files."
        )

    return len(requested_numbers), csv_count, xml_count


def write_stage_csv(path: Path, stages: list[dict]):
    columns = [
        "stage_name",
        "status",
        "elapsed_seconds",
        "start_rss_mb",
        "end_rss_mb",
        "peak_rss_mb",
        "peak_increase_mb",
        "output_count",
        "warning_count",
        "error_count",
        "errors",
    ]

    with path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()

        for stage in stages:
            memory = stage.get("memory", {})
            writer.writerow({
                "stage_name": stage["stage_name"],
                "status": stage["status"],
                "elapsed_seconds": stage["elapsed_seconds"],
                "start_rss_mb": memory.get("start_rss_mb"),
                "end_rss_mb": memory.get("end_rss_mb"),
                "peak_rss_mb": memory.get("peak_rss_mb"),
                "peak_increase_mb": memory.get("peak_increase_mb"),
                "output_count": len(stage["output_paths"]),
                "warning_count": len(stage["warnings"]),
                "error_count": len(stage["errors"]),
                "errors": " | ".join(stage["errors"]),
            })


def validate_artifacts(output_dir: Path, stage_results: list[dict]):
    """Check all declared pipeline outputs and every stage-reported output."""
    artifacts = []
    required_paths = {
        output_dir / filename
        for filename in REQUIRED_OUTPUT_ARTIFACTS
    }

    for stage in stage_results:
        required_paths.update(
            Path(path) for path in stage["output_paths"]
        )

    for path in sorted(required_paths, key=lambda item: str(item)):
        exists = path.is_file()
        artifacts.append({
            "path": str(path),
            "exists": exists,
            "size_bytes": path.stat().st_size if exists else None,
            "source": (
                "pipeline_required_artifact"
                if path.parent == output_dir
                and path.name in REQUIRED_OUTPUT_ARTIFACTS
                else "stage_reported_output"
            ),
        })

    missing = [
        artifact for artifact in artifacts
        if not artifact["exists"]
    ]

    empty = [
        artifact for artifact in artifacts
        if artifact["exists"] and artifact["size_bytes"] == 0
    ]

    return artifacts, missing, empty


def run_performance_test(
    dataset_dir: Path,
    sample_dir: Path,
    output_root: Path,
    start_sol: int,
    end_sol: int,
):
    dataset_dir = dataset_dir.expanduser().resolve()
    sample_dir = sample_dir.expanduser().resolve()
    output_root = output_root.expanduser().resolve()

    if (
        output_root == dataset_dir
        or dataset_dir in output_root.parents
        or output_root in dataset_dir.parents
    ):
        raise ValueError(
            "Performance output must be separate from the original dataset."
        )

    print("=" * 72)
    print("MEDA PIPELINE PERFORMANCE TEST")
    print("=" * 72)
    print(f"Original dataset: {dataset_dir}")
    print(f"Working sample:   {sample_dir}")
    print(f"Results root:     {output_root}")
    print(f"Requested range:  SOL {start_sol} - SOL {end_sol}")
    print()

    print("Preparing the working sample...")
    original_before = snapshot_input(dataset_dir)

    sol_count, csv_count, xml_count = prepare_sample(
        dataset_dir,
        sample_dir,
        start_sol,
        end_sol,
    )

    sample_before = snapshot_input(sample_dir)
    sample_file_count = len(sample_before)

    print(f"Selected SOL folders: {sol_count}")
    print(f"CSV files:            {csv_count}")
    print(f"XML files:            {xml_count}")
    print(f"Total sample files:   {sample_file_count}")
    print()

    output_root.mkdir(parents=True, exist_ok=True)
    runs_root = output_root / "runs"
    reports_root = output_root / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)

    memory = MemoryMonitor()
    memory.start()

    stage_results = []
    stage_start_times = {}
    stage_input_snapshots = {}
    stage_input_changes = []

    def on_stage_started(stage_name):
        stage_start_times[stage_name] = time.perf_counter()
        stage_input_snapshots[stage_name] = snapshot_input(sample_dir)
        memory.begin_stage(stage_name)
        print(f"[START] {stage_name}", flush=True)

    def on_stage_completed(stage):
        started = stage_start_times.get(stage.stage_name)
        elapsed = (
            round(time.perf_counter() - started, 3)
            if started is not None
            else None
        )

        memory.end_stage(stage.stage_name)
        stage_memory = memory.stage_report(stage.stage_name)

        stage_before = stage_input_snapshots.pop(
            stage.stage_name,
            {},
        )
        stage_after = snapshot_input(sample_dir)
        input_changes = compare_snapshots(stage_before, stage_after)
        input_changes["stage_name"] = stage.stage_name
        stage_input_changes.append(input_changes)

        item = {
            "stage_name": stage.stage_name,
            "status": stage.status,
            "elapsed_seconds": elapsed,
            "started_at": stage.started_at,
            "finished_at": stage.finished_at,
            "output_paths": [
                str(path) for path in stage.output_paths
            ],
            "warnings": list(stage.warnings),
            "errors": list(stage.errors),
            "summary": stage.summary or {},
            "memory": stage_memory,
            "input_changes": input_changes,
        }
        stage_results.append(item)

        print(
            f"[{stage.status.upper()}] {stage.stage_name} "
            f"({elapsed}s)",
            flush=True,
        )

        if input_changes["changed"]:
            print(
                "  INPUT CHANGE DETECTED: "
                f"{input_changes['file_count_before']} -> "
                f"{input_changes['file_count_after']} files",
                flush=True,
            )
            for category in ("added", "removed", "size_changed", "mtime_changed"):
                for relative_path in input_changes[category]:
                    print(f"    {category}: {relative_path}", flush=True)
        else:
            print(
                f"  Input files unchanged ({input_changes['file_count_after']} files)",
                flush=True,
            )

        if stage_memory.get("available"):
            print(
                "  Memory: "
                f"start={stage_memory['start_rss_mb']} MB, "
                f"peak={stage_memory['peak_rss_mb']} MB, "
                f"increase={stage_memory['peak_increase_mb']} MB",
                flush=True,
            )

        for warning in stage.warnings:
            print(f"  WARNING: {warning}", flush=True)

        for error in stage.errors:
            print(f"  ERROR: {error}", flush=True)

    started_at = datetime.now(timezone.utc)
    timer = time.perf_counter()
    result = None
    execution_error = None

    try:
        manager = RunManager(runs_root=runs_root)
        pipeline = AnalysisPipeline(manager)

        config = PipelineConfig(
            input_dir=sample_dir,
            start_sol=start_sol,
            end_sol=end_sol,
        )

        # Omitting run_id makes RunManager create its native sequential
        # identifier: run_range(START-END)_001, _002, and so on.
        result = pipeline.execute(
            config,
            input_source="performance_test",
            source_info={
                "test_type": "full_pipeline_performance",
                "original_dataset": str(dataset_dir),
                "sample_directory": str(sample_dir),
                "dataset_file_count": sample_file_count,
                "selected_sol_count": sol_count,
                "selected_start_sol": start_sol,
                "selected_end_sol": end_sol,
            },
            on_stage_started=on_stage_started,
            on_stage_completed=on_stage_completed,
        )
    except Exception as exc:
        execution_error = f"{type(exc).__name__}: {exc}"
        print(f"PERFORMANCE TEST ERROR: {execution_error}", flush=True)
    finally:
        elapsed_total = round(time.perf_counter() - timer, 3)
        memory.stop()

    finished_at = datetime.now(timezone.utc)
    sample_after = snapshot_input(sample_dir)
    original_after = snapshot_input(dataset_dir)

    sample_changes = compare_snapshots(sample_before, sample_after)
    sample_unchanged = not sample_changes["changed"]
    original_unchanged = original_before == original_after

    run_id = result.run_id if result is not None else None
    status = result.status if result is not None else "not_started"
    successful = result.successful if result is not None else False
    error = result.error if result is not None else execution_error

    run_directory = None
    output_directory = None
    discovered_count = None
    artifacts = []
    missing_artifacts = []
    empty_artifacts = []

    if result is not None:
        run_directory = result.record.paths.root_dir
        output_directory = result.record.paths.output_dir

        inventory_path = output_directory / "file_inventory.csv"
        if inventory_path.is_file():
            with inventory_path.open(
                "r",
                newline="",
                encoding="utf-8-sig",
            ) as file:
                discovered_count = sum(
                    1 for _ in csv.DictReader(file)
                )

        artifacts, missing_artifacts, empty_artifacts = (
            validate_artifacts(output_directory, stage_results)
        )

    report = {
        "test_type": "full_pipeline_performance",
        "run_id": run_id,
        "status": status,
        "successful": successful,
        "error": error,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "total_elapsed_seconds": elapsed_total,
        "original_dataset_directory": str(dataset_dir),
        "sample_directory": str(sample_dir),
        "requested_start_sol": start_sol,
        "requested_end_sol": end_sol,
        "selected_sol_count": sol_count,
        "sample_file_count": sample_file_count,
        "sample_csv_count": csv_count,
        "sample_xml_count": xml_count,
        "discovered_file_count": discovered_count,
        "original_dataset_unchanged": original_unchanged,
        "sample_unchanged": sample_unchanged,
        "sample_changes": sample_changes,
        "stage_input_changes": stage_input_changes,
        "first_stage_with_input_changes": next(
            (
                item["stage_name"]
                for item in stage_input_changes
                if item["changed"]
            ),
            None,
        ),
        "memory": memory.report(),
        "stages": stage_results,
        "required_output_artifacts": list(REQUIRED_OUTPUT_ARTIFACTS),
        "artifacts": artifacts,
        "missing_artifacts": missing_artifacts,
        "empty_artifacts": empty_artifacts,
        "run_directory": str(run_directory) if run_directory else None,
        "output_directory": str(output_directory) if output_directory else None,
    }

    report_stem = run_id or (
        f"run_range({start_sol}-{end_sol})_not_started_"
        + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    )
    json_path = reports_root / f"{report_stem}.json"
    csv_path = reports_root / f"{report_stem}_stages.csv"

    json_path.write_text(
        json.dumps(
            report,
            indent=4,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    write_stage_csv(csv_path, stage_results)

    print()
    print("=" * 72)
    print("PERFORMANCE TEST SUMMARY")
    print("=" * 72)
    print(f"Run ID:             {run_id}")
    print(f"Run status:         {status}")
    print(f"Successful:         {successful}")
    print(f"Total time:         {elapsed_total}s")
    print(f"Discovered files:   {discovered_count}")
    print(f"Original unchanged: {original_unchanged}")
    print(f"Sample unchanged:   {sample_unchanged}")

    memory_report = memory.report()
    if memory_report["available"]:
        print(f"Peak RSS:           {memory_report['peak_rss_mb']} MB")
        print(
            "Peak increase:      "
            f"{memory_report['peak_increase_mb']} MB"
        )
    else:
        print("Memory:             unavailable (install psutil)")

    print()
    print("Stage results:")
    for stage in stage_results:
        stage_memory = stage.get("memory", {})
        memory_text = ""
        if stage_memory.get("available"):
            memory_text = (
                f", peak RSS {stage_memory['peak_rss_mb']} MB"
                f", increase {stage_memory['peak_increase_mb']} MB"
            )

        print(
            f"  {stage['stage_name']}: {stage['status']} "
            f"({stage['elapsed_seconds']}s{memory_text})"
        )

    print()
    print(f"Missing artifacts: {len(missing_artifacts)}")
    print(f"Empty artifacts:   {len(empty_artifacts)}")
    print(f"JSON report:       {json_path}")
    print(f"Stage CSV:         {csv_path}")
    print(f"Run output:        {output_directory}")

    if not original_unchanged:
        print("ERROR: Original dataset metadata changed during the test.")

    if not sample_unchanged:
        print("WARNING: Working sample metadata changed during the test.")
        print("Sample input changes:")
        for category in ("added", "removed", "size_changed", "mtime_changed"):
            paths = sample_changes[category]
            print(f"  {category}: {len(paths)}")
            for relative_path in paths:
                print(f"    {relative_path}")
        print(
            "First stage with detected changes: "
            f"{report['first_stage_with_input_changes']}"
        )

    if missing_artifacts:
        print("ERROR: One or more required output artifacts are missing.")
        for artifact in missing_artifacts:
            print(f"  MISSING: {artifact['path']}")

    if empty_artifacts:
        print("WARNING: One or more output artifacts are empty.")
        for artifact in empty_artifacts:
            print(f"  EMPTY: {artifact['path']}")

    return (
        0
        if (
            successful
            and original_unchanged
            and sample_unchanged
            and not missing_artifacts
            and not empty_artifacts
        )
        else 1
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a SOL-range sample and run the complete MEDA "
            "pipeline while measuring time, memory, and output artifacts."
        )
    )

    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Original dataset directory (default: performance/performance_dataset).",
    )
    parser.add_argument(
        "--sample",
        type=Path,
        default=DEFAULT_SAMPLE,
        help="Working sample directory (default: performance/performance_sample).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Results directory (default: performance/performance_test_runs).",
    )
    parser.add_argument(
        "--start-sol",
        type=int,
        default=100,
        help="First SOL number to copy and analyze (default: 100).",
    )
    parser.add_argument(
        "--end-sol",
        type=int,
        default=100,
        help="Last SOL number to copy and analyze (default: 100).",
    )

    args = parser.parse_args()

    return run_performance_test(
        dataset_dir=args.dataset,
        sample_dir=args.sample,
        output_root=args.output,
        start_sol=args.start_sol,
        end_sol=args.end_sol,
    )


if __name__ == "__main__":
    raise SystemExit(main())
