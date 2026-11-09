
from pathlib import Path

import pytest

from backend.run_manager.run_logger import RunLogger


def test_creates_log_inside_central_logs_directory(tmp_path):
    logs_dir = tmp_path / "user_data" / "logs"

    logger = RunLogger(logs_dir, "run-test-001")
    logger.log("INFO", "Run started")
    logger.close()

    assert logger.log_path == logs_dir / "run-test-001_log.txt"
    assert logger.log_path.is_file()
    assert not (tmp_path / "runs" / "run-test-001" / "log.txt").exists()


def test_records_events_in_write_order(tmp_path):
    logger = RunLogger(tmp_path / "logs", "ordered-run")

    logger.log("INFO", "Run started")
    logger.log("INFO", "Stage started: file_discovery")
    logger.log("WARNING", "Example warning")
    logger.log("ERROR", "Example error")
    logger.log("INFO", "Run finished: status=FAILED")
    logger.close()

    content = logger.log_path.read_text(encoding="utf-8")

    expected = [
        "Run started",
        "Stage started: file_discovery",
        "Example warning",
        "Example error",
        "Run finished: status=FAILED",
    ]

    positions = [content.index(item) for item in expected]
    assert positions == sorted(positions)


def test_records_supplied_stage_timestamps(tmp_path):
    logger = RunLogger(tmp_path / "logs", "timestamp-run")

    logger.log_stage_started(
        "file_discovery",
        timestamp="2026-01-01T10:00:00+00:00",
    )
    logger.log_stage_finished(
        "file_discovery",
        "completed",
        timestamp="2026-01-01T10:00:05+00:00",
    )
    logger.close()

    content = logger.log_path.read_text(encoding="utf-8")

    assert "2026-01-01T10:00:00+00:00" in content
    assert "2026-01-01T10:00:05+00:00" in content


def test_close_is_safe_when_called_multiple_times(tmp_path):
    logger = RunLogger(tmp_path / "logs", "close-run")

    logger.log("INFO", "Before close")
    logger.close()
    logger.close()

    assert logger.log_path.is_file()


def test_writes_after_close_are_ignored(tmp_path):
    logger = RunLogger(tmp_path / "logs", "closed-run")

    logger.log("INFO", "Before close")
    logger.close()
    logger.log("INFO", "After close")

    content = logger.log_path.read_text(encoding="utf-8")

    assert "Before close" in content
    assert "After close" not in content


def test_context_manager_closes_log(tmp_path):
    with RunLogger(tmp_path / "logs", "context-run") as logger:
        logger.log("INFO", "Inside context")

    assert logger.log_path.is_file()
    assert "Inside context" in logger.log_path.read_text(
        encoding="utf-8"
    )


def test_rejects_empty_run_id(tmp_path):
    with pytest.raises(ValueError):
        RunLogger(tmp_path / "logs", "")


def test_does_not_overwrite_existing_run_log(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    existing = logs_dir / "duplicate-run_log.txt"
    existing.write_text("Existing log", encoding="utf-8")

    with pytest.raises(FileExistsError):
        RunLogger(logs_dir, "duplicate-run")

    assert existing.read_text(encoding="utf-8") == "Existing log"
