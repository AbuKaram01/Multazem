# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

r"""Which DLLs does an installed Multazem need that nothing inside it provides?

A machine that has never had the Microsoft Visual C++ Redistributable has no ``msvcp140.dll``. Multazem does not carry
it: GTK 4, libadwaita and PyGObject need only ``vcruntime140.dll`` and ``vcruntime140_1.dll``, which Python's own
installer puts beside ``python.exe``. The CI machine has the Redistributable, so a program that starts there proves
nothing about a clean machine. This script answers the question without depending on what the machine has:

    python packaging\windows\dlls.py scan   --app <installation folder>   [--strict] [--json file] [--github]
    python packaging\windows\dlls.py loaded --app <installation folder>   [--strict]

``scan`` reads the import tables of every ``.dll``, ``.pyd`` and ``.exe`` of the installation (and of the Python the
environment is made from) and says, for each DLL they import, whether it is beside the importer or in a folder the
program registers for DLLs, a Windows DLL, a Visual C++ runtime DLL nothing provides, or missing altogether. It reads
the files themselves, so it also runs on a machine without Windows. Delay-loaded imports are listed for information
only: they are looked up when first used, not when the library is loaded.

``loaded`` (Windows only, run with the installed program's own python.exe) imports the program and GTK the way the
program does and prints where each Visual C++ runtime DLL was actually loaded from: Multazem's folders, the Python
folder, or Windows. On a machine that has the Redistributable a program can start with ``scan`` still reporting gaps,
and this shows which copy it used.

Only the Python standard library is used, so either command runs with the installed program's own python.exe.
Output is plain ASCII: a Windows console that is not set to UTF-8 would fail on anything else.

The exit status is 0 when the command ran; with ``--strict`` it is 1 when the answer is bad. It is 2 when the command
cannot run at all: there is no installation at ``--app``, or ``loaded`` was started on a system other than Windows.
"""

from __future__ import annotations

import argparse
import json
import mmap
import os
import re
import struct
import sys
import textwrap
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

# --- Reading the import tables of a PE file ---

# Indexes of the import and delay-import tables in the data directories of a PE file.
_IMPORT_DIRECTORY = 1
_DELAY_IMPORT_DIRECTORY = 13

# A real file has a few hundred import descriptors at most; the limit keeps a damaged file from looping for ever.
_MAX_DESCRIPTORS = 4096
# Windows does not allow a DLL name longer than a path; the limit keeps a damaged name from running on.
_MAX_NAME_LENGTH = 260

# Layout of the PE format, in bytes.
_DOS_HEADER_SIZE = 0x40
_PE_OFFSET_FIELD = 0x3C
_COFF_HEADER_SIZE = 20
_SECTION_ENTRY_SIZE = 40
_IMPORT_DESCRIPTOR_SIZE = 20
_DELAY_DESCRIPTOR_SIZE = 32
_PE32_MAGIC = 0x10B
_PE32_PLUS_MAGIC = 0x20B


class PeError(ValueError):
    """The file is not a readable Windows executable."""


@dataclass(frozen=True)
class Imports:
    """The names of the DLLs that a PE file imports.

    Attributes:
        static: DLLs that are loaded together with the file; when one is missing, the file does not load.
        delayed: DLLs that are looked up only when the file first calls into them.
    """

    static: tuple[str, ...] = ()
    delayed: tuple[str, ...] = ()


# The little-endian unsigned integers of the PE format, read at a byte offset of ``data``.
def _u16(data, at: int) -> int:
    return struct.unpack_from("<H", data, at)[0]


def _u32(data, at: int) -> int:
    return struct.unpack_from("<I", data, at)[0]


def _u64(data, at: int) -> int:
    return struct.unpack_from("<Q", data, at)[0]


