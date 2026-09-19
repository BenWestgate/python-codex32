"""Graphical reference implementation for codex32 Bitcoin master-seed backups.

Every screen imports GTK through `gi.repository`. The required versions are
declared once, here, so that importing any submodule selects them before a
typelib is loaded. `reading` and `wallet_setup` hold the parts that decide
something, and neither imports a toolkit, so both are testable without one.

This is also where the accessibility bus is turned off. GTK otherwise publishes
every label and entry in the window on the desktop's shared accessibility bus,
where any other program running as the same user can read them, which on this
window would mean the master seed, the cards and the wallet passphrase. The
setting is left alone when the operator has already chosen one, so anyone who
needs a screen reader can run `GTK_A11Y=atspi codex32-gui` and get it back.
"""

from importlib.util import find_spec

__all__ = ["__version__"]

__version__ = "1.0.0rc1"

if find_spec("gi") is not None:
    import gi

    gi.require_version("Adw", "1")
    gi.require_version("Gtk", "4.0")

    from gi.repository import GLib

    GLib.setenv("GTK_A11Y", "none", False)
