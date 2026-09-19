"""One function per screen: build the widgets, wire one action, return the page.

No screen decides anything about codex32 text. Parsing, correction, recovery,
sharing, entropy, and every Bitcoin Core operation belong to the library.
"""

from __future__ import annotations

import difflib
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from gi.repository import Adw, Gtk

from codex32 import (
    ConfirmationResult,
    CoreLightningSecret,
    CorrectionCandidate,
    CreationCeremony,
    MasterSeed,
    Secret,
    Share,
    derive_share,
    generate_master_seed,
    recover_secret,
)
from codex32.errors import CodexError
from codex32.generation import ORDINARY_INDICES
from codex32_gui import reading, wallet_setup, work
from codex32_gui.entry import Codex32Entry
from codex32_gui.wallet_setup import BitcoinCore

Artifact = Share | Secret
Accept = Callable[[Artifact], None]
Timestamp = int | Literal["now"]

LEVELS = ("dim-label", "error", "warning", "success")
DONE_ICON = "object-select-symbolic"
_ICON_STYLE = {DONE_ICON: "success", "dialog-error-symbolic": "error"}
SEED_SIZES = ((16, "128-bit seed, 48 characters"), (32, "256-bit seed, 74 characters"))
PRESETS = (
    (2, 3, "Three cards, any two recover (recommended)"),
    (3, 5, "Five cards, any three recover"),
    (0, 1, "One card"),
)
CREATE_WALLET = "Create a new wallet"
NO_CAMERA = (
    "Do not photograph this and do not type it into any website, chat or password manager. "
    "Paper and pen only."
)
NOT_PROOF = (
    "A card that checks out is undamaged, but that does not prove it belongs to your wallet. "
    "Only restoring the wallet and comparing it with your wallet record shows that."
)
GUESSWORK = (
    "This was worked out from what you could still read. It was not read off the card, and codex32 "
    "cannot tell you it is right. Copy it onto a fresh card, then prove it by restoring your wallet "
    "and checking the master fingerprint against your wallet record."
)
_CREATED = (
    "Your wallet is ready",
    "Copy these onto your wallet record, and keep it apart from every card.",
    (
        "Store each card in a different safe place. Send a small test payment and wait for it to "
        "arrive before you put real savings here."
    ),
)
_RESTORED = (
    "Your wallet is back",
    "Check each of these against your wallet record. They should all match.",
    (
        "If the master fingerprint is not the one on your record, these cards do not belong to that "
        "wallet: stop, and do not send anything to it. Bitcoin Core is now scanning the chain from "
        "the beginning, so your balance and history are not complete until it has finished."
    ),
)
CARDS_SAFE = (
    "Your cards are unharmed and still recover this wallet. Nothing was written onto them and "
    "nothing about them changed. When Bitcoin Core is ready, choose \u201cRestore my wallet\u201d "
    "and enter them. Do not set up a new wallet: that would make a different backup."
)


@dataclass(frozen=True, slots=True)
class Record:
    """Exactly the wallet-verification record's wallet-identity fields, and nothing more."""

    identifier: str
    wallet: str
    version: str
    fingerprint: str
    account: int


# --- Building blocks -------------------------------------------------------


def _page(
    title: str,
    content: Gtk.Widget,
    *,
    actions: Gtk.Widget | None = None,
    can_pop: bool = True,
) -> Adw.NavigationPage:
    scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
    scroller.set_child(Adw.Clamp(maximum_size=700, child=content, margin_start=18, margin_end=18))
    bars = Adw.ToolbarView()
    bars.add_top_bar(Adw.HeaderBar())
    bars.set_content(scroller)
    if actions is not None:
        bars.add_bottom_bar(actions)
    page = Adw.NavigationPage(title=title, child=bars)
    page.set_can_pop(can_pop)
    return page


def _column(*children: Gtk.Widget) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=18, margin_bottom=18)
    for child in children:
        box.append(child)
    return box


def _title(text: str, subtitle: str = "", icon: str = "") -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    if icon:
        image = Gtk.Image(icon_name=icon, pixel_size=48, margin_bottom=6)
        image.add_css_class(_ICON_STYLE.get(icon, "dim-label"))
        box.append(image)
    heading = Gtk.Label(label=text, wrap=True, justify=Gtk.Justification.CENTER)
    heading.add_css_class("title-2")
    box.append(heading)
    if subtitle:
        detail = Gtk.Label(label=subtitle, wrap=True, justify=Gtk.Justification.CENTER)
        detail.add_css_class("dim-label")
        box.append(detail)
    return box


def _note(text: str, level: str = "") -> Gtk.Label:
    label = Gtk.Label(label=text, wrap=True, xalign=0.0)
    label.add_css_class("reading")
    label.add_css_class(level or "dim-label")
    return label


def _say(label: Gtk.Label, text: str, level: str = "") -> None:
    for name in LEVELS:
        label.remove_css_class(name)
    label.add_css_class(level or "dim-label")
    label.set_label(text)


def _button(label: str, on_click: Callable[[], None], *, style: str = "") -> Gtk.Button:
    button = Gtk.Button(label=label)
    if style:
        button.add_css_class(style)
    button.connect("clicked", lambda _button: on_click())
    return button


def _actions(*buttons: Gtk.Widget) -> Gtk.Widget:
    box = Gtk.Box(spacing=10, margin_top=12, margin_bottom=14, margin_start=18, margin_end=18)
    for position, button in enumerate(buttons):
        if position == len(buttons) - 1:
            button.set_hexpand(True)
            button.set_halign(Gtk.Align.END)
        box.append(button)
    return box


def _card(text: str, guessed: frozenset[int] = frozenset()) -> Gtk.FlowBox:
    """Show one card the way wallets.md asks: uppercase, in four-character windows."""
    text = text.upper()
    flow = Gtk.FlowBox(
        selection_mode=Gtk.SelectionMode.NONE,
        column_spacing=8,
        row_spacing=8,
        max_children_per_line=12,
        halign=Gtk.Align.CENTER,
    )
    for start in range(0, len(text), reading.GROUP):
        label = Gtk.Label(label=text[start : start + reading.GROUP])
        label.add_css_class("card-group")
        if start // reading.GROUP in guessed:
            label.add_css_class("guessed")
        flow.append(label)
    return flow


