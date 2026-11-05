"""Unified manager for isolated MEDA analysis runs.

This module coordinates run paths, metadata persistence, lifecycle status,
and the in-memory registry. It does not execute analyzers, workers,
pipelines, or scientific calculations.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from backend.run_manager.run_metadata import (
    RunMetadata,
    load_run_metadata,
    save_run_metadata,
)
from backend.run_manager.run_paths import RunPaths
from backend.run_manager.run_registry import RunRecord, RunRegistry
from backend.run_manager.run_status import RunStatus, validate_transition


__all__ = ["RunManager"]


class RunManager:
    """Coordinate creation and lifecycle management of analysis runs."""

    METADATA_FILENAME = "metadata.json"

    RANGE_RUN_ID_PATTERN = re.compile(
        r"^run_range\((\d+)-(\d+)\)_(\d+)$"
    )

    def __init__(
        self,
        runs_root: str | Path = "runs",
        *,
        registry: RunRegistry | None = None,
    ) -> None:
        if registry is not None and not isinstance(registry, RunRegistry):
            raise TypeError("registry must be a RunRegistry instance.")

        self.runs_root = Path(runs_root).expanduser().resolve()
        self.registry = registry if registry is not None else RunRegistry()

    @staticmethod
    def _utc_now() -> datetime:
        """Return an aware UTC timestamp for an application run event."""
        return datetime.now(timezone.utc)

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string.")

    @staticmethod
    def _validate_sol_range(
        start_sol: int | None,
        end_sol: int | None,
    ) -> None:
        """Validate an optional, complete SOL range."""
        if start_sol is not None:
            if isinstance(start_sol, bool) or not isinstance(start_sol, int):
                raise TypeError(
                    "start_sol must be a non-negative integer or None."
                )

            if start_sol < 0:
                raise ValueError("start_sol must be non-negative.")

        if end_sol is not None:
            if isinstance(end_sol, bool) or not isinstance(end_sol, int):
                raise TypeError(
                    "end_sol must be a non-negative integer or None."
                )

            if end_sol < 0:
                raise ValueError("end_sol must be non-negative.")

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

    @property
    def _metadata_filename(self) -> str:
        return self.METADATA_FILENAME

    def _metadata_path(self, paths: RunPaths) -> Path:
        return paths.root_dir / self._metadata_filename

    def _next_range_sequence(
        self,
        start_sol: int,
        end_sol: int,
    ) -> int:
        """Find the next sequence number for an exact SOL range.

        Existing run directories are inspected so numbering continues
        across manager instances and application restarts.
        """
        if not self.runs_root.exists():
            return 1

        highest_sequence = 0

        for entry in self.runs_root.iterdir():
            if not entry.is_dir():
                continue

            match = self.RANGE_RUN_ID_PATTERN.fullmatch(entry.name)

            if match is None:
                continue

            existing_start = int(match.group(1))
            existing_end = int(match.group(2))
            existing_sequence = int(match.group(3))

            if (
                existing_start == start_sol
                and existing_end == end_sol
            ):
                highest_sequence = max(
                    highest_sequence,
                    existing_sequence,
                )

        return highest_sequence + 1

    def _create_range_run_paths(
        self,
        start_sol: int,
        end_sol: int,
    ) -> RunPaths:
        """Create a uniquely numbered run directory for a SOL range.

        Directory creation is atomic. If another process creates the
        same candidate first, the next sequence number is attempted.
        """
        sequence = self._next_range_sequence(
            start_sol,
            end_sol,
        )

        while True:
            run_id = (
                f"run_range({start_sol}-{end_sol})_{sequence:03d}"
            )

            try:
                return RunPaths.create(
                    run_id=run_id,
                    runs_root=self.runs_root,
                    create=True,
                )
            except FileExistsError:
                sequence += 1

    def create_run(
        self,
        run_id: str | None = None,
        *,
        start_sol: int | None = None,
        end_sol: int | None = None,
        input_source: str | None = None,
        source_info: Mapping[str, Any] | None = None,
        settings: Mapping[str, Any] | None = None,
        application_version: str | None = None,
    ) -> RunRecord:
        """Create directories, persist metadata, and register a new run.

        When run_id is provided, the supplied identifier is used directly.

        When run_id is omitted, start_sol and end_sol are required.
        A sequential identifier is generated independently for each
        exact SOL range, for example:

            run_range(107-250)_001
            run_range(107-250)_002
            run_range(150-300)_001

        A run starts in PENDING status. Existing run directories are
        never reused or overwritten.
        """
        self._validate_sol_range(start_sol, end_sol)

        if run_id is None:
            if start_sol is None or end_sol is None:
                raise ValueError(
                    "start_sol and end_sol are required when run_id "
                    "is not provided."
                )

            paths = self._create_range_run_paths(
                start_sol,
                end_sol,
            )
            resolved_run_id = paths.run_id

        else:
            self._validate_run_id(run_id)
            resolved_run_id = run_id

            paths = RunPaths.create(
                run_id=resolved_run_id,
                runs_root=self.runs_root,
                create=True,
            )

        metadata = RunMetadata(
            run_id=resolved_run_id,
            start_sol=start_sol,
            end_sol=end_sol,
            input_source=input_source,
            source_info=dict(source_info or {}),
            settings=dict(settings or {}),
            application_version=application_version,
        )

        try:
            save_run_metadata(
                metadata,
                self._metadata_path(paths),
            )
        except Exception:
            # Avoid leaving an incomplete run directory if metadata
            # cannot be persisted.
            if paths.root_dir.exists():
                import shutil

                shutil.rmtree(paths.root_dir)
            raise

        return self.registry.register(
            paths=paths,
            metadata=metadata,
            status=RunStatus.PENDING,
        )

    def get_run(self, run_id: str) -> RunRecord:
        """Retrieve one registered run."""
        return self.registry.get(run_id)

    def list_runs(self) -> tuple[RunRecord, ...]:
        """Return all registered runs in deterministic order."""
        return self.registry.list_runs()

    def update_status(
        self,
        run_id: str,
        target_status: RunStatus | str,
    ) -> RunRecord:
        """Apply a valid status transition and persist updated metadata."""
        record = self.registry.get(run_id)

        new_status = validate_transition(
            record.status,
            target_status,
        )

        now = self._utc_now()
        metadata = record.metadata

        previous_started_at = metadata.started_at
        previous_finished_at = metadata.finished_at

        if new_status is RunStatus.RUNNING:
            metadata.started_at = now

        if new_status in {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            metadata.finished_at = now

        try:
            save_run_metadata(
                metadata,
                self._metadata_path(record.paths),
            )
        except (OSError, TypeError, ValueError):
            metadata.started_at = previous_started_at
            metadata.finished_at = previous_finished_at
            raise

        return self.registry.update_status(
            run_id,
            new_status,
        )

    def start_run(self, run_id: str) -> RunRecord:
        """Move a pending run to RUNNING."""
        return self.update_status(run_id, RunStatus.RUNNING)

    def complete_run(self, run_id: str) -> RunRecord:
        """Move a running run to COMPLETED."""
        return self.update_status(run_id, RunStatus.COMPLETED)

    def fail_run(self, run_id: str) -> RunRecord:
        """Move a running run to FAILED."""
        return self.update_status(run_id, RunStatus.FAILED)

    def cancel_run(self, run_id: str) -> RunRecord:
        """Cancel a pending or running run."""
        return self.update_status(run_id, RunStatus.CANCELLED)

    def load_persisted_metadata(self, run_id: str) -> RunMetadata:
        """Load a run's metadata JSON from its registered directory."""
        record = self.registry.get(run_id)
        return load_run_metadata(self._metadata_path(record.paths))