"""Unified manager for isolated MEDA analysis runs.

This module coordinates run paths, metadata persistence, lifecycle status,
and the in-memory registry. It does not execute analyzers, workers,
pipelines, or scientific calculations.
"""

from __future__ import annotations

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

    @property
    def _metadata_filename(self) -> str:
        return self.METADATA_FILENAME

    def _metadata_path(self, paths: RunPaths) -> Path:
        return paths.root_dir / self._metadata_filename

    def create_run(
        self,
        run_id: str,
        *,
        input_source: str | None = None,
        source_info: Mapping[str, Any] | None = None,
        settings: Mapping[str, Any] | None = None,
        application_version: str | None = None,
    ) -> RunRecord:
        """Create directories, persist metadata, and register a new run.

        A run starts in PENDING status. Existing run directories are never
        reused or overwritten.
        """
        self._validate_run_id(run_id)

        paths = RunPaths.create(
            run_id=run_id,
            runs_root=self.runs_root,
            create=True,
        )

        metadata = RunMetadata(
            run_id=run_id,
            input_source=input_source,
            source_info=dict(source_info or {}),
            settings=dict(settings or {}),
            application_version=application_version,
        )

        save_run_metadata(metadata, self._metadata_path(paths))

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
        except OSError:
            metadata.started_at = previous_started_at
            metadata.finished_at = previous_finished_at
            raise
        except (TypeError, ValueError):
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