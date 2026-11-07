
"""Main application status bar."""

from PySide6.QtWidgets import QStatusBar


__all__ = ["MainStatusBar"]


class MainStatusBar(QStatusBar):
    """Status bar used by the main application window."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("main_status_bar")
        self.showMessage("Ready")
