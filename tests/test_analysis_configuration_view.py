"""Tests for the MDRPA Analysis Configuration GUI."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication

from application.app_config import AppConfig
from application.app_paths import AppPaths
from backend.pipeline.pipeline_validator import (
    DEFAULT_REQUIRED_PRODUCTS,
    PipelineConfig,
)
from gui.analysis.analysis_configuration_view import (
    AnalysisConfigurationView,
)
from gui.input_manager.input_manager_view import InputManagerView
from gui.main_window.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def config_view(qapp, tmp_path):
    view = AnalysisConfigurationView()
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    view.set_input_directory(dataset)

    yield view
    view.close()


@pytest.fixture
def main_window(qapp, tmp_path):
    config = AppConfig(
        AppPaths.from_root(tmp_path / "application-data")
    )
    window = MainWindow(config)

    yield window
    window.close()


def make_meda_stem(
    sol: int = 100,
    product: str = "ATS",
) -> str:
    return (
        f"WE__{sol:04d}___________"
        f"CAL_{product}_________________P01"
    )


def create_valid_dataset(root: Path) -> Path:
    sol_dir = root / "SOL100"
    sol_dir.mkdir(parents=True)

    stem = make_meda_stem()

    (sol_dir / f"{stem}.CSV").write_text(
        "time,value\n1,2\n",
        encoding="utf-8",
    )
    (sol_dir / f"{stem}.XML").write_text(
        "<Product></Product>",
        encoding="utf-8",
    )

    return root


def test_initial_state_requires_dataset(qapp):
    view = AnalysisConfigurationView()

    assert view.input_directory is None
    assert view.validated_config is None
    assert view.validate_button.isEnabled() is False
    assert view.dataset_edit.text() == ""

    view.close()


def test_set_input_directory_enables_validation(
    config_view,
    tmp_path,
):
    expected = (tmp_path / "dataset").resolve()

    assert config_view.input_directory == expected
    assert config_view.dataset_edit.text() == str(expected)
    assert config_view.validate_button.isEnabled() is True


def test_set_input_directory_rejects_invalid_values(qapp, tmp_path):
    view = AnalysisConfigurationView()

    with pytest.raises(TypeError):
        view.set_input_directory(123)

    with pytest.raises(ValueError):
        view.set_input_directory("")

    with pytest.raises(ValueError):
        view.set_input_directory(tmp_path / "missing")

    view.close()


def test_build_config_uses_pipeline_defaults(config_view, tmp_path):
    config = config_view.build_config()

    assert isinstance(config, PipelineConfig)
    assert config.input_dir == (tmp_path / "dataset").resolve()
    assert config.start_sol is None
    assert config.end_sol is None
    assert config.gap_factor == 2.5
    assert config.tolerance == 1.0
    assert config.window_size == 10
    assert config.min_sol_fraction == 0.5
    assert config.min_metrics == 3
    assert config.required_products == DEFAULT_REQUIRED_PRODUCTS
    assert config.weight_files == 0.20
    assert config.weight_integrity == 0.45
    assert config.weight_quality == 0.15
    assert config.weight_sync == 0.20
    assert config.integrity_timestamps == 1.0
    assert config.integrity_values == 1.0


def test_build_config_accepts_custom_values(config_view, tmp_path):
    config_view.start_sol_edit.setText("100")
    config_view.end_sol_edit.setText("150")
    config_view.gap_factor_spin.setValue(3.0)
    config_view.tolerance_spin.setValue(2.0)
    config_view.window_size_spin.setValue(8)
    config_view.min_sol_fraction_spin.setValue(0.75)
    config_view.min_metrics_spin.setValue(2)
    config_view.required_products_edit.setText("ats, ps, RDS")
    config_view.weight_files_spin.setValue(0.3)
    config_view.weight_integrity_spin.setValue(0.4)
    config_view.weight_quality_spin.setValue(0.2)
    config_view.weight_sync_spin.setValue(0.1)
    config_view.integrity_timestamps_spin.setValue(2.0)
    config_view.integrity_values_spin.setValue(3.0)

    config = config_view.build_config()

    assert config.start_sol == 100
    assert config.end_sol == 150
    assert config.gap_factor == 3.0
    assert config.tolerance == 2.0
    assert config.window_size == 8
    assert config.min_sol_fraction == 0.75
    assert config.min_metrics == 2
    assert config.required_products == ("ATS", "PS", "RDS")
    assert config.weight_files == 0.3
    assert config.weight_integrity == 0.4
    assert config.weight_quality == 0.2
    assert config.weight_sync == 0.1
    assert config.integrity_timestamps == 2.0
    assert config.integrity_values == 3.0
    assert config.input_dir == (tmp_path / "dataset").resolve()


@pytest.mark.parametrize(
    "start,end",
    [
        ("100", ""),
        ("", "150"),
        ("200", "100"),
        ("-1", "100"),
        ("abc", "100"),
    ],
)
def test_invalid_sol_ranges_are_rejected(
    config_view,
    start,
    end,
):
    config_view.start_sol_edit.setText(start)
    config_view.end_sol_edit.setText(end)

    with pytest.raises((TypeError, ValueError)):
        config_view.build_config()


def test_empty_required_products_are_rejected(config_view):
    config_view.required_products_edit.setText(" , , ")

    with pytest.raises((TypeError, ValueError)):
        config_view.build_config()


def test_validation_emits_validated_config(config_view):
    emitted = []
    config_view.config_ready.connect(emitted.append)

    assert config_view.validate_configuration() is True
    assert len(emitted) == 1
    assert emitted[0] is config_view.validated_config
    assert isinstance(emitted[0], PipelineConfig)
    assert "successfully" in config_view.status_label.text().lower()


def test_invalid_configuration_does_not_emit(config_view):
    emitted = []
    config_view.config_ready.connect(emitted.append)

    config_view.start_sol_edit.setText("100")

    assert config_view.validate_configuration() is False
    assert emitted == []
    assert config_view.validated_config is None
    assert "invalid" in config_view.status_label.text().lower()


def test_configuration_cannot_be_built_without_dataset(qapp):
    view = AnalysisConfigurationView()

    with pytest.raises(ValueError, match="dataset"):
        view.build_config()

    assert view.validate_configuration() is False
    assert view.validate_button.isEnabled() is False

    view.close()


def test_clearing_dataset_invalidates_configuration(config_view):
    assert config_view.validate_configuration() is True
    assert config_view.validated_config is not None

    config_view.set_input_directory(None)

    assert config_view.input_directory is None
    assert config_view.validated_config is None
    assert config_view.dataset_edit.text() == ""
    assert config_view.validate_button.isEnabled() is False


def test_reset_defaults_restores_all_parameters(config_view):
    config_view.start_sol_edit.setText("100")
    config_view.end_sol_edit.setText("200")
    config_view.gap_factor_spin.setValue(4.0)
    config_view.required_products_edit.setText("ATS")

    config_view.reset_defaults()

    config = config_view.build_config()

    assert config.start_sol is None
    assert config.end_sol is None
    assert config.gap_factor == 2.5
    assert config.required_products == DEFAULT_REQUIRED_PRODUCTS


def test_main_window_contains_analysis_configuration(main_window):
    assert isinstance(
        main_window.analysis_configuration_view,
        AnalysisConfigurationView,
    )

    main_window.navigate_to("analysis")

    assert main_window.current_page_key == "analysis"
    assert main_window.page_stack.currentWidget() is (
        main_window.analysis_configuration_view
    )


def test_input_manager_selection_is_not_accepted_before_validation(
    main_window,
    tmp_path,
):
    dataset = create_valid_dataset(tmp_path / "dataset")

    main_window.input_manager_view.set_input_directory(dataset)

    assert main_window.selected_input_dir is None
    assert main_window.analysis_configuration_view.input_directory is None


def test_validated_input_is_forwarded_to_analysis_configuration(
    main_window,
    tmp_path,
):
    dataset = create_valid_dataset(tmp_path / "dataset")

    main_window.input_manager_view.set_input_directory(dataset)

    assert main_window.input_manager_view.validate_dataset() is True

    expected = dataset.resolve()

    assert main_window.selected_input_dir == expected
    assert (
        main_window.analysis_configuration_view.input_directory
        == expected
    )


def test_changing_input_invalidates_analysis_configuration(
    main_window,
    tmp_path,
):
    first = create_valid_dataset(tmp_path / "first")
    second = create_valid_dataset(tmp_path / "second")

    input_view = main_window.input_manager_view
    config_view = main_window.analysis_configuration_view

    input_view.set_input_directory(first)
    assert input_view.validate_dataset() is True
    assert config_view.validate_configuration() is True

    input_view.set_input_directory(second)

    assert config_view.input_directory is None
    assert config_view.validated_config is None


def test_clearing_input_invalidates_analysis_configuration(
    main_window,
    tmp_path,
):
    dataset = create_valid_dataset(tmp_path / "dataset")

    input_view = main_window.input_manager_view
    config_view = main_window.analysis_configuration_view

    input_view.set_input_directory(dataset)
    assert input_view.validate_dataset() is True
    assert config_view.validate_configuration() is True

    input_view.clear_selection()

    assert main_window.selected_input_dir is None
    assert config_view.input_directory is None
    assert config_view.validated_config is None

def test_unvalidated_input_never_reaches_configuration(
    main_window,
    tmp_path,
):
    dataset = create_valid_dataset(tmp_path / "dataset")

    input_view = main_window.input_manager_view
    config_view = main_window.analysis_configuration_view

    input_view.set_input_directory(dataset)

    assert config_view.input_directory is None
    assert config_view.validate_configuration() is False

    assert input_view.validate_dataset() is True
    assert config_view.input_directory == dataset.resolve()