class _PeImage:
    """A Windows program file, read far enough to list the DLLs it imports.

    Attributes:
        data: The content of the file, as bytes or an mmap.
    """

    def __init__(self, data) -> None:
        """Reads the headers of ``data``.

        Raises:
            PeError: The content is not a Windows executable.
            struct.error: The headers are cut short.
        """
        self.data = data
        if len(data) < _DOS_HEADER_SIZE or bytes(data[:2]) != b"MZ":
            raise PeError("not a Windows executable (no MZ header)")
        pe = _u32(data, _PE_OFFSET_FIELD)  # e_lfanew: where the PE signature is.
        if bytes(data[pe : pe + 4]) != b"PE\0\0":
            raise PeError("not a Windows executable (no PE signature)")
        coff = pe + 4
        section_count = _u16(data, coff + 2)
        optional_size = _u16(data, coff + 16)
        optional = coff + _COFF_HEADER_SIZE  # The optional header follows the COFF header.
        self._read_optional_header(optional)
        self._header_size = _u32(data, optional + 60)  # SizeOfHeaders
        self._sections = self._read_sections(optional + optional_size, section_count)

    def _read_optional_header(self, optional: int) -> None:
        """Finds the data directories and the image base, which lie at other offsets in a 32-bit and a 64-bit file."""
        data = self.data
        magic = _u16(data, optional)
        if magic == _PE32_PLUS_MAGIC:
            self._directories, count_at, self._image_base = optional + 112, optional + 108, _u64(data, optional + 24)
        elif magic == _PE32_MAGIC:
            self._directories, count_at, self._image_base = optional + 96, optional + 92, _u32(data, optional + 28)
        else:
            raise PeError(f"unknown optional header 0x{magic:x}")
        self._directory_count = _u32(data, count_at)

    def _read_sections(self, table_at: int, count: int) -> list[tuple[int, int, int]]:
        """Returns ``(virtual address, size in memory, offset in the file)`` of each section."""
        sections = []
        for index in range(count):
            at = table_at + _SECTION_ENTRY_SIZE * index
            virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", self.data, at + 8)
            sections.append((virtual_address, max(virtual_size, raw_size), raw_pointer))
        return sections

    def offset(self, rva: int) -> int:
        """Converts a relative virtual address into an offset in the file."""
        for address, size, pointer in self._sections:
            if address <= rva < address + size:
                return pointer + (rva - address)
        # The headers are not part of any section; they map to the same offset.
        if rva < self._header_size:
            return rva
        raise PeError(f"an address (0x{rva:x}) lies outside every section")

    def text(self, rva: int) -> str:
        """Reads a NUL-terminated name; the length is capped so that a damaged name cannot run on."""
        start = self.offset(rva)
        end = start
        while end - start < _MAX_NAME_LENGTH and self.data[end] != 0:
            end += 1
        # Latin-1 decodes every byte, so a damaged name cannot raise.
        return bytes(self.data[start:end]).decode("latin-1")

    def table(self, index: int) -> int | None:
        """Returns the address of the data directory ``index``, or None when the file has no such table."""
        if index >= self._directory_count:
            return None
        rva, size = struct.unpack_from("<II", self.data, self._directories + 8 * index)
        return rva if rva and size else None

    def static_imports(self) -> list[str]:
        """Returns the DLLs that are loaded together with the file.

        Import descriptors are 20 bytes long and hold the address of the DLL name at offset 12; the table ends at the
        first descriptor without a name.
        """
        names: list[str] = []
        rva = self.table(_IMPORT_DIRECTORY)
        if rva is None:
            return names
        at = self.offset(rva)
        for _ in range(_MAX_DESCRIPTORS):
            name_rva = _u32(self.data, at + 12)
            if name_rva == 0:
                break
            names.append(self.text(name_rva))
            at += _IMPORT_DESCRIPTOR_SIZE
        return names

    def delayed_imports(self) -> list[str]:
        """Returns the DLLs that are looked up when first used.

        Delay-import descriptors are 32 bytes long: the attributes come first, then the address of the DLL name.
        """
        names: list[str] = []
        rva = self.table(_DELAY_IMPORT_DIRECTORY)
        if rva is None:
            return names
        at = self.offset(rva)
        for _ in range(_MAX_DESCRIPTORS):
            attributes, name_rva = struct.unpack_from("<II", self.data, at)
            if name_rva == 0:
                break
            # Bit 0 of the attributes says that the name is an RVA. In the old style (32-bit files) it is a virtual
            # address, from which the image base has to be subtracted.
            if not attributes & 1:
                name_rva -= self._image_base
            names.append(self.text(name_rva))
            at += _DELAY_DESCRIPTOR_SIZE
        return names


def parse_imports(data) -> Imports:
    """Returns the DLLs that the PE file ``data`` imports.

    Args:
        data: The content of the file, as bytes or an mmap.

    Raises:
        PeError: The content is not a Windows executable, or is truncated or damaged.
    """
    try:
        image = _PeImage(data)
        return Imports(tuple(image.static_imports()), tuple(image.delayed_imports()))
    except (struct.error, IndexError) as error:
        raise PeError(f"truncated or damaged ({error})") from None


def read_imports(path: Path) -> Imports:
    """Returns the DLLs that the file at ``path`` imports.

    Raises:
        PeError: The file is empty, or is not a readable Windows executable.
        OSError: The file cannot be opened.
    """
    with path.open("rb") as handle:
        try:
            mapped = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        except ValueError:
            # An empty file cannot be mapped.
            raise PeError("empty file") from None
        with mapped:
            return parse_imports(mapped)


# --- What a DLL name means ---

# The runtime libraries of Visual C++. They come with the Visual C++ Redistributable, not with Windows, so a machine
# that never had a program needing it lacks them. (The Universal C Runtime, ucrtbase.dll and api-ms-win-crt-*, is part
# of Windows 10 and later.)
_VCPP = re.compile(
    r"^(msvcp\d+|msvcr\d+|vcruntime\d+|vcomp\d+|concrt\d+|vccorlib\d+|vcamp\d+|mfcm?\d+[a-z]*|atl\d+)"
    r"(_[a-z0-9_]+)?\.dll$"
)


def is_vcpp_runtime(name: str) -> bool:
    """Returns whether ``name`` is a Visual C++ runtime DLL, such as ``msvcp140.dll`` or ``vcruntime140_1.dll``.

    A copy that a wheel carries under its own name (``msvcp140-<hash>.dll``) is not one: the wheel provides that file
    itself.
    """
    return _VCPP.match(name.lower()) is not None


