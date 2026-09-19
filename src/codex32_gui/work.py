"""One background operation at a time, and results that never reach a page that is gone."""

from __future__ import annotations

import threading
from collections.abc import Callable

from gi.repository import Adw, GLib

from codex32.errors import CodexError
from codex32_gui.wallet_setup import BitcoinCoreError

_UNFINISHED = "That operation did not finish. Nothing was changed."
_BUSY = "Another Bitcoin Core operation is still finishing. Try again in a moment."
_running = False


def run[Result](
    page: Adw.NavigationPage,
    work: Callable[[], Result],
    done: Callable[[Result | Exception], None],
) -> None:
    """Run one blocking library call off the main loop and deliver its result back.

    `correct` runs for up to ten seconds and every Bitcoin Core call waits on a
    subprocess, so neither may run on the main loop. The page that starts an
    operation shows a spinner and takes no further input, so only one is ever in
    flight, and a page left before its result arrives receives nothing. The
    result is delivered from `finally`, so a failure no screen anticipated still
    releases the program instead of leaving it spinning.
    """
    global _running
    if _running:
        GLib.idle_add(_busy, done)
        return
    _running = True

    def worker() -> None:
        outcome: Result | Exception = RuntimeError(_UNFINISHED)
        try:
            outcome = work()
        except (CodexError, BitcoinCoreError, OSError, TypeError, ValueError) as error:
            outcome = error
        finally:
            GLib.idle_add(deliver, outcome)

    def deliver(outcome: Result | Exception) -> bool:
        global _running
        _running = False
        if page.get_root() is not None:
            done(outcome)
        return False

    threading.Thread(target=worker, daemon=True).start()


def _busy[Result](done: Callable[[Result | Exception], None]) -> bool:
    done(RuntimeError(_BUSY))
    return False
