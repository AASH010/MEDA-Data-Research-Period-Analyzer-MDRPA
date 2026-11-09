
"""Isolation, lifecycle, and recovery tests for RunManager."""

import json

import pytest

from backend.run_manager.run_manager import RunManager
from backend.run_manager.run_status import RunStatus


@pytest.fixture
def manager(tmp_path):
    return RunManager(runs_root=tmp_path / "runs")


# ---------------------------------------------------------------------
# Directory isolation tests
# ---------------------------------------------------------------------

def test_create_run_builds_isolated_directory_structure(manager):
    record = manager.create_run("run-a")

    assert record.paths.root_dir.is_dir()
    assert record.paths.input_dir.is_dir()
    assert record.paths.output_dir.is_dir()
    assert not (record.paths.root_dir / "logs").exists()

    assert record.status is RunStatus.PENDING


def test_each_run_has_separate_directories(manager):
    first = manager.create_run("run-a")
    second = manager.create_run("run-b")

    assert first.paths.root_dir != second.paths.root_dir
    assert first.paths.input_dir != second.paths.input_dir
    assert first.paths.output_dir != second.paths.output_dir
    assert not (first.paths.root_dir / "logs").exists()
    assert not (second.paths.root_dir / "logs").exists()


# ---------------------------------------------------------------------
# Metadata persistence tests
# ---------------------------------------------------------------------

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


# ---------------------------------------------------------------------
# SOL range run creation tests
# ---------------------------------------------------------------------

def test_create_run_generates_first_sequence_for_sol_range(manager):
    record = manager.create_run(
        start_sol=107,
        end_sol=250,
    )

    assert record.run_id == "run_range(107-250)_001"
    assert record.metadata.start_sol == 107
    assert record.metadata.end_sol == 250
    assert record.status is RunStatus.PENDING


def test_same_sol_range_increments_sequence(manager):
    first = manager.create_run(
        start_sol=107,
        end_sol=250,
    )
    second = manager.create_run(
        start_sol=107,
        end_sol=250,
    )
    third = manager.create_run(
        start_sol=107,
        end_sol=250,
    )

    assert first.run_id == "run_range(107-250)_001"
    assert second.run_id == "run_range(107-250)_002"
    assert third.run_id == "run_range(107-250)_003"


def test_different_sol_ranges_have_independent_sequences(manager):
    first_range_first = manager.create_run(
        start_sol=107,
        end_sol=250,
    )
    second_range_first = manager.create_run(
        start_sol=150,
        end_sol=300,
    )
    first_range_second = manager.create_run(
        start_sol=107,
        end_sol=250,
    )
    second_range_second = manager.create_run(
        start_sol=150,
        end_sol=300,
    )

    assert first_range_first.run_id == "run_range(107-250)_001"
    assert first_range_second.run_id == "run_range(107-250)_002"

    assert second_range_first.run_id == "run_range(150-300)_001"
    assert second_range_second.run_id == "run_range(150-300)_002"


def test_sol_range_is_persisted_in_metadata_json(manager):
    record = manager.create_run(
        start_sol=107,
        end_sol=250,
    )

    metadata_file = record.paths.root_dir / "metadata.json"

    assert metadata_file.is_file()

    data = json.loads(metadata_file.read_text(encoding="utf-8"))

    assert data["run_id"] == "run_range(107-250)_001"
    assert data["start_sol"] == 107
    assert data["end_sol"] == 250


def test_sol_range_can_be_loaded_from_manager(manager):
    record = manager.create_run(
        start_sol=107,
        end_sol=250,
    )

    loaded = manager.load_persisted_metadata(record.run_id)

    assert loaded.run_id == record.run_id
    assert loaded.start_sol == 107
    assert loaded.end_sol == 250


def test_sol_range_sequence_continues_with_new_manager(tmp_path):
    runs_root = tmp_path / "runs"

    first_manager = RunManager(runs_root=runs_root)

    first = first_manager.create_run(
        start_sol=107,
        end_sol=250,
    )

    second_manager = RunManager(runs_root=runs_root)

    second = second_manager.create_run(
        start_sol=107,
        end_sol=250,
    )

    assert first.run_id == "run_range(107-250)_001"
    assert second.run_id == "run_range(107-250)_002"


def test_sol_range_sequence_uses_existing_run_directories(manager):
    existing_run = manager.runs_root / "run_range(107-250)_004"
    existing_run.mkdir(parents=True)

    record = manager.create_run(
        start_sol=107,
        end_sol=250,
    )

    assert record.run_id == "run_range(107-250)_005"


