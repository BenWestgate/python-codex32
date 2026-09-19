"""The one field that interprets codex32 keystrokes."""

from __future__ import annotations

from gi.repository import GLib, Gtk

from codex32.profiles.ms32 import TEXT_LENGTHS
from codex32_gui.reading import (
    GROUP,
    HEADER_LENGTH,
    PREFIX,
    SLACK,
    Reading,
    grouped,
    header_fault,
    normalize,
    read,
)


class Codex32Entry(Gtk.Entry):
    """A Gtk.Entry that can only ever hold grouped uppercase codex32 text."""

    __gtype_name__ = "Codex32Entry"

    def __init__(self, *, accepted: tuple[str, ...] = (), length: int | None = None) -> None:
        super().__init__()
        self._accepted, self._length, self._pending = accepted, length, 0
        self._limit = (length or TEXT_LENGTHS[-1]) + SLACK
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
        return read(normalize(self.get_text()), accepted=self._accepted, length=self._length)

    def clear(self) -> None:
        """Drop the entered recovery text."""
        self.set_text(PREFIX)

    def _schedule(self, _entry: Gtk.Entry) -> None:
        # One edit reaches the buffer as a deletion and then an insertion. Reformat
        # once the whole edit has settled, so no intermediate state is rewritten.
        if not self._pending:
            self._pending = GLib.idle_add(self._reformat)

    def _reformat(self) -> bool:
        self._pending = 0
        raw, position = self.get_text(), self.get_position()
        canonical = normalize(raw)[: self._limit]
        if header_fault(canonical, self._accepted):
            canonical = canonical[: len(PREFIX) + HEADER_LENGTH]
        shown = grouped(canonical)
        if shown != raw:
            kept = min(len(normalize(raw[:position])), len(canonical))
            self.set_text(shown)
            self.set_position(kept + max(kept - 1, 0) // GROUP)
        return False