def is_windows_builtin(name: str) -> bool:
    """Returns whether ``name`` is provided by Windows itself, so that no file of the installation is needed.

    API sets are not files at all, and the Universal C Runtime has been part of Windows since Windows 10.
    """
    lowered = name.lower()
    return lowered.startswith(("api-ms-", "ext-ms-")) or lowered == "ucrtbase.dll"


# --- The scan ---

# Folders that hold no program files of the installed program. Skipped only directly inside the installation: the
# Python installer and the wheelhouse that the installer carries (both beside the program).
_SKIP_AT_TOP = {"wheelhouse", "python"}

# Skipped at any depth: the wheels inside the GTK runtime, caches and repository metadata.
_SKIP_ANYWHERE = {"wheels", "__pycache__", ".git"}

# The folders of the Python installation that are scanned: its own interpreter ("") and its extension modules (DLLs),
# not its Lib\site-packages.
_PYTHON_FOLDERS_SCANNED = ("", "DLLs")

# Suffixes of the files that have an import table.
_PE_SUFFIXES = {".dll", ".pyd", ".exe"}
# Folders inside site-packages that a library adds to the DLL search path itself when it is imported. The scan cannot
# see that call, so it takes these folders as known. None of the libraries of Multazem does it.
_SELF_REGISTERED_FOLDERS: tuple[tuple[str, ...], ...] = ()
# The programs of the environment that Multazem does start.
_INTERPRETERS = ("python.exe", "pythonw.exe")


@dataclass
class Report:
    r"""The result of scanning an installation.

    The attributes are also the structure of the JSON report that ``scan --json`` writes.

    Attributes:
        app: The installation folder that was scanned.
        python_home: The Python folder the environment is made from, or None when it is not known.
        files: How many program files were examined.
        unreadable: A ``(file, reason)`` pair for every file that is not a readable Windows program.
        vcpp: The Visual C++ runtime DLLs that are imported, by name:
            ``{"importers": n, "unprovided": [files], "provided_by": [folders]}``.
        missing: Static imports that nothing provides and Windows lacks, as DLL name -> importing files.
        delayed: Delay-loaded imports that nothing provides (information only), as DLL name -> importing files.
        tools: The command-line programs that Multazem never starts, GTK's (``gtk\bin\*.exe``) and the ones that
            Python libraries carry (in ``site-packages`` or in the environment's ``Scripts``, such as setuptools'
            launchers): ``count`` is how many there are, ``needs`` maps each runtime DLL that they lack beside them to
            the programs that import it.
        allowed: Lower-case DLL names that may be missing without counting as a problem.
    """

    app: str
    python_home: str | None
    files: int = 0
    unreadable: list[tuple[str, str]] = field(default_factory=list)
    vcpp: dict[str, dict] = field(default_factory=dict)
    missing: dict[str, list[str]] = field(default_factory=dict)
    delayed: dict[str, list[str]] = field(default_factory=dict)
    tools: dict = field(default_factory=lambda: {"count": 0, "needs": {}})
    allowed: list[str] = field(default_factory=list)

    def problems(self) -> list[str]:
        """Returns the DLL names that would stop the program on a machine with only Windows and the installation.

        Names in ``allowed`` and delay-loaded imports are not counted.
        """
        found = [name for name, entry in sorted(self.vcpp.items()) if entry["unprovided"] and name not in self.allowed]
        found += [name for name in sorted(self.missing) if name not in self.allowed]
        return found


def _python_home_of(app: Path) -> Path | None:
    """Returns the Python folder named by ``home =`` in the environment's ``pyvenv.cfg``, or None."""
    config = app / ".venv" / "pyvenv.cfg"
    try:
        lines = config.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        key, _, value = line.partition("=")
        if key.strip().lower() == "home" and value.strip():
            return Path(value.strip())
    return None


def _pe_files(root: Path, *, shallow: tuple[str, ...] | None = None) -> Iterator[Path]:
    """Yields the program files (``.dll``, ``.pyd``, ``.exe``) under ``root``, in a stable order.

    With ``shallow``, only the listed sub-folders of ``root`` (``""`` stands for ``root`` itself) are read, without
    descending into folders. Otherwise the whole tree is walked, except the folders that hold no program files.
    """
    if shallow is not None:
        for name in shallow:
            folder = root / name if name else root
            if folder.is_dir():
                yield from (
                    entry
                    for entry in sorted(folder.iterdir())
                    if entry.is_file() and entry.suffix.lower() in _PE_SUFFIXES
                )
        return
    for folder, directories, names in os.walk(root):
        skipped = _SKIP_ANYWHERE | (_SKIP_AT_TOP if Path(folder) == root else set())
        # Assigning to the slice prunes the walk in place.
        directories[:] = sorted(d for d in directories if d.lower() not in skipped)
        for name in sorted(names):
            if Path(name).suffix.lower() in _PE_SUFFIXES:
                yield Path(folder) / name


