"""Isolation and integration tests for RunManager."""

import json

import pytest

from backend.run_manager.run_manager import RunManager
from backend.run_manager.run_status import RunStatus


@pytest.fixture
def manager(tmp_path):
    return RunManager(runs_root=tmp_path / "runs")


def test_create_run_builds_isolated_directory_structure(manager):
    record = manager.create_run("run-a")

    assert record.paths.root_dir.is_dir()
    assert record.paths.input_dir.is_dir()
    assert record.paths.output_dir.is_dir()
    assert record.paths.logs_dir.is_dir()

    assert record.status is RunStatus.PENDING


def test_each_run_has_separate_directories(manager):
    first = manager.create_run("run-a")
    second = manager.create_run("run-b")

    assert first.paths.root_dir != second.paths.root_dir
    assert first.paths.input_dir != second.paths.input_dir
    assert first.paths.output_dir != second.paths.output_dir
    assert first.paths.logs_dir != second.paths.logs_dir


def test_each_run_has_separate_persisted_metadata(manager):
    first = manager.create_run(
        "run-a",
        input_source="source-a",
        settings={"mode": "first"},
    )
    second = manager.create_run(
        "run-b",
        input_source="source-b",
        settings={"mode": "second"},
    )

    first_file = first.paths.root_dir / "metadata.json"
    second_file = second.paths.root_dir / "metadata.json"

    assert first_file.is_file()
    assert second_file.is_file()
    assert first_file != second_file

    first_data = json.loads(first_file.read_text(encoding="utf-8"))
    second_data = json.loads(second_file.read_text(encoding="utf-8"))

    assert first_data["run_id"] == "run-a"
    assert second_data["run_id"] == "run-b"
    assert first_data["settings"]["mode"] == "first"
    assert second_data["settings"]["mode"] == "second"


def test_run_metadata_is_retrievable_from_manager(manager):
    record = manager.create_run(
        "run-a",
        input_source="MEDA",
        source_info={"product": "example"},
        settings={"sample": True},
        application_version="1.0",
    )

    loaded = manager.load_persisted_metadata("run-a")

    assert loaded.run_id == record.run_id
    assert loaded.input_source == "MEDA"
    assert loaded.source_info == {"product": "example"}
    assert loaded.settings == {"sample": True}
    assert loaded.application_version == "1.0"


def test_start_and_complete_run_persist_lifecycle_timestamps(manager):
    manager.create_run("run-a")

    started = manager.start_run("run-a")

    assert started.status is RunStatus.RUNNING
    assert started.metadata.started_at is not None

    completed = manager.complete_run("run-a")

    assert completed.status is RunStatus.COMPLETED
    assert completed.metadata.finished_at is not None

    loaded = manager.load_persisted_metadata("run-a")

    assert loaded.started_at == completed.metadata.started_at
    assert loaded.finished_at == completed.metadata.finished_at


def test_status_update_does_not_change_another_run(manager):
    manager.create_run("run-a")
    manager.create_run("run-b")

    manager.start_run("run-a")

    assert manager.get_run("run-a").status is RunStatus.RUNNING
    assert manager.get_run("run-b").status is RunStatus.PENDING


def test_cancel_pending_run(manager):
    manager.create_run("run-a")

    cancelled = manager.cancel_run("run-a")

    assert cancelled.status is RunStatus.CANCELLED
    assert cancelled.metadata.finished_at is not None


def test_fail_running_run(manager):
    manager.create_run("run-a")
    manager.start_run("run-a")

    failed = manager.fail_run("run-a")

    assert failed.status is RunStatus.FAILED
    assert failed.metadata.started_at is not None
    assert failed.metadata.finished_at is not None


def test_duplicate_run_id_is_rejected(manager):
    manager.create_run("run-a")

    with pytest.raises(FileExistsError):
        manager.create_run("run-a")


def test_invalid_status_transition_is_rejected(manager):
    manager.create_run("run-a")

    with pytest.raises(ValueError, match="Invalid run status transition"):
        manager.complete_run("run-a")

    assert manager.get_run("run-a").status is RunStatus.PENDING


def test_terminal_run_cannot_be_restarted(manager):
    manager.create_run("run-a")
    manager.start_run("run-a")
    manager.complete_run("run-a")

    with pytest.raises(ValueError, match="Invalid run status transition"):
        manager.start_run("run-a")


def test_list_runs_returns_all_runs(manager):
    manager.create_run("run-c")
    manager.create_run("run-a")
    manager.create_run("run-b")

    records = manager.list_runs()

    assert tuple(record.run_id for record in records) == (
        "run-a",
        "run-b",
        "run-c",
    )


def test_invalid_run_id_is_rejected(manager):
    with pytest.raises(ValueError, match="run_id"):
        manager.create_run(" ")