# ---------------------------------------------------------------------
# SOL range validation tests
# ---------------------------------------------------------------------

def test_auto_generated_run_requires_sol_range(manager):
    with pytest.raises(
        ValueError,
        match="start_sol and end_sol are required",
    ):
        manager.create_run()


def test_auto_generated_run_rejects_incomplete_sol_range(manager):
    with pytest.raises(
        ValueError,
        match="both be provided",
    ):
        manager.create_run(start_sol=107)


def test_auto_generated_run_rejects_reversed_sol_range(manager):
    with pytest.raises(
        ValueError,
        match="less than or equal",
    ):
        manager.create_run(
            start_sol=250,
            end_sol=107,
        )


@pytest.mark.parametrize(
    ("start_sol", "end_sol"),
    [
        (-1, 100),
        (100, -1),
    ],
)
def test_auto_generated_run_rejects_negative_sol_values(
    manager,
    start_sol,
    end_sol,
):
    with pytest.raises(ValueError, match="non-negative"):
        manager.create_run(
            start_sol=start_sol,
            end_sol=end_sol,
        )


@pytest.mark.parametrize(
    ("start_sol", "end_sol"),
    [
        (True, 100),
        (100, False),
        (100.5, 200),
        (100, "200"),
    ],
)
def test_auto_generated_run_rejects_non_integer_sol_values(
    manager,
    start_sol,
    end_sol,
):
    with pytest.raises(TypeError):
        manager.create_run(
            start_sol=start_sol,
            end_sol=end_sol,
        )


# ---------------------------------------------------------------------
# Manual run ID compatibility tests
# ---------------------------------------------------------------------

def test_manual_run_id_remains_supported(manager):
    record = manager.create_run("manual-run-001")

    assert record.run_id == "manual-run-001"
    assert record.metadata.start_sol is None
    assert record.metadata.end_sol is None


def test_manual_run_id_can_include_sol_metadata(manager):
    record = manager.create_run(
        "manual-run-001",
        start_sol=107,
        end_sol=250,
    )

    assert record.run_id == "manual-run-001"
    assert record.metadata.start_sol == 107
    assert record.metadata.end_sol == 250


# ---------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------

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


# ---------------------------------------------------------------------
# Failure detail persistence tests
# ---------------------------------------------------------------------

def test_fail_run_persists_failure_reason(manager):
    manager.create_run("failed-run")
    manager.start_run("failed-run")

    failed = manager.fail_run(
        "failed-run",
        failure_reason="coverage_stage_failed",
    )

    assert failed.status is RunStatus.FAILED
    assert failed.metadata.failure_reason == "coverage_stage_failed"

    loaded = manager.load_persisted_metadata("failed-run")

    assert loaded.status == RunStatus.FAILED.value
    assert loaded.failure_reason == "coverage_stage_failed"


def test_fail_run_merges_settings_updates(manager):
    manager.create_run(
        "failed-run",
        settings={
            "mode": "analysis",
            "keep_existing": True,
        },
    )
    manager.start_run("failed-run")

    failed = manager.fail_run(
        "failed-run",
        failure_reason="pipeline_execution_failed",
        settings_updates={
            "execution_summary": {
                "status": "failed",
                "stages": [],
            },
            "additional_setting": "preserved",
        },
    )

    assert failed.status is RunStatus.FAILED
    assert failed.metadata.settings == {
        "mode": "analysis",
        "keep_existing": True,
        "execution_summary": {
            "status": "failed",
            "stages": [],
        },
        "additional_setting": "preserved",
    }

    loaded = manager.load_persisted_metadata("failed-run")

    assert loaded.settings == failed.metadata.settings
    assert loaded.failure_reason == "pipeline_execution_failed"


def test_fail_run_preserves_failure_details_after_recovery(tmp_path):
    runs_root = tmp_path / "runs"

    first_manager = RunManager(runs_root=runs_root)
    first_manager.create_run(
        "failed-run",
        settings={"original": True},
    )
    first_manager.start_run("failed-run")

    first_manager.fail_run(
        "failed-run",
        failure_reason="synchronization_stage_failed",
        settings_updates={
            "execution_summary": {
                "status": "failed",
                "stages": [
                    {
                        "stage_name": "synchronization",
                        "status": "failed",
                    }
                ],
            }
        },
    )

    recovered_manager = RunManager(runs_root=runs_root)
    recovered = recovered_manager.get_run("failed-run")

    assert recovered.status is RunStatus.FAILED
    assert (
        recovered.metadata.failure_reason
        == "synchronization_stage_failed"
    )
    assert recovered.metadata.settings["original"] is True
    assert recovered.metadata.settings["execution_summary"] == {
        "status": "failed",
        "stages": [
            {
                "stage_name": "synchronization",
                "status": "failed",
            }
        ],
    }


