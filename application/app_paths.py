
"""Application-managed user data paths.

User data is stored in the operating system's application-data location,
not inside the source repository or application installation directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QStandardPaths


__all__ = ["AppPaths"]


@dataclass(frozen=True)
class AppPaths:
    """Resolved locations used for application-managed user data.

    The root directory is normally obtained from
    QStandardPaths.AppDataLocation.

    from_root() is provided for isolated tests and explicit deployments.
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
    def from_system(cls) -> "AppPaths":
        """Resolve the operating system's application-data location.

        The Qt application identity should be configured before calling
        this method so Qt can determine the correct application folder.
        """
        location = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )

        if not location:
            raise RuntimeError(
                "The operating system did not provide an "
                "application-data location."
            )

        return cls(Path(location))

    @classmethod
    def from_root(
        cls,
        root: str | Path,
    ) -> "AppPaths":
        """Create paths from an explicit root directory.

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
        """Directory reserved for application-level logs."""
        return self.app_data_dir / "logs"

    @property
    def settings_file(self) -> Path:
        """Persistent application settings file."""
        return self.settings_dir / "application.ini"

    def ensure_directories(self) -> None:
        """Create the application data directories when required."""
        for directory in (
            self.app_data_dir,
            self.runs_dir,
            self.settings_dir,
            self.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
