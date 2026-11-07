
"""Persistent application preferences backed by Qt QSettings."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSettings

from application.app_paths import AppPaths


__all__ = ["AppConfig"]


DEFAULT_SETTINGS: dict[str, Any] = {
    "appearance/theme": "classic",
    "window/width": 1100,
    "window/height": 760,
    "window/maximized": False,
    "tutorial/completed": False,
}


class AppConfig:
    """Read and write persistent application preferences.

    Settings are stored in an INI file under AppPaths.settings_dir.
    This keeps application preferences separate from source files
    and analysis run output.
    """

    def __init__(self, paths: AppPaths) -> None:
        if not isinstance(paths, AppPaths):
            raise TypeError("paths must be an AppPaths instance.")

        self.paths = paths
        self.paths.ensure_directories()

        self._settings = QSettings(
            str(self.paths.settings_file),
            QSettings.Format.IniFormat,
        )

        self._initialize_defaults()

    @property
    def settings_file(self):
        """Return the path of the persistent settings file."""
        return self.paths.settings_file

    @property
    def status(self) -> QSettings.Status:
        """Return the current QSettings status."""
        return self._settings.status()

    def _initialize_defaults(self) -> None:
        """Write default values only when a key is not already present."""
        for key, value in DEFAULT_SETTINGS.items():
            if not self._settings.contains(key):
                self._settings.setValue(key, value)

        self._settings.sync()

        if self._settings.status() != QSettings.Status.NoError:
            raise OSError(
                f"Could not initialize application settings: "
                f"{self._settings.fileName()}"
            )

    @staticmethod
    def _validate_key(key: str) -> None:
        if not isinstance(key, str):
            raise TypeError("Setting key must be a string.")

        if not key.strip():
            raise ValueError("Setting key must not be empty.")

    def get(
        self,
        key: str,
        default: Any = None,
        value_type: type | None = None,
    ) -> Any:
        """Return a setting value, optionally converting it to a type."""
        self._validate_key(key)

        if value_type is None:
            return self._settings.value(key, default)

        return self._settings.value(
            key,
            default,
            value_type,
        )

    def set(self, key: str, value: Any) -> None:
        """Persist a setting value."""
        self._validate_key(key)

        self._settings.setValue(key, value)
        self._settings.sync()

        if self._settings.status() != QSettings.Status.NoError:
            raise OSError(
                f"Could not save application setting: {key}"
            )

    def contains(self, key: str) -> bool:
        """Return whether a setting key exists."""
        self._validate_key(key)
        return self._settings.contains(key)

    def remove(self, key: str) -> None:
        """Remove one setting key."""
        self._validate_key(key)

        self._settings.remove(key)
        self._settings.sync()

        if self._settings.status() != QSettings.Status.NoError:
            raise OSError(
                f"Could not remove application setting: {key}"
            )

    def reset(self) -> None:
        """Reset all preferences to the application defaults."""
        self._settings.clear()

        for key, value in DEFAULT_SETTINGS.items():
            self._settings.setValue(key, value)

        self._settings.sync()

        if self._settings.status() != QSettings.Status.NoError:
            raise OSError(
                "Could not reset application settings."
            )
