# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Windows start-up work: finding the GTK runtime, console-less launches and the no-ops elsewhere."""

import ctypes
import io
import os
import sys
import types
from pathlib import Path

import pytest

from multazem import winsupport


@pytest.fixture
def on_windows(monkeypatch):
    """Makes the module believe it runs on Windows."""
    monkeypatch.setattr(winsupport, "is_windows", lambda: True)


@pytest.fixture
def off_windows(monkeypatch):
    """Makes the module believe it runs on another system, whichever one the tests really run on."""
    monkeypatch.setattr(winsupport, "is_windows", lambda: False)


@pytest.fixture
def message_boxes(monkeypatch):
    """Records the texts of the message boxes instead of opening them (a real one would wait for a click)."""
    shown = []
    monkeypatch.setattr(winsupport, "show_error_box", shown.append)
    return shown


def make_runtime(root: Path) -> Path:
    """Creates the folders that identify a GTK runtime under ``root`` and returns it."""
    (root / "bin").mkdir(parents=True)
    (root / "lib" / "girepository-1.0").mkdir(parents=True)
    return root


def test_a_folder_with_bin_and_typelibs_is_a_runtime(tmp_path):
    assert winsupport.is_gtk_runtime(make_runtime(tmp_path / "gtk"))


def test_a_folder_without_typelibs_is_not_a_runtime(tmp_path):
    (tmp_path / "bin").mkdir()
    assert not winsupport.is_gtk_runtime(tmp_path)


def test_the_environment_variable_names_the_first_candidate(monkeypatch, tmp_path):
    monkeypatch.setenv(winsupport.GTK_DIR_ENV, str(tmp_path / "mine"))
    assert winsupport.gtk_candidates()[0] == tmp_path / "mine"


def test_the_runtime_next_to_the_python_environment_is_a_candidate(monkeypatch, tmp_path):
    monkeypatch.delenv(winsupport.GTK_DIR_ENV, raising=False)
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "app" / ".venv"))
    assert winsupport.gtk_candidates()[0] == tmp_path / "app" / "gtk"


def test_the_first_candidate_that_is_a_runtime_wins(monkeypatch, tmp_path):
    runtime = make_runtime(tmp_path / "second")
    monkeypatch.setattr(winsupport, "gtk_candidates", lambda: [tmp_path / "missing", runtime, tmp_path / "third"])
    assert winsupport.find_gtk_runtime() == runtime


def test_no_runtime_is_none(monkeypatch, tmp_path):
    monkeypatch.setattr(winsupport, "gtk_candidates", lambda: [tmp_path / "missing"])
    assert winsupport.find_gtk_runtime() is None


def test_configuring_the_runtime_exposes_its_dlls_typelibs_schemas_and_icons(monkeypatch, tmp_path):
    gtk = make_runtime(tmp_path / "gtk")
    schemas = gtk / "share" / "glib-2.0" / "schemas"
    schemas.mkdir(parents=True)
    (schemas / "gschemas.compiled").write_bytes(b"")
    added = []
    monkeypatch.setattr(os, "add_dll_directory", added.append, raising=False)
    for name in ("PATH", "GI_TYPELIB_PATH", "XDG_DATA_DIRS", "GSETTINGS_SCHEMA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PATH", "existing")

    winsupport.configure_gtk(gtk)

    assert added == [str(gtk / "bin")]
    assert os.environ["PATH"].split(os.pathsep) == [str(gtk / "bin"), "existing"]
    assert os.environ["GI_TYPELIB_PATH"] == str(gtk / "lib" / "girepository-1.0")
    assert os.environ["XDG_DATA_DIRS"] == str(gtk / "share")
    assert os.environ["GSETTINGS_SCHEMA_DIR"] == str(schemas)


def test_configuring_twice_does_not_repeat_the_entries(monkeypatch, tmp_path):
    gtk = make_runtime(tmp_path / "gtk")
    monkeypatch.setattr(os, "add_dll_directory", lambda _path: None, raising=False)
    monkeypatch.setenv("PATH", "existing")
    winsupport.configure_gtk(gtk)
    winsupport.configure_gtk(gtk)
    assert os.environ["PATH"].split(os.pathsep).count(str(gtk / "bin")) == 1


def test_an_existing_schema_directory_setting_is_kept(monkeypatch, tmp_path):
    gtk = make_runtime(tmp_path / "gtk")
    schemas = gtk / "share" / "glib-2.0" / "schemas"
    schemas.mkdir(parents=True)
    (schemas / "gschemas.compiled").write_bytes(b"")
    monkeypatch.setattr(os, "add_dll_directory", lambda _path: None, raising=False)
    monkeypatch.setenv("GSETTINGS_SCHEMA_DIR", "D:\\mine")
    winsupport.configure_gtk(gtk)
    assert os.environ["GSETTINGS_SCHEMA_DIR"] == "D:\\mine"


