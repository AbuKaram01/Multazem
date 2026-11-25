# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Writing a JSON file so that readers never see half of it, including the retry that Windows needs."""

import json
from pathlib import Path

import pytest

from multazem.services import atomic_json


@pytest.fixture
def folder(tmp_path):
    """An empty directory of its own (the temporary directory of a test already holds the ``run`` directory)."""
    directory = tmp_path / "files"
    directory.mkdir()
    return directory


@pytest.fixture
def pauses(monkeypatch):
    """Replaces the pause between two attempts by a recorder, so the tests do not wait."""
    recorded = []
    monkeypatch.setattr(atomic_json.time, "sleep", recorded.append)
    return recorded


def locked_target(monkeypatch, refusals):
    """Makes ``Path.replace`` refuse ``refusals`` times with ``PermissionError``; returns the list of its calls."""
    real_replace = Path.replace
    calls = []

    def replace(self, target):
        calls.append(target)
        if len(calls) <= refusals:
            raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    return calls


def test_the_data_is_written_as_utf8_json_in_a_directory_that_is_created(tmp_path):
    target = tmp_path / "new" / "data.json"
    atomic_json.write_json_atomic(target, {"city": "القاهرة"})
    assert json.loads(target.read_bytes()) == {"city": "القاهرة"}
    assert [p.name for p in target.parent.iterdir()] == ["data.json"]


def test_on_windows_a_file_that_a_reader_has_open_is_replaced_once_the_reader_lets_go(monkeypatch, folder, pauses):
    monkeypatch.setattr(atomic_json, "is_windows", lambda: True)
    target = folder / "data.json"
    target.write_text("{}", encoding="utf-8")
    calls = locked_target(monkeypatch, refusals=3)
    atomic_json.write_json_atomic(target, {"n": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"n": 1}
    assert len(calls) == 4 and len(pauses) == 3
    assert [p.name for p in folder.iterdir()] == ["data.json"]


def test_on_windows_a_file_that_stays_locked_is_reported_and_leaves_the_old_one_untouched(monkeypatch, folder, pauses):
    monkeypatch.setattr(atomic_json, "is_windows", lambda: True)
    target = folder / "data.json"
    target.write_text('{"old": true}', encoding="utf-8")
    calls = locked_target(monkeypatch, refusals=10**6)
    with pytest.raises(PermissionError):
        atomic_json.write_json_atomic(target, {"n": 1})
    assert len(calls) == atomic_json.REPLACE_ATTEMPTS and len(pauses) == atomic_json.REPLACE_ATTEMPTS - 1
    assert json.loads(target.read_text(encoding="utf-8")) == {"old": True}
    assert [p.name for p in folder.iterdir()] == ["data.json"]


def test_elsewhere_a_refused_replacement_is_reported_at_once(monkeypatch, folder, pauses):
    monkeypatch.setattr(atomic_json, "is_windows", lambda: False)
    target = folder / "data.json"
    calls = locked_target(monkeypatch, refusals=10**6)
    with pytest.raises(PermissionError):
        atomic_json.write_json_atomic(target, {"n": 1})
    assert len(calls) == 1 and pauses == []
    assert list(folder.iterdir()) == []
