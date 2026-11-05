"""Metadata models and JSON persistence for isolated MEDA analysis runs.

This module stores run-level information only. It does not manage run
execution, status transitions, filesystem layout, or scientific analysis.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Union


__all__ = [
    "RunMetadata",
    "save_run_metadata",
    "load_run_metadata",
]


PathLike = Union[str, Path]


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _validate_datetime(
    value: datetime | None,
    field_name: str,
) -> None:
    """Ensure a timestamp is timezone-aware."""
    if value is None:
        return

    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime or None.")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{field_name} must be timezone-aware."
        )


def _parse_datetime(
    value: str | datetime | None,
    field_name: str,
) -> datetime | None:
    """Parse an ISO-8601 timestamp into a timezone-aware datetime."""
    if value is None:
        return None

    if isinstance(value, datetime):
        _validate_datetime(value, field_name)
        return value

    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be a non-empty ISO-8601 string."
        )

    try:
        parsed = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must contain a valid ISO-8601 timestamp."
        ) from exc

    _validate_datetime(parsed, field_name)
    return parsed


def _validate_sol_value(
    value: int | None,
    field_name: str,
) -> None:
    """Validate an optional non-negative integer SOL value."""
    if value is None:
        return

    # bool is a subclass of int, so reject it explicitly.
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
    """Validate that the optional SOL range is complete and ordered."""
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


def _validate_json_mapping(
    value: Mapping[str, Any],
    field_name: str,
) -> dict[str, Any]:
    """Validate and copy a mapping that will be stored in JSON."""
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")

    copied = dict(value)

    try:
        json.dumps(copied, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must contain JSON-compatible values."
        ) from exc

    return copied


@dataclass
class RunMetadata:
    """Descriptive metadata associated with one analysis run.

    Timestamps represent application run events, not MEDA observation
    timestamps or mission time coordinates.

    start_sol and end_sol describe the selected run range. They are
    metadata fields and do not perform any time conversion or analysis.
    """

    run_id: str
    start_sol: int | None = None
    end_sol: int | None = None
    created_at: datetime = field(default_factory=_utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    input_source: str | None = None
    source_info: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    application_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("run_id must be a non-empty string.")

        self.run_id = self.run_id.strip()

        _validate_sol_range(
            self.start_sol,
            self.end_sol,
        )

        _validate_datetime(self.created_at, "created_at")
        _validate_datetime(self.started_at, "started_at")
        _validate_datetime(self.finished_at, "finished_at")

        self.source_info = _validate_json_mapping(
            self.source_info,
            "source_info",
        )
        self.settings = _validate_json_mapping(
            self.settings,
            "settings",
        )

        if self.input_source is not None:
            if not isinstance(self.input_source, str):
                raise TypeError("input_source must be a string or None.")

        if self.application_version is not None:
            if not isinstance(self.application_version, str):
                raise TypeError(
                    "application_version must be a string or None."
                )

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata into a JSON-compatible dictionary."""
        return {
            "run_id": self.run_id,
            "start_sol": self.start_sol,
            "end_sol": self.end_sol,
            "created_at": self.created_at.isoformat(),
            "started_at": (
                self.started_at.isoformat()
                if self.started_at is not None
                else None
            ),
            "finished_at": (
                self.finished_at.isoformat()
                if self.finished_at is not None
                else None
            ),
            "input_source": self.input_source,
            "source_info": dict(self.source_info),
            "settings": dict(self.settings),
            "application_version": self.application_version,
        }

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
    ) -> "RunMetadata":
        """Create metadata from a dictionary.

        Unknown keys are ignored to allow compatible metadata extensions.
        Missing SOL range fields are treated as None for backward
        compatibility with metadata created by older versions.
        """
        if not isinstance(data, Mapping):
            raise TypeError("Metadata data must be a mapping.")

        if "run_id" not in data:
            raise ValueError("Metadata data is missing run_id.")

        return cls(
            run_id=data["run_id"],
            start_sol=data.get("start_sol"),
            end_sol=data.get("end_sol"),
            created_at=_parse_datetime(
                data.get("created_at", _utc_now()),
                "created_at",
            ),
            started_at=_parse_datetime(
                data.get("started_at"),
                "started_at",
            ),
            finished_at=_parse_datetime(
                data.get("finished_at"),
                "finished_at",
            ),
            input_source=data.get("input_source"),
            source_info=data.get("source_info", {}),
            settings=data.get("settings", {}),
            application_version=data.get("application_version"),
        )


def save_run_metadata(
    metadata: RunMetadata,
    file_path: PathLike,
) -> Path:
    """Save run metadata as formatted JSON.

    The destination parent directory is created when necessary.
    Returns the resolved path of the saved metadata file.
    """
    if not isinstance(metadata, RunMetadata):
        raise TypeError("metadata must be a RunMetadata instance.")

    destination = Path(file_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    content = json.dumps(
        metadata.to_dict(),
        indent=4,
        ensure_ascii=False,
        allow_nan=False,
    )

    temporary_path = destination.with_name(
        destination.name + ".tmp"
    )

    try:
        temporary_path.write_text(
            content + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(destination)
    except OSError:
        if temporary_path.exists():
            temporary_path.unlink()
        raise

    return destination


def load_run_metadata(file_path: PathLike) -> RunMetadata:
    """Load run metadata from a JSON file."""
    source = Path(file_path).expanduser()

    with source.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("Metadata JSON root must be an object.")

    return RunMetadata.from_dict(data)