

"""Application-managed user data paths.

User data is stored in the project's user_data directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


__all__ = ["AppPaths"]


@dataclass(frozen=True)
class AppPaths:
    """Resolved locations used for application-managed user data.

    The default root is:
        project_root/user_data

    from_root() remains available for isolated tests and
    explicit deployments.
    """

    app_data_dir: Path

    def __post_init__(self) -> None:
        if not isinstance(self.app_data_dir, Path):
            raise TypeError("app_data_dir must be a pathlib.Path.")

        object.__setattr__(
            self,
            "app_data_dir",
            self.app_data_dir.expanduser().resolve(),
        )

    @classmethod
    def from_project_root(
        cls,
        project_root: str | Path | None = None,
    ) -> "AppPaths":
        """Resolve user_data from the project root.

        When project_root is omitted, the repository root is resolved
        from this module's location, not from the current working
        directory.
        """
        if project_root is None:
            project_root = Path(__file__).resolve().parent.parent

        if not isinstance(project_root, (str, Path)):
            raise TypeError(
                "project_root must be a string or pathlib.Path."
            )

        if isinstance(project_root, str) and not project_root.strip():
            raise ValueError("project_root must not be empty.")

        return cls(Path(project_root) / "user_data")

    @classmethod
    def from_root(
        cls,
        root: str | Path,
    ) -> "AppPaths":
        """Create paths from an explicit user_data root.

        This method is useful for tests and controlled deployments.
        """
        if not isinstance(root, (str, Path)):
            raise TypeError("root must be a string or pathlib.Path.")

        if isinstance(root, str) and not root.strip():
            raise ValueError("root must not be empty.")

        return cls(Path(root))

    @property
    def runs_dir(self) -> Path:
        """Directory containing isolated analysis runs."""
        return self.app_data_dir / "runs"

    @property
    def settings_dir(self) -> Path:
        """Directory containing application preferences."""
        return self.app_data_dir / "settings"

    @property
    def logs_dir(self) -> Path:
        """Central directory containing application and Run logs."""
        return self.app_data_dir / "logs"

    @property
    def settings_file(self) -> Path:
        """Persistent application settings file."""
        return self.settings_dir / "user_settings.ini"

    def ensure_directories(self) -> None:
        """Create the user data directories when required."""
        for directory in (
            self.app_data_dir,
            self.runs_dir,
            self.settings_dir,
            self.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
