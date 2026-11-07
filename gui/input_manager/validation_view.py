"""Dataset validation result widget."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)


__all__ = ["ValidationView"]


class ValidationView(QWidget):
    """Display the result of the dataset structure check."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setObjectName("validation_view")
        self._build_ui()
        self.reset()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel("Dataset Validation")
        self.title_label.setObjectName("validation_title")

        self.status_label = QLabel()
        self.status_label.setObjectName("validation_status")
        self.status_label.setWordWrap(True)

        self.details_label = QLabel()
        self.details_label.setObjectName("validation_details")
        self.details_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.details_label)

    def reset(self) -> None:
        """Reset the displayed validation result."""
        self.status_label.setText(
            "Dataset has not been validated."
        )
        self.details_label.clear()

    def show_result(
        self,
        *,
        valid: bool,
        message: str,
        sol_count: int = 0,
        file_count: int = 0,
        warning_count: int = 0,
    ) -> None:
        """Display a dataset validation result."""
        self.status_label.setText(
            "Validation successful."
            if valid
            else "Validation failed."
        )

        self.details_label.setText(
            f"{message}\n"
            f"SOL directories: {sol_count}\n"
            f"Supported files: {file_count}\n"
            f"Discovery warnings: {warning_count}"
        )