class _Listings:
    """The file names (lower case) in folders, with each folder read only once."""

    def __init__(self) -> None:
        self._cache: dict[str, frozenset[str]] = {}

    def names(self, folder: Path) -> frozenset[str]:
        """Returns the lower-case names of the files in ``folder``; empty when it cannot be read."""
        key = os.path.normcase(str(folder))
        if key not in self._cache:
            try:
                self._cache[key] = frozenset(entry.name.lower() for entry in os.scandir(folder) if entry.is_file())
            except OSError:
                self._cache[key] = frozenset()
        return self._cache[key]


def shared_provider_folders(app: Path, python_home: Path | None, extra: tuple[Path, ...] = ()) -> list[Path]:
    r"""Returns the folders whose DLLs every library of the installation can use.

    These are the folders as the installed program sets them up. The Python folder is the application directory of
    the interpreter. Multazem puts ``gtk\bin`` on the DLL search path at start-up (``winsupport``). Wheels that carry
    their own copies of DLLs register their ``*.libs`` folder from their ``__init__``.

    Args:
        app: The installation folder.
        python_home: The Python folder the environment is made from, or None when it is not known.
        extra: Further folders that are known to provide DLLs.

    Returns:
        The folders that exist, in the order in which they are consulted.
    """
    folders: list[Path] = []
    if python_home is not None:
        folders.append(python_home)
    folders.append(app / "gtk" / "bin")
    packages = app / ".venv" / "Lib" / "site-packages"
    if packages.is_dir():
        folders += sorted(
            entry for entry in packages.iterdir() if entry.is_dir() and entry.name.lower().endswith(".libs")
        )
        folders += [packages.joinpath(*parts) for parts in _SELF_REGISTERED_FOLDERS]
    folders += list(extra)
    return [folder for folder in folders if folder.is_dir()]


def _inside(path: Path, folder: Path) -> bool:
    """Returns whether ``path`` lies inside ``folder``; whole folder names count, so ``app2`` is not inside ``app``."""
    return os.path.normcase(str(path)).startswith(os.path.normcase(str(folder)).rstrip("\\/") + os.sep)


def _is_tool(path: Path, folders: tuple[Path, ...]) -> bool:
    """Returns whether ``path`` is a command-line program that Multazem never starts.

    Every ``.exe`` inside ``folders`` is one, except the interpreter launchers (``python.exe``, ``pythonw.exe``): the
    Start menu entry starts ``pythonw.exe`` of the environment.
    """
    if path.suffix.lower() != ".exe" or path.name.lower() in _INTERPRETERS:
        return False
    return any(_inside(path, folder) for folder in folders)


def _shown(path: Path, root: Path, outside: bool) -> str:
    """Returns ``path`` as the report shows it: relative to ``root``, with files of the Python folder marked."""
    try:
        relative = str(path.relative_to(root))
    except ValueError:
        return str(path)
    return f"[Python folder]\\{relative}" if outside else relative


def _names(files: list[str], limit: int = 4) -> str:
    """Summarises ``files`` as at most ``limit`` distinct file names, followed by the total when there are more."""
    # Backslashes are turned into slashes so that Windows paths are split correctly on any system.
    base = sorted({Path(file.replace("\\", "/")).name for file in files})
    return ", ".join(base[:limit]) + (f", ... ({len(base)} in all)" if len(base) > limit else "")


def _sets() -> defaultdict[str, set[str]]:
    """Returns a dictionary that makes an empty set for every new key."""
    return defaultdict(set)


@dataclass
class _Findings:
    """What a scan noted, as sets of file names (as the report shows them) keyed by the lower-case DLL name.

    Attributes:
        importers: The files that import a Visual C++ runtime DLL.
        unprovided: Those of them that find no copy.
        provided_by: The folders where a copy was found.
        missing: The static imports that nothing provides.
        delayed: The delay-loaded imports that nothing provides.
        tool_needs: The runtime DLLs that the command-line tools lack beside them.
    """

    importers: defaultdict[str, set[str]] = field(default_factory=_sets)
    unprovided: defaultdict[str, set[str]] = field(default_factory=_sets)
    provided_by: defaultdict[str, set[str]] = field(default_factory=_sets)
    missing: defaultdict[str, set[str]] = field(default_factory=_sets)
    delayed: defaultdict[str, set[str]] = field(default_factory=_sets)
    tool_needs: defaultdict[str, set[str]] = field(default_factory=_sets)


