"""Tests for RunMetadata validation and JSON persistence."""

import json
from datetime import datetime, timezone

import pytest

from backend.run_manager.run_metadata import (
    RunMetadata,
    load_run_metadata,
    save_run_metadata,
)
from backend.run_manager.run_status import RunStatus


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def metadata():
    return RunMetadata(
        run_id="metadata-test-001",
        start_sol=107,
        end_sol=250,
        input_source="MEDA",
        source_info={"product": "example"},
        settings={"sample": True},
        application_version="1.0",
    )


# ---------------------------------------------------------------------
# Basic metadata tests
# ---------------------------------------------------------------------

def test_metadata_creation(metadata):
    assert metadata.run_id == "metadata-test-001"
    assert metadata.start_sol == 107
    assert metadata.end_sol == 250
    assert metadata.input_source == "MEDA"
    assert metadata.source_info == {"product": "example"}
    assert metadata.settings == {"sample": True}
    assert metadata.application_version == "1.0"
    assert metadata.status == RunStatus.PENDING.value
    assert metadata.failure_reason is None


def test_metadata_timestamps_are_timezone_aware(metadata):
    assert metadata.created_at.tzinfo is not None
    assert metadata.created_at.utcoffset() is not None


def test_metadata_rejects_empty_run_id():
    with pytest.raises(ValueError, match="run_id"):
        RunMetadata(run_id=" ")


# ---------------------------------------------------------------------
# SOL range validation
# ---------------------------------------------------------------------

def test_metadata_rejects_incomplete_sol_range():
    with pytest.raises(ValueError, match="both be provided"):
        RunMetadata(
            run_id="invalid-range",
            start_sol=107,
        )


