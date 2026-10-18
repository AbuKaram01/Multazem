# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The command-line entry point :func:`multazem.app.main`, with the application and the guard replaced by fakes."""

import pytest

pytest.importorskip("gi")

from multazem import app


class FakeInstance:
    """A single-instance guard that records what was asked of it.

    Attributes:
        first: What :meth:`acquire` answers: ``True`` when this launch is the first copy.
        asked: Whether another running copy was asked to show its window.
    """

    def __init__(self, first):
        self.first = first
        self.asked = False

    def acquire(self):
        """Returns whether this launch is the first copy."""
        return self.first

    def request_activation(self):
        """Records that the running copy was asked to show its window."""
        self.asked = True
        return True


@pytest.fixture
def entry(monkeypatch):
    """Replaces everything ``main`` starts and returns a dictionary that records what was started."""
    started = {"headless": 0, "window": []}
    monkeypatch.setattr(app, "configure_logging", lambda: None)
    monkeypatch.setattr(app, "run_headless", lambda: started.__setitem__("headless", started["headless"] + 1))

    class FakeApp:
        """An application whose ``run`` only records the arguments."""

        def __init__(self, instance):
            started["instance"] = instance

        def run(self, argv):
            """Records the command line and reports success."""
            started["window"].append(argv)
            return 0

    monkeypatch.setattr(app, "MultazemApp", FakeApp)
    return started


def use(monkeypatch, argv, first=True):
    """Sets the command line and a guard that is (or is not) the first copy; returns the guard."""
    instance = FakeInstance(first)
    monkeypatch.setattr(app, "SingleInstance", lambda: instance)
    monkeypatch.setattr(app.sys, "argv", ["multazem", *argv])
    return instance


def test_version_prints_and_starts_nothing(monkeypatch, entry, capsys):
    use(monkeypatch, ["--version"])
    assert app.main() == 0
    assert capsys.readouterr().out == f"multazem {app.__version__}\n"
    assert entry["headless"] == 0 and entry["window"] == []


def test_headless_runs_the_scheduler_without_a_window_or_the_guard(monkeypatch, entry):
    instance = use(monkeypatch, ["--headless"], first=False)
    assert app.main() == 0
    assert entry["headless"] == 1 and entry["window"] == [] and not instance.asked


def test_the_first_launch_opens_the_window_with_the_guard(monkeypatch, entry):
    instance = use(monkeypatch, ["--some-gtk-option"])
    assert app.main() == 0
    assert entry["window"] == [["multazem", "--some-gtk-option"]]
    assert entry["instance"] is instance and not instance.asked


def test_a_second_launch_only_asks_the_first_copy_to_show_its_window(monkeypatch, entry):
    instance = use(monkeypatch, [], first=False)
    assert app.main() == 0
    assert instance.asked and entry["window"] == []
