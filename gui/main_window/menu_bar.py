"""Main application menu bar."""

from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMenuBar

from gui.dialogs.about_dialog import AboutDialog
from gui.dialogs.credits_dialog import CreditsDialog
from gui.dialogs.help_dialog import HelpDialog


__all__ = ["MainMenuBar"]


class MainMenuBar(QMenuBar):
    """Provide File and Help menus for the main application window."""

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

        self._create_file_actions()
        self._create_help_actions()

    def _create_file_actions(self) -> None:
        self.exit_action = QAction("E&xit", self)
        self.exit_action.setObjectName("action_exit")
        self.exit_action.setStatusTip("Close the application.")
        self.exit_action.triggered.connect(
            lambda checked=False: self.main_window.close()
        )

        self.file_menu.addAction(self.exit_action)

    def _create_help_actions(self) -> None:
        self.help_action = QAction("&User Guide", self)
        self.help_action.setObjectName("action_help")
        self.help_action.setStatusTip(
            "Open the application user guide."
        )
        self.help_action.triggered.connect(self._show_help)

        self.about_action = QAction("&About", self)
        self.about_action.setObjectName("action_about")
        self.about_action.setStatusTip(
            "Show application information."
        )
        self.about_action.triggered.connect(self._show_about)

        self.credits_action = QAction("&Credits", self)
        self.credits_action.setObjectName("action_credits")
        self.credits_action.setStatusTip(
            "Show project credits and acknowledgements."
        )
        self.credits_action.triggered.connect(self._show_credits)

        self.help_menu.addAction(self.help_action)
        self.help_menu.addSeparator()
        self.help_menu.addAction(self.about_action)
        self.help_menu.addAction(self.credits_action)

    def _show_help(self) -> None:
        """Display the user guide."""
        dialog = HelpDialog(self.main_window)
        dialog.exec()

    def _show_about(self) -> None:
        """Display application identity information."""
        dialog = AboutDialog(self.main_window)
        dialog.exec()

    def _show_credits(self) -> None:
        """Display project credits and acknowledgements."""
        dialog = CreditsDialog(self.main_window)
        dialog.exec()