
"""Tests for the MDRPA navigation sidebar and main page stack."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication, QStackedWidget

from application.app_config import AppConfig
from application.app_paths import AppPaths
from gui.main_window.main_window import MainWindow
from gui.main_window.navigation_sidebar import NavigationSidebar


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def main_window(tmp_path, qapp):
    config = AppConfig(
        AppPaths.from_root(tmp_path / "application-data")
    )
    window = MainWindow(config)
    yield window
    window.close()


def test_sidebar_exposes_expected_pages(qapp):
    sidebar = NavigationSidebar()

    assert sidebar.page_keys == (
        "home",
        "input",
        "analysis",
        "dashboard",
        "reports",
    )

    sidebar.close()


def test_sidebar_buttons_have_expected_object_names(qapp):
    sidebar = NavigationSidebar()

    for page_key in sidebar.page_keys:
        button = sidebar.button_for(page_key)
        assert button.objectName() == f"navigation_{page_key}"
        assert button.isCheckable()

    sidebar.close()


def test_sidebar_emits_selected_page(qapp):
    sidebar = NavigationSidebar()
    selected = []
    sidebar.page_selected.connect(selected.append)

    sidebar.button_for("input").click()

    assert selected == ["input"]
    sidebar.close()


def test_sidebar_rejects_unknown_page(qapp):
    sidebar = NavigationSidebar()

    with pytest.raises(KeyError, match="Unknown navigation page"):
        sidebar.button_for("unknown")

    with pytest.raises(KeyError, match="Unknown navigation page"):
        sidebar.set_current_page("unknown")

    sidebar.close()


def test_main_window_builds_page_stack(main_window):
    assert isinstance(main_window.page_stack, QStackedWidget)
    assert main_window.page_stack.count() == 5
    assert main_window.current_page_key == "home"


@pytest.mark.parametrize(
    "page_key",
    ["home", "input", "analysis", "dashboard", "reports"],
)
def test_main_window_can_navigate_to_each_page(
    main_window,
    page_key,
):
    main_window.navigate_to(page_key)

    assert main_window.current_page_key == page_key
    assert main_window.page_stack.currentWidget().objectName() == (
        f"page_{page_key}"
    )
    assert main_window.navigation_sidebar.button_for(
        page_key
    ).isChecked()


def test_sidebar_click_changes_main_window_page(main_window):
    main_window.navigation_sidebar.button_for("dashboard").click()

    assert main_window.current_page_key == "dashboard"
    assert main_window.navigation_sidebar.button_for(
        "dashboard"
    ).isChecked()


def test_navigation_updates_status_bar(main_window):
    main_window.navigate_to("reports")

    assert main_window.application_status_bar.currentMessage() == (
        "Ready — Reports"
    )


def test_main_window_rejects_unknown_page(main_window):
    with pytest.raises(KeyError, match="Unknown application page"):
        main_window.navigate_to("unknown")


def test_navigation_does_not_create_duplicate_pages(main_window):
    initial_count = main_window.page_stack.count()

    main_window.navigate_to("input")
    main_window.navigate_to("analysis")
    main_window.navigate_to("home")

    assert main_window.page_stack.count() == initial_count
