
"""Application entry point and composition root for MDRPA."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from application.analysis_controller import AnalysisController
from application.app_config import AppConfig
from application.app_paths import AppPaths
from application.version import (
    APP_NAME,
    APP_SHORT_NAME,
    ORGANIZATION_NAME,
)
from backend.pipeline.analysis_pipeline import AnalysisPipeline
from backend.run_manager.run_manager import RunManager
from gui.main_window.main_window import MainWindow


__all__ = [
    "create_application",
    "create_main_window",
    "main",
]


def create_application(
    argv: Sequence[str] | None = None,
) -> QApplication:
    """Create or retrieve QApplication and configure its identity."""
    application = QApplication.instance()

    if application is None:
        arguments = list(argv) if argv is not None else sys.argv
        application = QApplication(arguments)

    application.setOrganizationName(ORGANIZATION_NAME)
    application.setApplicationName(APP_SHORT_NAME)
    application.setApplicationDisplayName(APP_NAME)

    return application


def create_main_window(
    paths: AppPaths | None = None,
) -> MainWindow:
    """Compose application services and create the main window."""
    resolved_paths = (
        paths
        if paths is not None
        else AppPaths.from_system()
    )

    config = AppConfig(resolved_paths)
    window = MainWindow(config)

    run_manager = RunManager(
        runs_root=resolved_paths.runs_dir,
    )
    pipeline = AnalysisPipeline(run_manager)

    controller = AnalysisController(
        pipeline,
        parent=window,
    )

    window.attach_analysis_controller(controller)

    return window


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """Start the desktop application and return its exit code."""
    application = create_application(argv)

    # Qt application identity is configured before resolving AppDataLocation.
    window = create_main_window()
    window.show()

    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