def test_preparing_the_runtime_does_nothing_off_windows(off_windows, monkeypatch):
    monkeypatch.setattr(winsupport, "find_gtk_runtime", lambda: pytest.fail("must not look for GTK"))
    winsupport.prepare_runtime()


def test_preparing_the_runtime_on_windows_configures_what_it_finds(on_windows, monkeypatch, tmp_path):
    runtime = make_runtime(tmp_path / "gtk")
    steps = []
    monkeypatch.setattr(winsupport, "ensure_standard_streams", lambda: steps.append("streams"))
    monkeypatch.setattr(winsupport, "find_gtk_runtime", lambda: runtime)
    monkeypatch.setattr(winsupport, "configure_gtk", lambda gtk: steps.append(("gtk", gtk)))
    monkeypatch.setattr(winsupport, "set_app_user_model_id", lambda: steps.append("identity"))
    winsupport.prepare_runtime()
    assert steps == ["streams", ("gtk", runtime), "identity"]


def test_a_missing_runtime_is_not_an_error_at_start_up(on_windows, monkeypatch):
    monkeypatch.setattr(winsupport, "ensure_standard_streams", lambda: None)
    monkeypatch.setattr(winsupport, "find_gtk_runtime", lambda: None)
    monkeypatch.setattr(winsupport, "set_app_user_model_id", lambda: None)
    winsupport.prepare_runtime()


def test_a_program_without_a_console_logs_to_the_file(monkeypatch, tmp_path):
    log = tmp_path / "logs" / "multazem.log"
    monkeypatch.setattr(winsupport, "log_file", lambda: log)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    winsupport.ensure_standard_streams()
    try:
        sys.stdout.write("info line\n")
        sys.stderr.write("warning line\n")
        sys.stdout.flush()
    finally:
        sys.stdout.close()
    assert log.read_text(encoding="utf-8") == "info line\nwarning line\n"


def test_a_program_with_a_console_keeps_its_streams(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(winsupport, "log_file", lambda: tmp_path / "none" / "multazem.log")
    before = (sys.stdout, sys.stderr)
    winsupport.ensure_standard_streams()
    assert (sys.stdout, sys.stderr) == before
    assert not (tmp_path / "none").exists()


def test_a_redirected_stream_prints_a_placeholder_for_what_its_encoding_lacks(monkeypatch):
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)
    winsupport.ensure_standard_streams()
    stream.write("\u2713 installed")
    stream.flush()
    assert raw.getvalue() == b"? installed"


def test_a_log_that_grew_too_big_is_moved_aside(monkeypatch, tmp_path):
    log = tmp_path / "multazem.log"
    log.write_bytes(b"x" * (winsupport.MAX_LOG_BYTES + 1))
    monkeypatch.setattr(winsupport, "log_file", lambda: log)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    winsupport.ensure_standard_streams()
    sys.stderr.write("fresh\n")
    sys.stderr.close()
    assert log.read_text(encoding="utf-8") == "fresh\n"
    assert (tmp_path / "multazem.old").stat().st_size == winsupport.MAX_LOG_BYTES + 1


def test_an_unwritable_log_discards_the_output_instead_of_failing(monkeypatch, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    monkeypatch.setattr(winsupport, "log_file", lambda: blocker / "multazem.log")
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    winsupport.ensure_standard_streams()
    sys.stderr.write("lost\n")
    sys.stderr.close()


def test_the_missing_toolkit_message_names_the_installer_and_the_override(on_windows, message_boxes, capsys):
    winsupport.report_missing_toolkit(ImportError("DLL load failed"))
    message = capsys.readouterr().err
    assert "DLL load failed" in message and "install-windows.ps1" in message and winsupport.GTK_DIR_ENV in message
    assert message_boxes == [message.rstrip("\n")]


def test_the_missing_toolkit_is_not_reported_off_windows(off_windows, message_boxes, capsys):
    winsupport.report_missing_toolkit(ImportError("x"))
    assert capsys.readouterr().err == "" and message_boxes == []


@pytest.fixture
def user32(monkeypatch):
    """A stand-in for ``ctypes.windll.user32`` that records the message boxes that are asked for."""
    asked = []
    fake = types.SimpleNamespace(MessageBoxW=lambda *arguments: asked.append(arguments))
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(user32=fake), raising=False)
    return asked


def test_the_message_box_is_an_error_box_titled_with_the_program_name(monkeypatch, user32):
    monkeypatch.delenv(winsupport.NO_DIALOGS_ENV, raising=False)
    winsupport.show_error_box("text")
    assert user32 == [(None, "text", "Multazem", 0x10)]


def test_a_message_box_is_not_opened_when_the_environment_says_nobody_can_click_it(monkeypatch, user32):
    monkeypatch.setenv(winsupport.NO_DIALOGS_ENV, "1")
    winsupport.show_error_box("text")
    assert user32 == []


def test_no_icon_is_applied_off_windows(off_windows, monkeypatch):
    monkeypatch.setattr(winsupport, "windows_icon_file", lambda: pytest.fail("must not look for the icon"))
    winsupport.apply_icon_to_own_windows()