@pytest.mark.parametrize(
    "failure_reason",
    [
        "",
        " ",
        123,
    ],
)
def test_fail_run_rejects_invalid_failure_reason(
    manager,
    failure_reason,
):
    manager.create_run("failed-run")
    manager.start_run("failed-run")

    with pytest.raises((TypeError, ValueError)):
        manager.fail_run(
            "failed-run",
            failure_reason=failure_reason,
        )

    record = manager.get_run("failed-run")

    assert record.status is RunStatus.RUNNING
    assert record.metadata.failure_reason is None


@pytest.mark.parametrize(
    "settings_updates",
    [
        [],
        "invalid",
        123,
    ],
)
def test_fail_run_rejects_non_mapping_settings_updates(
    manager,
    settings_updates,
):
    manager.create_run("failed-run")
    manager.start_run("failed-run")

    with pytest.raises(TypeError, match="settings_updates"):
        manager.fail_run(
            "failed-run",
            settings_updates=settings_updates,
        )

    record = manager.get_run("failed-run")

    assert record.status is RunStatus.RUNNING
    assert record.metadata.settings == {}


def test_fail_run_rolls_back_metadata_when_persistence_fails(
    manager,
    monkeypatch,
):
    import backend.run_manager.run_manager as run_manager_module

    record = manager.create_run(
        "failed-run",
        settings={"original": True},
    )
    manager.start_run("failed-run")

    original_metadata = manager.load_persisted_metadata("failed-run")

    def raise_persistence_error(*args, **kwargs):
        raise OSError("simulated metadata persistence failure")

    monkeypatch.setattr(
        run_manager_module,
        "save_run_metadata",
        raise_persistence_error,
    )

    with pytest.raises(
        OSError,
        match="simulated metadata persistence failure",
    ):
        manager.fail_run(
            "failed-run",
            failure_reason="pipeline_failed",
            settings_updates={
                "execution_summary": {"status": "failed"},
            },
        )

    current = manager.get_run("failed-run")

    assert current.status is RunStatus.RUNNING
    assert current.metadata.status == RunStatus.RUNNING.value
    assert current.metadata.failure_reason is None
    assert current.metadata.settings == {"original": True}

    persisted = manager.load_persisted_metadata("failed-run")

    assert persisted.status == original_metadata.status
    assert persisted.failure_reason == original_metadata.failure_reason
    assert persisted.settings == original_metadata.settings


# ---------------------------------------------------------------------
# Recovery tests
# ---------------------------------------------------------------------

def test_recovery_restores_pending_run_without_changing_status(tmp_path):
    runs_root = tmp_path / "runs"

    first_manager = RunManager(runs_root=runs_root)
    first_manager.create_run("pending-run")

    recovered_manager = RunManager(runs_root=runs_root)

    recovered = recovered_manager.get_run("pending-run")

    assert recovered.status is RunStatus.PENDING
    assert recovered.metadata.status == RunStatus.PENDING.value
    assert recovered.metadata.failure_reason is None


@pytest.mark.parametrize(
    ("finalize_method", "expected_status"),
    [
        ("complete_run", RunStatus.COMPLETED),
        ("fail_run", RunStatus.FAILED),
        ("cancel_run", RunStatus.CANCELLED),
    ],
)
def test_recovery_preserves_terminal_statuses(
    tmp_path,
    finalize_method,
    expected_status,
):
    runs_root = tmp_path / "runs"

    first_manager = RunManager(runs_root=runs_root)
    first_manager.create_run("terminal-run")

    if finalize_method == "cancel_run":
        getattr(first_manager, finalize_method)("terminal-run")
    else:
        first_manager.start_run("terminal-run")
        getattr(first_manager, finalize_method)("terminal-run")

    recovered_manager = RunManager(runs_root=runs_root)

    recovered = recovered_manager.get_run("terminal-run")

    assert recovered.status is expected_status
    assert recovered.metadata.status == expected_status.value

    if expected_status is RunStatus.FAILED:
        assert recovered.metadata.failure_reason is None


