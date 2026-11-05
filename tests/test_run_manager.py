
"""Tests for run status rules and the in-memory run registry."""

import pytest

from backend.run_manager.run_metadata import RunMetadata
from backend.run_manager.run_paths import RunPaths
from backend.run_manager.run_registry import RunRecord, RunRegistry
from backend.run_manager.run_status import (
    TERMINAL_STATUSES,
    RunStatus,
    can_transition,
    validate_transition,
)


# ---------------------------------------------------------------------
# RunStatus tests
# ---------------------------------------------------------------------

def test_run_status_contains_all_supported_states():
    assert {status.value for status in RunStatus} == {
        "PENDING",
        "RUNNING",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }


def test_terminal_statuses_are_correct():
    assert TERMINAL_STATUSES == {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }

    assert RunStatus.PENDING.is_terminal is False
    assert RunStatus.RUNNING.is_terminal is False

    for status in TERMINAL_STATUSES:
        assert status.is_terminal is True


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunStatus.PENDING, RunStatus.RUNNING),
        (RunStatus.PENDING, RunStatus.CANCELLED),
        (RunStatus.RUNNING, RunStatus.COMPLETED),
        (RunStatus.RUNNING, RunStatus.FAILED),
        (RunStatus.RUNNING, RunStatus.CANCELLED),
        ("pending", "running"),
        ("running", "completed"),
    ],
)
def test_allowed_transitions(current, target):
    assert can_transition(current, target) is True


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunStatus.PENDING, RunStatus.COMPLETED),
        (RunStatus.PENDING, RunStatus.FAILED),
        (RunStatus.RUNNING, RunStatus.PENDING),
        (RunStatus.COMPLETED, RunStatus.RUNNING),
        (RunStatus.FAILED, RunStatus.RUNNING),
        (RunStatus.CANCELLED, RunStatus.RUNNING),
        (RunStatus.COMPLETED, RunStatus.FAILED),
    ],
)
def test_disallowed_transitions(current, target):
    assert can_transition(current, target) is False


def test_validate_transition_returns_target_enum():
    result = validate_transition("pending", "running")

    assert result is RunStatus.RUNNING


def test_validate_transition_rejects_disallowed_transition():
    with pytest.raises(ValueError, match="Invalid run status transition"):
        validate_transition(
            RunStatus.COMPLETED,
            RunStatus.RUNNING,
        )


def test_unknown_status_is_rejected():
    with pytest.raises(ValueError, match="Unknown run status"):
        can_transition("UNKNOWN", "RUNNING")


def test_non_string_status_is_rejected():
    with pytest.raises(TypeError, match="status must be"):
        can_transition(123, RunStatus.RUNNING)


# ---------------------------------------------------------------------
# RunRegistry fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def registry():
    return RunRegistry()


@pytest.fixture
def registered_run(tmp_path, registry):
    run_id = "test-run-001"

    paths = RunPaths.create(
        run_id=run_id,
        runs_root=tmp_path,
    )

    metadata = RunMetadata(
        run_id=run_id,
        input_source="MEDA",
        settings={"sample": True},
    )

    record = registry.register(paths, metadata)

    return registry, record


# ---------------------------------------------------------------------
# RunRecord tests
# ---------------------------------------------------------------------

def test_run_record_contains_matching_run_information(tmp_path):
    run_id = "record-test"

    paths = RunPaths.create(run_id, tmp_path)
    metadata = RunMetadata(run_id=run_id)

    record = RunRecord(
        run_id=run_id,
        paths=paths,
        metadata=metadata,
    )

    assert record.run_id == run_id
    assert record.paths is paths
    assert record.metadata is metadata
    assert record.status is RunStatus.PENDING


def test_run_record_rejects_mismatched_paths(tmp_path):
    paths = RunPaths.create("run-a", tmp_path)
    metadata = RunMetadata(run_id="run-a")

    with pytest.raises(ValueError, match="paths.run_id"):
        RunRecord(
            run_id="run-b",
            paths=paths,
            metadata=metadata,
        )


def test_run_record_rejects_mismatched_metadata(tmp_path):
    paths = RunPaths.create("run-a", tmp_path)
    metadata = RunMetadata(run_id="run-b")

    with pytest.raises(ValueError, match="metadata.run_id"):
        RunRecord(
            run_id="run-a",
            paths=paths,
            metadata=metadata,
        )


# ---------------------------------------------------------------------
# Registration and retrieval tests
# ---------------------------------------------------------------------

