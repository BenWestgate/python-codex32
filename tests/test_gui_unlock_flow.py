"""The unlock and retry flow in a real GTK window, against a stand-in for bitcoin-cli.

Skipped unless libadwaita 1.5 or later and a display are available. Headless:
`xvfb-run -a python -m pytest tests/test_gui_unlock_flow.py`.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest

gi = pytest.importorskip("gi")
try:
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, GLib, Gtk
except (ImportError, ValueError):
    pytest.skip("libadwaita is not installed", allow_module_level=True)
if (Adw.get_major_version(), Adw.get_minor_version()) < (1, 5) or Gdk.Display.get_default() is None:
    pytest.skip("needs libadwaita 1.5 and a display", allow_module_level=True)

from test_gui_wallet_setup import _SEED, _Core, _Wallet

from codex32._bitcoin_core import BitcoinCore, BitcoinCoreError
from codex32_gui import pages, wallet_setup

RIGHT = "right horse"


class _Flow:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.fake = _Core({"cold": _Wallet(True, True)})
        self.imports: list[str] = []
        self.fail_import = False
        self.fail_lock = False
        original = _Core._reply

        def reply(core: _Core, method: str, arguments: list[str], name: str | None) -> str:
            if method == "walletpassphrase" and arguments[0] != RIGHT:
                raise BitcoinCoreError("incorrect passphrase")
            if method == "walletlock" and self.fail_lock:
                raise BitcoinCoreError("The local Bitcoin Core command did not complete.")
            return original(core, method, arguments, name)

        def initialize(_core: BitcoinCore, _secret: object, name: str, **_keywords: object) -> str:
            self.imports.append(name)
            if self.fake.wallets[name].locked:
                raise BitcoinCoreError("Bitcoin Core is waiting for something to be done in its own window.")
            if self.fail_import:
                raise BitcoinCoreError("Bitcoin Core did not import every private descriptor.")
            return name

        monkeypatch.setattr(_Core, "_reply", reply)
        monkeypatch.setattr(subprocess, "run", lambda command, **keywords: self.fake.run(command, **keywords))
        monkeypatch.setattr(wallet_setup, "initialize", initialize)
        monkeypatch.setattr(wallet_setup, "fingerprint", lambda _core, _secret: "00000000")
        self.core = BitcoinCore("bitcoin-cli", "regtest", 320000)
        self.view = Adw.NavigationView()
        self.window = Adw.Window(content=self.view, default_width=880, default_height=620)
        self.view.push(pages.home(self.view))
        self.window.present()

    def pump(self, seconds: float) -> None:
        context, end = GLib.MainContext.default(), time.monotonic() + seconds
        while time.monotonic() < end:
            while context.pending():
                context.iteration(False)
            time.sleep(0.01)

    def until(self, done: Callable[[], bool], seconds: float = 8.0) -> None:
        end = time.monotonic() + seconds
        while not done() and time.monotonic() < end:
            self.pump(0.05)

    def unlock_page(self) -> Adw.NavigationPage:
        found = wallet_setup.eligible(self.core)
        self.view.push(pages._wallet_page(self.view, self.core, _SEED, found, "now", None, False))
        page = pages._unlock_page(self.view, self.core, _SEED, found[0], "now", None)
        self.view.push(page)
        self.pump(0.3)
        return page

    def submit(self, page: Adw.NavigationPage, passphrase: str) -> None:
        _find(page, Adw.PasswordEntryRow).set_text(passphrase)
        _find(page, Gtk.Button, "Unlock").emit("clicked")

    @property
    def title(self) -> str:
        return str(self.view.get_visible_page().get_title())

    @property
    def alert(self) -> str:
        dialog = self.window.get_visible_dialog()
        return "" if dialog is None else str(dialog.get_body())


def _widgets(root: Any) -> Iterator[Any]:
    child = root.get_first_child()
    while child is not None:
        yield child
        yield from _widgets(child)
        child = child.get_next_sibling()


def _find(root: Any, kind: type, label: str | None = None) -> Any:
    return next(
        w for w in _widgets(root) if isinstance(w, kind) and (label is None or w.get_label() == label)
    )


@pytest.fixture
def flow(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Flow]:
    made = _Flow(monkeypatch)
    yield made
    made.window.destroy()


def test_a_mistyped_passphrase_is_typed_again_on_the_same_page(flow: _Flow) -> None:
    page = flow.unlock_page()
    flow.submit(page, "wrong horse")
    flow.until(lambda: bool(flow.alert))
    assert flow.view.get_visible_page() is page
    assert "did not accept" in flow.alert
    assert _find(page, Adw.PasswordEntryRow).get_text() == ""
    assert flow.imports == [] and flow.fake.wallets["cold"].locked
    flow.window.get_visible_dialog().close()
    flow.submit(page, RIGHT)
    flow.until(lambda: flow.title == "Finished")
    flow.pump(5)
    assert flow.title == "Finished"
    assert flow.imports == ["cold"] and flow.fake.wallets["cold"].locked


def test_an_unlock_in_bitcoin_core_is_noticed_once_and_locked_again(flow: _Flow) -> None:
    flow.unlock_page()
    flow.pump(2.5)
    assert flow.imports == []
    flow.fake.wallets["cold"].locked = False
    flow.until(lambda: flow.title == "Finished")
    flow.pump(5)
    assert flow.title == "Finished"
    assert flow.imports == ["cold"] and flow.fake.wallets["cold"].locked


def test_a_failed_import_shows_a_fresh_list_and_is_never_retried_unasked(flow: _Flow) -> None:
    flow.unlock_page()
    flow.fail_import = True
    flow.fake.wallets["cold"].locked = False
    flow.until(lambda: bool(flow.alert))
    assert flow.title == "Wallet"
    assert "did not import" in flow.alert and "fresh from Bitcoin Core" in flow.alert
    assert flow.fake.wallets["cold"].locked
    flow.window.get_visible_dialog().close()
    flow.fake.wallets["cold"].locked = False
    flow.pump(6)
    assert flow.imports == ["cold"]


def test_typing_while_bitcoin_core_is_unlocked_imports_once(flow: _Flow) -> None:
    page = flow.unlock_page()
    flow.pump(1)
    flow.fake.wallets["cold"].locked = False
    flow.submit(page, RIGHT)
    flow.until(lambda: flow.title == "Finished")
    flow.pump(5)
    assert flow.imports == ["cold"]


def test_a_failed_relock_is_said(flow: _Flow) -> None:
    page = flow.unlock_page()
    flow.fail_lock = True
    flow.submit(page, RIGHT)
    flow.until(lambda: bool(flow.alert))
    assert "Confirm in Bitcoin Core that the wallet is locked" in flow.alert


def test_a_worker_started_by_a_worker_goes_back_to_the_page_with_the_seed(
    flow: _Flow, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_core: BitcoinCore) -> tuple[wallet_setup.Wallet, ...]:
        raise BitcoinCoreError("The local Bitcoin Core command did not complete.")

    monkeypatch.setattr(wallet_setup, "verify", lambda *_arguments: None)
    monkeypatch.setattr(wallet_setup, "eligible", broken)
    page = pages._fingerprint_page(flow.view, flow.core, _SEED, 0, restoring=True)
    flow.view.push(page)
    flow.pump(0.3)
    fingerprint, date = (w for w in _widgets(page) if isinstance(w, Adw.EntryRow))
    fingerprint.set_text("00000000")
    date.set_text("2024-01-01")
    _find(page, Gtk.Button, "Check and continue").emit("clicked")
    flow.until(lambda: bool(flow.alert))
    assert flow.view.get_visible_page() is page
    assert "did not complete" in flow.alert
