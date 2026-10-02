"""The card read-back page: Enter submits, and a mismatch redraws only what was typed."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

gi = pytest.importorskip("gi")
try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Adw, Gdk, Gtk
except (ImportError, ValueError):
    pytest.skip("GTK 4 and libadwaita are unavailable", allow_module_level=True)
if not Gtk.init_check() or Gdk.Display.get_default() is None:
    pytest.skip("no display for GTK", allow_module_level=True)
Adw.init()

from data.bip93_vectors import VECTOR_2

from codex32 import parse_codex32
from codex32.generation import ConfirmationResult
from codex32_gui import pages

SHARE = VECTOR_2["share_A"]


def _widgets(root: Gtk.Widget, kind: type) -> Iterator[Gtk.Widget]:
    child = root.get_first_child()
    while child is not None:
        if isinstance(child, kind):
            yield child
        yield from _widgets(child, kind)
        child = child.get_next_sibling()


def _read_back(result: ConfirmationResult) -> tuple[Gtk.Widget, pages.Codex32Entry, list[str], list[bool]]:
    typed: list[str] = []
    finished: list[bool] = []

    def confirm(text: str) -> ConfirmationResult:
        typed.append(text)
        return result

    view = Adw.NavigationView()
    page = pages._read_back_page(view, parse_codex32(SHARE), 1, 3, confirm, lambda: finished.append(True))
    view.push(page)
    return page, next(_widgets(page, pages.Codex32Entry)), typed, finished


def test_enter_confirms_only_a_complete_card() -> None:
    _page, field, typed, finished = _read_back(ConfirmationResult(True))

    field.prefill(SHARE[:20])
    field.emit("activate")
    assert typed == [] and finished == []

    field.prefill(SHARE)
    field.emit("activate")
    assert typed == [SHARE.upper()] and finished == [True]


def test_a_mismatch_highlights_every_wrong_group_of_the_typed_text() -> None:
    page, field, _typed, finished = _read_back(ConfirmationResult(False, (2, 12)))

    field.prefill(SHARE)
    field.emit("activate")

    assert finished == []
    [card] = list(_widgets(page, Gtk.FlowBox))
    groups = [label for label in _widgets(card, Gtk.Label)]
    assert "".join(label.get_label() for label in groups) == SHARE.upper()
    assert [i for i, label in enumerate(groups) if label.has_css_class("guessed")] == [1, 11]
    assert any("highlighted groups do not match" in label.get_label() for label in _widgets(page, Gtk.Label))

    field.clear()
    assert list(_widgets(page, Gtk.FlowBox)) == []
