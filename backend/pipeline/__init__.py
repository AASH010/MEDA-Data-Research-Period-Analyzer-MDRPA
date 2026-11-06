"""MEDA analysis pipeline package.

Provides the public API for pipeline configuration,
sequential stage execution, and high-level run orchestration.
"""

from backend.pipeline.pipeline_validator import (
    PipelineConfig,
    validate_pipeline_config,
)

from backend.pipeline.pipeline_executor import (
    PipelineStageResult,
    PipelineExecutionResult,
    execute_pipeline_stages,
)

from backend.pipeline.analysis_pipeline import (
    PipelineRunResult,
    AnalysisPipeline,
)


__all__ = [
    "PipelineConfig",
    "validate_pipeline_config",
    "PipelineStageResult",
    "PipelineExecutionResult",
    "execute_pipeline_stages",
    "PipelineRunResult",
    "AnalysisPipeline",
]