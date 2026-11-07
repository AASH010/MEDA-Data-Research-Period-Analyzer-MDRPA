"""Dataset directory and discovered-file preview widget."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


__all__ = ["FilePreviewView"]


class FilePreviewView(QWidget):
    """Display a lightweight preview of the selected dataset."""

    MAX_VISIBLE_ITEMS = 250

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setObjectName("file_preview_view")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel("Dataset Preview")
        self.title_label.setObjectName("file_preview_title")

        self.summary_label = QLabel(
            "No dataset directory selected."
        )
        self.summary_label.setObjectName("file_preview_summary")
        self.summary_label.setWordWrap(True)

        self.tree = QTreeWidget(self)
        self.tree.setObjectName("file_preview_tree")
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Name", "Details"])
        self.tree.setRootIsDecorated(False)

        layout.addWidget(self.title_label)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.tree, 1)

    def clear(self) -> None:
        """Clear all preview information."""
        self.summary_label.setText(
            "No dataset directory selected."
        )
        self.tree.clear()

    def set_directory(self, directory: Path) -> None:
        """Show immediate entries in the selected directory."""
        self.tree.clear()

        if not directory.exists():
            self.summary_label.setText(
                "The selected directory does not exist."
            )
            return

        if not directory.is_dir():
            self.summary_label.setText(
                "The selected path is not a directory."
            )
            return

        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda item: (
                    not item.is_dir(),
                    item.name.casefold(),
                ),
            )
        except OSError as exc:
            self.summary_label.setText(
                f"Could not read directory: {exc}"
            )
            return

        visible_entries = entries[:self.MAX_VISIBLE_ITEMS]

        for entry in visible_entries:
            if entry.is_dir():
                details = "Directory"
            else:
                try:
                    details = f"File — {entry.stat().st_size:,} bytes"
                except OSError:
                    details = "File — size unavailable"

            QTreeWidgetItem(
                self.tree,
                [entry.name, details],
            )

        self.summary_label.setText(
            f"{len(entries)} top-level entries."
            if len(entries) <= self.MAX_VISIBLE_ITEMS
            else (
                f"{len(entries)} top-level entries. "
                f"Showing the first {self.MAX_VISIBLE_ITEMS}."
            )
        )

    def set_records(self, records: list[dict[str, Any]]) -> None:
        """Display records returned by the backend File Discovery."""
        self.tree.clear()

        visible_records = records[:self.MAX_VISIBLE_ITEMS]

        for record in visible_records:
            name = str(record.get("relative_path", ""))
            product = str(record.get("product_code", ""))
            extension = str(record.get("extension", ""))
            status = str(record.get("file_status", ""))
            pairing = str(record.get("pair_status", ""))

            details = (
                f"{product or 'Unknown product'} | "
                f"{extension} | {status} | Pair: {pairing}"
            )

            QTreeWidgetItem(
                self.tree,
                [name, details],
            )

        if len(records) <= self.MAX_VISIBLE_ITEMS:
            self.summary_label.setText(
                f"{len(records)} discovered files."
            )
        else:
            self.summary_label.setText(
                f"{len(records)} discovered files. "
                f"Showing the first {self.MAX_VISIBLE_ITEMS}."
            )