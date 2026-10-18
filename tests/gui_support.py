# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Helpers for the GUI tests, which drive the real application in a subprocess (under Xvfb on Linux).

Every GUI test passes a *scenario* (Python source) to :func:`run_scenario`. The scenario runs in a
fresh interpreter with its own configuration directory, fills the ``out`` dictionary and ends with
``finish()``, which prints it as JSON for the test to assert on. The module is skipped entirely when
``xvfb-run`` (Linux only), PyGObject, GTK4 or libadwaita is not available.
"""

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

WINDOWS = sys.platform == "win32"

if not WINDOWS and not shutil.which("xvfb-run"):
    pytest.skip("xvfb-run is not available", allow_module_level=True)
gi = pytest.importorskip("gi")
try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw  # noqa: F401 - checks that libadwaita loads
except (ValueError, ImportError):
    pytest.skip("GTK4/libadwaita are not available", allow_module_level=True)

PRELUDE = """
import sys, os, json, re
os.environ.setdefault("GSK_RENDERER", "cairo")
from multazem import winsupport
winsupport.prepare_runtime()
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk, Adw
from multazem.app import MultazemApp
from multazem.i18n import tr
from multazem.core.prayers import Prayer
from multazem.ui.preferences.add_region_row import AddRegionRow
app = MultazemApp(); out = {}
ARABIC = re.compile(r"[\\u0600-\\u06ff]")
def finish(): print("RESULT " + json.dumps(out, ensure_ascii=False)); app.quit(); return False
def walk(w, acc):
    acc.append(w); c = w.get_first_child()
    while c: walk(c, acc); c = c.get_next_sibling()
    return acc
def find(root, cls, title=None):
    return [w for w in walk(root, []) if isinstance(w, cls) and (title is None or w.get_title() == title)]
def one(root, cls, title=None):
    found = find(root, cls, title)
    assert len(found) == 1, (cls.__name__, title, len(found))
    return found[0]
def model_strings(combo):
    model = combo.get_model()
    return [model.get_string(i) for i in range(model.get_n_items())]
def open_preferences():
    app._window.lookup_action("preferences").activate(None)
    return app._window._pref_dialog
"""


def run_scenario(tmp_path, body, settings=None, timeout=90):
    """Runs a scenario against the real application and returns what it reported.

    Args:
        tmp_path: The test's temporary directory; it becomes the scenario's configuration and runtime directory.
        body: The scenario source, appended to ``PRELUDE`` and followed by ``app.run([])``.
        settings: Content of the settings file to start with; ``None`` starts from the defaults.
        timeout: Seconds before the scenario is killed.

    Returns:
        ``(out, stderr)``: the dictionary the scenario passed to ``finish()`` and the process's stderr.
    """
    cfg = tmp_path / "cfg"
    if settings is not None:
        (cfg / "multazem").mkdir(parents=True)
        (cfg / "multazem" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    script = tmp_path / "scenario.py"
    script.write_text(PRELUDE + textwrap.dedent(body) + "\napp.run([])\n", encoding="utf-8")
    pythonpath = os.pathsep.join([str(ROOT / "src"), str(ROOT / "packaging" / "vendor")])
    env = {
        **os.environ,
        "XDG_CONFIG_HOME": str(cfg),
        "XDG_RUNTIME_DIR": str(tmp_path / "run"),
        "PYTHONPATH": pythonpath,
        "GDK_BACKEND": "x11",
        "LIBGL_ALWAYS_SOFTWARE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    command = ["xvfb-run", "-a", "-s", "-screen 0 1366x768x24", sys.executable, str(script)]
    if WINDOWS:
        # The runner's own desktop is the display; the folders that Windows programs use are redirected as well.
        run = tmp_path / "run"
        run.mkdir(exist_ok=True)
        for name in ("GDK_BACKEND", "LIBGL_ALWAYS_SOFTWARE"):
            del env[name]
        env.update(
            APPDATA=str(cfg),
            LOCALAPPDATA=str(tmp_path / "local"),
            TEMP=str(run),
            TMP=str(run),
            PYTHONUTF8="1",
        )
        command = [sys.executable, str(script)]
    result = subprocess.run(
        command,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )
    lines = [line for line in result.stdout.splitlines() if line.startswith("RESULT ")]
    assert lines, f"the scenario printed no RESULT\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr[-1500:]}"
    return json.loads(lines[-1][7:]), result.stderr


_ROWS = {
    "en": ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"],
    "ar": ["الفجر", "الشروق", "الظهر", "العصر", "المغرب", "العشاء"],
}
_JUMUAH = {"en": "Jumu'ah", "ar": "الجمعة"}


def expected_rows(language, friday):
    """Returns the names the six timetable rows should show.

    Args:
        language: ``"en"`` or ``"ar"``.
        friday: Whether the day on screen is a Friday, when the Dhuhr row is titled "Jumu'ah".
    """
    rows = list(_ROWS[language])
    if friday:
        rows[2] = _JUMUAH[language]
    return rows


def saved_settings(tmp_path):
    """Returns the settings the application has saved to disk during the scenario."""
    return json.loads((tmp_path / "cfg" / "multazem" / "settings.json").read_text(encoding="utf-8"))
