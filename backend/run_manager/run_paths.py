
"""Path management for isolated MEDA analysis runs.

Each run receives its own directory containing input, output, and logs
subdirectories. This module only manages filesystem paths; it does not
copy source data or execute analysis tasks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Union


__all__ = [
    "RunPaths",
    "build_run_paths",
]


PathLike = Union[str, Path]

_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class RunPaths:
    """Filesystem locations belonging to one analysis run."""

    run_id: str
    root_dir: Path
    input_dir: Path
    output_dir: Path
    logs_dir: Path

    @classmethod
    def create(
        cls,
        run_id: str,
        runs_root: PathLike = "runs",
        *,
        create: bool = True,
    ) -> "RunPaths":
        """Build paths for a run and optionally create its directories.

        Args:
            run_id: Unique identifier for this run.
            runs_root: Parent directory containing all run directories.
            create: If True, create the run directory structure.

        Raises:
            ValueError: If the run ID is invalid.
            FileExistsError: If the run directory already exists.
            OSError: If the filesystem cannot create the directories.
        """
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_id must be a non-empty string.")

        if not _RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError(
                "run_id must start with a letter or number and contain "
                "only letters, numbers, dots, underscores, or hyphens."
            )

        root_dir = Path(runs_root).expanduser().resolve() / run_id

        paths = cls(
            run_id=run_id,
            root_dir=root_dir,
            input_dir=root_dir / "input",
            output_dir=root_dir / "output",
            logs_dir=root_dir / "logs",
        )

        if create:
            # Do not silently reuse an existing run directory.
            root_dir.mkdir(parents=True, exist_ok=False)

            paths.input_dir.mkdir()
            paths.output_dir.mkdir()
            paths.logs_dir.mkdir()

        return paths


def build_run_paths(
    run_id: str,
    runs_root: PathLike = "runs",
    *,
    create: bool = True,
) -> RunPaths:
    """Convenience function for building a run's directory structure."""
    return RunPaths.create(
        run_id=run_id,
        runs_root=runs_root,
        create=create,
    )
