# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""What the tests of the Windows installation files share.

That is where the project is, which tools a test needs, and how to run a PowerShell script of the project.
"""

import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

APP_ID = "com.github.multazem"

WINDOWS = ROOT / "packaging" / "windows"

BUNDLE = ROOT / "scripts" / "python-bundle.ps1"

CI = ROOT / ".github" / "workflows" / "ci.yml"

needs_pwsh = pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 (pwsh) is not available")


def read(path: Path) -> str:
    """Returns the text of a project file."""
    return path.read_text(encoding="utf-8")


def make_executable(path: Path, text: str) -> Path:
    """Writes ``text`` to ``path``, makes the file executable and returns the path."""
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def run_gtk_script(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    """Runs ``body`` in PowerShell with scripts/gtk-portable.ps1 loaded, and returns the finished process."""
    script = tmp_path / "case.ps1"
    script.write_text(f". '{ROOT / 'scripts' / 'gtk-portable.ps1'}'\n{body}\n", encoding="utf-8")
    return subprocess.run(["pwsh", "-NoProfile", "-File", str(script)], capture_output=True, text=True, check=False)
