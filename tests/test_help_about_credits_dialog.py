"""Tests for Help, About, and Credits dialogs."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QMainWindow,
)

from PySide6.QtWidgets import QApplication, QDialog, QMainWindow

from application.version import APP_NAME, APP_VERSION
from gui.dialogs.about_dialog import AboutDialog
from gui.dialogs.credits_dialog import CreditsDialog
from gui.dialogs.help_dialog import HelpDialog
from gui.main_window.menu_bar import MainMenuBar


@pytest.fixture(scope="session")
def qapp():
    """Provide one QApplication for the GUI tests."""
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


def test_help_dialog_builds_correctly(qapp):
    dialog = HelpDialog()

    assert isinstance(dialog, QDialog)
    assert dialog.objectName() == "help_dialog"
    assert dialog.windowTitle()
    assert dialog.help_browser is not None

    content = dialog.help_browser.toPlainText()

    assert "Overview" in content
    assert "Input Data" in content
    assert "Dashboard" in content
    assert "Reports" in content

    dialog.close()


def test_about_dialog_displays_application_identity(qapp):
    dialog = AboutDialog()

    assert isinstance(dialog, QDialog)
    assert dialog.objectName() == "about_dialog"
    assert dialog.windowTitle() == f"About {APP_NAME}"

    name_label = dialog.findChild(QLabel, "about_application_name")
    version_label = dialog.findChild(
        QLabel,
        "about_application_version",
    )

    assert name_label is not None
    assert version_label is not None
    assert APP_NAME in name_label.text()
    assert APP_VERSION in version_label.text()

    dialog.close()


def test_credits_dialog_displays_developer_information(qapp):
    dialog = CreditsDialog()

    assert isinstance(dialog, QDialog)
    assert dialog.objectName() == "credits_dialog"

    content = dialog.credits_browser.toHtml()

    assert "Abdelrahman El-Bahnasawi" in content
    assert "github.com/AASH010" in content
    assert "linkedin.com/in/abdelrahman-el-bahnasawi-7280653a8" in content
    assert "abdelrahmanelbahnasawi1@gmail.com" in content


def test_credits_dialog_contains_external_links(qapp):
    dialog = CreditsDialog()

    content = dialog.credits_browser.toHtml()

    assert 'href="https://github.com/AASH010"' in content
    assert (
        'href="https://www.linkedin.com/in/'
        'abdelrahman-el-bahnasawi-7280653a8/"'
    ) in content
    assert (
        'href="mailto:abdelrahmanelbahnasawi1@gmail.com"'
    ) in content

    assert dialog.credits_browser.openExternalLinks()

    dialog.close()


def test_menu_bar_exposes_help_about_and_credits_actions(qapp):
    window = QMainWindow()
    menu_bar = MainMenuBar(window)

    assert menu_bar.file_menu.title() == "&File"
    assert menu_bar.help_menu.title() == "&Help"

    assert menu_bar.exit_action.objectName() == "action_exit"

    assert menu_bar.help_action.text() == "&User Guide"
    assert menu_bar.help_action.objectName() == "action_help"

    assert menu_bar.about_action.text() == "&About"
    assert menu_bar.about_action.objectName() == "action_about"

    assert menu_bar.credits_action.text() == "&Credits"
    assert menu_bar.credits_action.objectName() == "action_credits"

    window.close()