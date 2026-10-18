# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Stand-ins for the Windows registry, so the Windows code can be tested on any system."""

import sys
import types


class FakeKey:
    """An open registry key: a context manager over the dictionary of its values."""

    def __init__(self, values):
        self.values = values

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class FakeWinreg(types.ModuleType):
    """A minimal ``winreg`` that keeps its keys in a dictionary.

    Attributes:
        keys: ``{(root, path): {value name: value}}``.
        write_error: When set, creating a key and writing a value raise it.
    """

    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1
    KEY_SET_VALUE = 2

    def __init__(self):
        super().__init__("winreg")
        self.keys = {}
        self.write_error = None

    def CreateKey(self, root, path):  # noqa: N802 - the name of the real function
        """Opens a key, creating it first when it does not exist."""
        if self.write_error is not None:
            raise self.write_error
        return FakeKey(self.keys.setdefault((root, path), {}))

    def OpenKey(self, root, path, _reserved=0, _access=0):  # noqa: N802
        """Opens an existing key; a missing one raises ``FileNotFoundError`` like the real function."""
        if (root, path) not in self.keys:
            raise FileNotFoundError(path)
        return FakeKey(self.keys[(root, path)])

    def SetValueEx(self, key, name, _reserved, _kind, value):  # noqa: N802
        """Sets a value of an open key."""
        if self.write_error is not None:
            raise self.write_error
        key.values[name] = value

    def QueryValueEx(self, key, name):  # noqa: N802
        """Returns ``(value, kind)``; a missing value raises ``FileNotFoundError``."""
        if name not in key.values:
            raise FileNotFoundError(name)
        return key.values[name], self.REG_SZ

    def DeleteValue(self, key, name):  # noqa: N802
        """Deletes a value; a missing one raises ``FileNotFoundError``."""
        if name not in key.values:
            raise FileNotFoundError(name)
        del key.values[name]

    def value(self, path, name):
        """Returns one value of the key ``path`` under ``HKEY_CURRENT_USER`` or ``None`` (for the assertions)."""
        return self.keys.get((self.HKEY_CURRENT_USER, path), {}).get(name)


def install_fake_winreg(monkeypatch):
    """Makes ``import winreg`` return a fresh :class:`FakeWinreg` for the rest of the test; returns it."""
    fake = FakeWinreg()
    monkeypatch.setitem(sys.modules, "winreg", fake)
    return fake
