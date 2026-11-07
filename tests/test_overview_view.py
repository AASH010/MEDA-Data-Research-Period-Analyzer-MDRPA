
"""Tests for the project-level Overview page."""

from __future__ import annotations

import os
from datetime import timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication

from backend.run_manager.run_manager import RunManager
from gui.overview.overview_view import OverviewView


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def run_manager(tmp_path):
    return RunManager(tmp_path / "runs")


@pytest.fixture
def overview_view(qapp):
    view = OverviewView()
    yield view
    view.close()


def create_run(
    manager: RunManager,
    run_id: str,
    *,
    status: str = "PENDING",
):
    record = manager.create_run(
        run_id=run_id,
        start_sol=100,
        end_sol=110,
        input_source="MEDA test dataset",
        application_version="test",
    )

    if status == "RUNNING":
        return manager.start_run(record.run_id)

    if status == "COMPLETED":
        manager.start_run(record.run_id)
        return manager.complete_run(record.run_id)

    if status == "FAILED":
        manager.start_run(record.run_id)
        return manager.fail_run(
            record.run_id,
            failure_reason="Test failure",
        )

    if status == "CANCELLED":
        return manager.cancel_run(record.run_id)

    return record


def test_overview_starts_in_unavailable_state(overview_view):
    assert overview_view.run_manager is None
    assert "not connected" in (
        overview_view.status_label.text().lower()
    )
    assert overview_view.recent_runs_table.rowCount() == 0


def test_overview_accepts_run_manager(
    overview_view,
    run_manager,
):
    overview_view.set_run_manager(run_manager)

    assert overview_view.run_manager is run_manager
    assert overview_view.records == ()
    assert "no analysis runs" in (
        overview_view.status_label.text().lower()
    )


def test_overview_displays_run_statistics(
    overview_view,
    run_manager,
):
    create_run(run_manager, "overview-pending")
    create_run(
        run_manager,
        "overview-completed",
        status="COMPLETED",
    )
    create_run(
        run_manager,
        "overview-failed",
        status="FAILED",
    )
    create_run(
        run_manager,
        "overview-cancelled",
        status="CANCELLED",
    )

    overview_view.set_run_manager(run_manager)

    assert overview_view.stat_labels["PENDING"].text() == "1"
    assert overview_view.stat_labels["RUNNING"].text() == "0"
    assert overview_view.stat_labels["COMPLETED"].text() == "1"
    assert overview_view.stat_labels["FAILED"].text() == "1"
    assert overview_view.stat_labels["CANCELLED"].text() == "1"


def test_overview_displays_latest_run(
    overview_view,
    run_manager,
):
    older = create_run(run_manager, "overview-older")
    latest = create_run(
        run_manager,
        "overview-latest",
        status="COMPLETED",
    )

    latest.metadata.created_at = (
        older.metadata.created_at + timedelta(seconds=10)
    )

    overview_view.set_run_manager(run_manager)

    text = overview_view.latest_run_label.text()

    assert "overview-latest" in text
    assert "COMPLETED" in text
    assert "100" in text
    assert "110" in text


def test_overview_limits_recent_runs(
    overview_view,
    run_manager,
):
    for index in range(7):
        create_run(
            run_manager,
            f"overview-run-{index}",
        )

    overview_view.set_run_manager(run_manager)

    assert overview_view.recent_runs_table.rowCount() == (
        overview_view.RECENT_RUN_LIMIT
    )


def test_overview_refreshes_after_new_run(
    overview_view,
    run_manager,
):
    overview_view.set_run_manager(run_manager)

    assert overview_view.records == ()

    create_run(run_manager, "overview-new-run")
    overview_view.refresh_runs()

    assert len(overview_view.records) == 1
    assert overview_view.recent_runs_table.rowCount() == 1
    assert "overview-new-run" in (
        overview_view.latest_run_label.text()
    )


def test_overview_handles_run_manager_error(
    overview_view,
    run_manager,
    monkeypatch,
):
    create_run(run_manager, "overview-error-run")
    overview_view.set_run_manager(run_manager)

    def fail_list_runs():
        raise RuntimeError("Registry unavailable")

    monkeypatch.setattr(
        run_manager,
        "list_runs",
        fail_list_runs,
    )

    overview_view.refresh_runs()

    assert "Registry unavailable" in (
        overview_view.status_label.text()
    )
    assert overview_view.records == ()
    assert overview_view.recent_runs_table.rowCount() == 0


def test_overview_can_detach_run_manager(
    overview_view,
    run_manager,
):
    create_run(run_manager, "overview-detach-run")
    overview_view.set_run_manager(run_manager)

    overview_view.set_run_manager(None)

    assert overview_view.run_manager is None
    assert overview_view.records == ()
    assert overview_view.recent_runs_table.rowCount() == 0


def test_overview_quick_navigation_emits_page_key(
    overview_view,
):
    selected = []
    overview_view.navigation_requested.connect(selected.append)

    overview_view.dashboard_button.click()
    overview_view.reports_button.click()
    overview_view.input_button.click()
    overview_view.analysis_button.click()

    assert selected == [
        "dashboard",
        "reports",
        "input",
        "analysis",
    ]


def test_overview_rejects_invalid_run_manager(
    overview_view,
):
    with pytest.raises(TypeError, match="RunManager"):
        overview_view.set_run_manager("invalid")
