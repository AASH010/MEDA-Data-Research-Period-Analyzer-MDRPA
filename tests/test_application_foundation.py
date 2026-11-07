
"""Tests for application version, paths, and persistent settings."""

from pathlib import Path

import pytest

from PySide6.QtCore import QSettings, QStandardPaths

from application.app_config import AppConfig, DEFAULT_SETTINGS
from application.app_paths import AppPaths
from application.version import (
    APP_NAME,
    APP_SHORT_NAME,
    APP_VERSION,
    ORGANIZATION_NAME,
    __version__,
)


def test_application_version_information_is_defined():
    assert APP_NAME
    assert APP_SHORT_NAME == "MDRPA"
    assert ORGANIZATION_NAME == "MDRPA"
    assert APP_VERSION == "0.1.0-dev"
    assert __version__ == APP_VERSION


def test_app_paths_from_root_resolves_expected_directories(tmp_path):
    paths = AppPaths.from_root(tmp_path / "mdrpa-data")

    assert paths.app_data_dir == (tmp_path / "mdrpa-data").resolve()
    assert paths.runs_dir == paths.app_data_dir / "runs"
    assert paths.settings_dir == paths.app_data_dir / "settings"
    assert paths.logs_dir == paths.app_data_dir / "logs"
    assert paths.settings_file == (
        paths.settings_dir / "application.ini"
    )


def test_app_paths_do_not_create_directories_automatically(tmp_path):
    root = tmp_path / "not-created"

    paths = AppPaths.from_root(root)

    assert not root.exists()

    paths.ensure_directories()

    assert paths.app_data_dir.is_dir()
    assert paths.runs_dir.is_dir()
    assert paths.settings_dir.is_dir()
    assert paths.logs_dir.is_dir()


def test_app_paths_ensure_directories_is_idempotent(tmp_path):
    paths = AppPaths.from_root(tmp_path / "app-data")

    paths.ensure_directories()
    paths.ensure_directories()

    assert paths.runs_dir.is_dir()
    assert paths.settings_dir.is_dir()
    assert paths.logs_dir.is_dir()


def test_app_paths_reject_invalid_root():
    with pytest.raises(TypeError, match="root"):
        AppPaths.from_root(None)

    with pytest.raises(ValueError, match="empty"):
        AppPaths.from_root("   ")


def test_app_paths_reject_non_path_app_data_dir():
    with pytest.raises(TypeError, match="app_data_dir"):
        AppPaths("invalid")


def test_app_paths_from_system_uses_qt_app_data_location(
    tmp_path,
    monkeypatch,
):
    expected = tmp_path / "system-app-data"

    monkeypatch.setattr(
        QStandardPaths,
        "writableLocation",
        lambda location: str(expected),
    )

    paths = AppPaths.from_system()

    assert paths.app_data_dir == expected.resolve()


def test_app_paths_from_system_rejects_empty_location(monkeypatch):
    monkeypatch.setattr(
        QStandardPaths,
        "writableLocation",
        lambda location: "",
    )

    with pytest.raises(RuntimeError, match="application-data location"):
        AppPaths.from_system()


def test_app_config_creates_settings_file_and_defaults(tmp_path):
    paths = AppPaths.from_root(tmp_path / "app-data")

    config = AppConfig(paths)

    assert config.settings_file == paths.settings_file
    assert config.settings_file.is_file()

    for key, expected_value in DEFAULT_SETTINGS.items():
        assert config.get(key) == expected_value


def test_app_config_persists_values_between_instances(tmp_path):
    paths = AppPaths.from_root(tmp_path / "app-data")

    first = AppConfig(paths)
    first.set("appearance/theme", "custom")
    first.set("window/width", 1280)

    second = AppConfig(paths)

    assert second.get("appearance/theme") == "custom"
    assert second.get("window/width", value_type=int) == 1280


def test_app_config_does_not_overwrite_existing_values_with_defaults(
    tmp_path,
):
    paths = AppPaths.from_root(tmp_path / "app-data")

    first = AppConfig(paths)
    first.set("appearance/theme", "dark")

    second = AppConfig(paths)

    assert second.get("appearance/theme") == "dark"


def test_app_config_supports_typed_values(tmp_path):
    config = AppConfig(
        AppPaths.from_root(tmp_path / "app-data")
    )

    config.set("custom/integer", "42")

    assert config.get(
        "custom/integer",
        value_type=int,
    ) == 42


def test_app_config_contains_and_remove(tmp_path):
    config = AppConfig(
        AppPaths.from_root(tmp_path / "app-data")
    )

    config.set("custom/value", "example")

    assert config.contains("custom/value") is True

    config.remove("custom/value")

    assert config.contains("custom/value") is False


def test_app_config_reset_restores_defaults(tmp_path):
    config = AppConfig(
        AppPaths.from_root(tmp_path / "app-data")
    )

    config.set("appearance/theme", "dark")
    config.set("custom/value", "temporary")

    config.reset()

    for key, expected_value in DEFAULT_SETTINGS.items():
        assert config.get(key) == expected_value

    assert config.contains("custom/value") is False


@pytest.mark.parametrize(
    "invalid_key",
    [
        "",
        "   ",
    ],
)
def test_app_config_rejects_empty_keys(tmp_path, invalid_key):
    config = AppConfig(
        AppPaths.from_root(tmp_path / "app-data")
    )

    with pytest.raises(ValueError, match="must not be empty"):
        config.get(invalid_key)


def test_app_config_rejects_non_string_keys(tmp_path):
    config = AppConfig(
        AppPaths.from_root(tmp_path / "app-data")
    )

    with pytest.raises(TypeError, match="must be a string"):
        config.get(123)


def test_app_config_rejects_invalid_paths_argument():
    with pytest.raises(TypeError, match="AppPaths"):
        AppConfig("not-app-paths")


def test_settings_file_is_an_ini_file(tmp_path):
    paths = AppPaths.from_root(tmp_path / "app-data")
    config = AppConfig(paths)

    settings = QSettings(
        str(config.settings_file),
        QSettings.Format.IniFormat,
    )

    assert settings.contains("appearance/theme")
    assert settings.value("appearance/theme") == "classic"