def _empty(*rows: Adw.EntryRow) -> None:
    """Take a passphrase out of the widget that was holding it."""
    for row in rows:
        row.set_text("")


def _blank(flow: Gtk.FlowBox) -> None:
    """Take the card off the screen and out of the widget tree."""
    while (child := flow.get_first_child()) is not None:
        flow.remove(child)


def _rows(title: str, values: Sequence[tuple[str, str]]) -> Adw.PreferencesGroup:
    group = Adw.PreferencesGroup(title=title)
    for label, value in values:
        group.add(Adw.ActionRow(title=label, subtitle=value, subtitle_selectable=True, use_markup=False))
    return group


def _forget_when_gone(view: Adw.NavigationView, page: Adw.NavigationPage, clear: Callable[[], None]) -> None:
    """Clear recovery text as soon as its page leaves the navigation stack.

    Both ways out are covered: the operator pressing Back or Escape, which emits
    `popped`, and a step rewriting the stack, which emits `replaced` instead.
    Membership of the stack is the test, so a page a rewrite has just added
    keeps what it holds.
    """
    handlers: list[int] = []

    def gone(*_arguments: object) -> None:
        stack = view.get_navigation_stack()
        if any(stack.get_item(index) is page for index in range(stack.get_n_items())):
            return
        clear()
        while handlers:
            view.disconnect(handlers.pop())

    handlers.append(view.connect("popped", gone))
    handlers.append(view.connect("replaced", gone))


def _replace(view: Adw.NavigationView, page: Adw.NavigationPage) -> None:
    """Rewrite the stack so Back leads home rather than back into a finished step."""
    view.replace([home(view), page])


def _failure(view: Adw.NavigationView, error: object, advice: str = "") -> None:
    """Stop, and where cards already exist, say plainly that they are still good."""
    buttons = [_button("Start again", lambda: view.replace([home(view)]))]
    if advice:
        buttons.append(_button("Restore my wallet", lambda: _again(view, _start_restore)))
    buttons[-1].add_css_class("suggested-action")
    page = _page(
        "Stopped",
        _column(
            _title("That did not work", str(error), "dialog-error-symbolic"),
            *((_note(advice, "success"),) if advice else ()),
        ),
        actions=_actions(*buttons),
        can_pop=False,
    )
    _replace(view, page)


def _working(view: Adw.NavigationView, title: str, message: str) -> Adw.NavigationPage:
    """Show one operation in flight. It cannot be left, so its result cannot be lost.

    Leaving would drop the result of work that has already happened: an import
    that reached Bitcoin Core would go unreported, and a ceremony left half way
    would strand its cards. Every operation behind this page is bounded, by the
    correction deadline or by `bitcoin-cli`'s own timeout.
    """
    spinner = Gtk.Spinner(halign=Gtk.Align.CENTER, width_request=32, height_request=32)
    spinner.start()
    page = _page(title, _column(spinner, _title(message)), can_pop=False)
    view.push(page)
    return page


def _then[Result](
    view: Adw.NavigationView,
    page: Adw.NavigationPage,
    follow: Callable[[Result], Adw.NavigationPage | None],
    advice: str = "",
) -> Callable[[Result | Exception], None]:
    """Turn a worker result into the next page, the failure page, or a step of its own."""

    def deliver(outcome: Result | Exception) -> None:
        if isinstance(outcome, Exception):
            _failure(view, outcome, advice)
            return
        following = follow(outcome)
        if following is not None:
            _replace(view, following)

    return deliver


def _describe(artifact: Artifact) -> str:
    header = artifact.header
    name = header.identifier.upper()
    if isinstance(artifact, Secret):
        whole = "the whole backup" if header.threshold == 0 else "the unsplit form of backup"
        return f"This is {whole} {name}. It needs no other card."
    return (
        f"It is card {header.index.upper()} of a backup called {name}. "
        f"Any {header.threshold} cards from that backup recover the wallet."
    )


def _compare(expected: str, entered: str) -> ConfirmationResult:
    """Report which four-character groups do not match, by the library's own rule."""
    observed, wanted = "".join(entered.split()).lower(), expected.lower()
    span = (max(len(observed), len(wanted)) + reading.GROUP - 1) // reading.GROUP
    mismatched = tuple(
        group + 1
        for group in range(span)
        if observed[group * reading.GROUP : (group + 1) * reading.GROUP]
        != wanted[group * reading.GROUP : (group + 1) * reading.GROUP]
    )
    return ConfirmationResult(not mismatched, mismatched)


