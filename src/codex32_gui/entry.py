"""The one field that interprets codex32 keystrokes."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal, cast

from gi.repository import GLib, Gtk

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


class Codex32Entry(Gtk.Entry):
    """One grouped field with explicit import, correction, and read-back behavior."""

    __gtype_name__ = "Codex32Entry"

    def __init__(
        self,
        *,
        accepted: tuple[str, ...] = (),
        length: int | None = None,
        mode: EntryMode = "import",
        expected_header: tuple[int, str] | None = None,
    ) -> None:
        super().__init__()
        if mode == "readback" and length is None:
            raise ValueError("read-back entry requires the card length")
        self._accepted, self._length, self._mode = accepted, length, mode
        self._expected_header, self._pending = expected_header, 0
        self._limit = (length or TEXT_LENGTHS[-1]) + SLACK
        self._dropped, self._rewriting, self._unpublishing = "", False, 0
        self._damaged_header, self._last_header_fault = False, ""
        self._stable = "" if mode == "readback" else PREFIX
        self.set_hexpand(True)
        self.add_css_class("card-entry")
        self.set_input_hints(Gtk.InputHints.NO_SPELLCHECK | Gtk.InputHints.NO_EMOJI)
        self.set_text(self._stable)
        self.set_position(-1)
        self.connect("changed", self._schedule)
        self.connect("notify::selection-bound", self._unpublish)
        self.connect("notify::cursor-position", self._unpublish)
        GLib.idle_add(self.set_position, -1)

    def prefill(self, text: str) -> None:
        """Offer a known header that the operator may still overtype."""
        if self._mode == "readback":
            raise ValueError("read-back entry cannot be prefilled")
        self._damaged_header = False
        self._stable = grouped(normalize(text))
        self.set_text(self._stable)
        self.set_position(-1)

    def reading(self) -> Reading:
        """Return the current reading of this field."""
        if self._mode == "readback":
            return readback(self.get_text(), cast(int, self._length))
        state = read(normalize(self.get_text()), accepted=self._accepted, length=self._length)
        if not self._damaged_header and (fault := self._header_fault()):
            state = replace(state, artifact=None, message=fault, level="error")
        if self._dropped and state.artifact is None and state.level != "error":
            return replace(state, message=self._dropped, level="error")
        return state

    def header_blocked(self) -> bool:
        """Report whether ordinary entry is waiting for a damaged-header decision."""
        return self._mode == "import" and not self._damaged_header and bool(self._header_fault())

    def allow_damaged_header(self) -> None:
        """Let ordinary entry continue after the operator chooses to transcribe damage literally."""
        self._damaged_header = True
        self._last_header_fault = ""

    def clear(self) -> None:
        """Drop the entered recovery text."""
        self._dropped, self._damaged_header, self._last_header_fault = "", False, ""
        self._stable = "" if self._mode == "readback" else PREFIX
        self.set_text(self._stable)
        self.set_position(-1)

    def _header_fault(self, raw: str | None = None) -> str:
        if self._mode == "readback":
            return ""
        value = self.get_text() if raw is None else raw
        compact = "".join(value.split()).upper()
        text = compact if compact.startswith(PREFIX) else normalize(value)
        return header_fault(text, self._accepted, self._expected_header)

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
        normalizer = normalize_readback if self._mode == "readback" else normalize
        compact = "".join(raw.split()).upper()
        if self._mode != "readback" and not compact.startswith(PREFIX):
            self.error_bell()
            self._rewrite(self._stable, -1)
            return False
        duplicated_prefix = self._mode == "import" and compact.startswith(PREFIX + PREFIX)
        source = compact[len(PREFIX) :] if duplicated_prefix else raw
        canonical = normalizer(source)[: self._limit]
        shown = grouped(canonical)
        self._dropped = "" if self._mode == "readback" else lookalike_fault(raw)
        fault = self._header_fault(canonical) if self._mode == "import" and not self._damaged_header else ""
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
