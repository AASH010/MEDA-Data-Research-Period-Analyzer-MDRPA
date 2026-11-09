
"""Central per-Run logging for MEDA analysis executions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


__all__ = ["RunLogger"]


class RunLogger:
    """Write chronological operational events to one Run log file."""

    def __init__(
        self,
        logs_root: str | Path,
        run_id: str,
    ) -> None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string.")

        self.logs_root = Path(logs_root).expanduser().resolve()
        self.logs_root.mkdir(parents=True, exist_ok=True)

        self.log_path = self.logs_root / f"{run_id}_log.txt"
        self._lock = Lock()
        self._closed = False
        self._file = self.log_path.open(
            "x",
            encoding="utf-8",
            newline="\n",
        )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(
            timespec="milliseconds"
        )

    def log(
        self,
        level: str,
        message: str,
        *,
        timestamp: str | None = None,
    ) -> None:
        """Write one timestamped operational event."""
        if not isinstance(level, str) or not level.strip():
            raise ValueError("level must be a non-empty string.")

        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string.")

        event_time = timestamp or self._timestamp()

        with self._lock:
            if self._closed:
                return

            self._file.write(
                f"{event_time} [{level.upper()}] {message}\n"
            )
            self._file.flush()

    def log_stage_started(
        self,
        stage_name: str,
        *,
        timestamp: str,
    ) -> None:
        self.log(
            "INFO",
            f"Stage started: {stage_name}",
            timestamp=timestamp,
        )

    def log_stage_finished(
        self,
        stage_name: str,
        status: str,
        *,
        timestamp: str,
    ) -> None:
        self.log(
            "INFO",
            f"Stage finished: {stage_name} | status={status}",
            timestamp=timestamp,
        )

    def close(self) -> None:
        """Flush and close the file safely; repeated calls are harmless."""
        with self._lock:
            if self._closed:
                return

            try:
                self._file.flush()
            finally:
                self._file.close()
                self._closed = True

    def __enter__(self) -> "RunLogger":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
