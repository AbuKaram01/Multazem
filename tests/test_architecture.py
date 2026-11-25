# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Architecture rules: layers depend only downwards and the core stays free of toolkit and environment access."""

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "multazem"

ALLOWED_DEPENDENCIES = {
    "i18n": set(),
    "core": {"i18n"},
    "services": {"i18n", "core"},
    "ui": {"i18n", "core", "services"},
}
FORBIDDEN_THIRD_PARTY = {"core": {"gi"}, "i18n": {"gi"}}


def imported_modules(path: Path) -> list[tuple[str, int]]:
    """Returns the modules a source file imports as ``(absolute name, line number)``, resolving relative imports."""
    relative_parts = path.relative_to(PACKAGE_ROOT.parent).with_suffix("").parts
    package_parts = list(relative_parts[:-1])
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [(alias.name, node.lineno) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package_parts[: len(package_parts) - (node.level - 1)]
                found.append((".".join([*base, *(node.module.split(".") if node.module else [])]), node.lineno))
            elif node.module:
                found.append((node.module, node.lineno))
    return found


def layer_of(path: Path) -> str | None:
    """Returns the layer (``i18n``, ``core``, ``services`` or ``ui``) a source file belongs to, or ``None``."""
    parts = path.relative_to(PACKAGE_ROOT).parts
    return parts[0] if len(parts) > 1 and parts[0] in ALLOWED_DEPENDENCIES else None


@pytest.mark.parametrize("layer", sorted(ALLOWED_DEPENDENCIES))
def test_layers_only_depend_downwards(layer):
    violations = []
    for path in sorted((PACKAGE_ROOT / layer).rglob("*.py")):
        for module, line in imported_modules(path):
            parts = module.split(".")
            if parts[0] == "multazem" and len(parts) > 1:
                target = parts[1]
                if target in ALLOWED_DEPENDENCIES and target != layer and target not in ALLOWED_DEPENDENCIES[layer]:
                    violations.append(f"{path.relative_to(PACKAGE_ROOT)}:{line} imports {module}")
            if parts[0] in FORBIDDEN_THIRD_PARTY.get(layer, set()):
                violations.append(f"{path.relative_to(PACKAGE_ROOT)}:{line} imports {module}")
    assert violations == []


def test_the_i18n_package_imports_nothing_else_from_the_application():
    for path in (PACKAGE_ROOT / "i18n").rglob("*.py"):
        internal = [
            m
            for m, _ in imported_modules(path)
            if m.startswith("multazem") and ".i18n" not in m and m != "multazem.i18n"
        ]
        assert internal == [], path


def test_core_modules_do_not_touch_the_toolkit_or_the_environment():
    for path in (PACKAGE_ROOT / "core").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("os.environ", "subprocess", "urllib", "threading", "open("):
            assert forbidden not in source, f"{path.name} uses {forbidden}"
