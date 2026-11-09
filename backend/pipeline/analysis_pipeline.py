"""High-level orchestration for one MEDA analysis run.

This module coordinates configuration validation, Run lifecycle
management, sequential pipeline execution, cooperative cancellation,
execution event forwarding, and persistence of execution details.

It does not implement analyzer logic, background workers, GUI behavior,
or scientific calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Any, Callable, Mapping

from backend.pipeline.pipeline_executor import (
    PipelineExecutionResult,
    PipelineStageResult,
    execute_pipeline_stages,
)
from backend.pipeline.pipeline_validator import (
    PipelineConfig,
    validate_pipeline_config,
)
from backend.run_manager.input_shortcut import (
    create_source_input_shortcut,
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

    @property
    def cancelled(self) -> bool:
        """Whether the Run ended through cooperative cancellation."""
        return self.record.status is RunStatus.CANCELLED


class AnalysisPipeline:
    """Coordinate one validated, sequential MEDA analysis run."""

    EXECUTION_SUMMARY_KEY = "execution_summary"

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
            "workers": config.workers,
        }

    @staticmethod
    def _build_execution_summary(
        execution: PipelineExecutionResult | None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Build a JSON-compatible summary of pipeline execution."""
        if execution is None:
            return {
                "status": RunStatus.FAILED.value.lower(),
                "error": error,
                "stages": [],
            }

        stages: list[dict[str, Any]] = []

        for stage in execution.stage_results:
            stages.append({
                "stage_name": stage.stage_name,
                "status": stage.status,
                "started_at": stage.started_at,
                "finished_at": stage.finished_at,
                "output_paths": [
                    str(path)
                    for path in stage.output_paths
                ],
                "warnings": list(stage.warnings),
                "errors": list(stage.errors),
            })

        return {
            "status": execution.status,
            "error": error,
            "stages": stages,
        }

    @staticmethod
    def _build_failure_reason(
        execution: PipelineExecutionResult | None,
        error: str | None = None,
    ) -> str:
        """Build a concise operational failure reason."""
        if error:
            return error

        if execution is not None:
            for stage in execution.stage_results:
                if stage.status == "failed":
                    if stage.errors:
                        return (
                            f"{stage.stage_name}: "
                            f"{stage.errors[0]}"
                        )

                    return (
                        f"Pipeline stage failed: {stage.stage_name}"
                    )

            return (
                "Pipeline execution ended with status "
                f"{execution.status!r}."
            )

        return "Pipeline execution failed."

    def _persist_execution_summary(
        self,
        record: RunRecord,
        execution: PipelineExecutionResult | None,
        error: str | None = None,
    ) -> None:
        """Persist execution details in the run metadata settings."""
        updated_settings = dict(record.metadata.settings)

        updated_settings[self.EXECUTION_SUMMARY_KEY] = (
            self._build_execution_summary(
                execution,
                error,
            )
        )

        record.metadata.settings = updated_settings

    def _persist_failure_details(
        self,
        record: RunRecord,
        execution: PipelineExecutionResult | None,
        error: str | None = None,
    ) -> None:
        """Attach execution details before persisting FAILED status."""
        self._persist_execution_summary(
            record,
            execution,
            error,
        )

        record.metadata.failure_reason = self._build_failure_reason(
            execution,
            error,
        )

    @staticmethod
    def _validate_callback(
        callback: Callable | None,
        name: str,
    ) -> None:
        if callback is not None and not callable(callback):
            raise TypeError(
                f"{name} must be callable or None."
            )

    def execute(
        self,
        config: PipelineConfig | Mapping[str, Any],
        *,
        run_id: str | None = None,
        input_source: str | None = None,
        source_info: Mapping[str, Any] | None = None,
        application_version: str | None = None,
        cancel_event: Event | None = None,
        on_stage_started: Callable[[str], None] | None = None,
        on_stage_completed: Callable[
            [PipelineStageResult], None
        ] | None = None,
        on_progress_updated: Callable[
            [int, str], None
        ] | None = None,
    ) -> PipelineRunResult:
        """Validate, create, and execute one analysis Run.

        Optional event callbacks are forwarded to the pipeline executor.

        Callback exceptions are isolated by the executor and do not
        change Run lifecycle or analyzer results.

        Configuration, cancellation-token, and callback validation
        occur before Run creation.

        A successful Run transitions through:
            PENDING -> RUNNING -> COMPLETED

        A cooperatively cancelled Run transitions through:
            PENDING -> RUNNING -> CANCELLED

        A failed Run transitions through:
            PENDING -> RUNNING -> FAILED

        Execution details are persisted in metadata.json for completed,
        cancelled, and failed executions.

        A generated Run ID requires a configured SOL range, following
        the existing RunManager contract. A caller may provide run_id
        when no SOL range is configured.
        """
        if cancel_event is not None and not isinstance(
            cancel_event,
            Event,
        ):
            raise TypeError(
                "cancel_event must be a threading.Event instance or None."
            )

        self._validate_callback(
            on_stage_started,
            "on_stage_started",
        )
        self._validate_callback(
            on_stage_completed,
            "on_stage_completed",
        )
        self._validate_callback(
            on_progress_updated,
            "on_progress_updated",
        )

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

        # A source shortcut is optional and must not interrupt the analysis.
        try:
            create_source_input_shortcut(
                source_dir=validated_config.input_dir,
                run_input_dir=record.paths.input_dir,
            )
        except Exception:
            pass

        record = self.run_manager.start_run(record.run_id)

        

        execution: PipelineExecutionResult | None = None

        try:
            # Preserve backward compatibility with existing callers,
            # tests, and integrations that use the original executor
            # call when no optional features are requested.
            executor_callbacks = {}

            if on_stage_started is not None:
                executor_callbacks["on_stage_started"] = (
                    on_stage_started
                )

            if on_stage_completed is not None:
                executor_callbacks["on_stage_completed"] = (
                    on_stage_completed
                )

            if on_progress_updated is not None:
                executor_callbacks["on_progress_updated"] = (
                    on_progress_updated
                )

            if cancel_event is None and not executor_callbacks:
                execution = execute_pipeline_stages(
                    validated_config,
                    record.paths,
                )

            elif cancel_event is None:
                execution = execute_pipeline_stages(
                    validated_config,
                    record.paths,
                    **executor_callbacks,
                )

            elif not executor_callbacks:
                execution = execute_pipeline_stages(
                    validated_config,
                    record.paths,
                    cancel_event=cancel_event,
                )

            else:
                execution = execute_pipeline_stages(
                    validated_config,
                    record.paths,
                    cancel_event=cancel_event,
                    **executor_callbacks,
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

            if execution.status == "cancelled":
                self._persist_execution_summary(
                    record,
                    execution,
                )

                record = self.run_manager.cancel_run(
                    record.run_id
                )

                return PipelineRunResult(
                    record=record,
                    execution=execution,
                )

            if execution.successful:
                # Persist the execution details before completing the Run
                # so the terminal metadata contains the full summary.
                self._persist_execution_summary(
                    record,
                    execution,
                )

                record = self.run_manager.complete_run(
                    record.run_id
                )

                return PipelineRunResult(
                    record=record,
                    execution=execution,
                )

            self._persist_failure_details(
                record,
                execution,
            )

            record = self.run_manager.fail_run(
                record.run_id
            )

            return PipelineRunResult(
                record=record,
                execution=execution,
            )

        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

            self._persist_failure_details(
                record,
                execution,
                error,
            )

            record = self.run_manager.fail_run(
                record.run_id
            )

            return PipelineRunResult(
                record=record,
                execution=None,
                error=error,
            )
