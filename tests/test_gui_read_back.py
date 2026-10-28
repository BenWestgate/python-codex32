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
        return result or ConfirmationResult(text == SHARE.upper(), ())

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
    field.set_text(text)
    _settle()
    field.emit("activate")
    return page, field, _boxes(page), finished


def _groups(text: str) -> list[str]:
    return [text[start : start + reading.GROUP] for start in range(0, len(text), reading.GROUP)]


CARD = _groups(SHARE.upper())


def _press(box: Gtk.Widget, key: int, modifiers: int = 0) -> bool:
    controllers = box.observe_controllers()
    found = (controllers.get_item(i) for i in range(controllers.get_n_items()))
    controller = next(item for item in found if isinstance(item, Gtk.EventControllerKey))
    return bool(controller.emit("key-pressed", key, 0, Gdk.ModifierType(modifiers)))


def test_readback_starts_empty_and_enter_confirms_the_whole_card() -> None:
    _page, field, typed, finished = _read_back(ConfirmationResult(True))

    assert field.get_text() == ""
    field.set_text(SHARE)
    field.emit("activate")
    assert typed == [SHARE.upper()] and finished == [True]


def test_invalid_characters_are_compared_and_kept_in_their_group() -> None:
    wrong = CARD.copy()
    wrong[7] = "B1!O"
    _page, _field, boxes, finished = _submit("".join(wrong))
    assert not finished
    assert isinstance(boxes[7], GroupEntry)
    assert boxes[7].get_text() == "B1!O"
    assert [index for index, box in enumerate(boxes) if isinstance(box, GroupEntry)] == [7]


def test_a_mismatch_locks_the_right_groups_and_opens_only_the_wrong_ones() -> None:
    wrong = CARD.copy()
    wrong[1], wrong[11] = "QQQQ", "PPPP"
    _page, field, boxes, finished = _submit("".join(wrong))

    assert finished == [] and not field.get_visible()
    assert [box.get_text() for box in boxes] == wrong
    assert [i for i, box in enumerate(boxes) if isinstance(box, GroupEntry)] == [1, 11]


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
    boxes[3].emit("activate")
    assert finished == [True] and field.get_text() == ""
    assert list(_widgets(page, Gtk.Grid)) == [] and field.get_visible()


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
    page, field, boxes, _finished = _submit("".join(wrong))
    field.clear()
    assert all(box.get_text() == "" for box in boxes)
    assert list(_widgets(page, Gtk.Grid)) == [] and field.get_visible()
    field.set_text(SHARE[:7])
    _settle()
    assert reading.normalize_readback(field.get_text()) == SHARE[:7].upper()


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


@pytest.mark.parametrize(
    ("key", "modifiers", "position", "target", "cursor"),
    [
        (Gdk.KEY_Right, 0, 4, 9, 0),
        (Gdk.KEY_Left, 0, 0, 2, 4),
        (Gdk.KEY_Right, Gdk.ModifierType.CONTROL_MASK, 1, 9, 0),
        (Gdk.KEY_Left, Gdk.ModifierType.CONTROL_MASK, 1, 2, 4),
        (Gdk.KEY_Home, 0, 2, 2, 0),
        (Gdk.KEY_End, 0, 2, 9, 4),
        (Gdk.KEY_Tab, 0, 2, 9, 0),
        (Gdk.KEY_ISO_Left_Tab, Gdk.ModifierType.SHIFT_MASK, 2, 2, 4),
    ],
)
def test_keyboard_navigation_skips_locked_groups(
    key: int, modifiers: int, position: int, target: int, cursor: int
) -> None:
    wrong = CARD.copy()
    wrong[2], wrong[9] = "QQQQ", "PPPP"
    page, _field, boxes, _finished = _submit("".join(wrong))
    window = Gtk.Window(child=page.get_parent())
    window.present()
    _settle()
    start = 9 if key in (Gdk.KEY_Left, Gdk.KEY_ISO_Left_Tab, Gdk.KEY_Home) else 2
    boxes[start].grab_focus()
    boxes[start].set_position(position)
    assert _press(boxes[start], key, modifiers)
    assert window.get_focus().get_parent() is boxes[target]
    assert boxes[target].get_position() == cursor
    window.destroy()


def test_more_than_eight_missing_characters_can_be_compared() -> None:
    _page, _field, boxes, finished = _submit(SHARE[:-12])
    assert not finished
    assert len(boxes) == len(CARD)
    assert any(isinstance(box, GroupEntry) and box.get_text() == "" for box in boxes)


def test_input_over_twice_the_card_opens_every_group_without_aligning() -> None:
    _page, _field, boxes, finished = _submit("Q" * (2 * len(SHARE) + 1))
    assert not finished and all(isinstance(box, GroupEntry) for box in boxes)


def test_correct_groups_lock_while_typing_and_a_wrong_one_turns_red() -> None:
    page, field, _typed, _finished = _read_back()
    field.set_text("".join(CARD[:3]))
    _settle()
    assert [box.get_text() for box in _boxes(page)] == CARD[:2]
    assert reading.normalize_readback(field.get_text()) == CARD[2]
    field.set_text(CARD[2] + "QQQQ" + "".join(CARD[4:6]))
    _settle()
    assert len(_boxes(page)) == 3 and field.has_css_class("error")
    field.set_text(CARD[3])
    _settle()
    assert not field.has_css_class("error")
    field.set_text("".join(CARD[3:]))
    _settle()
    field.emit("activate")
    assert _finished == [True]


def test_selecting_a_correction_box_releases_the_primary_selection() -> None:
    wrong = CARD.copy()
    wrong[3] = "QQQQ"
    page, _field, boxes, _finished = _submit("".join(wrong))
    window = Gtk.Window(child=page.get_parent())
    window.present()
    _settle()
    boxes[3].grab_focus()
    boxes[3].select_region(0, -1)
    _settle()
    assert window.get_display().get_primary_clipboard().get_content() is None
    window.destroy()


@pytest.mark.parametrize(("key", "cursor"), [(Gdk.KEY_Left, 0), (Gdk.KEY_Right, 4)])
def test_arrows_do_not_wrap_when_no_other_group_is_editable(key: int, cursor: int) -> None:
    wrong = CARD.copy()
    wrong[3] = "QQQQ"
    page, _field, boxes, _finished = _submit("".join(wrong))
    window = Gtk.Window(child=page.get_parent())
    window.present()
    _settle()
    box = boxes[3]
    box.grab_focus()
    box.set_position(cursor)
    assert not _press(box, key)
    assert box.get_position() == cursor
    window.destroy()
