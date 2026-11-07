
"""Tests for MDRPA application service composition."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication

from application.analysis_controller import AnalysisController
from application.app_paths import AppPaths
from application.main import create_main_window
from backend.pipeline.analysis_pipeline import AnalysisPipeline
from backend.run_manager.run_manager import RunManager
from gui.main_window.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    """Provide one QApplication for composition tests."""
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def application_paths(tmp_path):
    """Provide isolated application data paths."""
    return AppPaths.from_root(
        tmp_path / "application-data"
    )


@pytest.fixture
def main_window(qapp, application_paths):
    """Create a fully composed main window."""
    window = create_main_window(application_paths)

    yield window

    window.close()


def test_create_main_window_attaches_analysis_controller(
    main_window,
):
    assert isinstance(
        main_window.analysis_controller,
        AnalysisController,
    )


def test_controller_is_owned_by_main_window(main_window):
    assert main_window.analysis_controller.parent() is main_window


def test_controller_uses_analysis_pipeline(main_window):
    pipeline = main_window.analysis_controller.pipeline

    assert isinstance(pipeline, AnalysisPipeline)


def test_pipeline_uses_run_manager(main_window):
    run_manager = (
        main_window.analysis_controller.pipeline.run_manager
    )

    assert isinstance(run_manager, RunManager)


def test_run_manager_uses_application_runs_directory(
    main_window,
    application_paths,
):
    run_manager = (
        main_window.analysis_controller.pipeline.run_manager
    )

    assert run_manager.runs_root == application_paths.runs_dir.resolve()


def test_application_runs_directory_is_separate_from_source_root(
    application_paths,
):
    assert application_paths.runs_dir != application_paths.app_data_dir
    assert application_paths.runs_dir.name == "runs"


def test_main_window_rejects_controller_with_wrong_parent(
    qapp,
    application_paths,
):
    from application.app_config import AppConfig

    window = MainWindow(AppConfig(application_paths))
    pipeline = AnalysisPipeline(
        RunManager(application_paths.runs_dir)
    )
    controller = AnalysisController(pipeline)

    with pytest.raises(ValueError, match="QObject parent"):
        window.attach_analysis_controller(controller)

    controller.deleteLater()
    window.close()


def test_main_window_rejects_duplicate_controller_attachment(
    qapp,
    application_paths,
):
    from application.app_config import AppConfig

    window = MainWindow(AppConfig(application_paths))
    pipeline = AnalysisPipeline(
        RunManager(application_paths.runs_dir)
    )
    controller = AnalysisController(
        pipeline,
        parent=window,
    )

    window.attach_analysis_controller(controller)

    second_controller = AnalysisController(
        pipeline,
        parent=window,
    )

    with pytest.raises(RuntimeError, match="already attached"):
        window.attach_analysis_controller(second_controller)

    second_controller.deleteLater()
    window.close()


def test_controller_is_not_started_during_application_composition(
    main_window,
):
    controller = main_window.analysis_controller

    assert controller.is_active is False
    assert controller.is_running is False
