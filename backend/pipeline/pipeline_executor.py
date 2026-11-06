
"""Sequential execution of the MEDA analysis pipeline stages.

This module adapts the existing analyzers to one isolated RunPaths output
directory. It does not manage Run lifecycle status, create background
workers, or change scientific analyzer logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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
) -> tuple[Path, Path]:
    if not isinstance(config, PipelineConfig):
        raise TypeError(
            "config must be a validated PipelineConfig instance."
        )

    if not isinstance(run_paths, RunPaths):
        raise TypeError(
            "run_paths must be a RunPaths instance."
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


def execute_pipeline_stages(
    config: PipelineConfig,
    run_paths: RunPaths,
) -> PipelineExecutionResult:
    """Execute analyzers sequentially for one isolated run.

    A stage failure immediately stops execution of all remaining stages.
    Artifacts created by earlier completed stages are preserved.

    Run lifecycle status is managed by AnalysisPipeline.
    """
    input_dir, output_dir = _validate_execution_inputs(
        config,
        run_paths,
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
        "quality": _output_path(
            output_dir,
            "quality_field_report.csv",
        ),
        "quality_summary": _output_path(
            output_dir,
            "quality_summary.json",
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
        "ranking": _output_path(
            output_dir,
            "period_ranking.csv",
        ),
        "ranking_summary": _output_path(
            output_dir,
            "period_ranking_summary.json",
        ),
    }

    stage_results: list[PipelineStageResult] = []

    def build_execution_result() -> PipelineExecutionResult:
        statuses = {
            result.status
            for result in stage_results
        }

        if "failed" in statuses:
            overall_status = "failed"
        elif "completed_with_warnings" in statuses:
            overall_status = "completed_with_warnings"
        else:
            overall_status = "completed"

        return PipelineExecutionResult(
            run_id=run_paths.run_id,
            status=overall_status,
            stage_results=tuple(stage_results),
        )

    def execute_and_record(
        stage_name: str,
        operation: Callable,
    ) -> bool:
        """Execute one stage and stop immediately if it fails."""
        result = _execute_one_stage(
            stage_name,
            operation,
        )

        stage_results.append(result)

        if result.status == "failed":
            failed_index = len(stage_results)

            for remaining_stage in _STAGE_NAMES[failed_index:]:
                stage_results.append(
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

        coverage_reports = coverage_analyzer.analyze_coverage(
            input_dir,
            inventory_records,
            metadata_inventory,
            gap_factor=config.gap_factor,
        )

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

        if config.start_sol is not None:
            summary_start = config.start_sol
            summary_end = config.end_sol
        else:
            if not observed_sols:
                raise ValueError(
                    "Coverage summary requires at least one valid SOL "
                    "number in the file inventory when no SOL range "
                    "was configured."
                )

            summary_start = min(observed_sols)
            summary_end = max(observed_sols)

        product_summary = coverage_analyzer.build_product_summary(
            coverage_reports,
            summary_start,
            summary_end,
        )

        coverage_summary = {
            "start_sol": summary_start,
            "end_sol": summary_end,
            "report_count": len(coverage_reports),
            "products": product_summary,
        }

        coverage_analyzer.save_summary_json(
            coverage_summary,
            artifacts["coverage_summary"],
        )

        return (
            (
                artifacts["coverage"],
                artifacts["coverage_summary"],
            ),
            coverage_summary,
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

        quality_reports = quality_analyzer.run_analysis(
            input_dir,
            inventory_records,
            metadata_inventory,
        )

        quality_analyzer.write_report(
            artifacts["quality"],
            quality_reports,
        )

        quality_summary = quality_analyzer.build_summary(
            quality_reports
        )

        quality_analyzer.save_summary(
            artifacts["quality_summary"],
            quality_summary,
        )

        return (
            (
                artifacts["quality"],
                artifacts["quality_summary"],
            ),
            quality_summary,
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

        sync_summary = synchronization_analyzer.build_summary(
            sync_file_reports,
            sync_pair_reports,
            config.tolerance,
        )

        synchronization_analyzer.save_summary(
            artifacts["sync_summary"],
            sync_summary,
        )

        return (
            (
                artifacts["sync_files"],
                artifacts["sync_pairs"],
                artifacts["sync_summary"],
            ),
            sync_summary,
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
        ranker_args = SimpleNamespace(
            inventory=str(artifacts["inventory"]),
            coverage=str(artifacts["coverage"]),
            quality=str(artifacts["quality"]),
            sync_files=str(artifacts["sync_files"]),
            sync_pairs=str(artifacts["sync_pairs"]),
            output=str(artifacts["ranking"]),
            summary=str(artifacts["ranking_summary"]),
            start_sol=config.start_sol,
            end_sol=config.end_sol,
            window_size=config.window_size,
            min_sol_fraction=config.min_sol_fraction,
            min_metrics=config.min_metrics,
            required_products=list(config.required_products),
            weight_files=config.weight_files,
            weight_integrity=config.weight_integrity,
            weight_quality=config.weight_quality,
            weight_sync=config.weight_sync,
            integrity_timestamps=config.integrity_timestamps,
            integrity_values=config.integrity_values,
        )

        ranking_summary = period_ranker.run(ranker_args)

        return (
            (
                artifacts["ranking"],
                artifacts["ranking_summary"],
            ),
            ranking_summary,
            (),
        )

    if not execute_and_record(
        "period_ranker",
        run_period_ranker,
    ):
        return build_execution_result()

    return build_execution_result()
