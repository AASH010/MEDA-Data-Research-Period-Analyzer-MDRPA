"""Configuration and input validation for the MEDA analysis pipeline.

This module validates pipeline configuration before a Run is created.
It does not create run directories, execute analyzers, or perform
scientific calculations.
"""

from __future__ import annotations

import math

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


__all__ = [
    "PipelineConfig",
    "validate_pipeline_config",
]


DEFAULT_REQUIRED_PRODUCTS = (
    "ATS",
    "PS",
    "RDS",
    "RHS",
    "TIRS",
    "WS",
)

DEFAULT_RANKING_WEIGHTS = {
    "weight_files": 0.20,
    "weight_integrity": 0.45,
    "weight_quality": 0.15,
    "weight_sync": 0.20,
}

DEFAULT_INTEGRITY_WEIGHTS = {
    "integrity_timestamps": 1.0,
    "integrity_values": 1.0,
}


@dataclass(frozen=True)
class PipelineConfig:
    """Validated configuration for one pipeline execution."""

    input_dir: Path

    start_sol: int | None = None
    end_sol: int | None = None

    gap_factor: float = 2.5
    tolerance: float = 1.0

    window_size: int = 10
    min_sol_fraction: float = 0.5
    min_metrics: int = 3

    required_products: tuple[str, ...] = DEFAULT_REQUIRED_PRODUCTS

    weight_files: float = 0.20
    weight_integrity: float = 0.45
    weight_quality: float = 0.15
    weight_sync: float = 0.20

    integrity_timestamps: float = 1.0
    integrity_values: float = 1.0


_ALLOWED_CONFIG_KEYS = frozenset(
    PipelineConfig.__dataclass_fields__.keys()
)

_WEIGHT_FIELDS = (
    *DEFAULT_RANKING_WEIGHTS.keys(),
    *DEFAULT_INTEGRITY_WEIGHTS.keys(),
)


def _validate_sol_value(
    value: Any,
    field_name: str,
) -> None:
    if value is None:
        return

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            f"{field_name} must be a non-negative integer or None."
        )

    if value < 0:
        raise ValueError(
            f"{field_name} must be non-negative."
        )


def _validate_sol_range(
    start_sol: int | None,
    end_sol: int | None,
) -> None:
    _validate_sol_value(start_sol, "start_sol")
    _validate_sol_value(end_sol, "end_sol")

    if (start_sol is None) != (end_sol is None):
        raise ValueError(
            "start_sol and end_sol must either both be provided "
            "or both be None."
        )

    if (
        start_sol is not None
        and end_sol is not None
        and start_sol > end_sol
    ):
        raise ValueError(
            "start_sol must be less than or equal to end_sol."
        )


def _validate_finite_number(
    value: Any,
    field_name: str,
) -> float:
    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        raise TypeError(
            f"{field_name} must be a finite number."
        )

    number = float(value)

    if not math.isfinite(number):
        raise ValueError(
            f"{field_name} must be finite."
        )

    return number


def _validate_positive_number(
    value: Any,
    field_name: str,
) -> float:
    number = _validate_finite_number(
        value,
        field_name,
    )

    if number <= 0:
        raise ValueError(
            f"{field_name} must be greater than zero."
        )

    return number


def _validate_weights(config: PipelineConfig) -> None:
    ranking_weights = []
    integrity_weights = []

    for field_name in _WEIGHT_FIELDS:
        value = _validate_finite_number(
            getattr(config, field_name),
            field_name,
        )

        if value < 0:
            raise ValueError(
                f"{field_name} must be non-negative."
            )

        if field_name in DEFAULT_RANKING_WEIGHTS:
            ranking_weights.append(value)
        else:
            integrity_weights.append(value)

    if sum(ranking_weights) <= 0:
        raise ValueError(
            "At least one ranking weight must be positive."
        )

    if sum(integrity_weights) <= 0:
        raise ValueError(
            "At least one integrity component weight "
            "must be positive."
        )


def _validate_required_products(
    products: Any,
) -> tuple[str, ...]:
    if isinstance(products, (str, bytes)):
        raise TypeError(
            "required_products must be an iterable of product codes."
        )

    if not isinstance(products, (list, tuple)):
        raise TypeError(
            "required_products must be a list or tuple."
        )

    normalized = []

    for product in products:
        if not isinstance(product, str):
            raise TypeError(
                "Every required product code must be a string."
            )

        code = product.strip().upper()

        if code:
            normalized.append(code)

    if not normalized:
        raise ValueError(
            "At least one required product code must be provided."
        )

    # Preserve the first occurrence and the supplied order.
    return tuple(dict.fromkeys(normalized))


