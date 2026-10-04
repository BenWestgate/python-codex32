"""One background operation at a time, and results that never reach a page that is gone."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TypeVar

from gi.repository import Adw, GLib

from codex32.errors import CodexError
from codex32_gui.wallet_setup import BitcoinCoreError

_UNFINISHED = (
    "That operation stopped in a way this program did not expect. If it was writing to Bitcoin "
    "Core, check there what state the wallet is in before trying again."
)
_gate = threading.Lock()
Result = TypeVar("Result")


def showing(view: Adw.NavigationView, page: Adw.NavigationPage) -> bool:
    """Report whether a page is still on the navigation stack.

    Being rooted in the window is not the same test: a page keeps its root for
    the length of the navigation animation, so a result arriving during it would
    still be handed to a page the operator has already left.
    """
    stack = view.get_navigation_stack()
    return any(stack.get_item(position) is page for position in range(stack.get_n_items()))


def run(
    view: Adw.NavigationView,
    page: Adw.NavigationPage,
    work: Callable[[], Result],
    done: Callable[[Result | Exception], None],
) -> None:
    """Queue one blocking library call off the main loop and deliver its result back.

    `correct` runs for up to ten seconds and every Bitcoin Core call waits on a
    subprocess, so neither may run on the main loop. Background jobs share one
    gate, so a wallet-list poll cannot overlap an import. A result for a page
    that is gone is dropped.

    The thread is deliberately not a daemon. `BitcoinCore.initialize` locks an
    unlocked wallet again from a `finally`, and Python does not run `finally`
    blocks in daemon threads while the interpreter is shutting down, so closing
    the window during an import would otherwise leave that wallet open.
    """
    _start(view, page, work, done, claimed=False, daemon=False)


def poll(
    view: Adw.NavigationView,
    page: Adw.NavigationPage,
    work: Callable[[], Result],
    done: Callable[[Result | Exception], None],
) -> bool:
    """Start one low-priority poll, or skip it while another job owns the gate."""
    if not _gate.acquire(blocking=False):
        return False
    _start(view, page, work, done, claimed=True, daemon=True)
    return True


def _start(
    view: Adw.NavigationView,
    page: Adw.NavigationPage,
    work: Callable[[], Result],
    done: Callable[[Result | Exception], None],
    *,
    claimed: bool,
    daemon: bool,
) -> None:

    def worker() -> None:
        outcome: Result | Exception = RuntimeError(_UNFINISHED)
        if not claimed:
            _gate.acquire()
        try:
            outcome = work()
        except (CodexError, BitcoinCoreError, OSError, TypeError, ValueError) as error:
            outcome = error
        finally:
            _gate.release()
            GLib.idle_add(deliver, outcome)

    def deliver(outcome: Result | Exception) -> bool:
        if showing(view, page):
            done(outcome)
        return False

    threading.Thread(target=worker, daemon=daemon).start()
