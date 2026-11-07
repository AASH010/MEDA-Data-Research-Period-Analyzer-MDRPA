
"""Tests for the MDRPA Analysis Center execution controls."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication

from gui.analysis.analysis_center_view import AnalysisCenterView


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def view(qapp):
    widget = AnalysisCenterView()

    yield widget

    widget.close()


def test_initial_state_disables_execution_controls(view):
    assert view.configuration_available is False
    assert view.execution_active is False
    assert view.start_button.isEnabled() is False
    assert view.cancel_button.isEnabled() is False


def test_valid_configuration_enables_start(view):
    view.set_configuration_available(True)

    assert view.start_button.isEnabled() is True
    assert view.cancel_button.isEnabled() is False
    assert "ready" in view.status_label.text().lower()


def test_start_button_emits_request(view):
    received = []

    view.start_requested.connect(
        lambda: received.append(True)
    )

    view.set_configuration_available(True)
    view.start_button.click()

    assert received == [True]


def test_cancel_button_emits_request_only_while_running(view):
    received = []

    view.cancel_requested.connect(
        lambda: received.append(True)
    )

    view.set_configuration_available(True)
    view.set_execution_starting()

    assert view.start_button.isEnabled() is False
    assert view.cancel_button.isEnabled() is False

    view.set_execution_started()

    assert view.cancel_button.isEnabled() is True

    view.cancel_button.click()

    assert received == [True]


def test_execution_start_locks_start_button(view):
    view.set_configuration_available(True)
    view.set_execution_starting()

    assert view.execution_active is True
    assert view.start_button.isEnabled() is False
    assert view.cancel_button.isEnabled() is False
    assert view.run_id_label.text() == "Pending"


def test_cancellation_request_disables_repeated_cancel(view):
    view.set_configuration_available(True)
    view.set_execution_starting()
    view.set_execution_started()

    view.set_cancellation_requested()

    assert view.cancel_button.isEnabled() is False
    assert "cancellation requested" in (
        view.status_label.text().lower()
    )


def test_execution_result_displays_run_information(view):
    class Result:
        run_id = "run-test-001"
        successful = True
        cancelled = False
        error = None

    view.set_configuration_available(True)
    view.set_execution_starting()
    view.set_execution_started()
    view.set_execution_result(Result())

    assert view.run_id_label.text() == "run-test-001"
    assert "successfully" in view.status_label.text().lower()

    # The thread is still considered active until cleanup completes.
    assert view.execution_active is True
    assert view.start_button.isEnabled() is False


def test_execution_ended_restores_start_button(view):
    view.set_configuration_available(True)
    view.set_execution_starting()
    view.set_execution_started()
    view.set_execution_ended()

    assert view.execution_active is False
    assert view.start_button.isEnabled() is True
    assert view.cancel_button.isEnabled() is False


def test_execution_ended_preserves_unexpected_error(view):
    view.set_configuration_available(True)
    view.set_execution_starting()

    view.show_error("Unexpected worker error")
    view.set_execution_ended()

    assert "Unexpected worker error" in view.status_label.text()
    assert view.start_button.isEnabled() is True


def test_configuration_can_be_invalidated(view):
    view.set_configuration_available(True)
    assert view.start_button.isEnabled() is True

    view.set_configuration_available(False)

    assert view.start_button.isEnabled() is False