def _build_config(
    config: PipelineConfig | Mapping[str, Any],
) -> PipelineConfig:
    if isinstance(config, PipelineConfig):
        return config

    if not isinstance(config, Mapping):
        raise TypeError(
            "config must be a PipelineConfig or mapping."
        )

    unknown_keys = set(config) - _ALLOWED_CONFIG_KEYS

    if unknown_keys:
        unknown = ", ".join(
            sorted(str(key) for key in unknown_keys)
        )
        raise ValueError(
            f"Unknown pipeline configuration keys: {unknown}."
        )

    if "input_dir" not in config:
        raise ValueError(
            "input_dir is required."
        )

    values = dict(config)

    if "required_products" in values:
        values["required_products"] = _validate_required_products(
            values["required_products"]
        )

    return PipelineConfig(**values)


def validate_pipeline_config(
    config: PipelineConfig | Mapping[str, Any],
) -> PipelineConfig:
    """Validate and normalize a pipeline configuration.

    Args:
        config:
            A PipelineConfig instance or mapping containing its fields.

    Returns:
        A validated PipelineConfig with an absolute input directory.

    Raises:
        TypeError:
            If a configuration value has an unsupported type.
        ValueError:
            If a configuration value is invalid.
        FileNotFoundError:
            If the input directory does not exist.
        NotADirectoryError:
            If the input path is not a directory.

    This function does not create directories or modify input data.
    """
    validated = _build_config(config)

    # Input directory validation.
    if not isinstance(validated.input_dir, (str, Path)):
        raise TypeError(
            "input_dir must be a string or pathlib.Path."
        )

    if not str(validated.input_dir).strip():
        raise ValueError(
            "input_dir must not be empty."
        )

    input_dir = Path(
        validated.input_dir
    ).expanduser().resolve()

    if not input_dir.exists():
        raise FileNotFoundError(
            f"Input directory does not exist: {input_dir}"
        )

    if not input_dir.is_dir():
        raise NotADirectoryError(
            f"Input path is not a directory: {input_dir}"
        )

    # SOL range.
    _validate_sol_range(
        validated.start_sol,
        validated.end_sol,
    )

    # Coverage and synchronization parameters.
    gap_factor = _validate_positive_number(
        validated.gap_factor,
        "gap_factor",
    )

    tolerance = _validate_positive_number(
        validated.tolerance,
        "tolerance",
    )

    # Ranking parameters.
    if (
        isinstance(validated.window_size, bool)
        or not isinstance(validated.window_size, int)
    ):
        raise TypeError(
            "window_size must be an integer."
        )

    if validated.window_size < 1:
        raise ValueError(
            "window_size must be at least 1."
        )

    min_sol_fraction = _validate_finite_number(
        validated.min_sol_fraction,
        "min_sol_fraction",
    )

    if not 0 < min_sol_fraction <= 1:
        raise ValueError(
            "min_sol_fraction must be greater than 0 "
            "and at most 1."
        )

    if (
        isinstance(validated.min_metrics, bool)
        or not isinstance(validated.min_metrics, int)
    ):
        raise TypeError(
            "min_metrics must be an integer."
        )

    if not 1 <= validated.min_metrics <= 4:
        raise ValueError(
            "min_metrics must be between 1 and 4."
        )

    # Product configuration.
    required_products = _validate_required_products(
        validated.required_products
    )

    # Ranking and integrity weights.
    _validate_weights(validated)

    return PipelineConfig(
        input_dir=input_dir,
        start_sol=validated.start_sol,
        end_sol=validated.end_sol,
        gap_factor=gap_factor,
        tolerance=tolerance,
        window_size=validated.window_size,
        min_sol_fraction=min_sol_fraction,
        min_metrics=validated.min_metrics,
        required_products=required_products,
        weight_files=float(validated.weight_files),
        weight_integrity=float(validated.weight_integrity),
        weight_quality=float(validated.weight_quality),
        weight_sync=float(validated.weight_sync),
        integrity_timestamps=float(
            validated.integrity_timestamps
        ),
        integrity_values=float(
            validated.integrity_values
        ),
    )