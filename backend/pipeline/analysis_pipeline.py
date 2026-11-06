"""High-level orchestration for one MEDA analysis run.

This module coordinates configuration validation, Run lifecycle
management, and sequential pipeline execution.

It does not implement analyzer logic, background workers, GUI behavior,
or scientific calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from backend.pipeline.pipeline_executor import (
    PipelineExecutionResult,
    execute_pipeline_stages,
)
from backend.pipeline.pipeline_validator import (
    PipelineConfig,
    validate_pipeline_config,
)
from backend.run_manager.run_manager import RunManager
from backend.run_manager.run_registry import RunRecord
from backend.run_manager.run_status import RunStatus


__all__ = [
    "PipelineRunResult",
    "AnalysisPipeline",
]


@dataclass(frozen=True)
class PipelineRunResult:
    """Combined Run lifecycle and pipeline execution result."""

    record: RunRecord
    execution: PipelineExecutionResult | None = None
    error: str | None = None

    @property
    def run_id(self) -> str:
        """Return the identifier of the associated run."""
        return self.record.run_id

    @property
    def status(self) -> str:
        """Return the current Run lifecycle status."""
        return self.record.status.value

    @property
    def successful(self) -> bool:
        """Whether the Run completed successfully."""
        return (
            self.record.status is RunStatus.COMPLETED
            and self.execution is not None
            and self.execution.successful
            and self.error is None
        )


class AnalysisPipeline:
    """Coordinate one validated, sequential MEDA analysis run."""

    def __init__(
        self,
        run_manager: RunManager,
    ) -> None:
        if not isinstance(run_manager, RunManager):
            raise TypeError(
                "run_manager must be a RunManager instance."
            )

        self.run_manager = run_manager

    @staticmethod
    def _config_settings(
        config: PipelineConfig,
    ) -> dict[str, Any]:
        """Convert validated configuration into JSON-compatible settings."""
        return {
            "input_dir": str(config.input_dir),
            "start_sol": config.start_sol,
            "end_sol": config.end_sol,
            "gap_factor": config.gap_factor,
            "tolerance": config.tolerance,
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

    def execute(
        self,
        config: PipelineConfig | Mapping[str, Any],
        *,
        run_id: str | None = None,
        input_source: str | None = None,
        source_info: Mapping[str, Any] | None = None,
        application_version: str | None = None,
    ) -> PipelineRunResult:
        """Validate, create, and execute one analysis Run.

        Configuration validation occurs before Run creation.

        A successfully created Run transitions through:
            PENDING -> RUNNING -> COMPLETED

        If a pipeline stage fails, the Run transitions to FAILED.

        If an unexpected exception occurs during stage execution,
        the Run is marked FAILED and the exception is returned as
        a structured error string.

        A generated Run ID requires a configured SOL range, following
        the existing RunManager contract. A caller may provide run_id
        when no SOL range is configured.
        """
        validated_config = validate_pipeline_config(config)

        record = self.run_manager.create_run(
            run_id=run_id,
            start_sol=validated_config.start_sol,
            end_sol=validated_config.end_sol,
            input_source=input_source,
            source_info=source_info,
            settings=self._config_settings(validated_config),
            application_version=application_version,
        )

        record = self.run_manager.start_run(record.run_id)

        try:
            execution = execute_pipeline_stages(
                validated_config,
                record.paths,
            )

            if not isinstance(execution, PipelineExecutionResult):
                raise TypeError(
                    "Pipeline executor must return a "
                    "PipelineExecutionResult instance."
                )

            if execution.run_id != record.run_id:
                raise ValueError(
                    "Pipeline execution run_id does not match "
                    "the active Run."
                )

            if execution.successful:
                record = self.run_manager.complete_run(
                    record.run_id
                )
            else:
                record = self.run_manager.fail_run(
                    record.run_id
                )

            return PipelineRunResult(
                record=record,
                execution=execution,
            )

        except Exception as exc:
            record = self.run_manager.fail_run(
                record.run_id
            )

            return PipelineRunResult(
                record=record,
                execution=None,
                error=f"{type(exc).__name__}: {exc}",
            )