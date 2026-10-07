"""The codex32 field keeps a selected card off the primary clipboard."""

from __future__ import annotations

import pytest

gi = pytest.importorskip("gi")
try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib, Gtk
except (ImportError, ValueError):
    pytest.skip("GTK 4 is unavailable", allow_module_level=True)
if not Gtk.init_check() or Gdk.Display.get_default() is None:
    pytest.skip("no display for GTK", allow_module_level=True)

from data.bip93_vectors import VECTOR_2

from codex32_gui.entry import Codex32Entry


def _settle() -> None:
    while GLib.MainContext.default().iteration(False):
        pass


def test_selecting_in_the_field_leaves_nothing_on_the_primary_clipboard() -> None:
    field = Codex32Entry()
    field.prefill(VECTOR_2["share_A"])
    window = Gtk.Window(child=field)
    window.present()
    _settle()

    field.select_region(0, -1)
    _settle()
    assert window.get_display().get_primary_clipboard().get_content() is None
    window.destroy()
