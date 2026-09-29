"""Entry point for `codex32-gui` and for `python -m codex32_gui`."""

from codex32_gui.app import main

__all__ = ["main"]

if __name__ == "__main__":
    raise SystemExit(main())
