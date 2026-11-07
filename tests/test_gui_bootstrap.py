
"""Tests for the initial GUI window and application bootstrap."""

from __future__ import annotations

import os
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication, QMainWindow, QMenuBar, QStatusBar

from application.app_config import AppConfig
from application.app_paths import AppPaths
from application.main import (
    create_application,
    create_main_window,
    main,
)
from application.version import (
    APP_NAME,
    APP_SHORT_NAME,
    ORGANIZATION_NAME,
)
from gui.main_window.main_window import MainWindow
from gui.main_window.menu_bar import MainMenuBar
from gui.main_window.status_bar import MainStatusBar


@pytest.fixture(scope="session")
def qapp():
    """Provide one QApplication for the GUI tests."""
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def app_config(tmp_path):
    """Provide isolated persistent settings for a test."""
    return AppConfig(
        AppPaths.from_root(tmp_path / "application-data")
    )


def test_create_application_sets_qt_identity(qapp):
    application = create_application([])

    assert application is qapp
    assert application.organizationName() == ORGANIZATION_NAME
    assert application.applicationName() == APP_SHORT_NAME
    assert application.applicationDisplayName() == APP_NAME


def test_create_main_window_uses_supplied_paths(tmp_path):
    paths = AppPaths.from_root(tmp_path / "application-data")

    window = create_main_window(paths)

    assert isinstance(window, MainWindow)
    assert paths.settings_file.is_file()

    window.close()


def test_create_main_window_resolves_system_paths(
    tmp_path,
    monkeypatch,
):
    paths = AppPaths.from_root(tmp_path / "system-data")

    monkeypatch.setattr(
        AppPaths,
        "from_system",
        classmethod(lambda cls: paths),
    )

    window = create_main_window()

    assert isinstance(window, MainWindow)
    assert paths.settings_file.is_file()

    window.close()


def test_main_window_requires_app_config(qapp):
    with pytest.raises(TypeError, match="AppConfig"):
        MainWindow(None)


def test_main_window_has_expected_identity_and_widgets(
    qapp,
    app_config,
):
    window = MainWindow(app_config)

    assert isinstance(window, QMainWindow)
    assert window.windowTitle() == APP_NAME
    assert window.objectName() == "main_window"

    assert isinstance(window.menuBar(), QMenuBar)
    assert isinstance(window.statusBar(), QStatusBar)

    assert window.centralWidget().objectName() == (
        "main_window_placeholder"
    )

    assert window.application_status_bar.currentMessage() == "Ready"

    window.close()


def test_main_window_uses_default_dimensions(
    qapp,
    app_config,
):
    window = MainWindow(app_config)

    assert window.width() == MainWindow.DEFAULT_WIDTH
    assert window.height() == MainWindow.DEFAULT_HEIGHT

    window.close()


def test_main_window_restores_saved_dimensions(
    qapp,
    app_config,
):
    app_config.set("window/width", 1280)
    app_config.set("window/height", 820)

    window = MainWindow(app_config)

    assert window.width() == 1280
    assert window.height() == 820

    window.close()


def test_main_window_replaces_dimensions_below_minimum(
    qapp,
    app_config,
):
    app_config.set("window/width", 300)
    app_config.set("window/height", 200)

    window = MainWindow(app_config)

    assert window.width() == MainWindow.DEFAULT_WIDTH
    assert window.height() == MainWindow.DEFAULT_HEIGHT

    window.close()


def test_main_window_saves_dimensions_when_closed(
    qapp,
    app_config,
):
    window = MainWindow(app_config)
    window.resize(920, 680)
    window.show()
    qapp.processEvents()

    window.close()
    qapp.processEvents()

    assert app_config.get("window/width", value_type=int) == 920
    assert app_config.get("window/height", value_type=int) == 680
    assert app_config.get("window/maximized", value_type=bool) is False


def test_main_window_saves_maximized_state(
    qapp,
    app_config,
):
    window = MainWindow(app_config)
    window.showMaximized()
    qapp.processEvents()

    window.close()
    qapp.processEvents()

    assert app_config.get("window/maximized", value_type=bool) is True


def test_menu_bar_requires_main_window(qapp):
    with pytest.raises(TypeError, match="QMainWindow"):
        MainMenuBar(None)


def test_menu_bar_exposes_file_exit_and_help_about_actions(
    qapp,
):
    window = QMainWindow()
    menu_bar = MainMenuBar(window)

    assert menu_bar.file_menu.title() == "&File"
    assert menu_bar.help_menu.title() == "&Help"

    assert menu_bar.exit_action.text() == "E&xit"
    assert menu_bar.exit_action.objectName() == "action_exit"

    assert menu_bar.about_action.text() == "&About"
    assert menu_bar.about_action.objectName() == "action_about"

    window.close()


def test_exit_action_closes_main_window(qapp):
    window = QMainWindow()
    menu_bar = MainMenuBar(window)
    close_mock = Mock()
    window.close = close_mock

    menu_bar.exit_action.trigger()

    close_mock.assert_called_once_with()

    window.close()


def test_status_bar_starts_with_ready_message(qapp):
    status_bar = MainStatusBar()

    assert status_bar.objectName() == "main_status_bar"
    assert status_bar.currentMessage() == "Ready"


def test_main_returns_application_exit_code(monkeypatch):
    fake_application = Mock()
    fake_application.exec.return_value = 17

    fake_window = Mock()

    monkeypatch.setattr(
        "application.main.create_application",
        lambda argv=None: fake_application,
    )
    monkeypatch.setattr(
        "application.main.create_main_window",
        lambda: fake_window,
    )

    result = main(["mdrpa"])

    assert result == 17
    fake_window.show.assert_called_once_with()
    fake_application.exec.assert_called_once_with()
