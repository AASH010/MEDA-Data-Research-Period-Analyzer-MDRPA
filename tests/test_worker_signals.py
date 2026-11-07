
"""Tests for MEDA background worker signal definitions."""

from PySide6.QtCore import QObject

from backend.workers.worker_signals import WorkerSignals


def test_worker_signals_is_qobject():
    signals = WorkerSignals()

    assert isinstance(signals, QObject)


def test_started_signal_emits_without_arguments():
    signals = WorkerSignals()
    received = []

    signals.started.connect(
        lambda: received.append(True)
    )

    signals.started.emit()

    assert received == [True]


def test_stage_started_signal_emits_stage_name():
    signals = WorkerSignals()
    received = []

    signals.stage_started.connect(
        lambda stage_name: received.append(stage_name)
    )

    signals.stage_started.emit("quality_analyzer")

    assert received == ["quality_analyzer"]


def test_stage_completed_signal_emits_result_object():
    signals = WorkerSignals()
    received = []

    stage_result = object()

    signals.stage_completed.connect(
        lambda result: received.append(result)
    )

    signals.stage_completed.emit(stage_result)

    assert received == [stage_result]
    assert received[0] is stage_result


def test_progress_updated_signal_emits_percentage_and_message():
    signals = WorkerSignals()
    received = []

    signals.progress_updated.connect(
        lambda percentage, message: received.append(
            (percentage, message)
        )
    )

    signals.progress_updated.emit(
        50,
        "Quality Analyzer completed.",
    )

    assert received == [
        (50, "Quality Analyzer completed."),
    ]


def test_warning_occurred_signal_emits_message():
    signals = WorkerSignals()
    received = []

    signals.warning_occurred.connect(
        lambda message: received.append(message)
    )

    signals.warning_occurred.emit(
        "Some XML files could not be parsed."
    )

    assert received == [
        "Some XML files could not be parsed."
    ]


def test_error_occurred_signal_emits_message():
    signals = WorkerSignals()
    received = []

    signals.error_occurred.connect(
        lambda message: received.append(message)
    )

    signals.error_occurred.emit(
        "Pipeline execution failed."
    )

    assert received == [
        "Pipeline execution failed."
    ]


def test_finished_signal_emits_result_object():
    signals = WorkerSignals()
    received = []

    run_result = object()

    signals.finished.connect(
        lambda result: received.append(result)
    )

    signals.finished.emit(run_result)

    assert received == [run_result]
    assert received[0] is run_result


def test_cancelled_signal_emits_message():
    signals = WorkerSignals()
    received = []

    signals.cancelled.connect(
        lambda message: received.append(message)
    )

    signals.cancelled.emit(
        "Analysis cancelled after current stage completed."
    )

    assert received == [
        "Analysis cancelled after current stage completed."
    ]


def test_all_worker_signals_can_be_used_on_independent_instances():
    first = WorkerSignals()
    second = WorkerSignals()

    first_received = []
    second_received = []

    first.started.connect(
        lambda: first_received.append("first")
    )

    second.started.connect(
        lambda: second_received.append("second")
    )

    first.started.emit()

    assert first_received == ["first"]
    assert second_received == []
