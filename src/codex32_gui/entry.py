"""The one field that interprets codex32 keystrokes."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal, cast

from gi.repository import Gdk, GLib, Gtk

from codex32.profiles.ms32 import TEXT_LENGTHS
from codex32_gui.reading import (
    GROUP,
    PREFIX,
    SLACK,
    Reading,
    grouped,
    header_fault,
    lookalike_fault,
    normalize,
    normalize_readback,
    read,
    readback,
)

EntryMode = Literal["import", "correct", "readback"]


class PrivateEntry(Gtk.Entry):
    """An entry that releases its primary selection after GTK publishes it."""

    def __init__(self, **properties: object) -> None:
        super().__init__(**properties)
        self._watching = 0
        self.connect("realize", lambda _entry: self._watch(True))
        self.connect("unrealize", lambda _entry: self._watch(False))

    def _watch(self, start: bool) -> None:
        primary = self.get_primary_clipboard()
        if start:
            self._watching = primary.connect("changed", self._unpublish)
        elif self._watching:
            primary.disconnect(self._watching)
            self._watching = 0

    def _unpublish(self, primary: Gdk.Clipboard) -> None:
        if primary.is_local() and primary.get_content() is not None and self.get_selection_bounds():
            GLib.idle_add(self._drop, primary)

    @staticmethod
    def _drop(primary: Gdk.Clipboard) -> bool:
        primary.set_content(None)
        return False


class Codex32Entry(PrivateEntry):
    """One grouped field with explicit import, correction, and read-back behavior."""

    __gtype_name__ = "Codex32Entry"

    def __init__(
        self,
        *,
        accepted: tuple[str, ...] = (),
        length: int | None = None,
        mode: EntryMode = "import",
        expected_header: tuple[int, str] | None = None,
        allow_header_erasures: bool = False,
    ) -> None:
        super().__init__()
        if mode == "readback" and length is None:
            raise ValueError("read-back entry requires the card length")
        self._accepted, self._length, self._mode = accepted, length, mode
        self._expected_header, self._allow_header_erasures, self._pending = (
            expected_header,
            allow_header_erasures,
            0,
        )
        self._limit = (length or TEXT_LENGTHS[-1]) + SLACK
        self._dropped, self._rewriting = "", False
        self._last_header_fault = ""
        self._stable = "" if mode == "readback" else PREFIX
        self.set_hexpand(True)
        self.add_css_class("card-entry")
        self.set_input_hints(Gtk.InputHints.NO_SPELLCHECK | Gtk.InputHints.NO_EMOJI)
        self.set_text(self._stable)
        self.set_position(-1)
        self.connect("changed", self._schedule)
        if mode == "readback":
            refuse_paste(self)
        GLib.idle_add(self.set_position, -1)

    def prefill(self, text: str) -> None:
        """Offer a known header that the operator may still overtype."""
        if self._mode == "readback":
            raise ValueError("read-back entry cannot be prefilled")
        self._stable = grouped(normalize(text))
        self.set_text(self._stable)
        self.set_position(-1)

    def reading(self) -> Reading:
        """Return the current reading of this field."""
        if self._mode == "readback":
            return readback(self.get_text(), cast(int, self._length))
        state = read(normalize(self.get_text()), accepted=self._accepted, length=self._length)
        if fault := self._header_fault():
            state = replace(state, artifact=None, message=fault, level="error")
        if self._dropped and state.artifact is None and state.level != "error":
            return replace(state, message=self._dropped, level="error")
        return state

    def clear(self) -> None:
        """Drop the entered recovery text."""
        self._dropped, self._last_header_fault = "", ""
        self._stable = "" if self._mode == "readback" else PREFIX
        self.set_text(self._stable)
        self.set_position(-1)

    def _header_fault(self, raw: str | None = None) -> str:
        if self._mode == "readback":
            return ""
        value = self.get_text() if raw is None else raw
        compact = "".join(value.split()).upper()
        text = compact if compact.startswith(PREFIX) else normalize(value)
        if self._mode == "import" and not self._allow_header_erasures and "?" in text[len(PREFIX) : 9]:
            return "? cannot be used in this header. Type the character printed on the card."
        return header_fault(text, self._accepted, self._expected_header)

    def _schedule(self, _entry: Gtk.Entry) -> None:
        # One edit reaches the buffer as a deletion and then an insertion. Reformat
        # once the whole edit has settled, so no intermediate state is rewritten,
        # and never in answer to this field rewriting itself, which would report
        # the text it has just filtered as clean.
        if not self._rewriting and not self._pending:
            self._pending = GLib.idle_add(self._reformat)

    def _reformat(self) -> bool:
        self._pending = 0
        raw, position = self.get_text(), self.get_position()
        normalizer = normalize_readback if self._mode == "readback" else normalize
        compact = "".join(raw.split()).upper()
        if self._mode != "readback" and not compact.startswith(PREFIX):
            self.error_bell()
            self._rewrite(self._stable, -1)
            return False
        duplicated_prefix = self._mode == "import" and compact.startswith(PREFIX + PREFIX)
        source = compact[len(PREFIX) :] if duplicated_prefix else raw
        canonical = normalizer(source)
        if self._mode != "readback":
            canonical = canonical[: self._limit]
        shown = grouped(canonical)
        self._dropped = "" if self._mode == "readback" else lookalike_fault(raw)
        fault = self._header_fault(canonical) if self._mode == "import" else ""
        if fault and self._last_header_fault and len(canonical) > len(normalize(self._stable)):
            self.error_bell()
            self._rewrite(self._stable, -1)
            return False
        if fault and fault != self._last_header_fault:
            self.error_bell()
        self._last_header_fault = fault
        if shown != raw:
            if duplicated_prefix:
                self._rewrite(shown, -1)
                self._stable = shown
                return False
            before = "".join(raw[:position].split())
            normalized_before = len(normalizer(raw[:position]))
            kept = (
                len(before) if PREFIX.startswith(before.upper()) else min(normalized_before, len(canonical))
            )
            self._rewrite(shown, kept + max(kept - 1, 0) // GROUP)
        self._stable = shown
        return False

    def _rewrite(self, shown: str, position: int) -> None:
        self._rewriting = True
        self.set_text(shown)
        self._rewriting = False
        self.set_position(position)


class GroupEntry(Codex32Entry):
    """Only the operator's transcription of one mismatched group."""

    def __init__(self, text: str) -> None:
        super().__init__(length=GROUP, mode="readback")
        self.set_width_chars(5)
        self.set_max_width_chars(5)
        self.set_hexpand(False)
        self.set_text(text)


