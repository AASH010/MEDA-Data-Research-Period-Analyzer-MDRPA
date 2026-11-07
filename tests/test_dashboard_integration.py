
"""Integration tests for Dashboard and application composition."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication

from application.analysis_controller import AnalysisController
from application.app_config import AppConfig
from application.app_paths import AppPaths
from backend.pipeline.analysis_pipeline import AnalysisPipeline
from backend.run_manager.run_manager import RunManager
from gui.dashboard.dashboard_view import DashboardView
from gui.main_window.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def application_paths(tmp_path):
    return AppPaths.from_root(
        tmp_path / "application-data"
    )


@pytest.fixture
def main_window(qapp, application_paths):
    window = MainWindow(
        AppConfig(application_paths)
    )

    run_manager = RunManager(
        application_paths.runs_dir
    )
    pipeline = AnalysisPipeline(run_manager)

    controller = AnalysisController(
        pipeline,
        parent=window,
    )

    window.attach_analysis_controller(controller)

    yield window

    window.close()


def test_dashboard_is_registered_as_dashboard_page(main_window):
    dashboard = main_window.dashboard_view

    assert isinstance(dashboard, DashboardView)
    assert main_window.page_stack.widget(
        main_window.page_stack.indexOf(dashboard)
    ) is dashboard

    assert dashboard.objectName() == "page_dashboard"


def test_dashboard_uses_application_run_manager(main_window):
    expected_manager = (
        main_window.analysis_controller.pipeline.run_manager
    )

    assert main_window.dashboard_view.run_manager is expected_manager


def test_dashboard_loads_runs_when_page_is_opened(main_window):
    manager = main_window.analysis_controller.pipeline.run_manager

    record = manager.create_run(
        run_id="dashboard-integration-run",
        start_sol=100,
        end_sol=105,
    )

    manager.start_run(record.run_id)
    manager.complete_run(record.run_id)

    main_window.navigate_to("dashboard")

    dashboard = main_window.dashboard_view

    assert main_window.current_page_key == "dashboard"
    assert dashboard.run_table.rowCount() == 1
    assert dashboard.selected_run_id == record.run_id


def test_dashboard_refreshes_when_reopened(main_window):
    manager = main_window.analysis_controller.pipeline.run_manager

    main_window.navigate_to("dashboard")

    assert main_window.dashboard_view.run_table.rowCount() == 0

    manager.create_run(
        run_id="dashboard-refresh-run",
        start_sol=200,
        end_sol=210,
    )

    main_window.navigate_to("home")
    main_window.navigate_to("dashboard")

    assert main_window.dashboard_view.run_table.rowCount() == 1
    assert (
        main_window.dashboard_view.run_table.item(0, 0).text()
        == "dashboard-refresh-run"
    )


def test_dashboard_refreshes_after_controller_thread_finished(
    main_window,
):
    manager = main_window.analysis_controller.pipeline.run_manager
    dashboard = main_window.dashboard_view

    main_window.navigate_to("dashboard")

    assert dashboard.run_table.rowCount() == 0

    manager.create_run(
        run_id="dashboard-thread-finished-run",
        start_sol=300,
        end_sol=305,
    )

    main_window.analysis_controller.thread_finished.emit()

    assert dashboard.run_table.rowCount() == 1
    assert dashboard.run_table.item(0, 0).text() == (
        "dashboard-thread-finished-run"
    )


def test_dashboard_navigation_preserves_existing_pages(main_window):
    expected_pages = (
        "home",
        "input",
        "analysis",
        "dashboard",
        "reports",
    )

    assert main_window.navigation_sidebar.page_keys == expected_pages
    assert main_window.page_stack.count() == len(expected_pages)

    for page_key in expected_pages:
        main_window.navigate_to(page_key)
        assert main_window.current_page_key == page_key


def test_dashboard_does_not_start_analysis(main_window):
    controller = main_window.analysis_controller

    main_window.navigate_to("dashboard")

    assert controller.is_active is False
    assert controller.is_running is False
