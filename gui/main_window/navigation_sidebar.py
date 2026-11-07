
"""Navigation sidebar for the MDRPA main window."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


__all__ = ["NavigationSidebar"]


class NavigationSidebar(QFrame):
    """Provide exclusive navigation buttons for the main application pages."""

    page_selected = Signal(str)

    PAGES = (
        ("home", "Overview"),
        ("input", "Input Data"),
        ("analysis", "Analysis"),
        ("dashboard", "Dashboard"),
        ("reports", "Reports"),
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setObjectName("navigation_sidebar")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedWidth(190)

        self._buttons: dict[str, QPushButton] = {}
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(6)

        for index, (page_key, label) in enumerate(self.PAGES):
            button = QPushButton(label, self)
            button.setObjectName(f"navigation_{page_key}")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, key=page_key:
                    self.page_selected.emit(key)
            )

            self._button_group.addButton(button, index)
            self._buttons[page_key] = button
            layout.addWidget(button)

        layout.addStretch(1)
        self._buttons["home"].setChecked(True)

    @property
    def page_keys(self) -> tuple[str, ...]:
        """Return the supported page identifiers."""
        return tuple(self._buttons)

    def button_for(self, page_key: str) -> QPushButton:
        """Return a navigation button by page identifier."""
        try:
            return self._buttons[page_key]
        except KeyError as exc:
            raise KeyError(f"Unknown navigation page: {page_key}") from exc

    def set_current_page(self, page_key: str) -> None:
        """Update the checked navigation button."""
        self.button_for(page_key).setChecked(True)
