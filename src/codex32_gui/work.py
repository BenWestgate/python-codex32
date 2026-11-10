"""One background operation at a time, and results that never reach a page that is gone."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable

from gi.repository import Adw, GLib

from codex32.errors import CodexError
from codex32_gui.wallet_setup import BitcoinCoreError

_UNFINISHED = (
    "That operation stopped in a way this program did not expect. If it was writing to Bitcoin "
    "Core, check there what state the wallet is in before trying again."
)
_BUSY = "Another operation is still finishing. Try again in a moment."
_running = False


def showing(view: Adw.NavigationView, page: Adw.NavigationPage) -> bool:
    """Report whether a page is still on the navigation stack.

    Being rooted in the window is not the same test: a page keeps its root for
    the length of the navigation animation, so a result arriving during it would
    still be handed to a page the operator has already left.
    """
    stack = view.get_navigation_stack()
    return any(stack.get_item(position) is page for position in range(stack.get_n_items()))


def run[Result](
    view: Adw.NavigationView,
    page: Adw.NavigationPage,
    work: Callable[[], Result],
    done: Callable[[Result | Exception], None],
) -> None:
    """Run one blocking library call off the main loop and deliver its result back.

    `correct` runs for up to ten seconds and every Bitcoin Core call waits on a
    subprocess, so neither may run on the main loop. The page that starts an
    operation shows a spinner and cannot be left, so only one is ever in flight,
    and a result for a page that is gone anyway is dropped. The result is
    delivered from `finally`, so a failure no screen anticipated still releases
    the program instead of leaving it spinning.

    The thread is deliberately not a daemon. `BitcoinCore.initialize` locks an
    unlocked wallet again from a `finally`, and Python does not run `finally`
    blocks in daemon threads while the interpreter is shutting down, so closing
    the window during an import would otherwise leave that wallet open.
    """
    global _running
    if _running:
        GLib.idle_add(_busy, view, page, done)
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
        if showing(view, page):
            done(outcome)
        return False

    threading.Thread(target=worker).start()


def watch(
    view: Adw.NavigationView, page: Adw.NavigationPage, ready: Callable[[], bool], then: Callable[[], None]
) -> None:
    """Ask `ready` off the main loop every two seconds while `page` is in front; once it says yes, `then`."""
    # This is how the command line waits for something done in Bitcoin Core's own
    # window, so the operator never has to come back and say it is done. It goes on
    # once only: should that fail, the page must not try it again unasked.

    def check() -> None:
        found = False
        with contextlib.suppress(BitcoinCoreError, OSError, ValueError, TypeError):
            found = ready()
        GLib.idle_add(arrive, found)

    def arrive(found: bool) -> bool:
        if found and view.get_visible_page() is page and not _running:
            then()
        elif showing(view, page):
            GLib.timeout_add_seconds(2, ask)
        return False

    def ask() -> bool:
        # One question at a time: the next is only scheduled once this one is answered.
        if view.get_visible_page() is page and not _running:
            threading.Thread(target=check, daemon=True).start()
            return False
        return showing(view, page)

    GLib.timeout_add_seconds(2, ask)


def _busy[Result](
    view: Adw.NavigationView,
    page: Adw.NavigationPage,
    done: Callable[[Result | Exception], None],
) -> bool:
    if showing(view, page):
        done(RuntimeError(_BUSY))
    return False
