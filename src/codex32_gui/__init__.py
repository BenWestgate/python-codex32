"""Graphical reference implementation for codex32 Bitcoin master-seed backups.

Every screen imports GTK through `gi.repository`. The required versions are
declared once, here, so that importing any submodule selects them before a
typelib is loaded. `reading` and `wallet_setup` hold the parts that decide
something, and neither imports a toolkit, so both are testable without one.
"""

from importlib.util import find_spec

__all__ = ["__version__"]

__version__ = "1.0.0rc1"

if find_spec("gi") is not None:
    import gi

    gi.require_version("Adw", "1")
    gi.require_version("Gtk", "4.0")
