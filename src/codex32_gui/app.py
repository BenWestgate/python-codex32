"""The window: one navigation view, one stylesheet, and no command arguments."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from gi.repository import Adw, Gdk, Gio, Gtk

from codex32_gui import __version__, pages
from codex32_gui.style import CSS

USAGE = "usage: codex32-gui\n\nOpens the codex32 window. It takes no arguments: never put a secret in one.\n"


class Application(Adw.Application):
    """One window, with no D-Bus name, no settings, no recent list, and no files."""

    def __init__(self) -> None:
        super().__init__(application_id=None, flags=Gio.ApplicationFlags.NON_UNIQUE)

    def do_activate(self) -> None:
        display = Gdk.Display.get_default()
        if display is not None:
            provider = Gtk.CssProvider()
            provider.load_from_string(CSS)
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        view = Adw.NavigationView()
        view.push(pages.home(view))
        window = Adw.ApplicationWindow(
            application=self,
            title="codex32",
            default_width=880,
            default_height=620,
            content=view,
        )
        window.present()


def main(argv: Sequence[str] | None = None) -> int:
    """Open the window. Arguments are refused so that no secret can be passed in one."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--version"]:
        print(__version__)
        return 0
    if arguments in (["-h"], ["--help"]):
        print(USAGE, end="")
        return 0
    if arguments:
        print(USAGE, end="", file=sys.stderr)
        return 2
    return int(Application().run(["codex32-gui"]))
