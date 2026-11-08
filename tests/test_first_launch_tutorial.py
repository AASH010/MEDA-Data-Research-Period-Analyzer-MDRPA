
"""Tests for the first-launch tutorial and its integration."""

from __future__ import annotations

import os

from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication, QDialog, QMainWindow

from application.app_config import AppConfig
from application.app_paths import AppPaths
from gui.dialogs.tutorial_dialog import TutorialDialog
from gui.main_window.main_window import MainWindow
from gui.main_window.menu_bar import MainMenuBar


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def app_config(tmp_path):
    return AppConfig(
        AppPaths.from_root(tmp_path / "application-data")
    )


@pytest.fixture
def main_window(qapp, app_config):
    window = MainWindow(app_config)
    yield window
    window.close()


def test_tutorial_dialog_builds_initial_step(qapp):
    dialog = TutorialDialog()

    assert isinstance(dialog, QDialog)
    assert dialog.objectName() == "tutorial_dialog"
    assert dialog.current_step == 0
    assert dialog.step_count == 7
    assert dialog.step_label.text() == "Welcome to MDRPA"
    assert dialog.progress_label.text() == "Step 1 of 7"

    assert dialog.back_button.isEnabled() is False
    assert not dialog.next_button.isHidden()
    assert dialog.finish_button.isHidden()

    dialog.close()


def test_tutorial_navigation_moves_forward_and_backward(qapp):
    dialog = TutorialDialog()

    dialog.next_button.click()

    assert dialog.current_step == 1
    assert dialog.step_label.text() == "1. Overview"
    assert dialog.back_button.isEnabled()

    dialog.back_button.click()

    assert dialog.current_step == 0
    assert dialog.step_label.text() == "Welcome to MDRPA"

    dialog.close()


def test_tutorial_next_button_reaches_final_step(qapp):
    dialog = TutorialDialog()

    for _ in range(dialog.step_count - 1):
        dialog.next_button.click()

    assert dialog.current_step == dialog.step_count - 1
    assert dialog.step_label.text() == "You're ready to begin"
    assert dialog.next_button.isHidden()
    assert not dialog.finish_button.isHidden()

    dialog.close()


def test_tutorial_finish_emits_completion_and_accepts(qapp):
    dialog = TutorialDialog()
    completed = []

    dialog.completed.connect(lambda: completed.append(True))
    dialog.finish_button.click()

    assert completed == [True]
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_tutorial_skip_emits_skipped_and_accepts(qapp):
    dialog = TutorialDialog()
    skipped = []

    dialog.skipped.connect(lambda: skipped.append(True))
    dialog.skip_button.click()

    assert skipped == [True]
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_tutorial_completion_is_persisted(
    qapp,
    app_config,
    monkeypatch,
):
    window = MainWindow(app_config)

    def finish_dialog(dialog):
        dialog.completed.emit()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(TutorialDialog, "exec", finish_dialog)

    window.show_tutorial()

    assert app_config.get(
        "tutorial/completed",
        False,
        bool,
    ) is True

    window.close()


def test_tutorial_skip_is_persisted(
    qapp,
    app_config,
    monkeypatch,
):
    window = MainWindow(app_config)

    def skip_dialog(dialog):
        dialog.skipped.emit()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(TutorialDialog, "exec", skip_dialog)

    window.show_tutorial()

    assert app_config.get(
        "tutorial/completed",
        False,
        bool,
    ) is True

    window.close()


def test_first_launch_tutorial_is_shown_when_not_completed(
    main_window,
):
    main_window.show_tutorial = Mock()

    main_window.show_first_launch_tutorial()

    main_window.show_tutorial.assert_called_once_with()


def test_first_launch_tutorial_is_not_shown_after_completion(
    main_window,
    app_config,
):
    app_config.set("tutorial/completed", True)
    main_window.show_tutorial = Mock()

    main_window.show_first_launch_tutorial()

    main_window.show_tutorial.assert_not_called()


def test_tutorial_action_is_available_in_help_menu(
    qapp,
    main_window,
):
    menu_bar = main_window.application_menu_bar

    assert menu_bar.tutorial_action.text() == "&First-Launch Tutorial"
    assert menu_bar.tutorial_action.objectName() == "action_tutorial"

    show_mock = Mock()
    main_window.show_tutorial = show_mock

    menu_bar.tutorial_action.trigger()

    show_mock.assert_called_once_with()


def test_tutorial_setting_defaults_to_false(app_config):
    assert app_config.get(
        "tutorial/completed",
        value_type=bool,
    ) is False


def test_tutorial_setting_persists_between_config_instances(
    tmp_path,
):
    paths = AppPaths.from_root(tmp_path / "application-data")

    first = AppConfig(paths)
    first.set("tutorial/completed", True)

    second = AppConfig(paths)

    assert second.get(
        "tutorial/completed",
        False,
        bool,
    ) is True
def test_closing_tutorial_with_window_close_does_not_mark_it_completed(
    app_config,
):
    dialog = TutorialDialog()

    dialog.close()

    assert dialog.result() == QDialog.DialogCode.Rejected
    assert app_config.get("tutorial/completed", False, bool) is False