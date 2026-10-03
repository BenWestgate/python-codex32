"""The create flow asks for blank cards and a wallet record before the first card."""

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

from codex32_gui import FORMS, pages


def _widgets(root: Gtk.Widget, kind: type) -> Iterator[Gtk.Widget]:
    child = root.get_first_child()
    while child is not None:
        if isinstance(child, kind):
            yield child
        yield from _widgets(child, kind)
        child = child.get_next_sibling()


def _button(page: Gtk.Widget, label: str) -> Gtk.Button:
    return next(button for button in _widgets(page, Gtk.Button) if button.get_label() == label)


def _texts(page: Gtk.Widget) -> str:
    return " ".join(label.get_label() for label in _widgets(page, Gtk.Label))


def test_a_layout_choice_leads_to_the_checklist_not_to_a_card(monkeypatch: pytest.MonkeyPatch) -> None:
    began: list[tuple[Any, ...]] = []
    monkeypatch.setattr(pages, "_begin_cards", lambda *arguments: began.append(arguments))
    view = Adw.NavigationView()
    core: Any = object()
    view.push(pages._layout_page(view, core))

    _button(view.get_visible_page(), "Continue").emit("clicked")
    ready = view.get_visible_page()
    assert began == []
    assert "Have 3 blank recovery cards, a pen, and one wallet record ready." in _texts(ready)

    _button(ready, "I have them ready").emit("clicked")
    assert began == [(view, core, 2, 3, 16)]


def test_a_single_card_backup_asks_for_one_card() -> None:
    view = Adw.NavigationView()
    page = pages._ready_page(view, object(), 0, 1, 16)  # type: ignore[arg-type]
    assert "Have one blank recovery card, a pen, and one wallet record ready." in _texts(page)


@pytest.mark.parametrize(
    ("label", "name"),
    [
        ("Open the recovery card form", "recovery-card.html"),
        ("Open the wallet record form", "wallet-verification-record.html"),
    ],
)
def test_each_button_opens_its_shipped_form(monkeypatch: pytest.MonkeyPatch, label: str, name: str) -> None:
    opened: list[str] = []

    class Launcher:
        def __init__(self, file: Any) -> None:
            self.path = file.get_path()

        def launch(self, _parent: object, _cancellable: object, _callback: object) -> None:
            opened.append(self.path)

    monkeypatch.setattr(pages.Gtk, "FileLauncher", Launcher)
    view = Adw.NavigationView()
    page = pages._ready_page(view, object(), 2, 3, 16)  # type: ignore[arg-type]

    _button(page, label).emit("clicked")
    assert opened == [str(FORMS.joinpath(name))]
    assert FORMS.joinpath(name).is_file()


def test_an_old_gtk_shows_where_the_form_is(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pages.Gtk, "check_version", lambda *_version: "GTK is older than 4.10")
    view = Adw.NavigationView()
    page = pages._ready_page(view, object(), 2, 3, 16)  # type: ignore[arg-type]

    _button(page, "Open the wallet record form").emit("clicked")
    assert str(FORMS.joinpath("wallet-verification-record.html")) in _texts(page)