def test_recovery_marks_interrupted_running_run_as_failed(tmp_path):
    runs_root = tmp_path / "runs"

    first_manager = RunManager(runs_root=runs_root)
    first_manager.create_run("interrupted-run")
    first_manager.start_run("interrupted-run")

    recovered_manager = RunManager(runs_root=runs_root)

    recovered = recovered_manager.get_run("interrupted-run")

    assert recovered.status is RunStatus.FAILED
    assert recovered.metadata.status == RunStatus.FAILED.value
    assert (
        recovered.metadata.failure_reason
        == "interrupted_by_restart"
    )
    assert recovered.metadata.started_at is not None
    assert recovered.metadata.finished_at is not None

    persisted = json.loads(
        (
            runs_root
            / "interrupted-run"
            / "metadata.json"
        ).read_text(encoding="utf-8")
    )

    assert persisted["status"] == RunStatus.FAILED.value
    assert persisted["failure_reason"] == "interrupted_by_restart"
    assert persisted["finished_at"] is not None


def test_recovery_does_not_change_existing_finished_timestamp(tmp_path):
    runs_root = tmp_path / "runs"

    first_manager = RunManager(runs_root=runs_root)
    first_manager.create_run("interrupted-run")
    first_manager.start_run("interrupted-run")

    metadata_file = (
        runs_root
        / "interrupted-run"
        / "metadata.json"
    )

    data = json.loads(metadata_file.read_text(encoding="utf-8"))
    existing_finished_at = "2026-01-01T12:00:00+00:00"
    data["finished_at"] = existing_finished_at

    metadata_file.write_text(
        json.dumps(data),
        encoding="utf-8",
    )

    recovered_manager = RunManager(runs_root=runs_root)

    recovered = recovered_manager.get_run("interrupted-run")

    assert recovered.status is RunStatus.FAILED
    assert recovered.metadata.finished_at.isoformat() == existing_finished_at


def test_recovery_supports_legacy_metadata_without_status(tmp_path):
    runs_root = tmp_path / "runs"

    first_manager = RunManager(runs_root=runs_root)
    first_manager.create_run("legacy-run")

    metadata_file = (
        runs_root
        / "legacy-run"
        / "metadata.json"
    )

    data = json.loads(metadata_file.read_text(encoding="utf-8"))
    data.pop("status", None)
    data.pop("failure_reason", None)

    metadata_file.write_text(
        json.dumps(data),
        encoding="utf-8",
    )

    recovered_manager = RunManager(runs_root=runs_root)

    recovered = recovered_manager.get_run("legacy-run")

    assert recovered.status is RunStatus.PENDING
    assert recovered.metadata.status == RunStatus.PENDING.value
    assert recovered.metadata.failure_reason is None


def test_recovery_skips_run_directory_without_metadata(tmp_path):
    runs_root = tmp_path / "runs"
    incomplete_dir = runs_root / "incomplete-run"

    incomplete_dir.mkdir(parents=True)

    recovered_manager = RunManager(runs_root=runs_root)

    assert recovered_manager.list_runs() == ()
    assert incomplete_dir.is_dir()


def test_recovery_rejects_metadata_with_mismatched_run_id(tmp_path):
    runs_root = tmp_path / "runs"

    first_manager = RunManager(runs_root=runs_root)
    first_manager.create_run("actual-run")

    metadata_file = (
        runs_root
        / "actual-run"
        / "metadata.json"
    )

    data = json.loads(metadata_file.read_text(encoding="utf-8"))
    data["run_id"] = "different-run"

    metadata_file.write_text(
        json.dumps(data),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="does not match metadata run_id",
    ):
        RunManager(runs_root=runs_root)


def test_recovery_registers_multiple_runs(tmp_path):
    runs_root = tmp_path / "runs"

    first_manager = RunManager(runs_root=runs_root)

    first_manager.create_run("run-a")
    first_manager.create_run("run-b")
    first_manager.create_run("run-c")

    recovered_manager = RunManager(runs_root=runs_root)

    assert len(recovered_manager.list_runs()) == 3

    assert tuple(
        record.run_id
        for record in recovered_manager.list_runs()
    ) == (
        "run-a",
        "run-b",
        "run-c",
    )


# ---------------------------------------------------------------------
# Error handling and status transition tests
# ---------------------------------------------------------------------

def test_duplicate_run_id_is_rejected(manager):
    manager.create_run("run-a")

    with pytest.raises(FileExistsError):
        manager.create_run("run-a")


def test_invalid_status_transition_is_rejected(manager):
    manager.create_run("run-a")

    with pytest.raises(
        ValueError,
        match="Invalid run status transition",
    ):
        manager.complete_run("run-a")

    assert manager.get_run("run-a").status is RunStatus.PENDING


def test_terminal_run_cannot_be_restarted(manager):
    manager.create_run("run-a")
    manager.start_run("run-a")
    manager.complete_run("run-a")

    with pytest.raises(
        ValueError,
        match="Invalid run status transition",
    ):
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
