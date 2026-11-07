
"""Main window for the MDRPA desktop application."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from application.analysis_controller import AnalysisController
from application.app_config import AppConfig
from application.version import APP_NAME
from backend.run_manager.run_manager import RunManager
from gui.analysis.analysis_center_view import AnalysisCenterView
from gui.analysis.analysis_configuration_view import (
    AnalysisConfigurationView,
)
from gui.dashboard.dashboard_view import DashboardView
from gui.input_manager.input_manager_view import InputManagerView
from gui.main_window.menu_bar import MainMenuBar
from gui.main_window.navigation_sidebar import NavigationSidebar
from gui.main_window.status_bar import MainStatusBar
from gui.overview.overview_view import OverviewView
from gui.reports.reports_view import ReportsView


__all__ = ["MainWindow"]


class MainWindow(QMainWindow):
    """Provide the application shell, navigation, and service ownership."""

    DEFAULT_WIDTH = 1100
    DEFAULT_HEIGHT = 760

    MINIMUM_WIDTH = 640
    MINIMUM_HEIGHT = 480

    PAGE_DEFINITIONS = (
        ("home", "Overview"),
        ("input", "Input Data"),
        ("analysis", "Analysis"),
        ("dashboard", "Dashboard"),
        ("reports", "Reports"),
    )

    def __init__(
        self,
        config: AppConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)

        if not isinstance(config, AppConfig):
            raise TypeError("config must be an AppConfig instance.")

        self.config = config

        self._pages: dict[str, QWidget] = {}
        self._analysis_controller: AnalysisController | None = None
        self._input_manager_view: InputManagerView | None = None
        self._analysis_configuration_view: (
            AnalysisConfigurationView | None
        ) = None
        self._analysis_center_view: AnalysisCenterView | None = None
        self._overview_view: OverviewView | None = None
        self._dashboard_view: DashboardView | None = None
        self._reports_view: ReportsView | None = None

        self._shutdown_pending = False
        self._allow_close = False

        self.setObjectName("main_window")
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(
            self.MINIMUM_WIDTH,
            self.MINIMUM_HEIGHT,
        )

        self._build_menu_bar()
        self._build_status_bar()
        self._build_central_widget()

        self._connect_input_manager()
        self._connect_analysis_center()
        self._restore_window_state()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def analysis_controller(self) -> AnalysisController | None:
        """Return the attached analysis controller."""
        return self._analysis_controller

    @property
    def input_manager_view(self) -> InputManagerView | None:
        """Return the Input Manager page."""
        return self._input_manager_view

    @property
    def analysis_configuration_view(
        self,
    ) -> AnalysisConfigurationView | None:
        """Return the Analysis Configuration page."""
        return self._analysis_configuration_view

    @property
    def analysis_center_view(self) -> AnalysisCenterView | None:
        """Return the Analysis Execution controls."""
        return self._analysis_center_view

    @property
    def overview_view(self) -> OverviewView | None:
        """Return the project-level Overview page."""
        return self._overview_view

    @property
    def dashboard_view(self) -> DashboardView | None:
        """Return the Dashboard page."""
        return self._dashboard_view

    @property
    def reports_view(self) -> ReportsView | None:
        """Return the Reports page."""
        return self._reports_view

    @property
    def selected_input_dir(self) -> Path | None:
        """Return the validated input directory, if available."""
        view = self._input_manager_view

        if view is None or not view.is_validated:
            return None

        return view.selected_input_dir

    @property
    def current_page_key(self) -> str:
        """Return the identifier of the currently displayed page."""
        current_page = self.page_stack.currentWidget()

        for page_key, page in self._pages.items():
            if page is current_page:
                return page_key

        raise RuntimeError("The current page is not registered.")

    # ------------------------------------------------------------------
    # Analysis controller integration
    # ------------------------------------------------------------------

    def attach_analysis_controller(
        self,
        controller: AnalysisController,
    ) -> None:
        """Attach the controller owned by this main window."""
        if not isinstance(controller, AnalysisController):
            raise TypeError(
                "controller must be an AnalysisController instance."
            )

        if controller.parent() is not self:
            raise ValueError(
                "analysis controller must have this MainWindow "
                "as its QObject parent."
            )

        if self._analysis_controller is not None:
            raise RuntimeError(
                "An analysis controller is already attached."
            )

        self._analysis_controller = controller

        pipeline = controller.pipeline
        run_manager = getattr(pipeline, "run_manager", None)

        if isinstance(run_manager, RunManager):
            if self._overview_view is not None:
                self._overview_view.set_run_manager(run_manager)

            if self._dashboard_view is not None:
                self._dashboard_view.set_run_manager(run_manager)

            if self._reports_view is not None:
                self._reports_view.set_run_manager(run_manager)

        self._connect_analysis_controller(controller)

    def _connect_analysis_controller(
        self,
        controller: AnalysisController,
    ) -> None:
        """Connect controller events to the status bar and execution UI."""
        controller.started.connect(
            self.application_status_bar.analysis_started
        )
        controller.stage_started.connect(
            self.application_status_bar.stage_started
        )
        controller.stage_completed.connect(
            self.application_status_bar.stage_completed
        )
        controller.progress_updated.connect(
            self.application_status_bar.update_progress
        )
        controller.warning_occurred.connect(
            self.application_status_bar.show_warning
        )
        controller.error_occurred.connect(
            self.application_status_bar.show_error
        )
        controller.finished.connect(
            self.application_status_bar.analysis_finished
        )
        controller.cancelled.connect(
            self.application_status_bar.analysis_cancelled
        )
        controller.thread_finished.connect(
            self._handle_analysis_thread_finished
        )
        controller.thread_finished.connect(
            self._refresh_overview
        )
        controller.thread_finished.connect(
            self._refresh_dashboard
        )
        controller.thread_finished.connect(
            self._refresh_reports
        )

        if self._analysis_center_view is not None:
            controller.started.connect(
                self._analysis_center_view.set_execution_started
            )
            controller.stage_started.connect(
                self._analysis_center_view.set_stage_started
            )
            controller.stage_completed.connect(
                self._analysis_center_view.set_stage_completed
            )
            controller.progress_updated.connect(
                self._analysis_center_view.set_progress
            )
            controller.warning_occurred.connect(
                self._analysis_center_view.show_warning
            )
            controller.error_occurred.connect(
                self._analysis_center_view.show_error
            )
            controller.finished.connect(
                self._analysis_center_view.set_execution_result
            )
            controller.cancelled.connect(
                self._analysis_center_view.set_cancellation_completed
            )
            controller.thread_finished.connect(
                self._analysis_center_view.set_execution_ended
            )

    def _refresh_overview(self) -> None:
        """Refresh project-level Run statistics."""
        if self._overview_view is not None:
            self._overview_view.refresh()

    def _refresh_dashboard(self) -> None:
        """Refresh persisted Run information after execution ends."""
        if self._dashboard_view is not None:
            self._dashboard_view.refresh_runs()

    def _refresh_reports(self) -> None:
        """Refresh persisted report artifacts after execution ends."""
        if self._reports_view is not None:
            self._reports_view.refresh_runs()

    # ------------------------------------------------------------------
    # Input Manager / Analysis Configuration integration
    # ------------------------------------------------------------------

    def _connect_input_manager(self) -> None:
        """Connect Input Manager validation events to configuration."""
        input_view = self._input_manager_view

        if input_view is None:
            return

        input_view.input_directory_changed.connect(
            self._handle_input_directory_changed
        )
        input_view.input_ready.connect(
            self._handle_input_ready
        )

    def _handle_input_directory_changed(
        self,
        _directory: object,
    ) -> None:
        """Invalidate any previously accepted analysis dataset."""
        configuration_view = self._analysis_configuration_view

        if configuration_view is not None:
            configuration_view.set_input_directory(None)

        if self._analysis_center_view is not None:
            self._analysis_center_view.set_configuration_available(False)

    def _handle_input_ready(
        self,
        directory: object,
    ) -> None:
        """Forward an input directory only after successful validation."""
        input_view = self._input_manager_view
        configuration_view = self._analysis_configuration_view

        if input_view is None or configuration_view is None:
            return

        if not input_view.is_validated:
            return

        if not isinstance(directory, (str, Path)):
            return

        selected_directory = input_view.selected_input_dir

        if selected_directory is None:
            return

        try:
            received_directory = Path(directory).expanduser().resolve()
            selected_directory = (
                Path(selected_directory).expanduser().resolve()
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return

        if received_directory != selected_directory:
            return

        configuration_view.set_input_directory(selected_directory)

        if self._analysis_center_view is not None:
            self._analysis_center_view.set_configuration_available(False)

    # ------------------------------------------------------------------
    # Analysis configuration / execution UI
    # ------------------------------------------------------------------

    def _connect_analysis_center(self) -> None:
        """Connect execution controls to the MainWindow handlers."""
        center = self._analysis_center_view
        configuration = self._analysis_configuration_view

        if center is None or configuration is None:
            return

        center.start_requested.connect(self._start_analysis)
        center.cancel_requested.connect(self._cancel_analysis)
        configuration.config_ready.connect(
            self._handle_configuration_ready
        )

    def _handle_configuration_ready(self, config: object) -> None:
        """Enable Start only for the currently validated Input Manager path."""
        center = self._analysis_center_view
        input_directory = self.selected_input_dir

        if center is None or input_directory is None:
            if center is not None:
                center.set_configuration_available(False)
            return

        config_directory = getattr(config, "input_dir", None)

        if config_directory is None:
            center.set_configuration_available(False)
            return

        try:
            config_path = Path(config_directory).expanduser().resolve()
            selected_path = Path(input_directory).expanduser().resolve()
        except (OSError, RuntimeError, TypeError, ValueError):
            center.set_configuration_available(False)
            return

        center.set_configuration_available(config_path == selected_path)

    def _start_analysis(self) -> None:
        """Validate the latest configuration and start background execution."""
        center = self._analysis_center_view
        configuration = self._analysis_configuration_view
        controller = self._analysis_controller
        input_directory = self.selected_input_dir

        if center is None or configuration is None:
            return

        if controller is None:
            center.set_start_error(
                "The AnalysisController has not been attached."
            )
            return

        if controller.is_active:
            center.set_start_error(
                "An analysis execution is already active."
            )
            return

        if input_directory is None:
            center.set_configuration_available(False)
            center.set_start_error(
                "Select and validate a dataset in Input Data first."
            )
            return

        # Revalidate at click time so edited controls cannot use stale config.
        if not configuration.validate_configuration():
            center.set_configuration_available(False)
            return

        config = configuration.validated_config

        if config is None:
            center.set_configuration_available(False)
            center.set_start_error(
                "The configuration did not produce a validated PipelineConfig."
            )
            return

        try:
            config_path = Path(config.input_dir).expanduser().resolve()
            selected_path = Path(input_directory).expanduser().resolve()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            center.set_configuration_available(False)
            center.set_start_error(str(exc))
            return

        if config_path != selected_path:
            center.set_configuration_available(False)
            center.set_start_error(
                "The configured dataset no longer matches the validated input."
            )
            return

        center.set_configuration_available(True)
        center.set_execution_starting()

        try:
            controller.start(config)
        except Exception as exc:
            center.set_start_error(f"{type(exc).__name__}: {exc}")
            center.set_execution_ended()

    def _cancel_analysis(self) -> None:
        """Request cooperative cancellation of the active analysis."""
        center = self._analysis_center_view
        controller = self._analysis_controller

        if center is None or controller is None:
            return

        if controller.request_cancel():
            center.set_cancellation_requested()

    # ------------------------------------------------------------------
    # Application shutdown integration
    # ------------------------------------------------------------------

    def _handle_analysis_thread_finished(self) -> None:
        """Complete a pending window close after the worker stops."""
        if self._shutdown_pending:
            self._shutdown_pending = False
            self._allow_close = True
            self.close()

    # ------------------------------------------------------------------
    # Main window construction
    # ------------------------------------------------------------------

    def _build_menu_bar(self) -> None:
        """Create and install the application menu bar."""
        self.application_menu_bar = MainMenuBar(self)
        self.setMenuBar(self.application_menu_bar)

    def _build_status_bar(self) -> None:
        """Create and install the application status bar."""
        self.application_status_bar = MainStatusBar(self)
        self.setStatusBar(self.application_status_bar)

    def _build_central_widget(self) -> None:
        """Build the navigation sidebar and stacked page container."""
        central = QWidget(self)
        central.setObjectName("main_window_placeholder")

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.navigation_sidebar = NavigationSidebar(central)
        self.navigation_sidebar.page_selected.connect(
            self.navigate_to
        )

        self.page_stack = QStackedWidget(central)
        self.page_stack.setObjectName("main_page_stack")

        layout.addWidget(self.navigation_sidebar)
        layout.addWidget(self.page_stack, 1)

        for page_key, page_title in self.PAGE_DEFINITIONS:
            if page_key == "home":
                page = OverviewView(self.page_stack)
                self._overview_view = page

                # Connect Overview quick-navigation actions to MainWindow.
                page.navigation_requested.connect(
                    self.navigate_to
                )

            elif page_key == "input":
                page = InputManagerView(self.page_stack)
                self._input_manager_view = page

            elif page_key == "analysis":
                page = AnalysisConfigurationView(self.page_stack)
                self._analysis_configuration_view = page

                # Keep AnalysisConfigurationView as the registered page.
                # The execution controls are embedded inside its layout.
                center_view = AnalysisCenterView(page)
                self._analysis_center_view = center_view

                page_layout = page.layout()
                if page_layout is None:
                    raise RuntimeError(
                        "AnalysisConfigurationView must provide a layout."
                    )

                # Its existing final stretch is preserved after the new widget.
                insert_index = max(0, page_layout.count() - 1)
                page_layout.insertWidget(insert_index, center_view)

            elif page_key == "dashboard":
                page = DashboardView(self.page_stack)
                self._dashboard_view = page

            elif page_key == "reports":
                page = ReportsView(parent=self.page_stack)
                self._reports_view = page

            else:
                page = self._create_placeholder_page(
                    page_key,
                    page_title,
                )

            # Preserve the page objectName contract used by navigation.
            page.setObjectName(f"page_{page_key}")

            self._pages[page_key] = page
            self.page_stack.addWidget(page)

        self.setCentralWidget(central)

        # Initialize home without changing the initial Ready status.
        self.page_stack.setCurrentWidget(self._pages["home"])
        self.navigation_sidebar.set_current_page("home")

    @staticmethod
    def _create_placeholder_page(
        page_key: str,
        page_title: str,
    ) -> QWidget:
        """Create a placeholder for a future GUI module."""
        page = QWidget()
        page.setObjectName(f"page_{page_key}")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel(page_title)
        title.setObjectName(f"page_{page_key}_title")
        title.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )

        description = QLabel(
            f"{page_title} interface will be implemented "
            "in a later development phase."
        )
        description.setObjectName(f"page_{page_key}_placeholder")
        description.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addStretch(1)

        return page

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def navigate_to(self, page_key: str) -> None:
        """Select a page by its registered identifier."""
        if page_key not in self._pages:
            raise KeyError(f"Unknown application page: {page_key}")

        self.page_stack.setCurrentWidget(self._pages[page_key])
        self.navigation_sidebar.set_current_page(page_key)

        if page_key == "home":
            self._refresh_overview()
        elif page_key == "dashboard":
            self._refresh_dashboard()
        elif page_key == "reports":
            self._refresh_reports()

        page_titles = dict(self.PAGE_DEFINITIONS)
        self.application_status_bar.showMessage(
            f"Ready — {page_titles[page_key]}"
        )

    # ------------------------------------------------------------------
    # Window settings
    # ------------------------------------------------------------------

    def _restore_window_state(self) -> None:
        """Restore saved dimensions and maximized state."""
        width = self.config.get(
            "window/width",
            self.DEFAULT_WIDTH,
            int,
        )
        height = self.config.get(
            "window/height",
            self.DEFAULT_HEIGHT,
            int,
        )
        maximized = self.config.get(
            "window/maximized",
            False,
            bool,
        )

        if width < self.MINIMUM_WIDTH:
            width = self.DEFAULT_WIDTH

        if height < self.MINIMUM_HEIGHT:
            height = self.DEFAULT_HEIGHT

        self.resize(width, height)

        if maximized:
            self.setWindowState(
                self.windowState()
                | Qt.WindowState.WindowMaximized
            )

    def _save_window_state(self) -> None:
        """Persist the current window dimensions and maximized state."""
        maximized = self.isMaximized()

        if not maximized:
            current_size = self.size()
            self.config.set("window/width", current_size.width())
            self.config.set("window/height", current_size.height())

        self.config.set("window/maximized", maximized)

    # ------------------------------------------------------------------
    # Close event
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        """Wait for active analysis to stop before closing the window."""
        if self._allow_close:
            self._save_and_accept_close(event)
            return

        controller = self._analysis_controller

        if controller is not None and controller.is_active:
            event.ignore()

            if not self._shutdown_pending:
                self._shutdown_pending = True
                self.application_status_bar.shutdown_pending()

                if controller.is_running:
                    controller.request_cancel()

            return

        self._save_and_accept_close(event)

    def _save_and_accept_close(self, event: QCloseEvent) -> None:
        """Save window preferences and accept the close event."""
        try:
            self._save_window_state()
        except OSError:
            self.application_status_bar.showMessage(
                "Warning: window settings could not be saved.",
                5000,
            )

        super().closeEvent(event)