def test_register_run(registry, tmp_path):
    paths = RunPaths.create("run-001", tmp_path)
    metadata = RunMetadata(run_id="run-001")

    record = registry.register(paths, metadata)

    assert isinstance(record, RunRecord)
    assert record.run_id == "run-001"
    assert record.status is RunStatus.PENDING
    assert len(registry) == 1
    assert "run-001" in registry


def test_register_duplicate_run_id_is_rejected(registered_run):
    registry, record = registered_run

    with pytest.raises(ValueError, match="already registered"):
        registry.register(record.paths, record.metadata)


def test_register_rejects_mismatched_run_ids(registry, tmp_path):
    paths = RunPaths.create("run-a", tmp_path)
    metadata = RunMetadata(run_id="run-b")

    with pytest.raises(ValueError, match="must match"):
        registry.register(paths, metadata)

    assert len(registry) == 0


@pytest.mark.parametrize(
    "status",
    [
        RunStatus.PENDING,
        RunStatus.RUNNING,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    ],
)
def test_register_restores_status_from_metadata(
    registry,
    tmp_path,
    status,
):
    run_id = f"restored-{status.value.lower()}"

    paths = RunPaths.create(run_id, tmp_path)
    metadata = RunMetadata(
        run_id=run_id,
        status=status,
    )

    record = registry.register(paths, metadata)

    assert record.status is status
    assert registry.get(run_id).status is status


def test_register_explicit_status_overrides_metadata_status(
    registry,
    tmp_path,
):
    run_id = "explicit-status-run"

    paths = RunPaths.create(run_id, tmp_path)
    metadata = RunMetadata(
        run_id=run_id,
        status=RunStatus.RUNNING,
    )

    record = registry.register(
        paths,
        metadata,
        status=RunStatus.FAILED,
    )

    assert record.status is RunStatus.FAILED
    assert metadata.status == RunStatus.RUNNING.value


def test_register_rejects_invalid_explicit_status(
    registry,
    tmp_path,
):
    run_id = "invalid-status-run"

    paths = RunPaths.create(run_id, tmp_path)
    metadata = RunMetadata(run_id=run_id)

    with pytest.raises(TypeError, match="status must be"):
        registry.register(
            paths,
            metadata,
            status="RUNNING",
        )

    assert len(registry) == 0


def test_get_registered_run(registered_run):
    registry, record = registered_run

    retrieved = registry.get(record.run_id)

    assert retrieved is record


def test_get_unknown_run_raises_key_error(registry):
    with pytest.raises(KeyError, match="not registered"):
        registry.get("missing-run")


def test_list_runs_returns_sorted_records(registry, tmp_path):
    for run_id in ("run-c", "run-a", "run-b"):
        paths = RunPaths.create(run_id, tmp_path)
        metadata = RunMetadata(run_id=run_id)
        registry.register(paths, metadata)

    records = registry.list_runs()

    assert tuple(record.run_id for record in records) == (
        "run-a",
        "run-b",
        "run-c",
    )


def test_empty_registry_returns_empty_tuple(registry):
    assert registry.list_runs() == ()
    assert len(registry) == 0


# ---------------------------------------------------------------------
# Status update tests
# ---------------------------------------------------------------------

def test_update_status_successfully(registered_run):
    registry, record = registered_run

    updated = registry.update_status(
        record.run_id,
        RunStatus.RUNNING,
    )

    assert updated.status is RunStatus.RUNNING
    assert registry.get(record.run_id).status is RunStatus.RUNNING


def test_update_status_accepts_string_value(registered_run):
    registry, record = registered_run

    updated = registry.update_status(
        record.run_id,
        "running",
    )

    assert updated.status is RunStatus.RUNNING


def test_update_status_rejects_invalid_transition(registered_run):
    registry, record = registered_run

    with pytest.raises(ValueError, match="Invalid run status transition"):
        registry.update_status(
            record.run_id,
            RunStatus.COMPLETED,
        )

    assert registry.get(record.run_id).status is RunStatus.PENDING


def test_terminal_run_cannot_change_status(registered_run):
    registry, record = registered_run

    registry.update_status(record.run_id, RunStatus.RUNNING)
    registry.update_status(record.run_id, RunStatus.COMPLETED)

    with pytest.raises(ValueError, match="Invalid run status transition"):
        registry.update_status(record.run_id, RunStatus.FAILED)


def test_update_unknown_run_raises_key_error(registry):
    with pytest.raises(KeyError, match="not registered"):
        registry.update_status("missing-run", RunStatus.RUNNING)


def test_status_update_does_not_mutate_previous_record(registered_run):
    registry, original = registered_run

    updated = registry.update_status(
        original.run_id,
        RunStatus.RUNNING,
    )

    assert original.status is RunStatus.PENDING
    assert updated.status is RunStatus.RUNNING
    assert original is not updated
