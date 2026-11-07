
"""Read-only comparison of persisted metrics across MEDA analysis Runs."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.run_manager.run_registry import RunRecord


__all__ = ["ComparisonDashboard"]


class ComparisonDashboard(QWidget):
    """Compare numeric values already persisted in selected Runs."""

    SUMMARY_FILES = (
        ("Coverage", "coverage_summary.json"),
        ("Quality", "quality_summary.json"),
        ("Synchronization", "synchronization_summary.json"),
        ("Ranking", "period_ranking_summary.json"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setObjectName("comparison_dashboard")

        self._records_by_id: dict[str, RunRecord] = {}
        self._comparison_rows: list[dict[str, Any]] = []

        self._build_ui()
        self._update_compare_button()

    @property
    def comparison_rows(self) -> list[dict[str, Any]]:
        """Return a copy of the last comparison result rows."""
        return [dict(row) for row in self._comparison_rows]

    @property
    def available_run_ids(self) -> tuple[str, ...]:
        return tuple(self._records_by_id)

    @property
    def selected_run_ids(self) -> tuple[str, ...]:
        return tuple(
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.run_selector.selectedItems()
            if isinstance(item.data(Qt.ItemDataRole.UserRole), str)
        )

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.status_label = QLabel(
            "Select at least two Runs to compare persisted results.",
            self,
        )
        self.status_label.setObjectName("comparison_status")
        self.status_label.setWordWrap(True)

        selection_group = QGroupBox("Select Runs to Compare", self)
        selection_group.setObjectName("comparison_selection_group")
        selection_layout = QVBoxLayout(selection_group)

        self.run_selector = QListWidget(selection_group)
        self.run_selector.setObjectName("comparison_run_selector")
        self.run_selector.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.run_selector.setMinimumHeight(110)
        self.run_selector.itemSelectionChanged.connect(
            self._update_compare_button
        )

        controls_layout = QHBoxLayout()

        self.compare_button = QPushButton(
            "Compare Selected Runs",
            selection_group,
        )
        self.compare_button.setObjectName("comparison_run_button")
        self.compare_button.clicked.connect(self.compare_selected_runs)

        self.clear_button = QPushButton(
            "Clear Selection",
            selection_group,
        )
        self.clear_button.setObjectName("comparison_clear_button")
        self.clear_button.clicked.connect(self.clear_selection)

        controls_layout.addWidget(self.compare_button)
        controls_layout.addWidget(self.clear_button)
        controls_layout.addStretch(1)

        selection_layout.addWidget(self.run_selector)
        selection_layout.addLayout(controls_layout)

        results_group = QGroupBox(
            "Persisted Metric Comparison",
            self,
        )
        results_group.setObjectName("comparison_results_group")
        results_layout = QVBoxLayout(results_group)

        self.comparison_table = QTableWidget(0, 3, results_group)
        self.comparison_table.setObjectName("comparison_results_table")
        self.comparison_table.setHorizontalHeaderLabels(
            ("Artifact / Metric", "Run Values", "Comparison Status")
        )
        self.comparison_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.comparison_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.comparison_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.comparison_table.setAlternatingRowColors(True)
        self.comparison_table.setWordWrap(False)
        self.comparison_table.horizontalHeader().setStretchLastSection(
            True
        )

        results_layout.addWidget(self.comparison_table)

        layout.addWidget(self.status_label)
        layout.addWidget(selection_group)
        layout.addWidget(results_group, 1)

    def set_runs(self, records: Iterable[RunRecord]) -> None:
        """Replace available Runs while preserving valid selections."""
        selected_ids = set(self.selected_run_ids)
        normalized: dict[str, RunRecord] = {}

        for record in records:
            if not isinstance(record, RunRecord):
                raise TypeError(
                    "records must contain RunRecord instances."
                )
            normalized[record.run_id] = record

        self._records_by_id = normalized

        self.run_selector.blockSignals(True)
        self.run_selector.clear()

        for run_id, record in self._records_by_id.items():
            item = QListWidgetItem(
                f"{run_id}  [{record.status.value}]"
            )
            item.setData(Qt.ItemDataRole.UserRole, run_id)
            self.run_selector.addItem(item)

            if run_id in selected_ids:
                item.setSelected(True)

        self.run_selector.blockSignals(False)
        self._update_compare_button()

        if not self._records_by_id:
            self._clear_results(
                "No Runs are available for comparison."
            )
        elif len(self.selected_run_ids) < 2:
            self.status_label.setText(
                "Select at least two Runs to compare persisted results."
            )

    def _update_compare_button(self) -> None:
        self.compare_button.setEnabled(
            len(self.selected_run_ids) >= 2
        )

    def clear_selection(self) -> None:
        self.run_selector.clearSelection()
        self._clear_results(
            "Select at least two Runs to compare persisted results."
        )
        self._update_compare_button()

    def _clear_results(self, message: str) -> None:
        self._comparison_rows = []
        self.comparison_table.setRowCount(0)
        self.status_label.setText(message)

    @staticmethod
    def _artifact_identity(payload: dict[str, Any]) -> str | None:
        """Return the persisted analyzer identity for an artifact."""
        analyzer = payload.get("analyzer")

        if isinstance(analyzer, str) and analyzer.strip():
            return analyzer.strip()

        module = payload.get("module")

        if isinstance(module, str) and module.strip():
            return module.strip()

        tool = payload.get("tool")

        if isinstance(tool, str) and tool.strip():
            return tool.strip()

        return None

    @classmethod
    def _flatten_numeric_values(
        cls,
        payload: Any,
        prefix: str = "",
    ) -> dict[str, int | float]:
        """Flatten finite numeric leaves without deriving new metrics."""
        flattened: dict[str, int | float] = {}

        if isinstance(payload, dict):
            for key, value in payload.items():
                if not isinstance(key, str) or not key.strip():
                    continue

                path = f"{prefix}.{key}" if prefix else key
                flattened.update(
                    cls._flatten_numeric_values(value, path)
                )

        elif (
            isinstance(payload, (int, float))
            and not isinstance(payload, bool)
        ):
            if math.isfinite(payload):
                flattened[prefix] = payload

        return flattened

    @staticmethod
    def _format_value(value: Any) -> str:
        if value is None:
            return "Not available"

        if isinstance(value, bool):
            return "Not available"

        if isinstance(value, int):
            return f"{value:,}"

        if isinstance(value, float):
            if not math.isfinite(value):
                return "Not available"
            return f"{value:.6g}"

        return "Not available"

    @staticmethod
    def _read_summary(
        output_dir: Path,
        filename: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        path = output_dir / filename

        if not path.is_file():
            return None, "missing"

        try:
            with path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            return None, "invalid"

        if not isinstance(payload, dict):
            return None, "incompatible"

        return payload, None

    def compare_selected_runs(self) -> bool:
        """Compare persisted numeric leaves for the selected Runs."""
        selected_ids = self.selected_run_ids

        if len(selected_ids) < 2:
            self._clear_results(
                "Select at least two Runs before starting comparison."
            )
            self._update_compare_button()
            return False

        records = [
            self._records_by_id[run_id]
            for run_id in selected_ids
            if run_id in self._records_by_id
        ]

        if len(records) < 2:
            self._clear_results(
                "The selected Runs are no longer available."
            )
            return False

        self._comparison_rows = []

        for artifact_label, filename in self.SUMMARY_FILES:
            artifact_data: dict[str, dict[str, int | float]] = {}
            artifact_identities: dict[str, str | None] = {}
            artifact_errors: dict[str, str | None] = {}

            for record in records:
                payload, error = self._read_summary(
                    record.paths.output_dir,
                    filename,
                )

                artifact_errors[record.run_id] = error

                if payload is None:
                    artifact_data[record.run_id] = {}
                    artifact_identities[record.run_id] = None
                    continue

                artifact_data[record.run_id] = (
                    self._flatten_numeric_values(payload)
                )
                artifact_identities[record.run_id] = (
                    self._artifact_identity(payload)
                )

            metric_paths = sorted({
                metric_path
                for values in artifact_data.values()
                for metric_path in values
            })

            if not metric_paths:
                self._comparison_rows.append({
                    "artifact": artifact_label,
                    "metric": "No persisted numeric metrics",
                    "values": {
                        record.run_id: (
                            "Not available"
                            if artifact_errors[record.run_id]
                            else "No numeric metrics"
                        )
                        for record in records
                    },
                    "status": "Unavailable",
                })
                continue

            identities = set(artifact_identities.values())
            known_identities = {
                identity
                for identity in identities
                if identity is not None
            }

            identity_mismatch = (
                len(known_identities) > 1
            )

            for metric_path in metric_paths:
                values: dict[str, Any] = {}
                missing_value = False

                for record in records:
                    value = artifact_data[record.run_id].get(
                        metric_path
                    )

                    if value is None:
                        missing_value = True
                        error = artifact_errors[record.run_id]

                        if error == "missing":
                            values[record.run_id] = (
                                "Artifact missing"
                            )
                        elif error == "invalid":
                            values[record.run_id] = (
                                "Artifact invalid"
                            )
                        elif error == "incompatible":
                            values[record.run_id] = (
                                "Artifact incompatible"
                            )
                        else:
                            values[record.run_id] = (
                                "Metric not available"
                            )
                    else:
                        values[record.run_id] = value

                if identity_mismatch:
                    status = "Incompatible analyzer"
                elif missing_value:
                    status = "Incomplete — missing data"
                elif None in identities:
                    status = "Analyzer identity unavailable"
                else:
                    status = "Comparable"

                self._comparison_rows.append({
                    "artifact": artifact_label,
                    "metric": metric_path,
                    "values": values,
                    "status": status,
                })

        self._populate_table(records)

        comparable_count = sum(
            row["status"] == "Comparable"
            for row in self._comparison_rows
        )
        incomplete_count = sum(
            row["status"] == "Incomplete — missing data"
            for row in self._comparison_rows
        )
        incompatible_count = sum(
            row["status"] == "Incompatible analyzer"
            for row in self._comparison_rows
        )

        self.status_label.setText(
            f"Compared {len(records)} Runs. "
            f"Comparable metrics: {comparable_count}; "
            f"incomplete: {incomplete_count}; "
            f"incompatible: {incompatible_count}. "
            "Only persisted numeric values were read; no analysis was rerun."
        )

        return True

    def _populate_table(self, records: list[RunRecord]) -> None:
        headers = (
            ["Artifact / Metric"]
            + [record.run_id for record in records]
            + ["Comparison Status"]
        )

        self.comparison_table.clear()
        self.comparison_table.setColumnCount(len(headers))
        self.comparison_table.setHorizontalHeaderLabels(headers)
        self.comparison_table.setRowCount(
            len(self._comparison_rows)
        )

        for row_index, row in enumerate(self._comparison_rows):
            label = f"{row['artifact']} / {row['metric']}"

            self.comparison_table.setItem(
                row_index,
                0,
                QTableWidgetItem(label),
            )

            for column_index, record in enumerate(records, start=1):
                raw_value = row["values"].get(record.run_id)

                if isinstance(raw_value, str):
                    display_value = raw_value
                else:
                    display_value = self._format_value(raw_value)

                self.comparison_table.setItem(
                    row_index,
                    column_index,
                    QTableWidgetItem(display_value),
                )

            self.comparison_table.setItem(
                row_index,
                len(headers) - 1,
                QTableWidgetItem(row["status"]),
            )

        self.comparison_table.resizeColumnsToContents()
