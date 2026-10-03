"""The one field that interprets codex32 keystrokes."""

from __future__ import annotations

from dataclasses import replace

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
    lookalike_fault,
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
        self._dropped, self._rewriting, self._unpublishing = "", False, 0
        self._locked, self._shown = frozenset[int](), PREFIX
        self.set_hexpand(True)
        self.add_css_class("card-entry")
        self.set_input_hints(Gtk.InputHints.NO_SPELLCHECK | Gtk.InputHints.NO_EMOJI)
        self.set_text(PREFIX)
        self.connect("changed", self._schedule)
        self.connect("notify::selection-bound", self._unpublish)
        self.connect("notify::cursor-position", self._unpublish)

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
        self._dropped, self._locked, self._shown = "", frozenset(), PREFIX
        self.set_text(PREFIX)

    def lock(self, open_groups: frozenset[int] | None) -> None:
        """Freeze every four-character group except `open_groups`, which stay editable in place."""
        self._shown, every = self.get_text(), range(-(-len(normalize(self.get_text())) // GROUP))
        self._locked = frozenset(every) - open_groups if open_groups else frozenset()

    def _unpublish(self, *_arguments: object) -> None:
        # Selecting text in a Gtk.Entry hands it to the primary selection, where a
        # clipboard manager would copy the card into a history file on disk. The
        # selection still works; only the copy that leaves the program is taken
        # back, once GTK has finished publishing it.
        if self.get_selection_bounds() and not self._unpublishing:
            self._unpublishing = GLib.idle_add(self._drop_primary)

    def _drop_primary(self) -> bool:
        self._unpublishing = 0
        display = self.get_display()
        if display is not None:
            display.get_primary_clipboard().set_content(None)
        return False

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
        kept = min(len(normalize(raw[:position])), len(canonical))
        if self._locked and canonical != normalize(self._shown):
            canonical, kept = self._within_open_group(normalize(self._shown), canonical, kept)
        shown = self._shown = grouped(canonical)
        self._dropped = lookalike_fault(raw)
        if shown != raw:
            self._rewriting = True
            self.set_text(shown)
            self._rewriting = False
            self.set_position(kept + max(kept - 1, 0) // GROUP)
        return False

    def _within_open_group(self, old: str, new: str, cursor: int) -> tuple[str, int]:
        # Once groups are locked the card keeps its length and they keep their
        # text: an edit inside one open group is cut or padded with "?" back to
        # that group's size, and an edit reaching any other group is undone. In a
        # run of repeated symbols the edit is placed where GTK left the cursor.
        same = min(len(old), len(new))
        start = next((i for i in range(same) if old[i] != new[i]), same)
        tail = next((i for i in range(same - start) if old[-1 - i] != new[-1 - i]), same - start)
        while start and len(new) - tail > cursor and new[-1 - tail] == old[-1 - tail]:
            start, tail = start - 1, tail + 1
        first, end = start - start % GROUP, min(start - start % GROUP + GROUP, len(old))
        if first // GROUP in self._locked or len(old) - tail > end:
            return old, start
        typed = new[start : len(new) - tail]
        edited = (old[first:start] + typed + old[len(old) - tail : end] + "?" * GROUP)[: end - first]
        return old[:first] + edited + old[end:], min(start + len(typed), end)
