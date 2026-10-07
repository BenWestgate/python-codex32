"""The one field that interprets codex32 keystrokes."""

from __future__ import annotations

from dataclasses import replace

from gi.repository import Gdk, GLib, Gtk

from codex32.profiles.ms32 import TEXT_LENGTHS
from codex32_gui.reading import (
    GROUP,
    HEADER_LENGTH,
    PREFIX,
    SLACK,
    Reading,
    grouped,
    header_fault,
    lookalike_fault,
    normalize,
    read,
)


class PrivateEntry(Gtk.Entry):
    """An entry whose selected text does not stay on the primary clipboard."""

    def __init__(self, **properties: object) -> None:
        super().__init__(**properties)
        self._watching = 0
        self.connect("realize", lambda _entry: self._watch(True))
        self.connect("unrealize", lambda _entry: self._watch(False))

    def _watch(self, start: bool) -> None:
        # Selecting text hands it to the primary selection, where a clipboard
        # manager would copy the card into a history file on disk. GTK publishes
        # it again on focus and on any selection, not only when the selection
        # moves, so the clipboard itself is watched while this entry is on screen
        # and the copy is taken back once GTK has finished. The selection still works.
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
    """A Gtk.Entry that can only ever hold grouped uppercase codex32 text."""

    __gtype_name__ = "Codex32Entry"

    def __init__(self, *, accepted: tuple[str, ...] = (), length: int | None = None) -> None:
        super().__init__()
        self._accepted, self._length, self._pending = accepted, length, 0
        self._limit = (length or TEXT_LENGTHS[-1]) + SLACK
        self._dropped, self._rewriting = "", False
        self.set_hexpand(True)
        self.add_css_class("card-entry")
        self.set_input_hints(Gtk.InputHints.NO_SPELLCHECK | Gtk.InputHints.NO_EMOJI)
        self.set_text(PREFIX)
        self.connect("changed", self._schedule)

    def prefill(self, text: str) -> None:
        """Offer a known header that the operator may still overtype."""
        self.set_text(grouped(normalize(text)))
        self.set_position(-1)

    def reading(self) -> Reading:
        """Return the current reading of this field."""
        state = read(normalize(self.get_text()), accepted=self._accepted, length=self._length)
        if self._dropped and state.artifact is None and state.level != "error":
            return replace(state, message=self._dropped, level="error")
        return state

    def clear(self) -> None:
        """Drop the entered recovery text."""
        self._dropped = ""
        self.set_text(PREFIX)

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
        canonical = normalize(raw)[: self._limit]
        if header_fault(canonical, self._accepted):
            canonical = canonical[: len(PREFIX) + HEADER_LENGTH]
        shown = grouped(canonical)
        self._dropped = lookalike_fault(raw)
        if shown != raw:
            kept = min(len(normalize(raw[:position])), len(canonical))
            self._rewriting = True
            self.set_text(shown)
            self._rewriting = False
            self.set_position(kept + max(kept - 1, 0) // GROUP)
        return False
