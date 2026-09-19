"""Walk the graphical program's screens and report what they do.

The checks here need a display, so they are not part of the pytest suite. Run
them against a throwaway X server:

    Xvfb :90 -screen 0 900x700x24 &
    DISPLAY=:90 GDK_BACKEND=x11 PYTHONPATH=src python3 tools/gui_walkthrough.py

Nothing here touches Bitcoin Core: the preflight is answered by a stand-in, so
no wallet is opened, created, or changed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from codex32_gui import app, pages, reading, wallet_setup

SHARE_A = "MS12NAMEA320ZYXWVUTSRQPNMLKJHGFEDCAXRPP870HKKQRM"
SHARE_C = "MS12NAMECACDEFGHJKLMNPQRSTUVWXYZ023FTR2GDZMPY6PN"
DERIVED_D = "MS12NAMEDLL4F8JLH4E5VDVULDLFXU2JHDNLSM97XVENRXEG"
SECRET_S = "MS12NAMES6XQGUZTTXKEQNJSJZV4JV3NZ5K3KWGSPHUH6EVW"
OTHER_BACKUP = "ms13cashcacdefghjklmnpqrstuvwxyz023949xq35my48dr"
NETWORKS = ("mainnet", "signet", "regtest")

failures: list[str] = []
asked: list[str | None] = []


class _Stub:
    """Stands in for a connected Bitcoin Core, and answers nothing else."""

    version = 320000
    chain = "signet"


def _connect(chain: str | None = None) -> Any:
    asked.append(chain)
    if chain is None:
        raise wallet_setup.Offer(NETWORKS)
    return _Stub()


def check(name: str, condition: bool, detail: object = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'}  {name} {detail}", flush=True)
    if not condition:
        failures.append(name)


def walk(widget: Any) -> Iterator[Any]:
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from walk(child)
        child = child.get_next_sibling()


def card(page: Any) -> str:
    return "".join(item.get_label() for item in walk(page) if "card-group" in item.get_css_classes())


def button(page: Any, label: str) -> Any:
    found = [item for item in walk(page) if isinstance(item, Gtk.Button) and item.get_label() == label]
    return found[0] if found else None


def field_of(page: Any) -> Any:
    return next(item for item in walk(page) if type(item).__name__ == "Codex32Entry")


def press(page: Any, label: str) -> None:
    next(item for item in walk(page) if isinstance(item, Gtk.Button) and item.get_label() == label).emit(
        "clicked"
    )


def labels(page: Any) -> list[str]:
    return [item.get_label() for item in walk(page) if isinstance(item, Gtk.Label) and item.get_label()]


def rows(page: Any) -> list[Any]:
    return [item for item in walk(page) if type(item).__name__ == "ActionRow"]


def settle() -> None:
    context = GLib.MainContext.default()
    for _attempt in range(500):
        if not context.pending():
            return
        context.iteration(False)


class Walkthrough(app.Application):
    """Drive the window through one step per main-loop turn."""

    def do_activate(self) -> None:
        super().do_activate()
        self.view = self.get_active_window().get_content()
        self.steps: list[Callable[[], bool]] = [
            self.home,
            self.typing,
            self.intact,
            self.damaged,
            self.candidate,
            self.back_to_entry,
            self.preflight,
            self.network,
            self.letters,
            self.basis,
            self.second_card,
            self.derived,
            self.read_back,
            self.new_card_done,
            self.seed_entry,
            self.seed_shown,
        ]
        GLib.timeout_add(300, self.pump)

    def page(self) -> Any:
        return self.view.get_visible_page()

    def pump(self) -> bool:
        if not self.steps:
            self.quit()
            return False
        if self.steps[0]():
            self.steps.pop(0)
        GLib.timeout_add(200, self.pump)
        return False

    def home(self) -> bool:
        listed = rows(self.page())
        check("home offers six tasks", len(listed) == 6, [row.get_title() for row in listed])
        listed[2].emit("activated")
        return True

    def typing(self) -> bool:
        page = self.page()
        check("checking a card opens one entry page", page.get_title() == "Check a card", page.get_title())
        field = field_of(page)
        check("the field starts with the frozen prefix", field.get_text() == reading.PREFIX)
        go = next(
            item for item in walk(page) if isinstance(item, Gtk.Button) and item.get_label() == "Continue"
        )
        check("nothing may be submitted yet", not go.get_sensitive())
        field.set_text("ms12nameacd")
        settle()
        check("text is uppercased and grouped", field.get_text() == "MS12 NAME ACD", field.get_text())
        field.set_text("MS10NAMEA")
        settle()
        check("an impossible header stops the rest", field.get_text() == "MS10 NAME A", field.get_text())
        check(
            "and says why",
            any("never split is card S" in text for text in labels(page)),
            [text for text in labels(page) if "S" in text],
        )
        field.set_text(SHARE_C)
        settle()
        check("a valid card may be submitted", go.get_sensitive())
        go.emit("clicked")
        return True

    def intact(self) -> bool:
        page = self.page()
        text = labels(page)
        check("an intact card is reported as intact", any("This card is intact" in item for item in text))
        check(
            "the wording never states how many cards exist",
            any("Any 2 cards from that backup" in item for item in text)
            and not any(" of 3" in item for item in text),
            [item for item in text if "cards" in item],
        )
        press(page, "Done")
        return True

    def damaged(self) -> bool:
        page = self.page()
        check("done returns home", page.get_title() == "codex32", page.get_title())
        rows(page)[3].emit("activated")
        page = self.page()
        field = field_of(page)
        field.set_text(SHARE_C[:-1] + "?")
        settle()
        fix = next(
            item
            for item in walk(page)
            if isinstance(item, Gtk.Button) and item.get_label() == "Suggest a repair"
        )
        check("a repair is offered for an unreadable character", fix.get_sensitive())
        fix.emit("clicked")
        return True

    def candidate(self) -> bool:
        page = self.page()
        if page.get_title() != "Repair":
            return False
        groups = [item for item in walk(page) if "card-group" in item.get_css_classes()]
        check(
            "the repair is the published vector",
            "".join(item.get_label() for item in groups) == SHARE_C,
            "".join(item.get_label() for item in groups),
        )
        guessed = [item.get_label() for item in groups if "guessed" in item.get_css_classes()]
        check("only the guessed window is highlighted", guessed == ["Y6PN"], guessed)
        press(page, "It does not match my card")
        return True

    def back_to_entry(self) -> bool:
        page = self.page()
        if page.get_title() != "Repair a damaged card":
            return False
        typed = "".join(field_of(page).get_text().split())
        check("refusing a repair keeps what was typed", typed == SHARE_C[:-1] + "?", typed)
        self.view.replace([pages.home(self.view)])
        return True

    def preflight(self) -> bool:
        page = self.page()
        if page.get_title() != "codex32":
            return False
        rows(page)[0].emit("activated")
        return True

    def network(self) -> bool:
        page = self.page()
        if page.get_title() == "Bitcoin Core":
            return False
        check("more than one network asks which", page.get_title() == "Network", page.get_title())
        listed = [row.get_title() for row in rows(page)]
        check("every running network is listed", tuple(listed) == NETWORKS, listed)
        for row in rows(page):
            if row.get_title() == "signet":
                row.get_activatable_widget().set_active(True)
        press(page, "Continue")
        settle()
        check("the chosen network is the one used", asked == [None, "signet"], asked)
        self.view.replace([pages.home(self.view)])
        return True

    def letters(self) -> bool:
        page = self.page()
        if page.get_title() != "codex32":
            return False
        rows(page)[4].emit("activated")
        page = self.page()
        check("replacing a card starts with a letter", page.get_title() == "New card", page.get_title())
        offered = [item.get_label() for item in walk(page) if "card-group" in item.get_css_classes()]
        check("thirty-one ordinary letters, and no S", len(offered) == 31 and "S" not in offered, offered)
        flow = next(item for item in walk(page) if isinstance(item, Gtk.FlowBox))
        for position in range(31):
            child = flow.get_child_at_index(position)
            if child.get_child().get_label() == "D":
                flow.select_child(child)
        press(page, "Continue")
        return True

    def basis(self) -> bool:
        page = self.page()
        field = field_of(page)
        field.set_text(DERIVED_D)
        settle()
        check("the letter being made cannot also be entered", not button(page, "Continue").get_sensitive())
        field.set_text(SHARE_A)
        settle()
        check("an existing card is accepted", button(page, "Continue").get_sensitive())
        press(page, "Continue")
        return True

    def second_card(self) -> bool:
        page = self.page()
        field = field_of(page)
        check("the known header is pre-filled", field.get_text() == "MS12 NAME", field.get_text())
        field.set_text(SHARE_A)
        settle()
        check("the same card cannot be entered twice", not button(page, "Continue").get_sensitive())
        field.set_text(OTHER_BACKUP)
        settle()
        check(
            "a card from another backup is named and refused",
            any("belongs to backup CASH" in text for text in labels(page)),
            [text for text in labels(page) if "backup" in text],
        )
        field.set_text(SHARE_C)
        settle()
        press(page, "Continue")
        return True

    def derived(self) -> bool:
        page = self.page()
        if button(page, "I have written it down") is None:
            return False
        self.made = card(page)
        check("the derived card is the published vector", self.made == DERIVED_D, self.made)
        press(page, "I have written it down")
        return True

    def read_back(self) -> bool:
        page = self.page()
        field = field_of(page)
        field.set_text(self.made[:-4] + "QQQQ")
        settle()
        press(page, "Confirm card")
        check(
            "a mistyped group is named and refused",
            any("Group 12 does not match" in text for text in labels(page)),
            [text for text in labels(page) if "Group" in text],
        )
        field.set_text(self.made.lower())
        settle()
        press(page, "Confirm card")
        return True

    def new_card_done(self) -> bool:
        page = self.page()
        if button(page, "Done") is None:
            return False
        text = labels(page)
        check("the new card is reported confirmed", any("is written and confirmed" in item for item in text))
        check("and the wallet is said to be untouched", any("wallet is untouched" in item for item in text))
        check("and no card count is stated", not any(" of 3" in item for item in text), text)
        press(page, "Done")
        return True

    def seed_entry(self) -> bool:
        page = self.page()
        if page.get_title() != "codex32":
            return False
        rows(page)[5].emit("activated")
        for text in (SHARE_A, SHARE_C):
            page = self.page()
            field_of(page).set_text(text)
            settle()
            press(page, "Continue")
        return True

    def seed_shown(self) -> bool:
        page = self.page()
        if page.get_title() != "Master seed":
            return False
        check("two cards recover the published secret", card(page) == SECRET_S, card(page))
        check(
            "and the screen warns before anything else",
            any("take every coin" in text for text in labels(page)),
            [text for text in labels(page) if "coin" in text],
        )
        return True


def main() -> int:
    wallet_setup.connect = _connect  # type: ignore[assignment]
    Walkthrough().run(["gui_walkthrough"])
    print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'every check passed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
