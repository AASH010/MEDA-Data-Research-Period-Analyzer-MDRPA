from pathlib import Path
import subprocess

import pytest

from backend.run_manager import input_shortcut


def test_creates_shortcut_to_original_source_directory(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "original_meda"
    run_input_dir = tmp_path / "run" / "input"

    source_dir.mkdir()
    run_input_dir.mkdir(parents=True)

    source_file = source_dir / "example.txt"
    source_file.write_text("source data", encoding="utf-8")

    monkeypatch.setattr(
        input_shortcut.platform,
        "system",
        lambda: "Windows",
    )
    monkeypatch.setattr(
        input_shortcut.shutil,
        "which",
        lambda name: "powershell.exe",
    )

    def fake_run(command, **kwargs):
        shortcut_path = Path(
            kwargs["env"]["MWI_SHORTCUT_PATH"]
        )
        shortcut_path.write_bytes(b"test shortcut")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        input_shortcut.subprocess,
        "run",
        fake_run,
    )

    result = input_shortcut.create_source_input_shortcut(
        source_dir,
        run_input_dir,
    )

    shortcut = run_input_dir / "Open_Source_Input.lnk"

    assert result is True
    assert shortcut.is_file()
    assert source_file.read_text(encoding="utf-8") == "source data"
    assert not (run_input_dir / source_file.name).exists()


def test_returns_false_on_non_windows_platform(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "source"
    run_input_dir = tmp_path / "run" / "input"

    source_dir.mkdir()
    run_input_dir.mkdir(parents=True)

    monkeypatch.setattr(
        input_shortcut.platform,
        "system",
        lambda: "Linux",
    )

    result = input_shortcut.create_source_input_shortcut(
        source_dir,
        run_input_dir,
    )

    assert result is False
    assert not (
        run_input_dir / "Open_Source_Input.lnk"
    ).exists()


def test_returns_false_when_source_directory_is_missing(
    tmp_path,
    monkeypatch,
):
    run_input_dir = tmp_path / "run" / "input"
    run_input_dir.mkdir(parents=True)

    monkeypatch.setattr(
        input_shortcut.platform,
        "system",
        lambda: "Windows",
    )

    result = input_shortcut.create_source_input_shortcut(
        tmp_path / "missing-source",
        run_input_dir,
    )

    assert result is False


def test_returns_false_when_run_input_directory_is_missing(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    monkeypatch.setattr(
        input_shortcut.platform,
        "system",
        lambda: "Windows",
    )

    result = input_shortcut.create_source_input_shortcut(
        source_dir,
        tmp_path / "missing-input",
    )

    assert result is False


def test_returns_false_when_powershell_is_unavailable(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "source"
    run_input_dir = tmp_path / "run" / "input"

    source_dir.mkdir()
    run_input_dir.mkdir(parents=True)

    monkeypatch.setattr(
        input_shortcut.platform,
        "system",
        lambda: "Windows",
    )
    monkeypatch.setattr(
        input_shortcut.shutil,
        "which",
        lambda _name: None,
    )

    result = input_shortcut.create_source_input_shortcut(
        source_dir,
        run_input_dir,
    )

    assert result is False


def test_returns_false_when_shortcut_creation_fails(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "source"
    run_input_dir = tmp_path / "run" / "input"

    source_dir.mkdir()
    run_input_dir.mkdir(parents=True)

    monkeypatch.setattr(
        input_shortcut.platform,
        "system",
        lambda: "Windows",
    )
    monkeypatch.setattr(
        input_shortcut.shutil,
        "which",
        lambda _name: "powershell.exe",
    )

    def raise_error(*args, **kwargs):
        raise OSError("simulated shortcut failure")

    monkeypatch.setattr(
        input_shortcut.subprocess,
        "run",
        raise_error,
    )

    result = input_shortcut.create_source_input_shortcut(
        source_dir,
        run_input_dir,
    )

    assert result is False
    assert not (
        run_input_dir / "Open_Source_Input.lnk"
    ).exists()