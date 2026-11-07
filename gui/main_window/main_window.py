
"""Basic main window for the MDRPA desktop application."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QMainWindow

from application.app_config import AppConfig
from application.version import APP_NAME
from gui.main_window.menu_bar import MainMenuBar
from gui.main_window.status_bar import MainStatusBar


__all__ = ["MainWindow"]


class MainWindow(QMainWindow):
    """Provide the initial application window and persistent window state."""

    DEFAULT_WIDTH = 1100
    DEFAULT_HEIGHT = 760
    MINIMUM_WIDTH = 640
    MINIMUM_HEIGHT = 480

    def __init__(
        self,
        config: AppConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)

        if not isinstance(config, AppConfig):
            raise TypeError("config must be an AppConfig instance.")

        self.config = config

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
        """Install a neutral placeholder until GUI modules are implemented."""
        placeholder = QLabel(
            "MDRPA is ready.\n"
            "Analysis screens will be added in a later phase.",
            self,
        )
        placeholder.setObjectName("main_window_placeholder")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.setCentralWidget(placeholder)

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
