"""The claims a reviewer of the graphical program should be able to check cheaply."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

FORBIDDEN = frozenset(
    {
        "hashlib",
        "hmac",
        "http",
        "io",
        "logging",
        "os",
        "pathlib",
        "pickle",
        "random",
        "requests",
        "secrets",
        "shelve",
        "shutil",
        "socket",
        "sqlite3",
        "ssl",
        "subprocess",
        "tempfile",
        "urllib",
        "webbrowser",
    }
)
CORE_ADAPTER = "codex32._bitcoin_core"
BUDGET = 1800


def _package() -> Path:
    module = importlib.import_module("codex32_gui")
    assert module.__file__ is not None
    return Path(module.__file__).parent


def _modules() -> list[Path]:
    return sorted(_package().rglob("*.py"))


def _imports(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and not node.level:
            found.add(node.module)
    return found


@pytest.mark.parametrize("path", _modules(), ids=lambda path: path.name)
def test_the_gui_draws_no_entropy_opens_no_socket_and_touches_no_file(path: Path) -> None:
    imported = _imports(ast.parse(path.read_text()))
    assert not {name.split(".")[0] for name in imported} & FORBIDDEN, sorted(imported)


@pytest.mark.parametrize("path", _modules(), ids=lambda path: path.name)
def test_nothing_reads_or_writes_a_file(path: Path) -> None:
    called = {
        node.func.id
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in called and "eval" not in called and "exec" not in called


@pytest.mark.parametrize("path", _modules(), ids=lambda path: path.name)
def test_only_one_module_speaks_to_bitcoin_core(path: Path) -> None:
    imported = _imports(ast.parse(path.read_text()))
    assert (CORE_ADAPTER in imported) == (path.name == "wallet_setup.py"), sorted(imported)


def test_the_parts_that_decide_something_need_no_toolkit() -> None:
    for name in ("reading.py", "wallet_setup.py", "style.py"):
        imported = _imports(ast.parse((_package() / name).read_text()))
        assert not any(item == "gi" or item.startswith("gi.") for item in imported), name


def test_the_library_does_not_depend_on_the_gui() -> None:
    library = Path(importlib.import_module("codex32").__file__ or "").parent
    for path in library.rglob("*.py"):
        assert "codex32_gui" not in path.read_text(), path


def test_the_gui_keeps_its_own_size_budget() -> None:
    counts = {
        path.name: sum(
            bool(line.strip()) and not line.lstrip().startswith("#") for line in path.read_text().splitlines()
        )
        for path in _modules()
    }
    assert sum(counts.values()) < BUDGET, counts
