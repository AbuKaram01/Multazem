# Changelog

All notable changes to Multazem are written here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Windows 10/11 support. The application, the notifications (Windows toasts), the single running window and the
  background reminders (a sign-in entry plus a background process that holds a lock file) work on Windows.
- A self-contained Windows installer (`packaging/windows/multazem.iss`, built with `packaging/build-windows.ps1`): it
  carries the GTK 4 and libadwaita runtime, Python's installer and the Python libraries, installs for the current user
  without administrator rights, and keeps the settings and saved regions when it is run over an older version. Turning
  the background reminders on is an optional task that is off by default.
- `scripts/install-windows.ps1` and `scripts/uninstall-windows.ps1` for a checkout.
- Continuous integration (`.github/workflows/ci.yml`): linters and the whole suite on Linux, the suite on Windows with
  and without GTK, the installer build, and two manual jobs that run the installer for real (install, upgrade,
  uninstall, and a scan of the DLLs the installed program needs) and install by script.

### Changed

- The prayer-time engine, storage and services now use the `logging` module instead of `print`.
- The code is cleaned up (smaller functions, shared code for the packages in `packaging/stage.sh`), documented with
  Google-style docstrings and checked by a stricter ruff configuration; the large test files are split by topic.
- `tzdata` is a dependency on Windows, which has no time zone database of its own, and PyGObject is not requested from
  PyPI there (its wheel comes with the GTK runtime).
