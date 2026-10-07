"""The card read-back page: Enter submits, and a mismatch opens only the wrong groups."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

gi = pytest.importorskip("gi")
try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Adw, Gdk, GLib, Gtk
except (ImportError, ValueError):
    pytest.skip("GTK 4 and libadwaita are unavailable", allow_module_level=True)
if not Gtk.init_check() or Gdk.Display.get_default() is None:
    pytest.skip("no display for GTK", allow_module_level=True)
Adw.init()

from data.bip93_vectors import VECTOR_2

from codex32 import parse_codex32
from codex32.generation import ConfirmationResult
from codex32_gui import pages, reading
from codex32_gui.entry import GroupEntry

SHARE = VECTOR_2["share_A"]


def _widgets(root: Gtk.Widget, kind: type) -> Iterator[Gtk.Widget]:
    child = root.get_first_child()
    while child is not None:
        if isinstance(child, kind):
            yield child
        yield from _widgets(child, kind)
        child = child.get_next_sibling()


def _read_back(
    result: ConfirmationResult | None = None,
) -> tuple[Gtk.Widget, pages.Codex32Entry, list[str], list[bool]]:
    typed: list[str] = []
    finished: list[bool] = []

    def confirm(text: str) -> ConfirmationResult:
        typed.append(text)
        return result or pages._compare(SHARE, text)

    view = Adw.NavigationView()
    page = pages._read_back_page(view, parse_codex32(SHARE), 1, 3, confirm, lambda: finished.append(True))
    view.push(page)
    return page, next(_widgets(page, pages.Codex32Entry)), typed, finished


def _settle() -> None:
    while GLib.MainContext.default().iteration(False):
        pass


def _boxes(page: Gtk.Widget) -> list[Gtk.Widget]:
    [grid] = list(_widgets(page, Gtk.Grid))
    return [box for box in _widgets(grid, Gtk.Widget) if isinstance(box, Gtk.Label | GroupEntry)]


def _submit(text: str) -> tuple[Gtk.Widget, pages.Codex32Entry, list[Gtk.Widget], list[bool]]:
    page, field, _typed, finished = _read_back()
    field.prefill(text)
    field.emit("activate")
    return page, field, _boxes(page), finished


def _groups(text: str) -> list[str]:
    return [text[start : start + reading.GROUP] for start in range(0, len(text), reading.GROUP)]


CARD = _groups(SHARE.upper())


def test_enter_confirms_only_a_card_of_about_the_right_length() -> None:
    _page, field, typed, finished = _read_back(ConfirmationResult(True))

    field.prefill(SHARE[:20])
    field.emit("activate")
    assert typed == [] and finished == []

    field.prefill(SHARE)
    field.emit("activate")
    assert typed == [SHARE.upper()] and finished == [True]


def test_a_lookalike_is_named_and_must_be_fixed_before_the_card_is_compared() -> None:
    page, field, typed, _finished = _read_back()
    field.set_text(SHARE[:30].upper() + "B" + SHARE[31:].upper())
    _settle()
    field.emit("activate")
    assert typed == [] and field.get_visible()
    assert any("never contains B" in label.get_label() for label in _widgets(page, Gtk.Label))

    wrong = CARD.copy()
    wrong[4] = "QQQQ"
    field.prefill("".join(wrong))
    field.emit("activate")
    [box] = [box for box in _boxes(page) if isinstance(box, GroupEntry)]
    box.set_text("Q1QQ")
    box.emit("activate")
    assert len(typed) == 1 and isinstance(_boxes(page)[4], GroupEntry)


def test_a_mismatch_locks_the_right_groups_and_opens_only_the_wrong_ones() -> None:
    wrong = CARD.copy()
    wrong[1], wrong[11] = "QQQQ", "PPPP"
    page, field, boxes, finished = _submit("".join(wrong))

    assert finished == [] and not field.get_visible()
    assert [box.get_text() for box in boxes] == wrong
    assert [i for i, box in enumerate(boxes) if isinstance(box, GroupEntry)] == [1, 11]
    assert any("highlighted groups do not match" in label.get_label() for label in _widgets(page, Gtk.Label))


def test_a_missing_and_an_extra_character_open_only_their_own_groups() -> None:
    slipped = CARD.copy()
    slipped[2], slipped[6] = CARD[2][1:], CARD[6][:2] + "Q" + CARD[6][2:]
    _page, _field, boxes, _finished = _submit("".join(slipped))

    assert [i for i, box in enumerate(boxes) if isinstance(box, GroupEntry)] == [2, 6]
    assert [box.get_text() for box in boxes] == slipped


def test_correcting_the_open_boxes_confirms_the_card() -> None:
    wrong = CARD.copy()
    wrong[3] = "QQQQ"
    page, field, boxes, finished = _submit("".join(wrong))

    boxes[3].set_text(CARD[3].lower())
    _settle()
    assert boxes[3].get_text() == CARD[3]  # Shown in capitals, like the card.
    boxes[3].emit("activate")
    assert finished == [True] and field.get_text() == reading.PREFIX
    assert list(_widgets(page, Gtk.Grid)) == [] and field.get_visible()


def test_tab_moves_only_between_the_wrong_groups() -> None:
    wrong = CARD.copy()
    wrong[2], wrong[9] = "QQQQ", "PPPP"
    page, _field, boxes, _finished = _submit("".join(wrong))
    window = Gtk.Window(child=page.get_parent())
    window.present()
    _settle()

    boxes[2].grab_focus()
    page.child_focus(Gtk.DirectionType.TAB_FORWARD)
    assert window.get_focus().get_parent() is boxes[9]
    window.destroy()


def test_the_read_back_refuses_pasted_and_dropped_text() -> None:
    wrong = CARD.copy()
    wrong[5] = "QQQQ"
    _page, field, boxes, _finished = _submit("".join(wrong))
    field.get_clipboard().set("PPPP")
    _settle()

    for entry in (field, boxes[5]):
        before, text = entry.get_text(), entry.get_delegate()
        text.emit("paste-clipboard")
        _settle()
        assert entry.get_text() == before
        controllers = text.observe_controllers()
        assert not any(
            isinstance(controllers.get_item(i), Gtk.DropTarget) for i in range(controllers.get_n_items())
        )


def test_clearing_puts_the_single_field_back() -> None:
    wrong = CARD.copy()
    wrong[0] = "MS1Q"
    page, field, _boxes, _finished = _submit("".join(wrong))
    field.clear()
    assert list(_widgets(page, Gtk.Grid)) == [] and field.get_visible()
    field.prefill(SHARE[:20])
    _settle()
    assert reading.normalize(field.get_text()) == SHARE[:20].upper()


def test_a_retry_keeps_every_box_where_it_is() -> None:
    wrong = CARD.copy()
    wrong[0], wrong[2] = "MS1Q", "QQQQ"
    page, _field, boxes, _finished = _submit("".join(wrong))

    boxes[0].set_text("MS12N")  # One character too many, next to the locked group
    boxes[0].emit("activate")
    boxes = _boxes(page)
    assert [i for i, box in enumerate(boxes) if isinstance(box, GroupEntry)] == [0, 2]
    assert [box.get_text() for box in boxes[:2]] == ["MS12N", CARD[1]]


def test_a_retry_ignores_spaces_typed_into_a_box() -> None:
    wrong = CARD.copy()
    wrong[3], wrong[8] = "QQQQ", "PPPP"
    page, _field, boxes, _finished = _submit("".join(wrong))

    boxes[3].set_text(CARD[3][:2] + " " + CARD[3][2:])
    boxes[3].emit("activate")
    assert [i for i, box in enumerate(_boxes(page)) if isinstance(box, GroupEntry)] == [8]
