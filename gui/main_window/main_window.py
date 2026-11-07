
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
from gui.analysis.analysis_configuration_view import (
    AnalysisConfigurationView,
)
from gui.input_manager.input_manager_view import InputManagerView
from gui.main_window.menu_bar import MainMenuBar
from gui.main_window.navigation_sidebar import NavigationSidebar
from gui.main_window.status_bar import MainStatusBar


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
            raise TypeError(
                "config must be an AppConfig instance."
            )

        self.config = config

        self._pages: dict[str, QWidget] = {}

        self._analysis_controller: AnalysisController | None = None

        self._input_manager_view: InputManagerView | None = None

        self._analysis_configuration_view: (
            AnalysisConfigurationView | None
        ) = None

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

        raise RuntimeError(
            "The current page is not registered."
        )

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

        self._connect_analysis_controller(controller)

    def _connect_analysis_controller(
        self,
        controller: AnalysisController,
    ) -> None:
        """Connect controller events to the application status bar."""
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

    # ------------------------------------------------------------------
    # Input Manager / Analysis Configuration integration
    # ------------------------------------------------------------------

    def _connect_input_manager(self) -> None:
        """Connect Input Manager validation events to configuration."""
        input_view = self._input_manager_view
        configuration_view = self._analysis_configuration_view

        if input_view is None or configuration_view is None:
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
        """
        Invalidate the analysis input whenever the selection changes.

        The Analysis Configuration page must not retain an old
        dataset path after the user selects or clears a directory.
        """
        configuration_view = self._analysis_configuration_view

        if configuration_view is not None:
            configuration_view.set_input_directory(None)

    def _handle_input_ready(
        self,
        directory: object,
    ) -> None:
        """
        Forward an input directory only after successful validation.

        The emitted path must match the Input Manager's current
        validated selection.
        """
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
            received_directory = (
                Path(directory).expanduser().resolve()
            )
            selected_directory = (
                Path(selected_directory).expanduser().resolve()
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return

        if received_directory != selected_directory:
            return

        configuration_view.set_input_directory(
            selected_directory
        )

    # ------------------------------------------------------------------
    # Application shutdown integration
    # ------------------------------------------------------------------

    def _handle_analysis_thread_finished(self) -> None:
        """Complete a pending window close after the worker stops."""
        if not self._shutdown_pending:
            return

        self._shutdown_pending = False
        self._allow_close = True

        self.close()

    # ------------------------------------------------------------------
    # Main window construction
    # ------------------------------------------------------------------

    def _build_menu_bar(self) -> None:
        """Create and install the application menu bar."""
        self.application_menu_bar = MainMenuBar(self)

        self.setMenuBar(
            self.application_menu_bar
        )

    def _build_status_bar(self) -> None:
        """Create and install the application status bar."""
        self.application_status_bar = MainStatusBar(self)

        self.setStatusBar(
            self.application_status_bar
        )

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

        layout.addWidget(
            self.navigation_sidebar
        )

        layout.addWidget(
            self.page_stack,
            1,
        )

        for page_key, page_title in self.PAGE_DEFINITIONS:

            if page_key == "input":
                page = InputManagerView(self.page_stack)

                self._input_manager_view = page

            elif page_key == "analysis":
                page = AnalysisConfigurationView(
                    self.page_stack
                )

                self._analysis_configuration_view = page

            else:
                page = self._create_placeholder_page(
                    page_key,
                    page_title,
                )

            # Preserve the page objectName contract used by navigation.
            page.setObjectName(
                f"page_{page_key}"
            )

            self._pages[page_key] = page

            self.page_stack.addWidget(page)

        self.setCentralWidget(central)

        # Initialize the home page without changing the initial Ready status.
        self.page_stack.setCurrentWidget(
            self._pages["home"]
        )

        self.navigation_sidebar.set_current_page(
            "home"
        )

    @staticmethod
    def _create_placeholder_page(
        page_key: str,
        page_title: str,
    ) -> QWidget:
        """Create a placeholder for a future GUI module."""
        page = QWidget()

        page.setObjectName(
            f"page_{page_key}"
        )

        layout = QVBoxLayout(page)
        layout.setContentsMargins(
            24,
            24,
            24,
            24,
        )

        title = QLabel(page_title)

        title.setObjectName(
            f"page_{page_key}_title"
        )

        title.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )

        description = QLabel(
            f"{page_title} interface will be implemented "
            "in a later development phase."
        )

        description.setObjectName(
            f"page_{page_key}_placeholder"
        )

        description.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addStretch(1)

        return page

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def navigate_to(
        self,
        page_key: str,
    ) -> None:
        """Select a page by its registered identifier."""
        if page_key not in self._pages:
            raise KeyError(
                f"Unknown application page: {page_key}"
            )

        page = self._pages[page_key]

        self.page_stack.setCurrentWidget(page)

        self.navigation_sidebar.set_current_page(
            page_key
        )

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

        self.resize(
            width,
            height,
        )

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

            self.config.set(
                "window/width",
                current_size.width(),
            )

            self.config.set(
                "window/height",
                current_size.height(),
            )

        self.config.set(
            "window/maximized",
            maximized,
        )

    # ------------------------------------------------------------------
    # Close event
    # ------------------------------------------------------------------

    def closeEvent(
        self,
        event: QCloseEvent,
    ) -> None:
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

    def _save_and_accept_close(
        self,
        event: QCloseEvent,
    ) -> None:
        """Save window preferences and accept the close event."""
        try:
            self._save_window_state()

        except OSError:
            self.application_status_bar.showMessage(
                "Warning: window settings could not be saved.",
                5000,
            )

        super().closeEvent(event)