class _Scanner:
    """Reads the imports of every program file of an installation and judges where each DLL would come from."""

    def __init__(
        self,
        app: Path,
        python_home: Path | None,
        system_dir: Path | None,
        allow: tuple[str, ...],
        providers: tuple[Path, ...],
    ) -> None:
        self.app = app
        self.python_home = python_home
        self.system_dir = system_dir
        self.report = Report(
            app=str(app),
            python_home=str(python_home) if python_home else None,
            allowed=[name.lower() for name in allow],
        )
        self.listings = _Listings()
        self.shared = shared_provider_folders(app, python_home, providers)
        self.shared_names = {folder: self.listings.names(folder) for folder in self.shared}
        self.findings = _Findings()
        self.tools_folders = (app / "gtk" / "bin", app / ".venv" / "Lib" / "site-packages", app / ".venv" / "Scripts")

    def run(self) -> Report:
        """Scans the installation and the Python folder, and returns the finished report."""
        # Each source is (root folder, its files, whether it lies outside the installation); the last value only marks
        # the files of the Python folder in the report.
        sources = [(self.app, _pe_files(self.app), False)]
        if self.python_home is not None and self.python_home.is_dir():
            sources.append((self.python_home, _pe_files(self.python_home, shallow=_PYTHON_FOLDERS_SCANNED), True))
        for root, files, outside in sources:
            for path in files:
                self._scan_file(path, _shown(path, root, outside))
        return self._finish()

    def _label(self, folder: Path) -> str:
        """Names a folder that provides DLLs in the report: the Python folder, or a path inside the installation."""
        if self.python_home is not None and os.path.normcase(str(folder)) == os.path.normcase(str(self.python_home)):
            return "the Python folder"
        try:
            return str(folder.relative_to(self.app))
        except ValueError:
            return str(folder)

    def _scan_file(self, path: Path, shown: str) -> None:
        """Reads one program file and notes where each DLL it imports comes from."""
        self.report.files += 1
        try:
            imports = read_imports(path)
        except (PeError, OSError) as error:
            self.report.unreadable.append((shown, str(error)))
            return
        if _is_tool(path, self.tools_folders):
            self._note_tool(path, imports, shown)
            return
        # A program that is started on its own (an .exe, with its own DLLs beside it) looks beside itself and in
        # Windows, not in the folders that the Python process registers.
        use_shared = path.suffix.lower() != ".exe"
        for kind, names in (("static", imports.static), ("delayed", imports.delayed)):
            for raw in names:
                self._account_for(raw.lower(), kind, path, shown, use_shared=use_shared)

    def _note_tool(self, path: Path, imports: Imports, shown: str) -> None:
        """Counts a command-line tool and notes the runtime DLLs it would lack, without judging it.

        Such tools (gdbus.exe, glib-compile-schemas.exe, setuptools' cli.exe launchers ...) are started on their own,
        with only their own folder and Windows to look in. Multazem never starts them.
        """
        self.report.tools["count"] += 1
        beside = self.listings.names(path.parent)
        for raw in imports.static:
            if is_vcpp_runtime(raw) and raw.lower() not in beside:
                self.findings.tool_needs[raw.lower()].add(shown)

    def _provider_folder(self, name: str, path: Path, *, use_shared: bool) -> Path | None:
        """Returns the folder that provides the DLL ``name`` to ``path``: beside it, or one of the shared folders."""
        if name in self.listings.names(path.parent):
            return path.parent
        if not use_shared:
            return None
        return next((folder for folder in self.shared if name in self.shared_names[folder]), None)

    def _account_for(self, name: str, kind: str, path: Path, shown: str, *, use_shared: bool) -> None:
        """Notes where the DLL ``name`` (imported by ``path``) comes from.

        It is accounted for when it is beside its importer, in a shared folder or provided by Windows itself. What
        remains is a Visual C++ runtime DLL that nothing provides, or another DLL that is not in System32.
        """
        runtime = is_vcpp_runtime(name)
        folder = self._provider_folder(name, path, use_shared=use_shared)
        if folder is not None:
            if runtime:
                self.findings.importers[name].add(shown)
                self.findings.provided_by[name].add(self._label(folder))
            return
        if is_windows_builtin(name):
            return
        if runtime:
            self._note_unprovided_runtime(name, kind, shown)
        elif self.system_dir is not None and not (self.system_dir / name).exists():
            # Without System32 (not on Windows) nothing says what Windows has, so other DLLs are not judged.
            (self.findings.missing if kind == "static" else self.findings.delayed)[name].add(shown)

    def _note_unprovided_runtime(self, name: str, kind: str, shown: str) -> None:
        """Notes a Visual C++ runtime DLL that nothing provides: a problem when static, information when delayed."""
        if kind == "static":
            self.findings.importers[name].add(shown)
            self.findings.unprovided[name].add(shown)
        else:
            # Looked up only when first used, so a gap is information, not a problem.
            self.findings.delayed[name].add(shown)

    def _finish(self) -> Report:
        """Turns the findings into the report."""
        findings = self.findings
        for name, files in sorted(findings.importers.items()):
            self.report.vcpp[name] = {
                "importers": len(files),
                "unprovided": sorted(findings.unprovided.get(name, ())),
                "provided_by": sorted(findings.provided_by.get(name, ())),
            }
        self.report.tools["needs"] = {name: sorted(files) for name, files in sorted(findings.tool_needs.items())}
        self.report.missing = {name: sorted(files) for name, files in sorted(findings.missing.items())}
        self.report.delayed = {name: sorted(files) for name, files in sorted(findings.delayed.items())}
        return self.report


