"""Tests for the MDRPA Input Manager GUI."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication, QFileDialog

from application.app_config import AppConfig
from application.app_paths import AppPaths
from gui.input_manager.file_import_view import FileImportView
from gui.input_manager.input_manager_view import InputManagerView
from gui.main_window.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance()

    if application is None:
        application = QApplication([])

    yield application


@pytest.fixture
def input_view(qapp):
    view = InputManagerView()
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


def create_valid_dataset(
    root: Path,
    *,
    include_xml: bool = True,
) -> Path:
    sol_dir = root / "SOL100"
    sol_dir.mkdir(parents=True)

    stem = make_meda_stem()

    (sol_dir / f"{stem}.CSV").write_text(
        "time,value\n1,2\n",
        encoding="utf-8",
    )

    if include_xml:
        (sol_dir / f"{stem}.XML").write_text(
            "<Product></Product>",
            encoding="utf-8",
        )

    return root


def test_input_manager_initial_state(input_view):
    assert input_view.selected_input_dir is None
    assert input_view.is_validated is False
    assert input_view.discovered_records == ()
    assert input_view.validate_button.isEnabled() is False


def test_file_import_view_stores_selected_directory(
    qapp,
    tmp_path,
):
    view = FileImportView()
    selected = tmp_path / "dataset"
    selected.mkdir()

    view.set_selected_directory(selected)

    assert view.selected_directory == selected.resolve()
    assert view.path_edit.text() == str(selected.resolve())

    view.close()


def test_file_import_view_rejects_invalid_value(qapp):
    view = FileImportView()

    with pytest.raises(TypeError):
        view.set_selected_directory(123)

    with pytest.raises(ValueError):
        view.set_selected_directory("")

    view.close()


def test_browse_button_emits_selected_directory(
    input_view,
    tmp_path,
    monkeypatch,
):
    selected = tmp_path / "dataset"
    selected.mkdir()

    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(selected),
    )

    emitted = []
    input_view.input_directory_changed.connect(emitted.append)

    input_view.file_import_view.choose_directory()

    assert input_view.selected_input_dir == selected.resolve()
    assert emitted == [selected.resolve()]
    assert input_view.validate_button.isEnabled()


def test_set_input_directory_updates_preview(
    input_view,
    tmp_path,
):
    dataset = create_valid_dataset(tmp_path / "dataset")

    input_view.set_input_directory(dataset)

    assert input_view.selected_input_dir == dataset.resolve()
    assert input_view.file_import_view.path_edit.text() == (
        str(dataset.resolve())
    )
    assert input_view.file_preview_view.tree.topLevelItemCount() == 1
    assert input_view.is_validated is False


def test_validate_dataset_accepts_valid_dataset(input_view, tmp_path):
    dataset = create_valid_dataset(tmp_path / "dataset")

    input_view.set_input_directory(dataset)

    assert input_view.validate_dataset() is True
    assert input_view.is_validated is True
    assert len(input_view.discovered_records) == 2

    assert (
        input_view.validation_view.status_label.text()
        == "Validation successful."
    )

    assert "SOL directories: 1" in (
        input_view.validation_view.details_label.text()
    )

    assert "Supported files: 2" in (
        input_view.validation_view.details_label.text()
    )


def test_validate_dataset_reports_missing_sol_directories(
    input_view,
    tmp_path,
):
    dataset = tmp_path / "dataset"
    dataset.mkdir()

    (dataset / "unrelated.txt").write_text(
        "not a MEDA dataset",
        encoding="utf-8",
    )

    input_view.set_input_directory(dataset)

    assert input_view.validate_dataset() is False
    assert input_view.is_validated is False

    assert "No recognized SOL directories" in (
        input_view.validation_view.details_label.text()
    )


def test_validate_dataset_rejects_dataset_without_supported_files(
    input_view,
    tmp_path,
):
    dataset = tmp_path / "dataset"
    sol_dir = dataset / "SOL100"
    sol_dir.mkdir(parents=True)

    (sol_dir / "notes.txt").write_text(
        "unsupported file",
        encoding="utf-8",
    )

    input_view.set_input_directory(dataset)

    assert input_view.validate_dataset() is False
    assert input_view.is_validated is False

    assert "No supported MEDA CSV or XML files" in (
        input_view.validation_view.details_label.text()
    )


def test_validate_dataset_reports_missing_directory(
    input_view,
    tmp_path,
):
    missing = tmp_path / "missing"

    input_view.set_input_directory(missing)

    assert input_view.validate_dataset() is False
    assert input_view.is_validated is False

    assert "does not exist" in (
        input_view.validation_view.details_label.text()
    )


def test_validate_dataset_rejects_file_as_directory(
    input_view,
    tmp_path,
):
    input_file = tmp_path / "dataset.txt"
    input_file.write_text("not a directory", encoding="utf-8")

    input_view.set_input_directory(input_file)

    assert input_view.validate_dataset() is False
    assert input_view.is_validated is False

    assert "not a directory" in (
        input_view.validation_view.details_label.text()
    )


def test_missing_counterpart_is_warning_not_validation_failure(
    input_view,
    tmp_path,
):
    dataset = create_valid_dataset(
        tmp_path / "dataset",
        include_xml=False,
    )

    input_view.set_input_directory(dataset)

    assert input_view.validate_dataset() is True
    assert input_view.is_validated is True

    details = input_view.validation_view.details_label.text()

    assert "Discovery warnings: 1" in details
    assert "warnings" in details.lower()


def test_selecting_new_directory_resets_previous_validation(
    input_view,
    tmp_path,
):
    first_dataset = create_valid_dataset(tmp_path / "first")
    second_dataset = create_valid_dataset(tmp_path / "second")

    input_view.set_input_directory(first_dataset)

    assert input_view.validate_dataset() is True
    assert input_view.is_validated is True

    input_view.set_input_directory(second_dataset)

    assert input_view.is_validated is False
    assert input_view.discovered_records == ()
    assert "not been validated" in (
        input_view.validation_view.status_label.text()
    )


def test_clear_selection_resets_all_input_state(
    input_view,
    tmp_path,
):
    dataset = create_valid_dataset(tmp_path / "dataset")

    input_view.set_input_directory(dataset)
    assert input_view.validate_dataset() is True

    input_view.clear_selection()

    assert input_view.selected_input_dir is None
    assert input_view.is_validated is False
    assert input_view.discovered_records == ()
    assert input_view.file_import_view.selected_directory is None
    assert input_view.file_preview_view.tree.topLevelItemCount() == 0
    assert input_view.validate_button.isEnabled() is False


def test_main_window_uses_input_manager_page(main_window):
    assert isinstance(
        main_window.input_manager_view,
        InputManagerView,
    )

    main_window.navigate_to("input")

    assert main_window.current_page_key == "input"
    assert main_window.page_stack.currentWidget() is (
        main_window.input_manager_view
    )


def test_main_window_exposes_input_directory_after_validation(
    main_window,
    tmp_path,
):
    dataset = create_valid_dataset(tmp_path / "dataset")

    assert main_window.selected_input_dir is None

    main_window.input_manager_view.set_input_directory(dataset)

    assert main_window.selected_input_dir is None

    assert main_window.input_manager_view.validate_dataset() is True

    assert main_window.selected_input_dir == dataset.resolve()


def test_main_window_hides_input_directory_after_clear(
    main_window,
    tmp_path,
):
    dataset = create_valid_dataset(tmp_path / "dataset")

    main_window.input_manager_view.set_input_directory(dataset)
    assert main_window.input_manager_view.validate_dataset() is True

    assert main_window.selected_input_dir == dataset.resolve()

    main_window.input_manager_view.clear_selection()

    assert main_window.selected_input_dir is None


def test_validate_dataset_handles_discovery_os_error(
    input_view,
    tmp_path,
    monkeypatch,
):
    dataset = create_valid_dataset(tmp_path / "dataset")
    input_view.set_input_directory(dataset)

    monkeypatch.setattr(
        "gui.input_manager.input_manager_view.discover_files",
        lambda _directory: (_ for _ in ()).throw(
            PermissionError("Access denied")
        ),
    )

    ready_events = []
    input_view.input_ready.connect(ready_events.append)

    assert input_view.validate_dataset() is False
    assert input_view.is_validated is False
    assert input_view.discovered_records == ()
    assert ready_events == []

    details = input_view.validation_view.details_label.text()
    assert "Dataset discovery failed" in details
    assert "Access denied" in details


def test_input_ready_is_emitted_only_after_successful_validation(
    input_view,
    tmp_path,
):
    dataset = create_valid_dataset(tmp_path / "dataset")
    input_view.set_input_directory(dataset)

    ready_events = []
    input_view.input_ready.connect(ready_events.append)

    assert input_view.validate_dataset() is True
    assert ready_events == [dataset.resolve()]


def test_browse_cancel_preserves_existing_selection(
    input_view,
    tmp_path,
    monkeypatch,
):
    dataset = create_valid_dataset(tmp_path / "dataset")
    input_view.set_input_directory(dataset)

    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: "",
    )

    input_view.file_import_view.choose_directory()

    assert input_view.selected_input_dir == dataset.resolve()
    assert input_view.file_import_view.selected_directory == (
        dataset.resolve()
    )
    assert input_view.is_validated is False

