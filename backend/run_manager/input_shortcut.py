"""Create a Windows shortcut to the original MEDA input directory.

Shortcut creation is optional and must never interrupt analysis.
No source data files are copied by this module.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path


__all__ = ["create_source_input_shortcut"]


SHORTCUT_FILENAME = "Open_Source_Input.lnk"


def create_source_input_shortcut(
    source_dir: str | Path,
    run_input_dir: str | Path,
) -> bool:
    """Create a Windows shortcut to the original source directory.

    Returns:
        True if the shortcut was created successfully, otherwise False.

    This function is deliberately non-fatal. Unsupported platforms,
    missing directories, unavailable PowerShell, and shortcut creation
    errors all return False.
    """
    try:
        if platform.system() != "Windows":
            return False

        source_path = Path(source_dir).expanduser().resolve()
        input_path = Path(run_input_dir).expanduser().resolve()

        if not source_path.is_dir() or not input_path.is_dir():
            return False

        powershell = (
            shutil.which("powershell.exe")
            or shutil.which("powershell")
        )

        if powershell is None:
            return False

        shortcut_path = input_path / SHORTCUT_FILENAME

        environment = os.environ.copy()
        environment["MWI_SHORTCUT_PATH"] = str(shortcut_path)
        environment["MWI_SHORTCUT_TARGET"] = str(source_path)

        script = (
            "$ErrorActionPreference = 'Stop'; "
            "$shell = New-Object -ComObject WScript.Shell; "
            "$shortcut = $shell.CreateShortcut("
            "$env:MWI_SHORTCUT_PATH); "
            "$shortcut.TargetPath = $env:MWI_SHORTCUT_TARGET; "
            "$shortcut.WorkingDirectory = $env:MWI_SHORTCUT_TARGET; "
            "$shortcut.Save()"
        )

        subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
            env=environment,
        )

        return shortcut_path.is_file()

    except Exception:
        # Shortcut creation must never stop a MEDA analysis.
        return False