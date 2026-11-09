"""Sequential execution of the MEDA analysis pipeline stages.

This module adapts existing analyzers to one isolated RunPaths output
directory. It supports cooperative cancellation and optional execution
event callbacks.

It does not manage Run lifecycle status, create background workers,
or change scientific analyzer logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import Any, Callable

from backend.analyzers import (
    coverage_analyzer,
    file_discovery,
    period_ranker,
    quality_analyzer,
    synchronization_analyzer,
    xml_parser,
)
from backend.pipeline.pipeline_validator import PipelineConfig
from backend.run_manager.run_paths import RunPaths


__all__ = [
    "PipelineStageResult",
    "PipelineExecutionResult",
    "execute_pipeline_stages",
]


StageStartedCallback = Callable[[str], None]
StageCompletedCallback = Callable[["PipelineStageResult"], None]
ProgressCallback = Callable[[int, str], None]


@dataclass(frozen=True)
class PipelineStageResult:
    """Execution record for one pipeline stage."""

    stage_name: str
    status: str
    started_at: str
    finished_at: str
    output_paths: tuple[Path, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    summary: dict[str, Any] | None = None


@dataclass(frozen=True)
class PipelineExecutionResult:
    """Aggregate result returned by the pipeline executor."""

    run_id: str
    status: str
    stage_results: tuple[PipelineStageResult, ...]

    @property
    def successful(self) -> bool:
        """Whether all executed stages completed without failure."""
        return self.status in {
            "completed",
            "completed_with_warnings",
        }


_STAGE_NAMES = (
    "file_discovery",
    "xml_parser",
    "coverage_analyzer",
    "quality_analyzer",
    "synchronization_analyzer",
    "period_ranker",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _notify(
    callback: Callable | None,
    *args: Any,
) -> None:
    """Notify an observer without allowing it to affect execution.

    Callback exceptions are intentionally isolated. Monitoring or UI
    notification failures must not change analyzer execution results.
    """
    if callback is None:
        return

    try:
        callback(*args)
    except Exception:
        pass


def _validate_callback(
    callback: Callable | None,
    name: str,
) -> None:
    if callback is not None and not callable(callback):
        raise TypeError(
            f"{name} must be callable or None."
        )


def _output_path(output_dir: Path, filename: str) -> Path:
    """Build a direct child path inside the run output directory."""
    path = (output_dir / filename).resolve()

    if path.parent != output_dir.resolve():
        raise ValueError(
            f"Pipeline output must remain inside the run output directory: "
            f"{filename}"
        )

    return path


def _require_output_files(paths: tuple[Path, ...]) -> None:
    """Ensure that a stage actually created every declared artifact."""
    missing = [
        str(path)
        for path in paths
        if not path.is_file()
    ]

    if missing:
        raise FileNotFoundError(
            "Pipeline stage did not create expected output file(s): "
            + ", ".join(missing)
        )


def _validate_execution_inputs(
    config: PipelineConfig,
    run_paths: RunPaths,
    cancel_event: Event | None,
) -> tuple[Path, Path]:
    if not isinstance(config, PipelineConfig):
        raise TypeError(
            "config must be a validated PipelineConfig instance."
        )

    if not isinstance(run_paths, RunPaths):
        raise TypeError(
            "run_paths must be a RunPaths instance."
        )

    if cancel_event is not None and not isinstance(
        cancel_event,
        Event,
    ):
        raise TypeError(
            "cancel_event must be a threading.Event instance or None."
        )

    input_dir = config.input_dir.resolve()
    output_dir = run_paths.output_dir.resolve()
    root_dir = run_paths.root_dir.resolve()

    if not input_dir.is_dir():
        raise NotADirectoryError(
            f"Input directory does not exist: {input_dir}"
        )

    if output_dir.parent != root_dir:
        raise ValueError(
            "Run output directory must be a direct child of run root."
        )

    if not output_dir.is_dir():
        raise FileNotFoundError(
            f"Run output directory does not exist: {output_dir}"
        )

    return input_dir, output_dir


def _make_stage_result(
    *,
    stage_name: str,
    status: str,
    started_at: str,
    output_paths: tuple[Path, ...] = (),
    warnings: tuple[str, ...] = (),
    errors: tuple[str, ...] = (),
    summary: dict[str, Any] | None = None,
) -> PipelineStageResult:
    return PipelineStageResult(
        stage_name=stage_name,
        status=status,
        started_at=started_at,
        finished_at=_utc_now(),
        output_paths=output_paths,
        warnings=warnings,
        errors=errors,
        summary=summary,
    )


def _execute_one_stage(
    stage_name: str,
    operation: Callable,
) -> PipelineStageResult:
    """Execute one complete analyzer stage.

    Cancellation is deliberately not checked inside this function.
    An analyzer that has started is allowed to finish normally.
    """
    started_at = _utc_now()

    try:
        output_paths, summary, warnings = operation()

        output_paths = tuple(
            Path(path).resolve()
            for path in output_paths
        )

        warnings = tuple(warnings)

        _require_output_files(output_paths)

        status = (
            "completed_with_warnings"
            if warnings
            else "completed"
        )

        return _make_stage_result(
            stage_name=stage_name,
            status=status,
            started_at=started_at,
            output_paths=output_paths,
            warnings=warnings,
            summary=summary,
        )

    except Exception as exc:
        return _make_stage_result(
            stage_name=stage_name,
            status="failed",
            started_at=started_at,
            errors=(f"{type(exc).__name__}: {exc}",),
        )


def _skipped_stage(stage_name: str) -> PipelineStageResult:
    now = _utc_now()

    return PipelineStageResult(
        stage_name=stage_name,
        status="skipped",
        started_at=now,
        finished_at=now,
        warnings=(
            "Stage was not executed because a previous stage failed.",
        ),
    )


def _cancelled_stage(stage_name: str) -> PipelineStageResult:
    now = _utc_now()

    return PipelineStageResult(
        stage_name=stage_name,
        status="cancelled",
        started_at=now,
        finished_at=now,
        warnings=(
            "Stage was not executed because cancellation was requested.",
        ),
    )


def execute_pipeline_stages(
    config: PipelineConfig,
    run_paths: RunPaths,
    *,
    cancel_event: Event | None = None,
    on_stage_started: StageStartedCallback | None = None,
    on_stage_completed: StageCompletedCallback | None = None,
    on_progress_updated: ProgressCallback | None = None,
) -> PipelineExecutionResult:
    """Execute analyzers sequentially for one isolated run.

    Optional callbacks report actual stage lifecycle events:

    - on_stage_started(stage_name): called immediately before an
      analyzer stage starts.
    - on_stage_completed(stage_result): called when a stage result is
      recorded, including failed, skipped, and cancelled stages.
    - on_progress_updated(percentage, message): called after each
      stage result is recorded. Percentage is based on the six
      pipeline stages, not elapsed time.

    Stages marked skipped or cancelled are not reported as started.

    Callback exceptions are isolated and do not alter pipeline results.

    A stage failure immediately stops execution of all remaining stages.

    When cancel_event is set, cancellation is applied at the next safe
    stage boundary. An analyzer that has already started is allowed to
    finish before the remaining stages are marked as cancelled.

    Artifacts created by completed stages are preserved.

    Run lifecycle status is managed by AnalysisPipeline.
    """
    _validate_callback(
        on_stage_started,
        "on_stage_started",
    )
    _validate_callback(
        on_stage_completed,
        "on_stage_completed",
    )
    _validate_callback(
        on_progress_updated,
        "on_progress_updated",
    )

    input_dir, output_dir = _validate_execution_inputs(
        config,
        run_paths,
        cancel_event,
    )

    artifacts = {
        "inventory": _output_path(
            output_dir,
            "file_inventory.csv",
        ),
        "metadata": _output_path(
            output_dir,
            "metadata_inventory.json",
        ),
        "coverage": _output_path(
            output_dir,
            "coverage_report.csv",
        ),
        "coverage_summary": _output_path(
            output_dir,
            "coverage_summary.json",
        ),
        "coverage_range_summary": _output_path(
            output_dir,
            "coverage_range_summary.json",
        ),
        "quality": _output_path(
            output_dir,
            "quality_field_report.csv",
        ),
        "quality_summary": _output_path(
            output_dir,
            "quality_summary.json",
        ),
        "quality_range_summary": _output_path(
            output_dir,
            "quality_range_summary.json",
        ),
        "sync_files": _output_path(
            output_dir,
            "synchronization_file_report.csv",
        ),
        "sync_pairs": _output_path(
            output_dir,
            "synchronization_pair_report.csv",
        ),
        "sync_summary": _output_path(
            output_dir,
            "synchronization_summary.json",
        ),
        "sync_range_summary": _output_path(
            output_dir,
            "synchronization_range_summary.json",
        ),
        "ranking": _output_path(
            output_dir,
            "period_ranking.csv",
        ),
        "ranking_summary": _output_path(
            output_dir,
            "period_ranking_summary.json",
        ),
        "ranking_full": _output_path(
            output_dir,
            "period_ranking_full.csv",
        ),
        "ranking_full_summary": _output_path(
            output_dir,
            "period_ranking_full_summary.json",
        ),
    }

    stage_results: list[PipelineStageResult] = []

    def record_stage_result(
        result: PipelineStageResult,
    ) -> None:
        """Store a stage result and notify observers."""
        stage_results.append(result)

        _notify(
            on_stage_completed,
            result,
        )

        percentage = round(
            len(stage_results) / len(_STAGE_NAMES) * 100
        )

        _notify(
            on_progress_updated,
            percentage,
            f"{result.stage_name}: {result.status}",
        )

    def build_execution_result() -> PipelineExecutionResult:
        statuses = {
            result.status
            for result in stage_results
        }

        if "failed" in statuses:
            overall_status = "failed"
        elif "cancelled" in statuses:
            overall_status = "cancelled"
        elif "completed_with_warnings" in statuses:
            overall_status = "completed_with_warnings"
        else:
            overall_status = "completed"

        return PipelineExecutionResult(
            run_id=run_paths.run_id,
            status=overall_status,
            stage_results=tuple(stage_results),
        )

    def record_cancelled_stages(
        first_stage_index: int,
    ) -> None:
        """Record the current and all remaining stages as cancelled."""
        for remaining_stage in _STAGE_NAMES[first_stage_index:]:
            record_stage_result(
                _cancelled_stage(remaining_stage)
            )

    def execute_and_record(
        stage_name: str,
        operation: Callable,
    ) -> bool:
        """Execute one stage, respecting failure and cancellation."""
        stage_index = _STAGE_NAMES.index(stage_name)

        # Safe checkpoint before starting the next analyzer.
        if (
            cancel_event is not None
            and cancel_event.is_set()
        ):
            record_cancelled_stages(stage_index)
            return False

        _notify(
            on_stage_started,
            stage_name,
        )

        result = _execute_one_stage(
            stage_name,
            operation,
        )

        record_stage_result(result)

        # A real stage failure takes precedence over a simultaneous
        # cancellation request. Remaining stages are skipped because
        # their required inputs may be incomplete.
        if result.status == "failed":
            failed_index = stage_index + 1

            for remaining_stage in _STAGE_NAMES[failed_index:]:
                record_stage_result(
                    _skipped_stage(remaining_stage)
                )

            return False

        return True

    inventory_records: list[dict] = []
    metadata_inventory: dict[str, Any] = {}
    coverage_reports: list[dict] = []
    quality_reports: list[dict] = []
    sync_file_reports: list[dict] = []
    sync_pair_reports: list[dict] = []

    observed_start: int | None = None
    observed_end: int | None = None
    selected_start: int | None = None
    selected_end: int | None = None

    # -----------------------------------------------------
    # 1. File Discovery
    # -----------------------------------------------------

    def run_file_discovery():
        nonlocal inventory_records

        inventory_records = file_discovery.discover_files(
            input_dir
        )

        if not inventory_records:
            raise ValueError(
                "File Discovery found no files inside "
                "recognized SOL directories."
            )

        # Preserve the complete inventory, including unsupported files,
        # so that the inventory remains useful for diagnostics.
        file_discovery.write_inventory(
            inventory_records,
            artifacts["inventory"],
        )

        supported_extensions = {
            str(extension).lower()
            for extension in file_discovery.SUPPORTED_EXTENSIONS
        }

        supported_records = []

        for record in inventory_records:
            extension = record.get("extension")

            if not extension:
                filename = (
                    record.get("filename")
                    or record.get("relative_path")
                    or ""
                )
                extension = Path(str(filename)).suffix

            if str(extension).lower() in supported_extensions:
                supported_records.append(record)

        if not supported_records:
            raise ValueError(
                "File Discovery found no supported CSV or XML files "
                "inside recognized SOL directories."
            )

        return (
            (artifacts["inventory"],),
            {
                "inventory_record_count": len(inventory_records),
                "supported_file_count": len(supported_records),
            },
            (),
        )

    if not execute_and_record(
        "file_discovery",
        run_file_discovery,
    ):
        return build_execution_result()

    # -----------------------------------------------------
    # 2. XML Parser
    # -----------------------------------------------------

    def run_xml_parser():
        nonlocal metadata_inventory

        metadata_inventory = xml_parser.build_metadata_inventory(
            input_dir
        )

        if not isinstance(metadata_inventory, dict):
            raise TypeError(
                "XML Parser must return a metadata inventory dictionary."
            )

        metadata_records = metadata_inventory.get("records")

        if not isinstance(metadata_records, list):
            raise ValueError(
                "XML Parser metadata inventory must contain a "
                "'records' list."
            )

        xml_parser.save_json(
            metadata_inventory,
            artifacts["metadata"],
        )

        warnings = []
        parser_summary = metadata_inventory.get("summary", {})

        failed_xml = parser_summary.get("failed_to_parse", 0)

        if isinstance(failed_xml, int) and failed_xml > 0:
            warnings.append(
                f"XML Parser reported {failed_xml} XML file(s) "
                "that could not be parsed."
            )

        return (
            (artifacts["metadata"],),
            {
                "metadata_record_count": len(metadata_records),
                "parser_summary": parser_summary,
            },
            tuple(warnings),
        )

    if not execute_and_record(
        "xml_parser",
        run_xml_parser,
    ):
        return build_execution_result()

    # -----------------------------------------------------
    # 3. Coverage Analyzer
    # -----------------------------------------------------

    def run_coverage_analyzer():
        nonlocal coverage_reports
        nonlocal observed_start, observed_end
        nonlocal selected_start, selected_end

        csv_file_count = coverage_analyzer.count_csv_records(
            inventory_records
        )

        effective_workers = coverage_analyzer.choose_workers(
            config.workers,
            csv_file_count,
        )

        coverage_reports = coverage_analyzer.analyze_coverage(
            input_dir,
            inventory_records,
            metadata_inventory,
            gap_factor=config.gap_factor,
            workers=effective_workers,
        )

        # Detailed coverage remains a full-dataset report.
        coverage_analyzer.save_coverage_csv(
            coverage_reports,
            artifacts["coverage"],
        )

        observed_sols = [
            row.get("sol_number")
            for row in inventory_records
            if isinstance(row.get("sol_number"), int)
            and not isinstance(row.get("sol_number"), bool)
            and row.get("sol_number") >= 0
        ]

        if not observed_sols:
            raise ValueError(
                "Coverage summaries require at least one valid SOL "
                "number in the file inventory."
            )

        # Full dataset boundaries are independent of user selection.
        observed_start = min(observed_sols)
        observed_end = max(observed_sols)

        full_product_summary = (
            coverage_analyzer.build_product_summary(
                coverage_reports,
                observed_start,
                observed_end,
            )
        )

        full_coverage_summary = {
            "start_sol": observed_start,
            "end_sol": observed_end,
            "report_count": len(coverage_reports),
            "products": full_product_summary,
        }

        coverage_analyzer.save_summary_json(
            full_coverage_summary,
            artifacts["coverage_summary"],
        )

        # Resolve omitted bounds against the observed dataset range.
        requested_start = (
            config.start_sol
            if config.start_sol is not None
            else observed_start
        )
        requested_end = (
            config.end_sol
            if config.end_sol is not None
            else observed_end
        )

        # Restrict the effective selected range to observed SOLs.
        selected_start = max(
            requested_start,
            observed_start,
        )
        selected_end = min(
            requested_end,
            observed_end,
        )

        if selected_start > selected_end:
            raise ValueError(
                "The selected SOL range does not overlap the observed "
                f"dataset range ({observed_start}-{observed_end})."
            )

        selected_reports = [
            report
            for report in coverage_reports
            if isinstance(report.get("sol_number"), int)
            and not isinstance(report.get("sol_number"), bool)
            and selected_start <= report["sol_number"] <= selected_end
        ]

        selected_product_summary = (
            coverage_analyzer.build_product_summary(
                coverage_reports,
                selected_start,
                selected_end,
            )
        )

        selected_coverage_summary = {
            "start_sol": selected_start,
            "end_sol": selected_end,
            "report_count": len(selected_reports),
            "products": selected_product_summary,
        }

        coverage_analyzer.save_summary_json(
            selected_coverage_summary,
            artifacts["coverage_range_summary"],
        )

        return (
            (
                artifacts["coverage"],
                artifacts["coverage_summary"],
                artifacts["coverage_range_summary"],
            ),
            {
                "full_dataset": full_coverage_summary,
                "selected_range": selected_coverage_summary,
                "observed_range": {
                    "start_sol": observed_start,
                    "end_sol": observed_end,
                },
                "parallelism": {
                    "workers_requested": config.workers,
                    "workers_used": effective_workers,
                    "csv_files": csv_file_count,
                },
            },
            (),
        )

    if not execute_and_record(
        "coverage_analyzer",
        run_coverage_analyzer,
    ):
        return build_execution_result()

    # -----------------------------------------------------
    # 4. Quality Analyzer
    # -----------------------------------------------------

    def run_quality_analyzer():
        nonlocal quality_reports

        if (
            observed_start is None
            or observed_end is None
            or selected_start is None
            or selected_end is None
        ):
            raise RuntimeError(
                "SOL ranges must be resolved before Quality Analyzer."
            )

        quality_reports = quality_analyzer.run_analysis(
            input_dir,
            inventory_records,
            metadata_inventory,
        )

        # Detailed quality report remains unfiltered.
        quality_analyzer.write_report(
            artifacts["quality"],
            quality_reports,
        )

        full_quality_summary = quality_analyzer.build_summary(
            quality_reports,
            start_sol=observed_start,
            end_sol=observed_end,
        )

        quality_analyzer.save_summary(
            artifacts["quality_summary"],
            full_quality_summary,
        )

        selected_quality_summary = quality_analyzer.build_summary(
            quality_reports,
            start_sol=selected_start,
            end_sol=selected_end,
        )

        quality_analyzer.save_summary(
            artifacts["quality_range_summary"],
            selected_quality_summary,
        )

        return (
            (
                artifacts["quality"],
                artifacts["quality_summary"],
                artifacts["quality_range_summary"],
            ),
            {
                "full_dataset": full_quality_summary,
                "selected_range": selected_quality_summary,
            },
            (),
        )

    if not execute_and_record(
        "quality_analyzer",
        run_quality_analyzer,
    ):
        return build_execution_result()

    # -----------------------------------------------------
    # 5. Synchronization Analyzer
    # -----------------------------------------------------

    def run_synchronization_analyzer():
        nonlocal sync_file_reports, sync_pair_reports

        if (
            observed_start is None
            or observed_end is None
            or selected_start is None
            or selected_end is None
        ):
            raise RuntimeError(
                "SOL ranges must be resolved before Synchronization Analyzer."
            )

        metadata_records = metadata_inventory["records"]

        (
            sync_file_reports,
            sync_pair_reports,
        ) = synchronization_analyzer.run_analysis(
            input_dir,
            inventory_records,
            metadata_records,
            tolerance=config.tolerance,
        )

        # Detailed synchronization reports remain unfiltered.
        synchronization_analyzer.write_csv(
            artifacts["sync_files"],
            sync_file_reports,
            synchronization_analyzer.FILE_REPORT_COLUMNS,
        )

        synchronization_analyzer.write_csv(
            artifacts["sync_pairs"],
            sync_pair_reports,
            synchronization_analyzer.PAIR_REPORT_COLUMNS,
        )

        full_sync_summary = synchronization_analyzer.build_summary(
            sync_file_reports,
            sync_pair_reports,
            config.tolerance,
            start_sol=observed_start,
            end_sol=observed_end,
        )

        synchronization_analyzer.save_summary(
            artifacts["sync_summary"],
            full_sync_summary,
        )

        selected_sync_summary = synchronization_analyzer.build_summary(
            sync_file_reports,
            sync_pair_reports,
            config.tolerance,
            start_sol=selected_start,
            end_sol=selected_end,
        )

        synchronization_analyzer.save_summary(
            artifacts["sync_range_summary"],
            selected_sync_summary,
        )

        return (
            (
                artifacts["sync_files"],
                artifacts["sync_pairs"],
                artifacts["sync_summary"],
                artifacts["sync_range_summary"],
            ),
            {
                "full_dataset": full_sync_summary,
                "selected_range": selected_sync_summary,
            },
            (),
        )

    if not execute_and_record(
        "synchronization_analyzer",
        run_synchronization_analyzer,
    ):
        return build_execution_result()

    # -----------------------------------------------------
    # 6. Period Ranker
    # -----------------------------------------------------

    def run_period_ranker():
        if (
            observed_start is None
            or observed_end is None
            or selected_start is None
            or selected_end is None
        ):
            raise RuntimeError(
                "SOL ranges must be resolved before Period Ranker."
            )

        common_ranker_args = {
            "inventory": str(artifacts["inventory"]),
            "coverage": str(artifacts["coverage"]),
            "quality": str(artifacts["quality"]),
            "sync_files": str(artifacts["sync_files"]),
            "sync_pairs": str(artifacts["sync_pairs"]),
            "window_size": config.window_size,
            "min_sol_fraction": config.min_sol_fraction,
            "min_metrics": config.min_metrics,
            "required_products": list(config.required_products),
            "weight_files": config.weight_files,
            "weight_integrity": config.weight_integrity,
            "weight_quality": config.weight_quality,
            "weight_sync": config.weight_sync,
            "integrity_timestamps": config.integrity_timestamps,
            "integrity_values": config.integrity_values,
        }

        # Run the full-dataset ranking independently of the selected range.
        full_ranker_args = SimpleNamespace(
            **common_ranker_args,
            output=str(artifacts["ranking_full"]),
            summary=str(artifacts["ranking_full_summary"]),
            start_sol=observed_start,
            end_sol=observed_end,
        )

        full_ranking_summary = period_ranker.run(
            full_ranker_args
        )

        # Preserve the existing ranking artifact names and their
        # selected-range behavior for backward compatibility.
        selected_ranker_args = SimpleNamespace(
            **common_ranker_args,
            output=str(artifacts["ranking"]),
            summary=str(artifacts["ranking_summary"]),
            start_sol=selected_start,
            end_sol=selected_end,
        )

        selected_ranking_summary = period_ranker.run(
            selected_ranker_args
        )

        return (
            (
                artifacts["ranking_full"],
                artifacts["ranking_full_summary"],
                artifacts["ranking"],
                artifacts["ranking_summary"],
            ),
            {
                "full_dataset": full_ranking_summary,
                "selected_range": selected_ranking_summary,
            },
            (),
        )

    if not execute_and_record(
        "period_ranker",
        run_period_ranker,
    ):
        return build_execution_result()

    return build_execution_result()