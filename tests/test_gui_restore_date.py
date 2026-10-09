"""Restore takes the wallet's creation date from the record, so a pruned node can rescan it."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

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

from codex32._bitcoin_core import BitcoinCoreError
from codex32_gui import pages


def _widgets(root: Gtk.Widget, kind: type) -> Iterator[Gtk.Widget]:
    child = root.get_first_child()
    while child is not None:
        if isinstance(child, kind):
            yield child
        yield from _widgets(child, kind)
        child = child.get_next_sibling()


def _fill(view: Adw.NavigationView, *texts: str) -> None:
    page = view.get_visible_page()
    for row, text in zip(_widgets(page, Adw.EntryRow), texts, strict=True):
        row.set_text(text)
    next(b for b in _widgets(page, Gtk.Button) if b.get_label() == "Check and continue").emit("clicked")


@pytest.fixture
def restore(monkeypatch: pytest.MonkeyPatch) -> tuple[Adw.NavigationView, list[Any], list[Any]]:
    checked: list[Any] = []
    reached: list[Any] = []

    def verify(_core: Any, _secret: Any, expected: bytes | None, start: Any = "now") -> None:
        checked.append((expected, start))
        if start == 0:
            raise BitcoinCoreError("This pruned node no longer has the blocks")

    monkeypatch.setattr(pages.work, "run", lambda _view, _page, job, done: done(job()))
    monkeypatch.setattr(pages.wallet_setup, "verify", verify)
    monkeypatch.setattr(pages, "_wallets", lambda *arguments, **keywords: reached.append(arguments[3]))
    view = Adw.NavigationView()
    view.push(pages._fingerprint_page(view, object(), object(), 0, restoring=True))  # type: ignore[arg-type]
    return view, checked, reached


def test_restore_rescans_from_the_recorded_creation_date(restore: Any) -> None:
    view, checked, reached = restore
    _fill(view, "3f3521a6", "2024-03-02")
    assert checked == [(bytes.fromhex("3f3521a6"), 1709251200)]
    assert reached == [1709251200]


def test_a_rescan_the_node_cannot_do_stays_on_the_page(restore: Any) -> None:
    view, checked, reached = restore
    _fill(view, "3f3521a6", "")
    assert checked == [(bytes.fromhex("3f3521a6"), 0)]
    assert reached == []
    shown = " ".join(label.get_label() for label in _widgets(view.get_visible_page(), Gtk.Label))
    assert "pruned node" in shown


def test_a_malformed_date_is_refused_before_bitcoin_core_is_asked(restore: Any) -> None:
    view, checked, reached = restore
    _fill(view, "3f3521a6", "March 2024")
    assert checked == [] and reached == []


def test_a_new_wallet_record_check_asks_for_no_date() -> None:
    view = Adw.NavigationView()
    page = pages._fingerprint_page(view, object(), object(), "now")  # type: ignore[arg-type]
    assert len(list(_widgets(page, Adw.EntryRow))) == 1