def test_metadata_rejects_reversed_sol_range():
    with pytest.raises(ValueError, match="less than or equal"):
        RunMetadata(
            run_id="invalid-range",
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
def test_metadata_rejects_negative_sol_values(start_sol, end_sol):
    with pytest.raises(ValueError, match="non-negative"):
        RunMetadata(
            run_id="invalid-sol",
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
def test_metadata_rejects_non_integer_sol_values(
    start_sol,
    end_sol,
):
    with pytest.raises(TypeError, match="non-negative integer"):
        RunMetadata(
            run_id="invalid-sol",
            start_sol=start_sol,
            end_sol=end_sol,
        )


# ---------------------------------------------------------------------
# Status and failure reason validation
# ---------------------------------------------------------------------

def test_metadata_default_status_is_pending():
    metadata = RunMetadata(run_id="pending-run")

    assert metadata.status == RunStatus.PENDING.value


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
def test_metadata_accepts_supported_status_enum(status):
    metadata = RunMetadata(
        run_id="status-run",
        status=status,
    )

    assert metadata.status == status.value


@pytest.mark.parametrize(
    "status",
    [
        "pending",
        "running",
        "completed",
        "failed",
        "cancelled",
    ],
)
def test_metadata_normalizes_status_string(status):
    metadata = RunMetadata(
        run_id="status-run",
        status=status,
    )

    assert metadata.status == status.upper()


def test_metadata_rejects_unknown_status():
    with pytest.raises(ValueError, match="Unknown run status"):
        RunMetadata(
            run_id="invalid-status",
            status="UNKNOWN",
        )


def test_metadata_rejects_non_string_status():
    with pytest.raises(TypeError, match="status"):
        RunMetadata(
            run_id="invalid-status",
            status=123,
        )


def test_failed_metadata_accepts_failure_reason():
    metadata = RunMetadata(
        run_id="failed-run",
        status=RunStatus.FAILED,
        failure_reason="interrupted_by_restart",
    )

    assert metadata.status == RunStatus.FAILED.value
    assert metadata.failure_reason == "interrupted_by_restart"


def test_metadata_rejects_failure_reason_for_non_failed_status():
    with pytest.raises(
        ValueError,
        match="only be set when status is FAILED",
    ):
        RunMetadata(
            run_id="pending-run",
            status=RunStatus.PENDING,
            failure_reason="interrupted_by_restart",
        )


def test_metadata_rejects_empty_failure_reason():
    with pytest.raises(ValueError, match="must not be empty"):
        RunMetadata(
            run_id="failed-run",
            status=RunStatus.FAILED,
            failure_reason=" ",
        )


def test_metadata_rejects_non_string_failure_reason():
    with pytest.raises(TypeError, match="failure_reason"):
        RunMetadata(
            run_id="failed-run",
            status=RunStatus.FAILED,
            failure_reason=123,
        )


# ---------------------------------------------------------------------
# Timestamp validation
# ---------------------------------------------------------------------

def test_metadata_rejects_naive_created_at():
    with pytest.raises(ValueError, match="timezone-aware"):
        RunMetadata(
            run_id="invalid-time",
            created_at=datetime(2026, 1, 1),
        )


def test_metadata_rejects_naive_started_at():
    with pytest.raises(ValueError, match="timezone-aware"):
        RunMetadata(
            run_id="invalid-time",
            started_at=datetime(2026, 1, 1),
        )


def test_metadata_rejects_naive_finished_at():
    with pytest.raises(ValueError, match="timezone-aware"):
        RunMetadata(
            run_id="invalid-time",
            finished_at=datetime(2026, 1, 1),
        )


# ---------------------------------------------------------------------
# JSON mapping validation
# ---------------------------------------------------------------------

def test_metadata_rejects_non_mapping_source_info():
    with pytest.raises(TypeError, match="source_info"):
        RunMetadata(
            run_id="invalid-source",
            source_info=["not", "a", "mapping"],
        )


def test_metadata_rejects_non_mapping_settings():
    with pytest.raises(TypeError, match="settings"):
        RunMetadata(
            run_id="invalid-settings",
            settings=["not", "a", "mapping"],
        )


def test_metadata_rejects_non_json_source_info():
    with pytest.raises(ValueError, match="JSON-compatible"):
        RunMetadata(
            run_id="invalid-source",
            source_info={"value": object()},
        )


def test_metadata_rejects_non_json_settings():
    with pytest.raises(ValueError, match="JSON-compatible"):
        RunMetadata(
            run_id="invalid-settings",
            settings={"value": object()},
        )


# ---------------------------------------------------------------------
# Dictionary serialization tests
# ---------------------------------------------------------------------

def test_metadata_to_dict_contains_new_fields(metadata):
    data = metadata.to_dict()

    assert data["status"] == RunStatus.PENDING.value
    assert data["failure_reason"] is None


def test_metadata_to_dict_contains_all_expected_fields(metadata):
    data = metadata.to_dict()

    expected_fields = {
        "run_id",
        "start_sol",
        "end_sol",
        "created_at",
        "started_at",
        "finished_at",
        "input_source",
        "source_info",
        "settings",
        "application_version",
        "status",
        "failure_reason",
    }

    assert set(data) == expected_fields


def test_metadata_from_dict_restores_values(metadata):
    restored = RunMetadata.from_dict(metadata.to_dict())

    assert restored.run_id == metadata.run_id
    assert restored.start_sol == metadata.start_sol
    assert restored.end_sol == metadata.end_sol
    assert restored.input_source == metadata.input_source
    assert restored.source_info == metadata.source_info
    assert restored.settings == metadata.settings
    assert restored.application_version == metadata.application_version
    assert restored.status == metadata.status
    assert restored.failure_reason == metadata.failure_reason


def test_metadata_from_dict_restores_failed_status():
    data = {
        "run_id": "failed-run",
        "status": "FAILED",
        "failure_reason": "interrupted_by_restart",
    }

    restored = RunMetadata.from_dict(data)

    assert restored.status == RunStatus.FAILED.value
    assert restored.failure_reason == "interrupted_by_restart"


def test_metadata_from_dict_ignores_unknown_fields():
    data = {
        "run_id": "legacy-run",
        "unknown_future_field": "ignored",
    }

    restored = RunMetadata.from_dict(data)

    assert restored.run_id == "legacy-run"
    assert restored.status == RunStatus.PENDING.value


def test_metadata_from_dict_rejects_non_mapping():
    with pytest.raises(TypeError, match="Metadata data"):
        RunMetadata.from_dict(["invalid"])


def test_metadata_from_dict_requires_run_id():
    with pytest.raises(ValueError, match="missing run_id"):
        RunMetadata.from_dict({})


# ---------------------------------------------------------------------
# Backward compatibility tests
# ---------------------------------------------------------------------

def test_legacy_metadata_without_sol_and_status_fields():
    legacy_data = {
        "run_id": "legacy-run",
        "created_at": "2026-01-01T12:00:00+00:00",
        "started_at": None,
        "finished_at": None,
        "input_source": "MEDA",
        "source_info": {},
        "settings": {},
        "application_version": "1.0",
    }

    restored = RunMetadata.from_dict(legacy_data)

    assert restored.run_id == "legacy-run"
    assert restored.start_sol is None
    assert restored.end_sol is None
    assert restored.status == RunStatus.PENDING.value
    assert restored.failure_reason is None


# ---------------------------------------------------------------------
# JSON persistence tests
# ---------------------------------------------------------------------

def test_save_run_metadata_creates_json_file(metadata, tmp_path):
    file_path = tmp_path / "run" / "metadata.json"

    saved_path = save_run_metadata(metadata, file_path)

    assert saved_path == file_path.resolve()
    assert saved_path.is_file()


def test_save_run_metadata_writes_status_and_failure_reason(tmp_path):
    metadata = RunMetadata(
        run_id="failed-run",
        status=RunStatus.FAILED,
        failure_reason="interrupted_by_restart",
    )

    file_path = tmp_path / "metadata.json"

    save_run_metadata(metadata, file_path)

    data = json.loads(file_path.read_text(encoding="utf-8"))

    assert data["status"] == "FAILED"
    assert data["failure_reason"] == "interrupted_by_restart"


def test_load_run_metadata_restores_saved_metadata(metadata, tmp_path):
    file_path = tmp_path / "metadata.json"

    save_run_metadata(metadata, file_path)
    loaded = load_run_metadata(file_path)

    assert loaded.run_id == metadata.run_id
    assert loaded.start_sol == metadata.start_sol
    assert loaded.end_sol == metadata.end_sol
    assert loaded.status == metadata.status
    assert loaded.source_info == metadata.source_info
    assert loaded.settings == metadata.settings


def test_load_run_metadata_restores_failed_reason(tmp_path):
    metadata = RunMetadata(
        run_id="failed-run",
        status=RunStatus.FAILED,
        failure_reason="interrupted_by_restart",
    )

    file_path = tmp_path / "metadata.json"

    save_run_metadata(metadata, file_path)
    loaded = load_run_metadata(file_path)

    assert loaded.status == RunStatus.FAILED.value
    assert loaded.failure_reason == "interrupted_by_restart"


def test_load_run_metadata_rejects_non_object_json(tmp_path):
    file_path = tmp_path / "metadata.json"
    file_path.write_text(
        json.dumps(["invalid"]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="root must be an object"):
        load_run_metadata(file_path)


def test_save_run_metadata_rejects_invalid_object(tmp_path):
    with pytest.raises(TypeError, match="RunMetadata"):
        save_run_metadata(
            {"run_id": "invalid"},
            tmp_path / "metadata.json",
        )