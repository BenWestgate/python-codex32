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
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gdk, GLib, Gtk

from codex32 import MasterSeed, parse_codex32
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


def _primary() -> str:
    """Read back whatever the display's primary selection holds, without blocking."""
    display = Gdk.Display.get_default()
    if display is None:
        return ""
    holder: list[str] = []
    display.get_primary_clipboard().read_text_async(None, lambda clip, done: holder.append(_text(clip, done)))
    for _attempt in range(200):
        settle()
        if holder:
            return holder[0]
    return ""


def _text(clipboard: Any, done: Any) -> str:
    try:
        return clipboard.read_text_finish(done) or ""
    except GLib.Error:
        return ""


def _primary_is_empty() -> bool:
    return _primary() == ""


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
            self.short_repair_entry,
            self.short_repair_candidate,
            self.damaged,
            self.candidate,
            self.back_to_entry,
            self.accepted_repair,
            self.completion_entry,
            self.completion_gate,
            self.preflight,
            self.network,
            self.wallet_poll_start,
            self.wallet_poll_update,
            self.wallet_poll_retries,
            self.wallet_poll_disappears,
            self.wallet_poll_stops,
            self.restore_record_gate,
            self.restore_no_record,
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
        artwork = [
            item.get_property("file")
            for item in walk(self.page())
            if isinstance(item, Gtk.Image) and item.get_property("file")
        ]
        check(
            "all six tasks use distinct book illustrations", len(artwork) == 6 == len(set(artwork)), artwork
        )
        listed[2].emit("activated")
        return True

    def typing(self) -> bool:
        page = self.page()
        check("checking a card opens one entry page", page.get_title() == "Check a card", page.get_title())
        field = field_of(page)
        check("the field starts with the frozen prefix", field.get_text() == reading.PREFIX)
        check("typing starts after the frozen prefix", field.get_position() == len(reading.PREFIX))
        field.insert_text(SHARE_C.lower(), field.get_position())
        settle()
        check(
            "pasting a full card after the frozen prefix does not duplicate it",
            "".join(field.get_text().split()) == SHARE_C,
            field.get_text(),
        )
        field.clear()
        settle()
        field.delete_text(0, 1)
        settle()
        check("the frozen prefix cannot be deleted", field.get_text() == reading.PREFIX, field.get_text())
        go = next(
            item for item in walk(page) if isinstance(item, Gtk.Button) and item.get_label() == "Continue"
        )
        check("nothing may be submitted yet", not go.get_sensitive())
        field.insert_text("X", len(reading.PREFIX))
        settle()
        check("a bad threshold is kept so it can be corrected", field.get_text() == "MS1X", field.get_text())
        field.insert_text("N", len(field.get_text()))
        settle()
        check(
            "forward typing stays frozen after the bad threshold",
            field.get_text() == "MS1X",
            field.get_text(),
        )
        field.set_text("MS1?")
        settle()
        check(
            "check rejects an unreadable threshold marker",
            any("? cannot be used" in text for text in labels(page)),
            labels(page),
        )
        field.insert_text("N", len(field.get_text()))
        settle()
        check(
            "check freezes after a question mark in the header", field.get_text() == "MS1?", field.get_text()
        )
        field.delete_text(3, 4)
        field.insert_text("2", 3)
        settle()
        field.set_text("ms12nameacd")
        settle()
        check("text is uppercased and grouped", field.get_text() == "MS12 NAME ACD", field.get_text())
        field.set_text("MS12NAMECB")
        settle()
        check(
            "a character no card can carry is named, not silently dropped",
            any("never contains B" in text for text in labels(page)),
            [text for text in labels(page) if "contains" in text],
        )
        check("and it is gone from the field", "B" not in field.get_text(), field.get_text())
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
        field.emit("activate")
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

    def short_repair_entry(self) -> bool:
        page = self.page()
        if page.get_title() != "codex32":
            return False
        rows(page)[2].emit("activated")
        page = self.page()
        field = field_of(page)
        field.set_text(SHARE_C[:-1])
        settle()
        check(
            "a 47-character card is eligible for correction", button(page, "Suggest a repair").get_sensitive()
        )
        field.emit("activate")
        return True

    def short_repair_candidate(self) -> bool:
        page = self.page()
        if page.get_title() != "Repair" or button(page, "It does not match my card") is None:
            return False
        groups = [item for item in walk(page) if "card-group" in item.get_css_classes()]
        flow = next(item for item in walk(page) if isinstance(item, Gtk.FlowBox))

        def row_positions() -> list[float]:
            children = [flow.get_child_at_index(index) for index in range(len(groups))]
            return [child.compute_bounds(flow)[1].origin.y for child in children]

        def four_columns(rows_y: list[float]) -> bool:
            return len(set(rows_y)) == (len(groups) + 3) // 4 and all(
                rows_y[index] == rows_y[(index // 4) * 4] for index in range(len(rows_y))
            )

        rows_y = row_positions()
        check("Enter invokes repair for short input", "".join(item.get_label() for item in groups) == SHARE_C)
        check(
            "ordinary repair does not claim where the error was",
            not any("guessed" in item.get_css_classes() for item in groups),
        )
        check(
            "card display uses four aligned groups per row",
            flow.get_min_children_per_line() == 4
            and flow.get_max_children_per_line() == 4
            and four_columns(rows_y),
            rows_y,
        )
        window = self.get_active_window()
        window.set_default_size(640, 620)
        settle()
        narrow = row_positions()
        window.set_default_size(1100, 620)
        settle()
        wide = row_positions()
        check(
            "card columns stay aligned when the window is resized",
            four_columns(narrow) and four_columns(wide),
        )
        press(page, "It does not match my card")
        settle()
        self.view.replace([pages.home(self.view)])
        return True

    def damaged(self) -> bool:
        page = self.page()
        check("done returns home", page.get_title() == "codex32", page.get_title())
        rows(page)[3].emit("activated")
        page = self.page()
        field = field_of(page)
        field.insert_text("X", len(reading.PREFIX))
        field.insert_text("N", len(reading.PREFIX) + 1)
        settle()
        check(
            "explicit correction does not freeze a damaged header",
            "X" in field.get_text() and "N" in field.get_text(),
        )
        field.set_text(SHARE_C[:-1] + "?")
        settle()
        check("explicit correction preserves a literal erasure", "?" in field.get_text(), field.get_text())
        fix = next(
            item
            for item in walk(page)
            if isinstance(item, Gtk.Button) and item.get_label() == "Suggest a repair"
        )
        check("a repair is offered for an unreadable character", fix.get_sensitive())
        fix.emit("clicked")
        working = self.page()
        spinners = [item for item in walk(working) if isinstance(item, Adw.Spinner)]
        settings = Gtk.Settings.get_default()
        animations = settings is None or bool(settings.get_property("gtk-enable-animations"))
        check(
            "an actual repair search shows the Adwaita spinner when animations are enabled",
            len(spinners) == 1 and spinners[0].get_visible() == animations,
            [spinner.get_visible() for spinner in spinners],
        )
        return True

    def candidate(self) -> bool:
        page = self.page()
        # The spinner shares this title, so wait for the candidate itself to arrive.
        if page.get_title() != "Repair" or button(page, "It does not match my card") is None:
            return False
        groups = [item for item in walk(page) if "card-group" in item.get_css_classes()]
        check(
            "the repair is the published vector",
            "".join(item.get_label() for item in groups) == SHARE_C,
            "".join(item.get_label() for item in groups),
        )
        guessed = [item.get_label() for item in groups if "guessed" in item.get_css_classes()]
        check("explicit correction may highlight changed windows", guessed == ["Y6PN"], guessed)
        press(page, "It does not match my card")
        return True

    def back_to_entry(self) -> bool:
        page = self.page()
        if page.get_title() != "Repair a damaged card":
            return False
        typed = "".join(field_of(page).get_text().split())
        check("refusing a repair keeps what was typed", typed == SHARE_C[:-1] + "?", typed)
        press(page, "Suggest a repair")
        return True

    def accepted_repair(self) -> bool:
        page = self.page()
        if page.get_title() != "Repair" or button(page, "It matches my card") is None:
            return False
        press(page, "It matches my card")
        settle()
        page, shown = self.page(), labels(self.page())
        check(
            "an accepted repair is never called intact",
            not any("intact" in text for text in shown),
            [text for text in shown if "intact" in text],
        )
        check(
            "and it says the card was guessed at, not read",
            any("cannot tell you it is right" in text for text in shown),
            shown[:3],
        )
        check("and the repair is still the published vector", card(page) == SHARE_C, card(page))
        press(page, "Done")
        return True

    def completion_entry(self) -> bool:
        """Thirteen unreadable characters at the end are a whole checksum."""
        page = self.page()
        if page.get_title() != "codex32":
            return False
        rows(page)[3].emit("activated")
        page = self.page()
        field = field_of(page)
        field.set_text(SHARE_C[:-13] + "?" * 13)
        settle()
        fix = button(page, "Suggest a repair")
        check("completing a checksum is offered as a repair", fix.get_sensitive())
        fix.emit("clicked")
        return True

    def completion_gate(self) -> bool:
        page = self.page()
        if page.get_title() != "Warning" or button(page, "Show the guess") is None:
            return False
        shown = labels(page)
        check("nothing about the guess is disclosed yet", card(page) == "", card(page))
        check(
            "the gate warns that completion locks earlier errors in",
            any(
                "hand-written data" in text and "locks earlier transcription errors in" in text
                for text in shown
            ),
            [text for text in shown if "hand-written" in text],
        )
        check(
            "and someone recovering a damaged card",
            any(
                "damaged card" in text and "valid-looking guess may still be wrong" in text for text in shown
            ),
            [text for text in shown if "damaged card" in text],
        )
        check(
            "and forbids replacing a checksum outright",
            any("Never erase or replace" in text for text in shown),
            [text for text in shown if "Never erase" in text],
        )
        show = button(page, "Show the guess")
        check("the guess stays hidden until YES is typed", not show.get_sensitive())
        entry = next(item for item in walk(page) if isinstance(item, Gtk.Entry))
        for typed in ("yes", "Yes", "YES please", "Y"):
            entry.set_text(typed)
            settle()
            check(f"{typed!r} does not open the gate", not show.get_sensitive())
        entry.set_text("YES")
        settle()
        check("literal YES opens it", show.get_sensitive())
        press(page, "Cancel")
        settle()
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

    def wallet_poll_start(self) -> bool:
        seed = parse_codex32(SECRET_S)
        check("the wallet poll uses a master seed", isinstance(seed, MasterSeed), type(seed).__name__)
        if not isinstance(seed, MasterSeed):
            return True
        self.wallet_polls = 0
        self.wallet_fail_once = False
        self.wallet_include_zeta = True
        self.wallet_zeta = wallet_setup.Wallet("zeta", False, False)

        def eligible(_core: Any) -> tuple[wallet_setup.Wallet, ...]:
            self.wallet_polls += 1
            if self.wallet_fail_once:
                self.wallet_fail_once = False
                raise wallet_setup.BitcoinCoreError("wallet disappeared during refresh")
            wallets = (wallet_setup.Wallet("alpha", False, False),)
            return wallets + ((self.wallet_zeta,) if self.wallet_include_zeta else ())

        wallet_setup.eligible = eligible  # type: ignore[assignment]
        wallet_setup.version_text = lambda _core: "32.0.0"  # type: ignore[assignment]
        wallet_setup.network = lambda _core: "signet"  # type: ignore[assignment]
        page = pages._wallet_page(self.view, _Stub(), seed, (self.wallet_zeta,), 0, None, False)
        self.view.replace([pages.home(self.view), page])
        return True

    def wallet_poll_update(self) -> bool:
        if self.wallet_polls == 0:
            return False
        page = self.page()
        listed = rows(page)
        check(
            "a newly empty wallet appears without a button press",
            [row.get_title() for row in listed] == ["alpha", "zeta", pages.CREATE_WALLET],
            [row.get_title() for row in listed],
        )
        zeta = next(row for row in listed if row.get_title() == "zeta")
        check("refresh preserves the selected wallet by name", zeta.get_activatable_widget().get_active())
        check("manual wallet refresh is no longer needed", button(page, "Check again") is None)
        self.wallet_fail_once = True
        self.wallet_retry_poll = self.wallet_polls
        return True

    def wallet_poll_retries(self) -> bool:
        if self.wallet_polls == self.wallet_retry_poll:
            return False
        check(
            "a transient refresh failure leaves the wallet chooser in place",
            self.page().get_title() == "Wallet",
        )
        self.wallet_include_zeta = False
        self.wallet_removal_poll = self.wallet_polls
        return True

    def wallet_poll_disappears(self) -> bool:
        if self.wallet_polls == self.wallet_removal_poll:
            return False
        page = self.page()
        listed = rows(page)
        check(
            "a selected wallet that stops being eligible disappears",
            [row.get_title() for row in listed] == ["alpha", pages.CREATE_WALLET],
            [row.get_title() for row in listed],
        )
        check(
            "a disappearing selected wallet does not select a different destination",
            not any(row.get_activatable_widget().get_active() for row in listed),
        )
        check(
            "Continue is disabled until the operator chooses again",
            not button(page, "Continue").get_sensitive(),
        )
        listed[0].get_activatable_widget().set_active(True)
        check("choosing again re-enables Continue", button(page, "Continue").get_sensitive())
        self.wallet_poll_count = self.wallet_polls
        self.wallet_poll_left = GLib.get_monotonic_time()
        self.view.replace([pages.home(self.view)])
        return True

    def wallet_poll_stops(self) -> bool:
        if GLib.get_monotonic_time() - self.wallet_poll_left < 1_300_000:
            return False
        check("wallet polling stops after leaving the page", self.wallet_polls == self.wallet_poll_count)
        return True

    def restore_record_gate(self) -> bool:
        seed = parse_codex32(SECRET_S)
        if not isinstance(seed, MasterSeed):
            return True
        self.restore_poll_count = self.wallet_polls
        wallet_setup.identity = lambda _core, _secret: ("00112233", "identifier note")  # type: ignore[assignment]
        pages._restore(self.view, _Stub(), seed)
        page = self.page()
        check("restore asks for an unseen record fingerprint", page.get_title() == "Wallet record")
        check("the recovered fingerprint stays hidden", "00112233" not in " ".join(labels(page)))
        press(page, "I have no wallet record")
        return True

    def restore_no_record(self) -> bool:
        page = self.page()
        if page.get_title() != "No wallet record":
            return False
        check("no-record path reveals the recovered fingerprint", "00112233" in " ".join(labels(page)))
        check("no-record path requires explicit confirmation", button(page, "Restore anyway") is not None)
        check("revealed fingerprint cannot be typed back in this attempt", button(page, "Go back") is None)
        press(page, "Stop")
        check("stopping did not list a wallet", self.wallet_polls == self.restore_poll_count)
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
        field.set_text("MS12C")
        settle()
        check(
            "the first incompatible backup-identifier character pauses entry",
            any("backup identifier NAME" in text for text in labels(page)),
            [text for text in labels(page) if "backup" in text],
        )
        field.insert_text("A", len(field.get_text()))
        settle()
        check(
            "forward typing stays frozen after the incompatible identifier",
            "".join(field.get_text().split()) == "MS12C",
            field.get_text(),
        )
        field.set_text("MS12?")
        settle()
        field.insert_text("A", len(field.get_text()))
        settle()
        check(
            "an erasure in an incompatible header lets multi-card entry continue",
            "".join(field.get_text().split()) == "MS12?A",
            field.get_text(),
        )
        field.set_text("MS12NAME")
        settle()
        field.set_text(OTHER_BACKUP)
        settle()
        check(
            "a card from a different split is refused at its threshold",
            any("different split" in text for text in labels(page)),
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
        check("a replacement card is named, never counted", page.get_title() == "Card D", page.get_title())
        check(
            "and nothing on it states a total",
            not any(" of 1" in text for text in labels(page)),
            [text for text in labels(page) if " of " in text],
        )
        self.made = card(page)
        check("the derived card is the published vector", self.made == DERIVED_D, self.made)
        press(page, "I have written it down")
        return True

    def read_back(self) -> bool:
        page = self.page()
        field = field_of(page)
        check("the read-back is named the same way", page.get_title() == "Card D", page.get_title())
        check("read-back starts completely empty", field.get_text() == "", field.get_text())
        field.set_text(self.made)
        settle()
        field.select_region(0, -1)
        settle()
        check("selecting a card does not publish it", _primary_is_empty(), _primary())
        field.set_text(self.made[:-4] + "QQQQ")
        settle()
        press(page, "Confirm card")
        mismatches = [
            item.get_label()
            for item in walk(page)
            if "card-group" in item.get_css_classes() and "mismatch" in item.get_css_classes()
        ]
        check(
            "a mistyped group is highlighted without revealing its correction",
            mismatches == ["QQQQ"],
            mismatches,
        )
        check(
            "the mismatch display contains only what was typed",
            card(page) == self.made[:-4] + "QQQQ",
            card(page),
        )
        field.set_text(self.made.lower())
        settle()
        field.emit("activate")
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
