# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""One running copy of the application on Windows, checked with a fake ``kernel32``."""

import threading

import pytest

from multazem.services import single_instance as si


class FakeKernel32:
    """A ``kernel32`` with just the functions the guard uses, backed by dictionaries.

    Attributes:
        mutexes: Names of the mutexes that exist.
        events: ``{name: number of times it was signalled}``.
        closed: The handles that were closed.
        waits: The results the next waits return, in order; ``0`` means "signalled".
    """

    def __init__(self):
        self.mutexes = set()
        self.events = {}
        self.closed = []
        self.waits = []
        self.last_error = 0

    def CreateMutexW(self, _security, _owner, name):  # noqa: N802 - the name of the real function
        """Creates a mutex, or opens the existing one and remembers that it existed."""
        self.last_error = 183 if name in self.mutexes else 0
        self.mutexes.add(name)
        return f"mutex:{name}"

    def CreateEventW(self, _security, _manual, _initial, name):  # noqa: N802
        """Creates an event."""
        self.events.setdefault(name, 0)
        return f"event:{name}"

    def OpenEventW(self, _access, _inherit, name):  # noqa: N802
        """Opens an event; returns ``None`` (a null handle) when it does not exist."""
        return f"event:{name}" if name in self.events else None

    def SetEvent(self, handle):  # noqa: N802
        """Signals an event."""
        self.events[handle.removeprefix("event:")] += 1
        return 1

    def WaitForSingleObject(self, _handle, _timeout):  # noqa: N802
        """Returns the next prepared result."""
        return self.waits.pop(0)

    def CloseHandle(self, handle):  # noqa: N802
        """Records a closed handle."""
        self.closed.append(handle)
        return 1


@pytest.fixture
def kernel(monkeypatch):
    """Makes the guard run its Windows code against a fake ``kernel32``; returns the fake."""
    fake = FakeKernel32()
    monkeypatch.setattr(si, "is_windows", lambda: True)
    monkeypatch.setattr(si, "_kernel32", lambda: fake)
    monkeypatch.setattr(si.ctypes, "get_last_error", lambda: fake.last_error, raising=False)
    return fake


def test_every_launch_is_the_first_one_off_windows(monkeypatch):
    monkeypatch.setattr(si, "is_windows", lambda: False)
    guard = si.SingleInstance()
    assert guard.acquire() is True
    assert guard.request_activation() is False
    guard.listen(lambda: None)  # nothing to listen to; must not raise


def test_the_first_copy_gets_the_mutex_and_creates_the_event(kernel):
    assert si.SingleInstance().acquire() is True
    assert si.MUTEX_NAME in kernel.mutexes and si.EVENT_NAME in kernel.events


def test_a_later_copy_is_refused_and_lets_go_of_the_mutex_handle(kernel):
    assert si.SingleInstance().acquire() is True
    assert si.SingleInstance().acquire() is False
    assert f"mutex:{si.MUTEX_NAME}" in kernel.closed


def test_a_system_that_cannot_create_the_mutex_does_not_block_the_launch(kernel):
    kernel.CreateMutexW = lambda *_args: None
    assert si.SingleInstance().acquire() is True


def test_a_later_copy_signals_the_event_of_the_first(kernel):
    si.SingleInstance().acquire()
    assert si.SingleInstance().request_activation() is True
    assert kernel.events[si.EVENT_NAME] == 1
    assert f"event:{si.EVENT_NAME}" in kernel.closed


def test_a_request_with_no_first_copy_to_receive_it_is_not_delivered(kernel):
    assert si.SingleInstance().request_activation() is False


def test_the_first_copy_runs_the_callback_for_every_request_until_the_wait_fails(kernel):
    guard = si.SingleInstance()
    guard.acquire()
    kernel.waits = [0, 0, 258]  # two requests, then a timeout ends the loop
    calls, finished = [], threading.Event()

    def callback():
        calls.append(1)
        if len(calls) == 2:
            finished.set()

    guard.listen(callback)
    assert finished.wait(5)
    assert calls == [1, 1]


def test_a_copy_that_does_not_own_the_event_listens_to_nothing(kernel):
    guard = si.SingleInstance()
    guard.listen(lambda: pytest.fail("there is nothing to wait for"))