def scan(
    app: Path,
    python_home: Path | None = None,
    system_dir: Path | None = None,
    allow: tuple[str, ...] = (),
    extra_providers: tuple[Path, ...] = (),
) -> Report:
    r"""Reads the imports of every program file of ``app`` and of the Python behind its environment.

    Args:
        app: The installation folder.
        python_home: The Python folder the environment is made from; read from ``.venv\pyvenv.cfg`` when None.
        system_dir: The Windows System32 folder. Without it, a DLL that is neither beside its importer nor a Visual C++
            runtime is taken to be a Windows one and is not judged.
        allow: DLL names that may be missing without counting as a problem, compared without regard to case.
        extra_providers: Further folders whose DLLs the program can use.

    Returns:
        The findings of the scan.
    """
    if python_home is None:
        python_home = _python_home_of(app)
    return _Scanner(app, python_home, system_dir, allow, extra_providers).run()


# --- Reporting ---


def _vcpp_lines(report: Report) -> list[str]:
    """Returns the lines about the Visual C++ runtime DLLs that the program imports."""
    lines = [
        "Visual C++ runtime DLLs that the program imports "
        "(they come with the Visual C++ Redistributable, not with Windows):"
    ]
    if not report.vcpp:
        lines.append("  none")
    for name, entry in report.vcpp.items():
        source = "; ".join(entry["provided_by"]) or "nowhere"
        if not entry["unprovided"]:
            lines.append(f"  {name}: imported by {entry['importers']} files; always provided (in: {source})")
            continue
        allowed = " (allowed)" if name in report.allowed else ""
        lines.append(
            f"  {name}: imported by {entry['importers']} files; "
            f"NOT PROVIDED for {len(entry['unprovided'])} of them{allowed}: {_names(entry['unprovided'])}"
        )
        if entry["provided_by"]:
            lines.append(f"      the rest find it in: {source}")
    return lines


def _other_lines(report: Report) -> list[str]:
    """Returns the lines about the DLLs that are neither runtime DLLs nor found: the missing and the delay-loaded."""
    lines = ["Other DLLs that are not beside the importer, not in a folder the program registers and not in System32:"]
    if not report.missing:
        lines.append("  none")
    for name, files in report.missing.items():
        lines.append(f"  {name}: {_names(files)}" + (" (allowed)" if name in report.allowed else ""))
    if report.delayed:
        lines.append(
            "Delay-loaded DLLs nothing provides (only needed when the feature that uses them is used; information):"
        )
        lines += [f"  {name}: {_names(files)}" for name, files in report.delayed.items()]
    return lines


def _tools_lines(report: Report) -> list[str]:
    """Returns the line about the command-line tools that were counted but not judged."""
    if not report.tools["count"]:
        return []
    needs = (
        ", ".join(f"{name} ({len(files)})" for name, files in report.tools["needs"].items())
        or "nothing from the machine"
    )
    return [
        f"{report.tools['count']} command-line tools (GTK's in gtk\\bin, and the ones that Python libraries carry) "
        f"are not started by Multazem and were not judged; run on their own they would look for: {needs}"
    ]


def format_report(report: Report) -> list[str]:
    """Returns the lines of the plain-text report that the ``scan`` command prints."""
    scanned = f"Scanned {report.files} program files under {report.app}"
    if report.python_home:
        scanned += f" and the Python folder {report.python_home}"
    scanned += f"; {len(report.unreadable)} could not be read." if report.unreadable else "."
    lines = [scanned]
    lines += [f"  unreadable: {path} ({why})" for path, why in report.unreadable[:5]]
    lines += _vcpp_lines(report) + _other_lines(report) + _tools_lines(report)
    problems = report.problems()
    if problems:
        lines.append(
            f"RESULT: {len(problems)} DLL(s) the program needs would have to come from the machine: "
            f"{', '.join(problems)}"
        )
    else:
        lines.append("RESULT: every DLL that the program loads comes with Windows or with the installation.")
    return lines


def github_summary(report: Report) -> str:
    """Returns the Markdown job summary that the ``--github`` option appends to the GitHub Actions step summary."""
    problems = report.problems()
    out = ["### DLLs the installed program needs from the machine", ""]
    if problems:
        out += [f"**{len(problems)} DLL(s) that nothing in the installation provides:** `{'`, `'.join(problems)}`", ""]
    else:
        out += ["Everything the program loads comes with Windows or with the installation.", ""]
    out += ["| DLL | imported by | not provided for | provided in |", "|---|---|---|---|"]
    for name, entry in report.vcpp.items():
        out.append(
            f"| `{name}` | {entry['importers']} | {len(entry['unprovided'])}: {_names(entry['unprovided'])} | "
            f"{'; '.join(entry['provided_by']) or '-'} |"
        )
    for name, files in report.missing.items():
        out.append(f"| `{name}` (missing) | {len(files)} | {len(files)}: {_names(files)} | - |")
    return "\n".join(out) + "\n"


def _say(text: str = "") -> None:
    """Writes one line to the standard output."""
    sys.stdout.write(text + "\n")


# --- What was loaded ---

# The modules that ``loaded`` imports when no ``--import`` is given: the libraries of the program.
DEFAULT_IMPORTS = ("adhanpy", "cairo")