def refuse_paste(entry: Gtk.Entry) -> None:
    """Require read-back from paper, including in correction boxes."""
    text = entry.get_delegate()
    text.connect("paste-clipboard", lambda text: text.stop_emission_by_name("paste-clipboard"))
    middle = Gtk.GestureClick(button=2, propagation_phase=Gtk.PropagationPhase.CAPTURE)
    middle.connect("pressed", lambda gesture, *_: gesture.set_state(Gtk.EventSequenceState.CLAIMED))
    entry.add_controller(middle)
    controllers = text.observe_controllers()
    for controller in [controllers.get_item(i) for i in range(controllers.get_n_items())]:
        if isinstance(controller, Gtk.DropTarget):
            text.remove_controller(controller)


def navigate_groups(entries: list[GroupEntry]) -> None:
    """Navigate editable groups while leaving character movement to GTK."""

    def key(_controller: Gtk.EventControllerKey, value: int, _code: int, state: Gdk.ModifierType) -> bool:
        current = entries.index(_controller.get_widget())
        entry = entries[current]
        backwards = value in (Gdk.KEY_Left, Gdk.KEY_KP_Left, Gdk.KEY_ISO_Left_Tab)
        tab = value in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab)
        edge = entry.get_position() == (0 if backwards else len(entry.get_text()))
        if value in (Gdk.KEY_Home, Gdk.KEY_End):
            target = 0 if value == Gdk.KEY_Home else len(entries) - 1
        elif tab or value in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_KP_Left, Gdk.KEY_KP_Right):
            if not tab and not edge and not state & Gdk.ModifierType.CONTROL_MASK:
                return False
            target = current + (-1 if backwards or tab and state & Gdk.ModifierType.SHIFT_MASK else 1)
            target = target % len(entries) if tab else min(max(target, 0), len(entries) - 1)
            if not tab and target == current:
                return False
        else:
            return False
        entries[target].grab_focus()
        entries[target].set_position(-1 if backwards or value == Gdk.KEY_End else 0)
        return True

    for entry in entries:
        controller = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", key)
        entry.add_controller(controller)
