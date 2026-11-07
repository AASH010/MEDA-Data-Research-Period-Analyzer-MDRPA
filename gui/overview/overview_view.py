
"""Project-level overview for monitoring MEDA analysis Runs."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.run_manager.run_manager import RunManager
from backend.run_manager.run_registry import RunRecord


__all__ = ["OverviewView"]


class OverviewView(QWidget):
    """Display project-level Run statistics and recent activity."""

    navigation_requested = Signal(str)

    RECENT_RUN_LIMIT = 5
    USER_ROLE = 32

    STATUS_KEYS = (
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
        ("CANCELLED", "Cancelled"),
    )

    def __init__(
        self,
        parent: QWidget | None = None,
        run_manager: RunManager | None = None,
    ) -> None:
        super().__init__(parent)

        if run_manager is not None and not isinstance(
            run_manager,
            RunManager,
        ):
            raise TypeError("run_manager must be a RunManager or None.")

        self.setObjectName("overview_view")

        self._run_manager: RunManager | None = None
        self._records: tuple[RunRecord, ...] = ()
        self._records_by_id: dict[str, RunRecord] = {}

        self._build_ui()
        self._connect_signals()

        if run_manager is not None:
            self.set_run_manager(run_manager)
        else:
            self._show_unavailable_state()

    @property
    def run_manager(self) -> RunManager | None:
        """Return the RunManager used as the overview data source."""
        return self._run_manager

    @property
    def records(self) -> tuple[RunRecord, ...]:
        """Return the most recently loaded Run records."""
        return self._records

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Project Overview", self)
        title.setObjectName("overview_title")

        description = QLabel(
            "Monitor analysis activity, Run status, and recent project "
            "history from one place.",
            self,
        )
        description.setObjectName("overview_description")
        description.setWordWrap(True)

        header_layout = QHBoxLayout()
        header_layout.addWidget(title)
        header_layout.addStretch(1)

        self.refresh_button = QPushButton("Refresh Overview", self)
        self.refresh_button.setObjectName("overview_refresh_button")
        header_layout.addWidget(self.refresh_button)

        self.status_label = QLabel(
            "Run Manager is not connected.",
            self,
        )
        self.status_label.setObjectName("overview_status")
        self.status_label.setWordWrap(True)

        statistics_group = QGroupBox("Run Statistics", self)
        statistics_group.setObjectName("overview_statistics_group")

        statistics_layout = QGridLayout(statistics_group)
        statistics_layout.setHorizontalSpacing(12)
        statistics_layout.setVerticalSpacing(10)

        self.stat_labels: dict[str, QLabel] = {}

        for index, (key, title_text) in enumerate(self.STATUS_KEYS):
            card = QGroupBox(title_text, statistics_group)
            card.setObjectName(f"overview_stat_{key.lower()}")

            card_layout = QVBoxLayout(card)

            value_label = QLabel("—", card)
            value_label.setObjectName(
                f"overview_stat_value_{key.lower()}"
            )
            value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value_label.setStyleSheet(
                "font-size: 22px; font-weight: 600;"
            )

            card_layout.addWidget(value_label)

            statistics_layout.addWidget(
                card,
                index // 3,
                index % 3,
            )

            self.stat_labels[key] = value_label

        latest_group = QGroupBox("Latest Run", self)
        latest_group.setObjectName("overview_latest_group")

        latest_layout = QVBoxLayout(latest_group)

        self.latest_run_label = QLabel(
            "No Run information is available.",
            latest_group,
        )
        self.latest_run_label.setObjectName("overview_latest_run")
        self.latest_run_label.setWordWrap(True)

        latest_layout.addWidget(self.latest_run_label)

        recent_group = QGroupBox("Recent Runs", self)
        recent_group.setObjectName("overview_recent_group")

        recent_layout = QVBoxLayout(recent_group)

        self.recent_runs_table = QTableWidget(0, 4, recent_group)
        self.recent_runs_table.setObjectName(
            "overview_recent_runs_table"
        )
        self.recent_runs_table.setHorizontalHeaderLabels(
            ("Run ID", "Status", "SOL Range", "Created")
        )
        self.recent_runs_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.recent_runs_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.recent_runs_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.recent_runs_table.setAlternatingRowColors(True)
        self.recent_runs_table.setWordWrap(False)
        self.recent_runs_table.horizontalHeader().setStretchLastSection(
            True
        )

        recent_layout.addWidget(self.recent_runs_table)

        actions_group = QGroupBox("Quick Navigation", self)
        actions_layout = QHBoxLayout(actions_group)

        self.input_button = QPushButton("Input Data", actions_group)
        self.input_button.setObjectName("overview_input_button")

        self.analysis_button = QPushButton("Analysis", actions_group)
        self.analysis_button.setObjectName("overview_analysis_button")

        self.dashboard_button = QPushButton(
            "Dashboard",
            actions_group,
        )
        self.dashboard_button.setObjectName("overview_dashboard_button")

        self.reports_button = QPushButton("Reports", actions_group)
        self.reports_button.setObjectName("overview_reports_button")

        for button in (
            self.input_button,
            self.analysis_button,
            self.dashboard_button,
            self.reports_button,
        ):
            actions_layout.addWidget(button)

        layout.addLayout(header_layout)
        layout.addWidget(description)
        layout.addWidget(self.status_label)
        layout.addWidget(statistics_group)
        layout.addWidget(latest_group)
        layout.addWidget(recent_group, 1)
        layout.addWidget(actions_group)

    def _connect_signals(self) -> None:
        """Connect overview controls to their actions."""
        self.refresh_button.clicked.connect(self.refresh_runs)

        self.input_button.clicked.connect(
            lambda: self.navigation_requested.emit("input")
        )
        self.analysis_button.clicked.connect(
            lambda: self.navigation_requested.emit("analysis")
        )
        self.dashboard_button.clicked.connect(
            lambda: self.navigation_requested.emit("dashboard")
        )
        self.reports_button.clicked.connect(
            lambda: self.navigation_requested.emit("reports")
        )

    def set_run_manager(
        self,
        run_manager: RunManager | None,
    ) -> None:
        """Attach or detach the RunManager and refresh the overview."""
        if run_manager is not None and not isinstance(
            run_manager,
            RunManager,
        ):
            raise TypeError("run_manager must be a RunManager or None.")

        self._run_manager = run_manager
        self.refresh_runs()

    @staticmethod
    def _format_sol_range(record: RunRecord) -> str:
        start_sol = record.metadata.start_sol
        end_sol = record.metadata.end_sol

        if start_sol is None or end_sol is None:
            return "Not specified"

        if start_sol == end_sol:
            return str(start_sol)

        return f"{start_sol} – {end_sol}"

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return "Not available"

        return value.astimezone().strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        )

    def _clear_display(self, message: str) -> None:
        """Clear stale Run information and display a status message."""
        self._records = ()
        self._records_by_id.clear()

        self.status_label.setText(message)
        self.latest_run_label.setText(
            "No Run information is available."
        )
        self.recent_runs_table.setRowCount(0)

        for label in self.stat_labels.values():
            label.setText("—")

    def _show_unavailable_state(self) -> None:
        """Display the initial state when no RunManager is connected."""
        self._clear_display(
            "Run Manager is not connected. "
            "Project Run information is unavailable."
        )

    def refresh_runs(self) -> None:
        """Reload Run statistics and recent activity."""
        manager = self._run_manager

        if manager is None:
            self._show_unavailable_state()
            return

        try:
            records = tuple(manager.list_runs())
        except Exception as exc:
            self._clear_display(
                f"Unable to load Runs: {type(exc).__name__}: {exc}"
            )
            return

        records = tuple(
            sorted(
                records,
                key=lambda record: record.metadata.created_at,
                reverse=True,
            )
        )

        self._records = records
        self._records_by_id = {
            record.run_id: record
            for record in records
        }

        counts = {
            key: sum(
                1
                for record in records
                if record.status.value == key
            )
            for key, _title in self.STATUS_KEYS
        }

        for key, _title in self.STATUS_KEYS:
            self.stat_labels[key].setText(str(counts[key]))

        total = len(records)

        if not records:
            self.status_label.setText(
                "No analysis Runs are available yet. "
                "Select Input Data to begin."
            )
            self.latest_run_label.setText(
                "No Runs have been created yet."
            )
            self.recent_runs_table.setRowCount(0)
            return

        self.status_label.setText(
            f"{total} Run(s) recorded | "
            f"{counts['COMPLETED']} completed | "
            f"{counts['RUNNING']} running | "
            f"{counts['FAILED']} failed"
        )

        self._display_latest_run(records[0])
        self._display_recent_runs(
            records[: self.RECENT_RUN_LIMIT]
        )

    def refresh(self) -> None:
        """Refresh the Overview using the connected Run Manager."""
        self.refresh_runs()

    def _display_latest_run(self, record: RunRecord) -> None:
        """Display details for the most recently created Run."""
        metadata = record.metadata

        details = (
            f"Run ID: {record.run_id}\n"
            f"Status: {record.status.value}\n"
            f"SOL Range: {self._format_sol_range(record)}\n"
            f"Created: {self._format_datetime(metadata.created_at)}\n"
            f"Input Source: {metadata.input_source or 'Not available'}\n"
            f"Application Version: "
            f"{metadata.application_version or 'Not available'}"
        )

        if metadata.failure_reason:
            details += (
                f"\nFailure Reason: {metadata.failure_reason}"
            )

        self.latest_run_label.setText(details)

    def _display_recent_runs(
        self,
        records: tuple[RunRecord, ...],
    ) -> None:
        """Populate the recent Runs table."""
        self.recent_runs_table.setRowCount(len(records))

        for row, record in enumerate(records):
            values = (
                record.run_id,
                record.status.value,
                self._format_sol_range(record),
                self._format_datetime(record.metadata.created_at),
            )

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)

                if column == 0:
                    item.setData(
                        self.USER_ROLE,
                        record.run_id,
                    )

                self.recent_runs_table.setItem(
                    row,
                    column,
                    item,
                )
