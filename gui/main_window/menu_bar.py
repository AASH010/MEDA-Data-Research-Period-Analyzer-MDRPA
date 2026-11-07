
"""Main application menu bar."""

from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMenuBar, QMessageBox

from application.version import APP_NAME, APP_VERSION


__all__ = ["MainMenuBar"]


class MainMenuBar(QMenuBar):
    """Provide the basic File and Help menus for the main window."""

    def __init__(
        self,
        main_window: QMainWindow,
    ) -> None:
        if not isinstance(main_window, QMainWindow):
            raise TypeError("main_window must be a QMainWindow instance.")

        super().__init__(main_window)

        self.main_window = main_window

        self.file_menu = self.addMenu("&File")
        self.help_menu = self.addMenu("&Help")

        self.exit_action = QAction("E&xit", self)
        self.exit_action.setObjectName("action_exit")
        self.exit_action.setStatusTip("Close the application.")
        self.exit_action.triggered.connect(
            lambda checked=False: self.main_window.close()
        )
        self.file_menu.addAction(self.exit_action)

        self.about_action = QAction("&About", self)
        self.about_action.setObjectName("action_about")
        self.about_action.setStatusTip("Show application information.")
        self.about_action.triggered.connect(self._show_about)
        self.help_menu.addAction(self.about_action)

    def _show_about(self) -> None:
        """Display basic application identity information."""
        QMessageBox.about(
            self.main_window,
            f"About {APP_NAME}",
            f"{APP_NAME}\nVersion {APP_VERSION}",
        )
