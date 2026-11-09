"""Analysis configuration page for the MDRPA desktop application."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from backend.pipeline.pipeline_validator import (
    DEFAULT_REQUIRED_PRODUCTS,
    PipelineConfig,
    validate_pipeline_config,
)


__all__ = ["AnalysisConfigurationView", "WORKER_CHOICES"]


# (label, value) pairs for the "Parallel workers" selector.
# Index 0 is the default and must stay sequential.
WORKER_CHOICES: tuple[tuple[str, int | str], ...] = (
    ("Sequential (1 worker)", 1),
    ("Optimized (automatic)", "optimized"),
    ("2 workers", 2),
    ("4 workers", 4),
    ("8 workers", 8),
)


class AnalysisConfigurationView(QWidget):
    """Collect and validate settings for one MEDA analysis run."""

    config_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setObjectName("analysis_configuration_view")
        self._input_directory: Path | None = None
        self._validated_config: PipelineConfig | None = None

        self._build_ui()
        self._connect_signals()
        self._set_dataset_state()

    @property
    def input_directory(self) -> Path | None:
        return self._input_directory

    @property
    def validated_config(self) -> PipelineConfig | None:
        return self._validated_config

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self.title_label = QLabel("Analysis Configuration")
        self.title_label.setObjectName("analysis_configuration_title")

        self.description_label = QLabel(
            "Configure the MEDA analysis parameters. "
            "A successfully validated dataset is required."
        )
        self.description_label.setWordWrap(True)

        self.dataset_edit = QLineEdit(self)
        self.dataset_edit.setObjectName("analysis_dataset_path")
        self.dataset_edit.setReadOnly(True)
        self.dataset_edit.setPlaceholderText(
            "Select and validate a dataset in Input Data first."
        )

        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )

        self.start_sol_edit = QLineEdit(self)
        self.start_sol_edit.setObjectName("start_sol")
        self.start_sol_edit.setPlaceholderText("Automatic")

        self.end_sol_edit = QLineEdit(self)
        self.end_sol_edit.setObjectName("end_sol")
        self.end_sol_edit.setPlaceholderText("Automatic")

        self.gap_factor_spin = self._double_spin(
            "gap_factor", 2.5, 0.000001, 1000000.0
        )
        self.tolerance_spin = self._double_spin(
            "tolerance", 1.0, 0.000001, 1000000.0
        )
        self.window_size_spin = self._integer_spin(
            "window_size", 10, 1, 1000000
        )
        self.min_sol_fraction_spin = self._double_spin(
            "min_sol_fraction", 0.5, 0.000001, 1.0
        )
        self.min_metrics_spin = self._integer_spin(
            "min_metrics", 3, 1, 4
        )

        self.required_products_edit = QLineEdit(
            ",".join(DEFAULT_REQUIRED_PRODUCTS),
            self,
        )
        self.required_products_edit.setObjectName(
            "required_products"
        )

        self.weight_files_spin = self._double_spin(
            "weight_files", 0.20, 0.0, 1000000.0
        )
        self.weight_integrity_spin = self._double_spin(
            "weight_integrity", 0.45, 0.0, 1000000.0
        )
        self.weight_quality_spin = self._double_spin(
            "weight_quality", 0.15, 0.0, 1000000.0
        )
        self.weight_sync_spin = self._double_spin(
            "weight_sync", 0.20, 0.0, 1000000.0
        )

        self.integrity_timestamps_spin = self._double_spin(
            "integrity_timestamps", 1.0, 0.0, 1000000.0
        )
        self.integrity_values_spin = self._double_spin(
            "integrity_values", 1.0, 0.0, 1000000.0
        )

        self.workers_combo = QComboBox(self)
        self.workers_combo.setObjectName("workers")

        for label, value in WORKER_CHOICES:
            self.workers_combo.addItem(label, value)

        self.workers_combo.setToolTip(
            "Optimized picks the number of processes from your CPU "
            "and the number of CSV files. Sequential is the safest "
            "choice."
        )

        form.addRow("Input dataset:", self.dataset_edit)
        form.addRow("Start Sol (optional):", self.start_sol_edit)
        form.addRow("End Sol (optional):", self.end_sol_edit)
        form.addRow("Gap factor:", self.gap_factor_spin)
        form.addRow("Tolerance:", self.tolerance_spin)
        form.addRow("Window size:", self.window_size_spin)
        form.addRow(
            "Minimum Sol fraction:",
            self.min_sol_fraction_spin,
        )
        form.addRow("Minimum metrics:", self.min_metrics_spin)
        form.addRow(
            "Required products (comma-separated):",
            self.required_products_edit,
        )
        form.addRow("Files ranking weight:", self.weight_files_spin)
        form.addRow(
            "Integrity ranking weight:",
            self.weight_integrity_spin,
        )
        form.addRow(
            "Quality ranking weight:",
            self.weight_quality_spin,
        )
        form.addRow(
            "Synchronization ranking weight:",
            self.weight_sync_spin,
        )
        form.addRow(
            "Timestamp integrity weight:",
            self.integrity_timestamps_spin,
        )
        form.addRow(
            "Value integrity weight:",
            self.integrity_values_spin,
        )
        form.addRow("Parallel workers:", self.workers_combo)

        actions = QHBoxLayout()

        self.validate_button = QPushButton(
            "Validate Configuration",
            self,
        )
        self.validate_button.setObjectName(
            "validate_analysis_config_button"
        )

        self.reset_button = QPushButton("Reset Defaults", self)
        self.reset_button.setObjectName(
            "reset_analysis_config_button"
        )

        actions.addWidget(self.validate_button)
        actions.addWidget(self.reset_button)
        actions.addStretch(1)

        self.status_label = QLabel(
            "Select and validate a dataset before configuring analysis."
        )
        self.status_label.setObjectName(
            "analysis_configuration_status"
        )
        self.status_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.description_label)
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

    @staticmethod
    def _double_spin(
        object_name: str,
        default: float,
        minimum: float,
        maximum: float,
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setObjectName(object_name)
        widget.setDecimals(6)
        widget.setRange(minimum, maximum)
        widget.setValue(default)
        widget.setKeyboardTracking(False)
        return widget

    @staticmethod
    def _integer_spin(
        object_name: str,
        default: int,
        minimum: int,
        maximum: int,
    ) -> QSpinBox:
        widget = QSpinBox()
        widget.setObjectName(object_name)
        widget.setRange(minimum, maximum)
        widget.setValue(default)
        widget.setKeyboardTracking(False)
        return widget

    def _connect_signals(self) -> None:
        self.validate_button.clicked.connect(
            self.validate_configuration
        )
        self.reset_button.clicked.connect(self.reset_defaults)

    def _set_dataset_state(self) -> None:
        available = self._input_directory is not None
        self.validate_button.setEnabled(available)

    def set_input_directory(
        self,
        directory: str | Path | None,
    ) -> None:
        """Set or clear the dataset accepted by Input Manager."""
        if directory is None:
            self._input_directory = None
            self.dataset_edit.clear()
            self._validated_config = None
            self.status_label.setText(
                "No validated dataset is available."
            )
            self._set_dataset_state()
            return

        if not isinstance(directory, (str, Path)):
            raise TypeError(
                "directory must be a string, pathlib.Path, or None."
            )

        if isinstance(directory, str) and not directory.strip():
            raise ValueError("directory must not be empty.")

        resolved = Path(directory).expanduser().resolve()

        if not resolved.exists() or not resolved.is_dir():
            raise ValueError(
                "The input directory must exist and be a directory."
            )

        self._input_directory = resolved
        self.dataset_edit.setText(str(resolved))
        self._validated_config = None
        self.status_label.setText(
            "Dataset accepted. Review the parameters and validate."
        )
        self._set_dataset_state()

    def _read_optional_sol(
        self,
        widget: QLineEdit,
        field_name: str,
    ) -> int | None:
        value = widget.text().strip()

        if not value:
            return None

        try:
            parsed = int(value)
        except ValueError as exc:
            raise ValueError(
                f"{field_name} must be a non-negative integer."
            ) from exc

        if parsed < 0:
            raise ValueError(
                f"{field_name} must be a non-negative integer."
            )

        return parsed

    def build_config(self) -> PipelineConfig:
        """Build and validate a PipelineConfig from the current controls."""
        if self._input_directory is None:
            raise ValueError(
                "Select and validate a dataset in Input Data first."
            )

        products = [
            item.strip()
            for item in self.required_products_edit.text().split(",")
            if item.strip()
        ]

        config = PipelineConfig(
            input_dir=self._input_directory,
            start_sol=self._read_optional_sol(
                self.start_sol_edit, "start_sol"
            ),
            end_sol=self._read_optional_sol(
                self.end_sol_edit, "end_sol"
            ),
            gap_factor=self.gap_factor_spin.value(),
            tolerance=self.tolerance_spin.value(),
            window_size=self.window_size_spin.value(),
            min_sol_fraction=self.min_sol_fraction_spin.value(),
            min_metrics=self.min_metrics_spin.value(),
            required_products=tuple(products),
            weight_files=self.weight_files_spin.value(),
            weight_integrity=self.weight_integrity_spin.value(),
            weight_quality=self.weight_quality_spin.value(),
            weight_sync=self.weight_sync_spin.value(),
            integrity_timestamps=(
                self.integrity_timestamps_spin.value()
            ),
            integrity_values=self.integrity_values_spin.value(),
            workers=self.workers_combo.currentData(),
        )

        return validate_pipeline_config(config)

    def validate_configuration(self) -> bool:
        """Validate current settings and emit the validated config."""
        self._validated_config = None

        try:
            config = self.build_config()
        except (TypeError, ValueError, OSError) as exc:
            self.status_label.setText(
                f"Configuration invalid: {exc}"
            )
            return False

        self._validated_config = config
        self.status_label.setText(
            "Configuration validated successfully."
        )
        self.config_ready.emit(config)
        return True

    def reset_defaults(self) -> None:
        """Restore PipelineConfig defaults without changing the dataset."""
        self.start_sol_edit.clear()
        self.end_sol_edit.clear()

        self.gap_factor_spin.setValue(2.5)
        self.tolerance_spin.setValue(1.0)
        self.window_size_spin.setValue(10)
        self.min_sol_fraction_spin.setValue(0.5)
        self.min_metrics_spin.setValue(3)

        self.required_products_edit.setText(
            ",".join(DEFAULT_REQUIRED_PRODUCTS)
        )

        self.weight_files_spin.setValue(0.20)
        self.weight_integrity_spin.setValue(0.45)
        self.weight_quality_spin.setValue(0.15)
        self.weight_sync_spin.setValue(0.20)

        self.integrity_timestamps_spin.setValue(1.0)
        self.integrity_values_spin.setValue(1.0)

        self.workers_combo.setCurrentIndex(0)

        self._validated_config = None

        if self._input_directory is None:
            self.status_label.setText(
                "Select and validate a dataset before configuring analysis."
            )
        else:
            self.status_label.setText(
                "Default parameters restored. Validate the configuration."
            )