def classify_loaded(paths: list[str], app: Path, python_home: Path | None, windows_dirs) -> dict[str, list[str]]:
    """Sorts the modules of a process by where they were loaded from.

    A path goes into the first group that matches, in this order: ``app`` (the installation), ``python`` (the Python
    folder), ``windows`` and ``other``.

    Args:
        paths: The full paths of the loaded modules.
        app: The installation folder.
        python_home: The Python folder, or None when it is not known.
        windows_dirs: One folder or several: Windows itself, and the folder of Microsoft Defender, which puts a module
            into every process.

    Returns:
        The paths of each group, in their original order, under the keys ``app``, ``python``, ``windows`` and
        ``other``.
    """
    if isinstance(windows_dirs, Path) or windows_dirs is None:
        windows_dirs = [windows_dirs]

    def under(path: str, folder: Path | None) -> bool:
        if folder is None:
            return False
        folder_text = os.path.normcase(str(folder)).rstrip("\\/") + os.sep
        return os.path.normcase(path).startswith(folder_text)

    buckets: dict[str, list[str]] = {"app": [], "python": [], "windows": [], "other": []}
    for path in paths:
        if under(path, app):
            buckets["app"].append(path)
        elif under(path, python_home):
            buckets["python"].append(path)
        elif any(under(path, folder) for folder in windows_dirs):
            buckets["windows"].append(path)
        else:
            buckets["other"].append(path)
    return buckets


