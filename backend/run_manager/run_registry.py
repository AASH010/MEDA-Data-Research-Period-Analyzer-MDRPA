"""In-memory registry for isolated MEDA analysis runs.

The registry keeps run records separate by run_id during application
execution. Persistent metadata is handled by run_metadata.py.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock

from backend.run_manager.run_metadata import RunMetadata
from backend.run_manager.run_paths import RunPaths
from backend.run_manager.run_status import RunStatus, validate_transition


__all__ = [
    "RunRecord",
    "RunRegistry",
]


@dataclass(frozen=True)
class RunRecord:
    """A registered run and its current lifecycle status."""

    run_id: str
    paths: RunPaths
    metadata: RunMetadata
    status: RunStatus = RunStatus.PENDING

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("run_id must be a non-empty string.")

        if not isinstance(self.paths, RunPaths):
            raise TypeError("paths must be a RunPaths instance.")

        if not isinstance(self.metadata, RunMetadata):
            raise TypeError("metadata must be a RunMetadata instance.")

        if self.paths.run_id != self.run_id:
            raise ValueError("Run ID does not match paths.run_id.")

        if self.metadata.run_id != self.run_id:
            raise ValueError("Run ID does not match metadata.run_id.")

        if not isinstance(self.status, RunStatus):
            raise TypeError("status must be a RunStatus instance.")


class RunRegistry:
    """Thread-safe in-memory registry of analysis runs."""

    def __init__(self) -> None:
        self._records: dict[str, RunRecord] = {}
        self._lock = RLock()

    def register(
        self,
        paths: RunPaths,
        metadata: RunMetadata,
        status: RunStatus | None = None,
    ) -> RunRecord:
        """Register a new or restored run.

        When status is omitted, the persisted status in RunMetadata
        is used. This allows restored runs to retain their lifecycle
        state instead of always defaulting to PENDING.

        Raises:
            TypeError: If supplied objects have unsupported types.
            ValueError: If identifiers do not match or are duplicated.
        """
        if not isinstance(paths, RunPaths):
            raise TypeError("paths must be a RunPaths instance.")

        if not isinstance(metadata, RunMetadata):
            raise TypeError("metadata must be a RunMetadata instance.")

        if status is None:
            try:
                resolved_status = RunStatus(metadata.status)
            except ValueError as exc:
                raise ValueError(
                    f"Metadata contains an unsupported run status: "
                    f"{metadata.status!r}."
                ) from exc
        else:
            if not isinstance(status, RunStatus):
                raise TypeError("status must be a RunStatus instance or None.")

            resolved_status = status

        if paths.run_id != metadata.run_id:
            raise ValueError(
                "paths.run_id and metadata.run_id must match."
            )

        record = RunRecord(
            run_id=paths.run_id,
            paths=paths,
            metadata=metadata,
            status=resolved_status,
        )

        with self._lock:
            if record.run_id in self._records:
                raise ValueError(
                    f"Run {record.run_id!r} is already registered."
                )

            self._records[record.run_id] = record

        return record

    def get(self, run_id: str) -> RunRecord:
        """Retrieve a registered run by its identifier."""
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string.")

        with self._lock:
            try:
                return self._records[run_id]
            except KeyError as exc:
                raise KeyError(
                    f"Run {run_id!r} is not registered."
                ) from exc

    def list_runs(self) -> tuple[RunRecord, ...]:
        """Return all registered runs in deterministic ID order."""
        with self._lock:
            return tuple(
                self._records[run_id]
                for run_id in sorted(self._records)
            )

    def update_status(
        self,
        run_id: str,
        target_status: RunStatus | str,
    ) -> RunRecord:
        """Validate and apply a lifecycle status transition."""
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string.")

        with self._lock:
            try:
                current_record = self._records[run_id]
            except KeyError as exc:
                raise KeyError(
                    f"Run {run_id!r} is not registered."
                ) from exc

            new_status = validate_transition(
                current_record.status,
                target_status,
            )

            updated_record = replace(
                current_record,
                status=new_status,
            )

            self._records[run_id] = updated_record

            return updated_record

    def __len__(self) -> int:
        """Return the number of registered runs."""
        with self._lock:
            return len(self._records)

    def __contains__(self, run_id: object) -> bool:
        """Check whether a run identifier is registered."""
        with self._lock:
            return run_id in self._records