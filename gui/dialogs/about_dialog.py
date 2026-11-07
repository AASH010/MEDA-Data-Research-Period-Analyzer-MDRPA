"""About dialog for the MEDA Data Research & Period Analyzer application."""

from __future__ import annotations



from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from application.version import APP_NAME, APP_VERSION


__all__ = ["AboutDialog"]


class AboutDialog(QDialog):
    """Display the application's identity and version information."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setObjectName("about_dialog")
        self.setWindowTitle(f"About {APP_NAME}")
        self.setMinimumWidth(440)
        self.setModal(True)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)

        title_label = QLabel(APP_NAME, self)
        title_label.setObjectName("about_application_name")
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            "font-size: 18px; font-weight: bold;"
        )

        version_label = QLabel(
            f"Version {APP_VERSION}",
            self,
        )
        version_label.setObjectName("about_application_version")

        description_label = QLabel(
            "A desktop application for researching, analyzing, "
            "and comparing observation periods using NASA MEDA data.",
            self,
        )
        description_label.setObjectName("about_description")
        description_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(version_label)
        layout.addWidget(description_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close,
            parent=self,
        )
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout.addWidget(buttons)