def loaded_module_paths() -> list[str]:
    """Returns the full path of every module (DLL or program) loaded into this process. Windows only.

    Raises:
        OSError: The list of modules cannot be read.
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # The signatures are declared because ctypes assumes ``int`` for anything undeclared, which would truncate
    # 64-bit handles.
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.K32EnumProcessModules.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HMODULE),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.K32EnumProcessModules.restype = wintypes.BOOL
    kernel32.K32GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    kernel32.K32GetModuleFileNameExW.restype = wintypes.DWORD
    process = kernel32.GetCurrentProcess()
    # Room for 4096 modules. The size that the call reports as needed can be larger, so the loop below clamps it.
    modules = (wintypes.HMODULE * 4096)()
    needed = wintypes.DWORD()
    if not kernel32.K32EnumProcessModules(process, modules, ctypes.sizeof(modules), ctypes.byref(needed)):
        raise ctypes.WinError(ctypes.get_last_error())
    paths = []
    for index in range(min(needed.value // ctypes.sizeof(wintypes.HMODULE), len(modules))):
        # Long enough for the longest path that Windows allows.
        buffer = ctypes.create_unicode_buffer(32768)
        if kernel32.K32GetModuleFileNameExW(process, modules[index], buffer, len(buffer)):
            paths.append(buffer.value)
    return paths


def _import_all(names: tuple[str, ...]) -> list[tuple[str, str]]:
    """Imports ``multazem.app``, GTK and every module of ``names`` in the order the program does.

    Returns:
        A ``(name, "ExceptionType: message")`` pair for every import that failed.
    """
    import importlib

    failures: list[tuple[str, str]] = []

    def attempt(name: str, action) -> None:
        try:
            action()
        except BaseException as error:  # noqa: BLE001 - every failure is the answer here
            failures.append((name, f"{type(error).__name__}: {error}"))

    # Importing multazem.app runs winsupport.prepare_runtime(), which prepares the DLL folders; the program does that
    # before GTK is imported, so it has to come first here too.
    attempt("multazem.app", lambda: importlib.import_module("multazem.app"))

    def gtk() -> None:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gtk  # noqa: F401

    attempt("GTK and libadwaita", gtk)
    for name in names:
        # The default argument binds the current name; a plain closure would see only the last one.
        attempt(name, lambda name=name: importlib.import_module(name))
    return failures


def _runtime_dlls_outside(buckets: dict[str, list[str]]) -> list[str]:
    """Prints where each Visual C++ runtime DLL was loaded from, and returns the names of those from the machine."""
    bad = []
    _say("Visual C++ runtime DLLs of this process, and where each was loaded from:")
    titles = (
        ("app", "the installation"),
        ("python", "the Python folder"),
        ("windows", "Windows"),
        ("other", "somewhere else"),
    )
    for bucket, title in titles:
        for path in sorted(buckets[bucket]):
            name = Path(path).name
            if is_vcpp_runtime(name):
                _say(f"  {name}: {title}: {path}")
                if bucket in ("windows", "other"):
                    bad.append(name)
    return bad


def _print_other_modules(buckets: dict[str, list[str]]) -> None:
    """Prints the libraries loaded from the installation, and the modules loaded from outside everything."""
    inside = sorted({Path(path).name for path in buckets["app"]}, key=str.lower)
    _say(
        textwrap.fill(
            f"Loaded from the installation ({len(inside)} libraries): " + ", ".join(inside),
            width=118,
            subsequent_indent="  ",
        )
    )
    outside = [path for path in sorted(buckets["other"]) if not is_vcpp_runtime(Path(path).name)]
    if outside:
        _say(
            "Modules loaded from outside the installation, Python and Windows "
            "(something of the machine that the program uses):"
        )
        for path in outside:
            _say(f"  {path}")


def run_loaded(app: Path, python_home: Path | None, *, strict: bool, names: tuple[str, ...]) -> int:
    r"""Imports the program's libraries and prints where the Visual C++ runtime DLLs of this process came from.

    Args:
        app: The installation folder.
        python_home: The Python folder the environment is made from; read from ``.venv\pyvenv.cfg`` when None.
        strict: Whether a bad answer is reported through the exit status.
        names: The modules to import.

    Returns:
        0 when the answer is good, or when it is bad and ``strict`` is false; 1 when it is bad and ``strict`` is true;
        2 when the system is not Windows.
    """
    if sys.platform != "win32":
        _say("The 'loaded' command lists the DLLs of a running process and works on Windows only.")
        return 2
    if python_home is None:
        python_home = _python_home_of(app)
    failures = _import_all(names)
    windows_dirs = [
        Path(os.environ.get("SYSTEMROOT", r"C:\Windows")),
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "Windows Defender",
    ]
    buckets = classify_loaded(loaded_module_paths(), app, python_home, windows_dirs)
    for name, why in failures:
        _say(f"IMPORT FAILED: {name}: {why}")
    bad = _runtime_dlls_outside(buckets)
    _print_other_modules(buckets)
    if not (failures or bad):
        _say("RESULT: every import worked and every runtime DLL came from the installation or the Python folder.")
        return 0
    _say(
        f"RESULT: {len(failures)} import(s) failed; {len(set(bad))} runtime DLL(s) came from the machine instead of "
        "the installation" + (f": {', '.join(sorted(set(bad)))}" if bad else ".")
    )
    return 1 if strict else 0


# --- Command line ---


def _default_app() -> Path:
    r"""Returns the folder where the installer puts the program by default: ``%LOCALAPPDATA%\Programs\Multazem``."""
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / "Multazem"


def _build_parser() -> argparse.ArgumentParser:
    """Returns the parser of the command line."""
    # The first paragraph of the module docstring is also the description in ``--help``, so it is part of the output.
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("scan", "loaded"):
        command = commands.add_parser(name)
        command.add_argument("--app", type=Path, default=_default_app(), help="the installation folder")
        command.add_argument(
            "--python-home",
            type=Path,
            help="the Python the environment is made from (default: read from .venv\\pyvenv.cfg)",
        )
        command.add_argument("--strict", action="store_true", help="exit with 1 when the answer is bad")
    scanner = commands.choices["scan"]
    scanner.add_argument(
        "--system-dir", type=Path, default=None, help="Windows' System32 (default: the machine's own, on Windows)"
    )
    scanner.add_argument(
        "--provider", type=Path, action="append", default=[], help="another folder whose DLLs the program can use"
    )
    scanner.add_argument("--allow", action="append", default=[], help="a DLL name that may be missing (repeatable)")
    scanner.add_argument("--json", type=Path, help="write the full report here")
    scanner.add_argument(
        "--github", action="store_true", help="also write a job summary and a workflow warning for GitHub Actions"
    )
    commands.choices["loaded"].add_argument(
        "--import", dest="imports", action="append", help="a module to import (default: the program's libraries)"
    )
    return parser


def _publish_to_github(report: Report) -> None:
    """Appends the Markdown job summary to the step summary of GitHub Actions and prints a workflow warning."""
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(github_summary(report))
    problems = report.problems()
    if problems:
        _say(f"::warning title=The installed program needs DLLs from the machine::{', '.join(problems)}")


def _run_scan(args: argparse.Namespace) -> int:
    """Runs the ``scan`` command and returns the exit status."""
    # Off Windows nothing says what Windows has, so DLLs that nothing provides are then not judged (see scan()).
    system_dir = args.system_dir
    if system_dir is None and sys.platform == "win32":
        system_dir = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32"
    if not args.app.is_dir():
        _say(f"There is no installation at {args.app}.")
        return 2
    report = scan(args.app, args.python_home, system_dir, tuple(args.allow), tuple(args.provider))
    for line in format_report(report):
        _say(line)
    if args.json:
        args.json.write_text(json.dumps(report.__dict__, indent=2, default=str), encoding="utf-8")
    if args.github:
        _publish_to_github(report)
    return 1 if (args.strict and report.problems()) else 0


def main(argv: list[str] | None = None) -> int:
    """Runs the command line and returns the exit status.

    Args:
        argv: The command-line arguments; ``sys.argv[1:]`` when None.

    Returns:
        0 when the command ran, 1 when ``--strict`` is given and the answer is bad, 2 when the command cannot run.
    """
    args = _build_parser().parse_args(argv)
    # A user name with Arabic letters in a path must not crash a console that is not UTF-8, so characters that the
    # console cannot encode are printed as backslash escapes.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")
    if args.command == "loaded":
        return run_loaded(args.app, args.python_home, strict=args.strict, names=tuple(args.imports or DEFAULT_IMPORTS))
    return _run_scan(args)


if __name__ == "__main__":
    sys.exit(main())
