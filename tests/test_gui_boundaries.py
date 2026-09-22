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
BUDGET = 2000


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


def _named_function(tree: ast.AST, name: str) -> ast.FunctionDef:
    return next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name)


def _direct_calls(function: ast.FunctionDef) -> set[str]:
    """Collect calls in one function body without entering callbacks it defines."""
    found: set[str] = set()

    class Calls(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if node is function:
                self.generic_visit(node)

        def visit_Lambda(self, _node: ast.Lambda) -> None:
            return

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Name):
                found.add(node.func.id)
            self.generic_visit(node)

    Calls().visit(function)
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


def test_the_accessibility_bus_is_turned_off_before_gtk_starts() -> None:
    """GTK otherwise publishes every label and entry, seed and passphrase included."""
    source = (_package() / "__init__.py").read_text()
    assert 'GLib.setenv("GTK_A11Y", "none", False)' in source
    tree = ast.parse(source)
    settings = [node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)]
    assert settings, "the setting has to be made before any typelib is loaded"


@pytest.mark.parametrize("path", _modules(), ids=lambda path: path.name)
def test_nothing_but_the_version_pin_may_import_a_module_by_name(path: Path) -> None:
    """`importlib` would reach any of the forbidden modules without naming one."""
    imported = {name.split(".")[0] for name in _imports(ast.parse(path.read_text()))}
    assert "importlib" not in imported or path.name == "__init__.py", sorted(imported)


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


def test_restore_verifies_identity_before_wallet_mutation() -> None:
    tree = ast.parse((_package() / "pages.py").read_text())
    restore = _named_function(tree, "_restore")
    verify = _named_function(tree, "_verify_restore")
    identity_page = _named_function(tree, "_restore_identity_page")

    assert "_verify_restore" in _direct_calls(restore)
    assert "_wallets" not in _direct_calls(restore)
    assert "_wallets" not in _direct_calls(verify)
    assert "_wallets" not in _direct_calls(identity_page)