def _guessed(observed: str, corrected: str) -> frozenset[int]:
    """Mark the four-character windows a correction changed, so they can be compared."""
    changed: set[int] = set()
    matcher = difflib.SequenceMatcher(None, observed.lower(), corrected.lower(), autojunk=False)
    for tag, _left, _right, start, end in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed.update(range(start // reading.GROUP, (end + reading.GROUP - 1) // reading.GROUP))
        if start == end:
            changed.add(min(start // reading.GROUP, (len(corrected) - 1) // reading.GROUP))
    return frozenset(changed)


def _radio_group(group: Adw.PreferencesGroup, rows: Sequence[tuple[str, str]]) -> list[Gtk.CheckButton]:
    """Build one radio row per choice. Rows carry Bitcoin Core's text, so none of it is markup."""
    first: Gtk.CheckButton | None = None
    buttons: list[Gtk.CheckButton] = []
    for label, detail in rows:
        choice = Gtk.CheckButton()
        if first is None:
            first = choice
            choice.set_active(True)
        else:
            choice.set_group(first)
        row = Adw.ActionRow(title=label, subtitle=detail, activatable_widget=choice, use_markup=False)
        row.add_prefix(choice)
        group.add(row)
        buttons.append(choice)
    return buttons


def _selected(buttons: Sequence[Gtk.CheckButton]) -> int:
    """Return which row is chosen by position, so no wallet name can stand in for another."""
    return next(index for index, choice in enumerate(buttons) if choice.get_active())


# --- Home ------------------------------------------------------------------


def home(view: Adw.NavigationView) -> Adw.NavigationPage:
    """The six things this program does, in plain words."""
    tasks = (
        ("Set up a new wallet", "Make recovery cards, then a Bitcoin Core wallet", _start_create),
        ("Restore my wallet", "Use my cards to load a Bitcoin Core wallet", _start_restore),
        ("Check a card", "Make sure a card is still readable and undamaged", _start_check),
        ("Repair a damaged card", "Work out what a smudged or torn card should say", _start_repair),
        ("Replace a lost card", "Make a fresh card for a set you still have enough of", _start_share),
        ("Show my master seed", "Advanced. Displays the secret itself on screen.", _start_seed),
    )
    group = Adw.PreferencesGroup()
    for label, detail, start in tasks:
        row = Adw.ActionRow(title=label, subtitle=detail, activatable=True)
        row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
        row.connect("activated", lambda _row, begin=start: begin(view))
        group.add(row)
    content = _column(
        _title("What would you like to do?", "A codex32 backup is your Bitcoin wallet master seed."),
        group,
        _note("Everything happens on this computer. codex32 never connects to the internet."),
    )
    return _page("codex32", content)


# --- Bitcoin Core preflight ------------------------------------------------


def _connect(
    view: Adw.NavigationView,
    chain: str | None,
    then: Callable[[BitcoinCore], Adw.NavigationPage],
) -> None:
    """Discover Bitcoin Core before any entropy is drawn or any card is read."""
    page = _working(view, "Bitcoin Core", "Looking for Bitcoin Core on this computer…")

    def probe() -> BitcoinCore | tuple[str, ...]:
        try:
            return wallet_setup.connect(chain)
        except wallet_setup.Offer as offer:
            return offer.options

    def follow(found: BitcoinCore | tuple[str, ...]) -> Adw.NavigationPage:
        if isinstance(found, tuple):
            return _network_page(view, found, then)
        return then(found)

    deliver = _then(view, page, follow)
    work.run(view, page, probe, deliver)


def _network_page(
    view: Adw.NavigationView,
    options: Sequence[str],
    then: Callable[[BitcoinCore], Adw.NavigationPage],
) -> Adw.NavigationPage:
    group = Adw.PreferencesGroup(title="Bitcoin Core is running on more than one network")
    buttons = _radio_group(group, [(label, "") for label in options])
    content = _column(
        _title("Which network?", "Practise on signet. Use mainnet only for coins you cannot replace."),
        group,
    )
    action = _button(
        "Continue",
        lambda: _connect(view, options[_selected(buttons)], then),
        style="suggested-action",
    )
    return _page("Network", content, actions=_actions(action))


# --- Writing and reading back one card -------------------------------------


def _counted(letter: str, position: int, count: int | None) -> str:
    """Name this card. Only the create flow may say how many cards there are."""
    return f"Card {position + 1} of {count}" if count is not None else f"Card {letter}"


def _write_page(
    view: Adw.NavigationView,
    *,
    card: Artifact,
    position: int,
    count: int | None,
    confirm: Callable[[str], ConfirmationResult],
    after: Callable[[], None],
    cancel: Callable[[Adw.NavigationPage], None],
) -> Adw.NavigationPage:
    """Show one card, then take it off the screen before it is read back."""
    letter = card.header.index.upper()
    name = card.header.identifier.upper()
    shown = _card(card.text)
    where = f"Copy this onto card {position + 1}" if count is not None else "Copy this onto a fresh card"
    content = _column(
        _title("Write it down", where),
        _note("Use pen on a card you can keep dry. Copy each shaded group exactly, left to right."),
        shown,
        _note(f"Label this card {letter}. The letter after {name} is the card's name."),
        _note(NO_CAMERA, "warning"),
    )
    page = _page(
        _counted(letter, position, count),
        content,
        actions=_actions(
            _button("Cancel", lambda: cancel(page)),
            _button(
                "I have written it down",
                lambda: view.push(_read_back_page(view, card, position, count, confirm, after)),
                style="suggested-action",
            ),
        ),
        can_pop=False,
    )
    _forget_when_gone(view, page, lambda: _blank(shown))
    return page


def _read_back_page(
    view: Adw.NavigationView,
    card: Artifact,
    position: int,
    count: int | None,
    confirm: Callable[[str], ConfirmationResult],
    after: Callable[[], None],
) -> Adw.NavigationPage:
    """Read the card back from the paper, with the original off the screen."""
    field = Codex32Entry(length=len(card.text))
    status = _note("")
    accept = _button("Confirm card", lambda: None, style="suggested-action")

    def update(*_arguments: object) -> None:
        state = field.reading()
        accept.set_sensitive(state.complete)
        # A character a card can never carry is named, never quietly deleted: this
        # is the step whose whole purpose is to catch a misread glyph.
        fault = state.message if state.level == "error" else ""
        counted = f"{len(state.text)} of {state.expected} characters"
        _say(status, fault or counted, "error" if fault else "")

    def check() -> None:
        try:
            result = confirm(reading.normalize(field.get_text()))
        except CodexError as error:
            _failure(view, error, CARDS_SAFE)
            return
        if not result.accepted:
            groups = result.mismatched_groups
            where = f"Group {min(groups)}" if groups else "What you typed"
            _say(status, f"{where} does not match. Check it against your card.", "error")
            return
        field.clear()
        after()

    accept.connect("clicked", lambda _button: check())
    field.connect("changed", update)
    content = _column(
        _title("Now type it back from the card", _counted(card.header.index.upper(), position, count)),
        _note(
            "The original is no longer on screen. Read from the card you just wrote, so a slip of the "
            "pen is caught now rather than years from now."
        ),
        field,
        status,
        _note(
            "Spaces and capitals do not matter, and you may try as many times as you like. Correct only "
            "the group named above; the rest stays as you typed it."
        ),
    )
    page = _page(
        _counted(card.header.index.upper(), position, count),
        content,
        actions=_actions(_button("Show the card again", view.pop), accept),
    )
    _forget_when_gone(view, page, field.clear)
    update()
    return page


def _abandon(view: Adw.NavigationView, page: Adw.NavigationPage) -> None:
    dialog = Adw.AlertDialog(
        heading="Start over?",
        body="Destroy every card you have already written from this backup. It will be abandoned.",
    )
    dialog.add_response("keep", "Keep going")
    dialog.add_response("stop", "Start over")
    dialog.set_response_appearance("stop", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.set_default_response("keep")
    dialog.connect(
        "response",
        lambda _dialog, response: view.replace([home(view)]) if response == "stop" else None,
    )
    dialog.present(page)


# --- Making a backup -------------------------------------------------------


def _start_create(view: Adw.NavigationView) -> None:
    _connect(view, None, lambda core: _layout_page(view, core))


def _layout_page(view: Adw.NavigationView, core: BitcoinCore) -> Adw.NavigationPage:
    """Choose how many cards the backup has, and how many of them recovery needs."""
    details = {
        PRESETS[0][2]: "One card can be lost, burned or stolen and you still have your bitcoin. "
        "One card on its own reveals nothing.",
        PRESETS[1][2]: "Two cards can be lost. More places to hide, and more places to keep safe.",
        PRESETS[2][2]: "Simplest to store. Anyone who finds that card can take everything, and "
        "losing it loses everything.",
        "Something else": "Choose the numbers yourself, and the size of the seed.",
    }
    group = Adw.PreferencesGroup()
    buttons = _radio_group(group, [(label, details[label]) for label in details])
    custom = Adw.PreferencesGroup(title="Your own combination", visible=False)
    needed = Adw.SpinRow(
        title="Cards needed to recover",
        adjustment=Gtk.Adjustment(lower=2, upper=9, step_increment=1, value=2),
    )
    total = Adw.SpinRow(
        title="Cards in total",
        adjustment=Gtk.Adjustment(lower=2, upper=31, step_increment=1, value=3),
    )
    size = Adw.ComboRow(
        title="Seed size",
        model=Gtk.StringList.new([label for _length, label in SEED_SIZES]),
    )
    # Neither number may leave the other impossible.
    needed.connect(
        "notify::value",
        lambda row, _spec: total.set_value(max(total.get_value(), row.get_value())),
    )
    total.connect(
        "notify::value",
        lambda row, _spec: needed.set_value(min(needed.get_value(), row.get_value())),
    )
    for row in (needed, total, size):
        custom.add(row)
    buttons[-1].connect("toggled", lambda choice: custom.set_visible(choice.get_active()))

    def begin() -> None:
        chosen = list(details)[_selected(buttons)]
        if chosen != "Something else":
            threshold, count = next((t, c) for t, c, label in PRESETS if label == chosen)
            _begin_cards(view, core, threshold, count, SEED_SIZES[0][0])
            return
        threshold, count = int(needed.get_value()), int(total.get_value())
        if count < threshold:
            _failure(view, "A backup cannot need more cards than it has.")
            return
        _begin_cards(view, core, threshold, count, SEED_SIZES[size.get_selected()][0])

    content = _column(
        _title(
            "How many cards do you want?",
            "Splitting your wallet across cards means losing one is not a disaster, and finding one "
            "is not a jackpot for a thief.",
        ),
        group,
        custom,
    )
    return _page(
        "New wallet", content, actions=_actions(_button("Continue", begin, style="suggested-action"))
    )


def _begin_cards(
    view: Adw.NavigationView, core: BitcoinCore, threshold: int, count: int, byte_length: int
) -> None:
    if threshold == 0:
        page = _working(view, "New backup", "Drawing a fresh master seed…")
        work.run(
            view,
            page,
            lambda: generate_master_seed(
                byte_length=byte_length, fingerprint=wallet_setup.fingerprint_provider(core)
            ),
            _then(view, page, lambda secret: _unshared_page(view, core, secret)),
        )
        return
    try:
        ceremony = CreationCeremony.master_seed(
            threshold=threshold, share_count=count, byte_length=byte_length
        )
    except CodexError as error:
        _failure(view, error)
        return
    _next_card(view, core, ceremony, 0, count)


def _unshared_page(view: Adw.NavigationView, core: BitcoinCore, secret: MasterSeed) -> Adw.NavigationPage:
    return _write_page(
        view,
        card=secret,
        position=0,
        count=1,
        confirm=lambda text: _compare(secret.text, text),
        after=lambda: _wallets(view, core, secret, "now"),
        cancel=lambda page: _abandon(view, page),
    )


def _next_card(
    view: Adw.NavigationView,
    core: BitcoinCore,
    ceremony: CreationCeremony,
    position: int,
    count: int,
) -> None:
    page = _working(view, f"Card {position + 1} of {count}", "Drawing this card from the operating system…")

    def follow(card: Share) -> Adw.NavigationPage:
        return _write_page(
            view,
            card=card,
            position=position,
            count=count,
            confirm=ceremony.confirm,
            after=lambda: _card_confirmed(view, core, ceremony, position, count),
            cancel=lambda shown: _abandon(view, shown),
        )

    work.run(view, page, ceremony.next_share, _then(view, page, follow))


def _card_confirmed(
    view: Adw.NavigationView,
    core: BitcoinCore,
    ceremony: CreationCeremony,
    position: int,
    count: int,
) -> None:
    if position + 1 < count:
        _next_card(view, core, ceremony, position + 1, count)
        return
    page = _working(view, "Backup", "Finishing the backup…")

    def follow(secret: MasterSeed | CoreLightningSecret) -> None:
        if not isinstance(secret, MasterSeed):
            _failure(view, "That ceremony did not produce a Bitcoin master seed.")
            return
        _wallets(view, core, secret, "now")

    deliver = _then(view, page, follow, CARDS_SAFE)
    work.run(view, page, ceremony.finish, deliver)


# --- The Bitcoin Core wallet -----------------------------------------------


def _wallets(
    view: Adw.NavigationView,
    core: BitcoinCore,
    secret: MasterSeed,
    timestamp: Timestamp,
    *,
    restoring: bool = False,
) -> None:
    page = _working(view, "Bitcoin Core", "Asking Bitcoin Core which wallets are empty…")
    work.run(
        view,
        page,
        lambda: wallet_setup.eligible(core),
        _then(
            view,
            page,
            lambda found: _wallet_page(view, core, secret, found, timestamp, restoring),
            CARDS_SAFE,
        ),
    )


def _wallet_page(
    view: Adw.NavigationView,
    core: BitcoinCore,
    secret: MasterSeed,
    found: tuple[wallet_setup.Wallet, ...],
    timestamp: Timestamp,
    restoring: bool,
) -> Adw.NavigationPage:
    """Name the wallet that will hold the keys. The library confirms that name again."""
    group = Adw.PreferencesGroup(title="Empty wallets Bitcoin Core has ready")
    rows = [(item.name, "Empty, encrypted" if item.encrypted else "Empty, not encrypted") for item in found]
    rows.append((CREATE_WALLET, "codex32 asks Bitcoin Core for a blank wallet, with a passphrase you choose"))
    buttons = _radio_group(group, rows)

    def go() -> None:
        # By position, so that a wallet named like the create row is still reachable.
        index = _selected(buttons)
        if index == len(found):
            view.push(_new_wallet_page(view, core, secret, timestamp, restoring))
            return
        chosen = found[index]
        if chosen.locked:
            view.push(_unlock_page(view, core, secret, chosen, timestamp, restoring))
            return
        _import(view, core, secret, chosen.name, "", timestamp, restoring)

    content = _column(
        _title(
            "Which wallet should hold your keys?",
            f"Bitcoin Core {wallet_setup.version_text(core)} is running on {wallet_setup.network(core)}.",
        ),
        group,
        _note(
            "Only empty wallets are listed, so no wallet you already use can be overwritten. You may also "
            "create one in Bitcoin Core yourself and check again."
        ),
        *(
            (
                _note(
                    "This restores account 0. If your wallet record shows a different account number, "
                    "restore with the ms32 wallet --account command instead.",
                    "warning",
                ),
            )
            if restoring
            else ()
        ),
    )
    return _page(
        "Wallet",
        content,
        actions=_actions(
            _button("Check again", lambda: _wallets(view, core, secret, timestamp)),
            _button("Continue", go, style="suggested-action"),
        ),
    )


def _new_wallet_page(
    view: Adw.NavigationView,
    core: BitcoinCore,
    secret: MasterSeed,
    timestamp: Timestamp,
    restoring: bool = False,
) -> Adw.NavigationPage:
    """Ask Bitcoin Core for one blank wallet, with a passphrase the operator chooses."""
    name = Adw.EntryRow(title="Wallet name", text=secret.header.identifier.upper())
    first = Adw.PasswordEntryRow(title="Wallet passphrase")
    again = Adw.PasswordEntryRow(title="Repeat the passphrase")
    group = Adw.PreferencesGroup()
    for row in (name, first, again):
        group.add(row)
    status = _note("")

    def make(passphrase: str) -> None:
        # Read the field here: the worker runs off the main loop and must not touch a widget.
        chosen = name.get_text().strip()
        page = _working(view, "Bitcoin Core", "Creating the wallet and writing your keys into it…")

        def job() -> Record:
            wallet_setup.create(core, chosen, passphrase)
            return _record(core, secret, chosen, timestamp, passphrase)

        work.run(
            view,
            page,
            job,
            _then(view, page, lambda record: _finished_page(view, record, restoring), CARDS_SAFE),
        )

    def go() -> None:
        passphrase = first.get_text()
        if passphrase != again.get_text():
            _say(status, "The two passphrases are not the same.", "error")
            return
        if passphrase:
            make(passphrase)
            return
        dialog = Adw.AlertDialog(
            heading="Create it without a passphrase?",
            body="Anyone who can use this computer could then spend from this wallet.",
        )
        dialog.add_response("back", "Go back")
        dialog.add_response("plain", "Create without one")
        dialog.set_response_appearance("plain", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("back")
        dialog.connect("response", lambda _dialog, answer: make("") if answer == "plain" else None)
        dialog.present(view)

    content = _column(
        _title("Create a wallet for these keys", "Bitcoin Core makes it; codex32 fills it in."),
        group,
        status,
        _note(
            "Your passphrase goes straight to Bitcoin Core on standard input and nowhere else. It is "
            "never saved, never written to a file, and never shown in the list of running programs."
        ),
        _note(
            "Forgetting this passphrase does not lose your bitcoin: your cards still recover the seed. "
            "It protects the wallet on this computer.",
            "success",
        ),
    )
    page = _page("New wallet", content, actions=_actions(_button("Create", go, style="suggested-action")))
    _forget_when_gone(view, page, lambda: _empty(first, again))
    return page


def _unlock_page(
    view: Adw.NavigationView,
    core: BitcoinCore,
    secret: MasterSeed,
    wallet: wallet_setup.Wallet,
    timestamp: Timestamp,
    restoring: bool = False,
) -> Adw.NavigationPage:
    """Unlock one already encrypted wallet, or step aside and let Bitcoin Core do it."""
    field = Adw.PasswordEntryRow(title="Wallet passphrase")
    group = Adw.PreferencesGroup()
    group.add(field)
    manual = Adw.ExpanderRow(
        title="I would rather unlock it in Bitcoin Core myself",
        subtitle="Then codex32 never sees the passphrase, exactly as the command line works.",
    )
    manual.add_row(
        Adw.ActionRow(
            title="In Bitcoin Core, open Window ▸ Console",
            subtitle=(
                f"Select the wallet {wallet.name}, then type: "
                f'walletpassphrase "YOUR PASSPHRASE" {wallet_setup.UNLOCK_SECONDS}'
            ),
            subtitle_selectable=True,
            use_markup=False,
        )
    )
    group.add(manual)

    def check() -> None:
        page = _working(view, "Bitcoin Core", "Checking whether the wallet is unlocked…")

        def job() -> Record:
            wallet_setup.require_unlocked(core, wallet.name)
            return _record(core, secret, wallet.name, timestamp)

        work.run(
            view,
            page,
            job,
            _then(view, page, lambda record: _finished_page(view, record, restoring), CARDS_SAFE),
        )

    def go() -> None:
        _import(view, core, secret, wallet.name, field.get_text(), timestamp, restoring)

    content = _column(
        _title(
            f"The wallet \u201c{wallet.name}\u201d is locked",
            "Bitcoin Core needs its passphrase before your keys can be written into it.",
        ),
        group,
        _note(
            "Your passphrase goes straight to Bitcoin Core on standard input and nowhere else. It is "
            "never saved, never written to a file, and never shown in the list of running programs. "
            "codex32 locks the wallet again as soon as it has finished."
        ),
    )
    page = _page(
        "Unlock",
        content,
        actions=_actions(
            _button("I unlocked it myself", check),
            _button("Unlock and finish", go, style="suggested-action"),
        ),
    )
    _forget_when_gone(view, page, lambda: _empty(field))
    return page


def _record(
    core: BitcoinCore, secret: MasterSeed, name: str, timestamp: Timestamp, passphrase: str = ""
) -> Record:
    final = wallet_setup.fill(core, secret, name, passphrase, timestamp=timestamp)
    return Record(
        secret.header.identifier.upper(),
        final,
        wallet_setup.version_text(core),
        wallet_setup.fingerprint(core, secret),
        0,
    )


def _import(
    view: Adw.NavigationView,
    core: BitcoinCore,
    secret: MasterSeed,
    name: str,
    passphrase: str,
    timestamp: Timestamp,
    restoring: bool = False,
) -> None:
    page = _working(view, "Bitcoin Core", f"Writing your keys into {name}…")
    work.run(
        view,
        page,
        lambda: _record(core, secret, name, timestamp, passphrase),
        _then(view, page, lambda record: _finished_page(view, record, restoring), CARDS_SAFE),
    )


def _finished_page(view: Adw.NavigationView, record: Record, restoring: bool = False) -> Adw.NavigationPage:
    """Show the wallet-identity fields.

    A new wallet's are copied onto the wallet record. A restored wallet's are the
    only proof the cards just entered belong to that wallet, so they are checked
    against the record instead, and no creation date is offered: the one this
    wallet was born with is on the record already, and today's would replace it.
    """
    heading, asked, closing = _RESTORED if restoring else _CREATED
    dated = () if restoring else (("Approximate creation date", time.strftime("%Y-%m-%d")),)
    content = _column(
        _title(heading, asked, DONE_ICON),
        _rows(
            "Wallet identity",
            (
                ("Backup identifier", record.identifier),
                ("Bitcoin Core wallet name", record.wallet),
                ("Bitcoin Core version", record.version),
                *dated,
                ("Master fingerprint", record.fingerprint),
                ("Derivation standards", "BIP 44, 49, 84 and 86"),
                ("Account number", str(record.account)),
            ),
        ),
        _note(closing, "warning" if restoring else ""),
    )
    return _page(
        "Finished",
        content,
        actions=_actions(_button("Done", lambda: view.replace([home(view)]), style="suggested-action")),
        can_pop=False,
    )


# --- Entering cards --------------------------------------------------------


def _outstanding(gathered: tuple[Artifact, ...], basis: bool, wanted: int | None) -> int:
    if wanted is not None:
        return max(wanted - len(gathered), 0)
    first = gathered[0]
    if not basis and isinstance(first, Secret):
        return 0
    return max(first.header.threshold - len(gathered), 0)


def _incompatible(artifact: Artifact | None, accepted: tuple[Artifact, ...], basis: bool) -> str:
    if artifact is None:
        return ""
    if basis and artifact.header.threshold == 0:
        return "This backup was never split into cards, so there is no card to replace."
    if not accepted:
        return ""
    first = accepted[0]
    if artifact.header.identifier != first.header.identifier:
        return (
            f"This card belongs to backup {artifact.header.identifier.upper()}, "
            f"not {first.header.identifier.upper()}."
        )
    if artifact.header.threshold != first.header.threshold:
        return "This card comes from a different split of that backup."
    if len(artifact.text) != len(first.text):
        return "This card is a different length from the first one."
    if not basis and isinstance(artifact, Secret):
        return "This is the whole backup rather than one of its cards."
    return ""


def _collect(
    view: Adw.NavigationView,
    *,
    title: str,
    heading: str,
    body: str,
    accepted: tuple[Artifact, ...] = (),
    basis: bool = False,
    wanted: int | None = None,
    reserved: tuple[str, ...] = (),
    repaired: bool = False,
    then: Callable[[tuple[Artifact, ...], bool], None],
) -> Adw.NavigationPage:
    """Take one card, and keep taking them until the backup has enough."""
    first = accepted[0] if accepted else None
    length = len(first.text) if first is not None else None
    blocked = tuple(dict.fromkeys([*(item.header.index for item in accepted), *reserved]))
    # Correction accepts ordinary indices only; S is refused by the field instead.
    excluded = tuple(index for index in blocked if index != "s")
    field = Codex32Entry(accepted=blocked, length=length)
    if first is not None:
        field.prefill(f"{reading.PREFIX}{first.header.threshold}{first.header.identifier}")
    status = _note("")
    fix = _button("Suggest a repair", lambda: suggest())
    go = _button("Continue", lambda: proceed(), style="suggested-action")

    def refuse(artifact: Artifact | None) -> str:
        """Say why this card cannot join the ones already entered, if it cannot."""
        if artifact is not None and artifact.header.index in blocked:
            letter = artifact.header.index.upper()
            return f"That would be card {letter}, which cannot be used here."
        return _incompatible(artifact, accepted, basis)

    def update(*_arguments: object) -> None:
        state = field.reading()
        problem = refuse(state.artifact)
        go.set_sensitive(state.artifact is not None and not problem)
        fix.set_sensitive(state.repairable)
        _say(status, problem or state.message, "error" if problem else state.level)

    def accept(artifact: Artifact, guessed: bool = False) -> None:
        # Checked again here: a repair arrives from its own screen, not from the field.
        problem = refuse(artifact)
        if problem:
            if work.showing(view, page):
                view.pop_to_page(page)
            _say(status, problem, "error")
            return
        gathered = (*accepted, artifact)
        field.clear()
        if _outstanding(gathered, basis, wanted):
            _replace(
                view,
                _collect(
                    view,
                    title=title,
                    heading=heading,
                    body=body,
                    accepted=gathered,
                    basis=basis,
                    wanted=wanted,
                    reserved=reserved,
                    repaired=repaired or guessed,
                    then=then,
                ),
            )
        else:
            then(gathered, repaired or guessed)

    def proceed() -> None:
        artifact = field.reading().artifact
        if artifact is not None:
            accept(artifact)

    def suggest() -> None:
        observed = field.reading().text
        spinner = _working(view, "Repair", "Working out what the card should say…")

        def deliver(result: object) -> None:
            view.pop()
            if not isinstance(result, CorrectionCandidate):
                _say(status, str(result), "error")
                return

            def following() -> Adw.NavigationPage:
                return _repair_page(view, result, observed, lambda card: accept(card, True), page)

            gated = result.low_checksum_discrimination
            view.push(_guess_gate_page(view, following) if gated else following())

        work.run(view, spinner, lambda: reading.repair(observed, length, excluded), deliver)

    field.connect("changed", update)
    progress = []
    if first is not None:
        letters = ", ".join(item.header.index.upper() for item in accepted)
        progress.append(
            _note(
                f"Card{'s' if len(accepted) > 1 else ''} {letters} accepted. Backup "
                f"{first.header.identifier.upper()} needs {first.header.threshold} cards in all.",
                "success",
            )
        )
    content = _column(_title(heading, body), *progress, field, status)
    page = _page(title, content, actions=_actions(fix, go))
    _forget_when_gone(view, page, field.clear)
    update()
    return page


def _guess_gate_page(
    view: Adw.NavigationView, following: Callable[[], Adw.NavigationPage]
) -> Adw.NavigationPage:
    """Invariant 5: disclose nothing about the candidate until literal YES is typed."""
    field = Gtk.Entry(placeholder_text="YES")
    show = _button("Show the guess", lambda: view.push(following()), style="destructive-action")
    show.set_sensitive(False)
    field.connect("changed", lambda _entry: show.set_sensitive(field.get_text().strip() == "YES"))
    content = _column(
        _title("This repair would be a guess"),
        _note(
            "So much of this card is unreadable that codex32 can fill in the blanks in a way that looks "
            "correct without being correct. If any earlier character is also wrong, that mistake gets "
            "locked in and the card becomes wrong forever, with nothing left to detect it.",
            "warning",
        ),
        _note("If the funds matter, stop here and get help instead."),
        _note("Type YES in capitals to continue anyway."),
        field,
    )
    return _page("Warning", content, actions=_actions(_button("Cancel", view.pop), show))


def _repair_page(
    view: Adw.NavigationView,
    candidate: CorrectionCandidate,
    observed: str,
    accept: Accept,
    back: Adw.NavigationPage,
) -> Adw.NavigationPage:
    corrected = candidate.artifact.text
    shown = _card(corrected, _guessed(observed, corrected))
    content = _column(
        _title("One possible repair", "It might not be the only one."),
        shown,
        _note(
            "Hold this next to your card and compare it character by character. The highlighted groups "
            "are the guesses. If they do not match what you can still read on the paper, say no."
        ),
    )
    page = _page(
        "Repair",
        content,
        actions=_actions(
            _button("It does not match my card", lambda: view.pop_to_page(back)),
            _button("It matches my card", lambda: accept(candidate.artifact), style="suggested-action"),
        ),
    )
    _forget_when_gone(view, page, lambda: _blank(shown))
    return page


# --- The remaining tasks ---------------------------------------------------


def _again(view: Adw.NavigationView, start: Callable[[Adw.NavigationView], None]) -> None:
    view.replace([home(view)])
    start(view)


def _intact_page(view: Adw.NavigationView, artifact: Artifact, repaired: bool = False) -> Adw.NavigationPage:
    """Report one card. A card that was guessed at is never called intact."""
    shown = _card(artifact.text)
    content = _column(
        _title(
            "This is what the card should say" if repaired else "This card is intact",
            _describe(artifact),
            "" if repaired else DONE_ICON,
        ),
        shown,
        _note(GUESSWORK, "warning") if repaired else _note(NOT_PROOF),
    )
    page = _page(
        "Card",
        content,
        actions=_actions(
            _button("Check another card", lambda: _again(view, _start_check)),
            _button("Done", lambda: view.replace([home(view)]), style="suggested-action"),
        ),
        can_pop=False,
    )
    _forget_when_gone(view, page, lambda: _blank(shown))
    return page


def _start_check(view: Adw.NavigationView) -> None:
    view.push(
        _collect(
            view,
            title="Check a card",
            heading="Type what your card says",
            body="Nothing is saved and nothing leaves this computer.",
            wanted=1,
            then=lambda found, guessed: _replace(view, _intact_page(view, found[0], guessed)),
        )
    )


def _start_repair(view: Adw.NavigationView) -> None:
    view.push(
        _collect(
            view,
            title="Repair a damaged card",
            heading="What you can read on the card",
            body="Type ? for anything you cannot make out. Nothing is saved and nothing leaves this computer.",
            wanted=1,
            then=lambda found, guessed: _replace(view, _intact_page(view, found[0], guessed)),
        )
    )


def _recover(view: Adw.NavigationView, found: tuple[Artifact, ...], then: Callable[[Secret], None]) -> None:
    if len(found) == 1 and isinstance(found[0], Secret):
        then(found[0])
        return
    shares = [item for item in found if isinstance(item, Share)]
    if len(shares) != len(found):
        _failure(view, "Recovery needs ordinary cards, not the whole backup.")
        return
    try:
        then(recover_secret(shares))
    except CodexError as error:
        _failure(view, error)


def _seed_page(view: Adw.NavigationView, secret: Secret) -> Adw.NavigationPage:
    shown = _card(secret.text)
    frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    frame.add_css_class("card-frame")
    frame.append(shown)
    content = _column(
        _note(
            "Anyone who reads this line can take every coin in your wallet. Check that nobody is behind "
            "you and no camera is pointed at the screen.",
            "error",
        ),
        _title("Your whole backup in one line", _describe(secret)),
        frame,
        _note(
            "Nothing was saved, copied or sent anywhere, and your cards and wallet are unchanged. If you "
            "write this down, guard it the way you would guard all your cards at once."
        ),
    )
    page = _page(
        "Master seed",
        content,
        actions=_actions(
            _button("Hide this and go back", lambda: view.replace([home(view)]), style="suggested-action")
        ),
        can_pop=False,
    )
    _forget_when_gone(view, page, lambda: _blank(shown))
    return page


def _start_seed(view: Adw.NavigationView) -> None:
    view.push(
        _collect(
            view,
            title="Show my master seed",
            heading="Enter your cards",
            body="This never opens a Bitcoin Core wallet and never changes your backup.",
            then=lambda found, _guessed: _recover(
                view, found, lambda secret: _replace(view, _seed_page(view, secret))
            ),
        )
    )


def _letter_page(view: Adw.NavigationView) -> Adw.NavigationPage:
    flow = Gtk.FlowBox(
        selection_mode=Gtk.SelectionMode.SINGLE,
        column_spacing=8,
        row_spacing=8,
        max_children_per_line=11,
        homogeneous=True,
        halign=Gtk.Align.CENTER,
    )
    for letter in sorted(ORDINARY_INDICES):
        label = Gtk.Label(label=letter.upper())
        label.add_css_class("card-group")
        flow.append(label)
    flow.select_child(flow.get_child_at_index(0))

    def go() -> None:
        selected = flow.get_selected_children()
        if not selected:
            return
        child = selected[0].get_child()
        letter = child.get_label().lower()
        view.push(
            _collect(
                view,
                title="Replace a lost card",
                heading="Now enter the cards you still have",
                body="codex32 works out the new card from them. Nothing else changes.",
                basis=True,
                reserved=(letter,),
                then=lambda found, _guessed: _derive(view, found, letter),
            )
        )

    content = _column(
        _title(
            "Give the new card a letter",
            "Every card in a backup carries its own letter. Choose one that no card already uses.",
        ),
        flow,
        _note(
            "codex32 cannot tell which letters your other cards already use — only your own records can. "
            "Two cards sharing a letter cannot be used together. S is reserved for an unsplit backup."
        ),
    )
    return _page("New card", content, actions=_actions(_button("Continue", go, style="suggested-action")))


def _start_share(view: Adw.NavigationView) -> None:
    view.push(_letter_page(view))


def _derive(view: Adw.NavigationView, found: tuple[Artifact, ...], letter: str) -> None:
    try:
        share = derive_share(list(found), letter)
    except CodexError as error:
        _failure(view, error)
        return
    _replace(
        view,
        _write_page(
            view,
            card=share,
            position=0,
            count=None,
            confirm=lambda text: _compare(share.text, text),
            after=lambda: _replace(view, _share_done_page(view, share)),
            cancel=lambda _page: view.replace([home(view)]),
        ),
    )


def _share_done_page(view: Adw.NavigationView, share: Share) -> Adw.NavigationPage:
    letter = share.header.index.upper()
    content = _column(
        _title(
            f"Card {letter} is written and confirmed",
            "It works with the cards you already have, exactly as the card it replaces did.",
            DONE_ICON,
        ),
        _rows(
            "The new card",
            (
                ("New card letter", letter),
                ("Backup identifier", share.header.identifier.upper()),
                ("Cards needed to recover", str(share.header.threshold)),
            ),
        ),
        _note(
            f"Store card {letter} somewhere safe before you destroy the card it replaces. Until then, "
            "treat both as live.",
            "warning",
        ),
        _note(
            "Your wallet is untouched. No Bitcoin Core wallet was opened and your master seed has not "
            "changed — this only added another way to reach it."
        ),
    )
    return _page(
        "New card",
        content,
        actions=_actions(
            _button("Make another card", lambda: _again(view, _start_share)),
            _button("Done", lambda: view.replace([home(view)]), style="suggested-action"),
        ),
        can_pop=False,
    )


def _restore(view: Adw.NavigationView, core: BitcoinCore, secret: Secret) -> None:
    if not isinstance(secret, MasterSeed):
        _failure(view, "Only a Bitcoin master-seed backup can restore a wallet.")
        return
    _wallets(view, core, secret, 0, restoring=True)


def _start_restore(view: Adw.NavigationView) -> None:
    _connect(
        view,
        None,
        lambda core: _collect(
            view,
            title="Restore my wallet",
            heading="Enter your cards",
            body="Type what each card says. Nothing is saved and nothing leaves this computer.",
            then=lambda found, _guessed: _recover(view, found, lambda secret: _restore(view, core, secret)),
        ),
    )
