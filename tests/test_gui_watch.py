"""`work.watch`, the GUI's stand-in for the command line's wait on Bitcoin Core, driven by a fake main loop."""

from __future__ import annotations

import importlib.util
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import codex32_gui


class _Loop:
    """Holds what GLib would run later, so a test decides exactly when each callback runs."""

    def __init__(self) -> None:
        self.queued: list[tuple[Callable[..., bool], tuple[Any, ...]]] = []

    def timeout_add_seconds(self, _seconds: int, callback: Callable[..., bool], *args: Any) -> int:
        self.queued.append((callback, args))
        return len(self.queued)

    def idle_add(self, callback: Callable[..., bool], *args: Any) -> int:
        return self.timeout_add_seconds(0, callback, *args)

    def run(self, rounds: int = 20) -> None:
        for _ in range(rounds):
            due, self.queued = self.queued, []
            for callback, args in due:
                if callback(*args):
                    self.queued.append((callback, args))


class _Stack:
    def __init__(self, pages: list[object]) -> None:
        self.pages = pages

    def get_n_items(self) -> int:
        return len(self.pages)

    def get_item(self, position: int) -> object:
        return self.pages[position]


class _View:
    def __init__(self, *pages: object) -> None:
        self.pages = list(pages)

    def get_visible_page(self) -> object:
        return self.pages[-1]

    def get_navigation_stack(self) -> _Stack:
        return _Stack(self.pages)


class _Inline:
    """Runs a thread's target at once, so the order of events is the test's."""

    def __init__(self, target: Callable[[], None], daemon: bool = False) -> None:
        self.target = target

    def start(self) -> None:
        self.target()


@pytest.fixture
def work(monkeypatch: pytest.MonkeyPatch) -> tuple[types.ModuleType, _Loop]:
    loop = _Loop()
    repository = types.ModuleType("gi.repository")
    repository.GLib = loop  # type: ignore[attr-defined]
    repository.Adw = types.SimpleNamespace()  # type: ignore[attr-defined]
    gi = types.ModuleType("gi")
    gi.repository = repository  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    path = Path(codex32_gui.__file__).parent / "work.py"
    spec = importlib.util.spec_from_file_location("codex32_gui._work_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.threading, "Thread", _Inline)
    return module, loop


def test_it_waits_while_the_wallet_is_locked_and_goes_on_once(work: tuple[types.ModuleType, _Loop]) -> None:
    module, loop = work
    page, view, state, went = object(), _View(), {"open": False}, []
    view.pages = ["home", page]
    module.watch(view, page, lambda: state["open"], lambda: went.append(1))
    loop.run()
    assert went == []
    state["open"] = True
    loop.run()
    assert went == [1]
    view.pages.append("working")  # `then` moved on; it comes back here after a failure
    loop.run()
    view.pages.pop()
    loop.run()
    assert went == [1], "a finished or failed attempt must never start another one unasked"
    assert loop.queued == []


def test_a_typed_attempt_stops_it_for_good(work: tuple[types.ModuleType, _Loop]) -> None:
    module, loop = work
    page, view, went = object(), _View(), []
    view.pages = ["home", page]
    stop = module.watch(view, page, lambda: True, lambda: went.append(1))
    stop()
    loop.run()
    assert went == []
    assert loop.queued == []


def test_an_answer_that_arrives_after_a_typed_attempt_is_dropped(
    work: tuple[types.ModuleType, _Loop],
) -> None:
    module, loop = work
    page, view, went = object(), _View(), []
    view.pages = ["home", page]
    stop: list[Callable[[], None]] = []

    def ready() -> bool:
        stop[0]()  # the operator presses Unlock while Bitcoin Core is being asked
        return True

    stop.append(module.watch(view, page, ready, lambda: went.append(1)))
    loop.run()
    assert went == []


def test_it_never_asks_behind_another_page_or_another_operation(work: tuple[types.ModuleType, _Loop]) -> None:
    module, loop = work
    page, view, asked, went = object(), _View(), [], []
    view.pages = ["home", page, "working"]
    module.watch(view, page, lambda: asked.append(1) or True, lambda: went.append(1))
    loop.run()
    assert asked == [] and went == []
    view.pages.pop()
    module._running = True
    loop.run()
    assert asked == [] and went == []
    module._running = False
    loop.run()
    assert went == [1]


def test_it_ends_with_its_page_and_survives_core_errors(work: tuple[types.ModuleType, _Loop]) -> None:
    module, loop = work
    page, view, went = object(), _View(), []
    view.pages = ["home", page]

    def broken() -> bool:
        raise module.BitcoinCoreError("The local Bitcoin Core command did not complete.")

    module.watch(view, page, broken, lambda: went.append(1))
    loop.run(3)
    assert went == [] and loop.queued
    view.pages.pop()
    loop.run()
    assert went == [] and loop.queued == []
