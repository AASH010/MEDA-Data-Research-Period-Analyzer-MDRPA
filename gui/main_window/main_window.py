
"""Main window for the MDRPA desktop application."""

from __future__ import annotations

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

from application.app_config import AppConfig
from application.version import APP_NAME
from gui.main_window.menu_bar import MainMenuBar
from gui.main_window.navigation_sidebar import NavigationSidebar
from gui.main_window.status_bar import MainStatusBar


__all__ = ["MainWindow"]


class MainWindow(QMainWindow):
    """Provide the application shell, navigation, and persistent window state."""

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

        self.setObjectName("main_window")
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(
            self.MINIMUM_WIDTH,
            self.MINIMUM_HEIGHT,
        )

        self._build_menu_bar()
        self._build_status_bar()
        self._build_central_widget()
        self._restore_window_state()

    def _build_menu_bar(self) -> None:
        """Create and install the application menu bar."""
        self.application_menu_bar = MainMenuBar(self)
        self.setMenuBar(self.application_menu_bar)

    def _build_status_bar(self) -> None:
        """Create and install the application status bar."""
        self.application_status_bar = MainStatusBar(self)
        self.setStatusBar(self.application_status_bar)

    def _build_central_widget(self) -> None:
        """Build the sidebar and stacked page container."""
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
            page = self._create_placeholder_page(
                page_key,
                page_title,
            )
            self._pages[page_key] = page
            self.page_stack.addWidget(page)

        self.setCentralWidget(central)

        # Initialize the first page without changing the initial Ready status.
        self.page_stack.setCurrentWidget(self._pages["home"])
        self.navigation_sidebar.set_current_page("home")

    @staticmethod
    def _create_placeholder_page(
        page_key: str,
        page_title: str,
    ) -> QWidget:
        """Create a neutral placeholder for a future GUI module."""
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
        description.setObjectName(
            f"page_{page_key}_placeholder"
        )
        description.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addStretch(1)

        return page

    def navigate_to(self, page_key: str) -> None:
        """Select a page by its registered identifier."""
        if page_key not in self._pages:
            raise KeyError(f"Unknown application page: {page_key}")

        page = self._pages[page_key]
        self.page_stack.setCurrentWidget(page)
        self.navigation_sidebar.set_current_page(page_key)
        self.application_status_bar.showMessage(
            f"Ready — {dict(self.PAGE_DEFINITIONS)[page_key]}"
        )

    @property
    def current_page_key(self) -> str:
        """Return the identifier of the currently displayed page."""
        current_page = self.page_stack.currentWidget()

        for page_key, page in self._pages.items():
            if page is current_page:
                return page_key

        raise RuntimeError("The current page is not registered.")

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

    def closeEvent(self, event: QCloseEvent) -> None:
        """Save window preferences before closing."""
        try:
            self._save_window_state()
        except OSError:
            self.application_status_bar.showMessage(
                "Warning: window settings could not be saved.",
                5000,
            )

        super().closeEvent(event)
