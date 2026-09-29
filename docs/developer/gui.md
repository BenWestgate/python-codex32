# Reviewing the graphical program

`src/codex32_gui/` is an optional package installed with `codex32[gui]` and run
as `codex32-gui`. It adds presentation and Bitcoin Core orchestration; it adds no
cryptography, entropy source, socket, or file storage.

## Review order

| File | Purpose |
|---|---|
| `reading.py` | Entry interpretation and repair policy; no GTK. |
| `wallet_setup.py` | All Bitcoin Core calls, passphrase handling, and relocking; no GTK. |
| `work.py` | One bounded background operation at a time. |
| `entry.py` | Ordinary, correction, and read-back entry modes. |
| `pages.py` | Screen construction and wording. |
| `app.py` | Application and window setup. |
| `style.py` | CSS string. |
| `__init__.py`, `__main__.py` | GTK setup and entry point. |

Review `reading.py`, `wallet_setup.py`, and `work.py` first. Their behavior is
covered without a display. `tools/gui_walkthrough.py` exercises the real GTK
screens under Xvfb. `tests/test_gui_boundaries.py` enforces a separate 2,000
logical-line GUI budget.

## Security boundaries

`tests/test_gui_boundaries.py` checks the first four mechanically.

1. **No entropy or cryptography.** Seed creation stays in `CreationCeremony`.
2. **No network stack.** The GUI imports no socket, TLS, HTTP, or subprocess
   modules. Bitcoin Core access remains in the library's `bitcoin-cli` wrapper.
3. **No secret persistence.** The GUI imports no filesystem, database, logging,
   or clipboard storage APIs and never calls `open`.
4. **One Core boundary.** Only `wallet_setup.py` imports
   `codex32._bitcoin_core`.
5. **Page secrets are cleared.** `_forget_when_gone` clears card or entry text
   when an `AdwNavigationView` page leaves the stack.
6. **One worker at a time.** `work.run` serializes background jobs, returns on the
   GTK thread, and drops callbacks for pages that are gone.
7. **Accessibility is opt-in.** `__init__.py` defaults `GTK_A11Y` to `none`
   before GTK loads; an operator can override it.
8. **Labels never select wallets.** Choice rows use position and disable markup;
   exact wallet-name confirmation remains in the Core adapter.

## Entry and correction

The entry widget has three internal modes:

- **Ordinary:** supplies and protects `MS1` and blocks forward typing after an
  invalid header. Multi-card jobs may use `?` for an unreadable header character;
  Check a card does not accept `?`.
- **Correction:** preserves damaged headers and literal `?`, matching the CLI's
  correction input.
- **Read-back:** starts empty, normalizes only spacing and ASCII case, and never
  reveals expected text after a mismatch.

Enter activates the enabled primary action. Card displays use four
four-character groups per row, matching `docs/user/recovery-card.html`.
Ordinary repair suggestions are unmarked; explicit correction may mark changed
groups, which are described as changes rather than known error locations.

Low-discrimination correction keeps the CLI's literal-`YES` gate. Its single
warning covers both hazards: checksum completion can lock errors into new data,
and a damaged-card guess can be wrong. It also forbids replacing a checksum just
to make invalid data validate.

## Bitcoin Core integration

These GUI-specific behaviors are confined to `wallet_setup.py` and documented in
`docs/security/invariants.md` and `docs/security/model.md`.

**Passphrase input.** The GUI may ask for a wallet passphrase. It reaches
`bitcoin-cli` through `-stdinwalletpassphrase`, never `argv`, and is not stored.
The operator can instead unlock in Bitcoin Core.

**Relocking.** `wallet_setup.fill` owns unlock, import, and relock in one
`finally`, including failures before `BitcoinCore.initialize` has armed its own
relock path. Core's 180-second timeout remains a backstop.

**Blank-wallet creation.** The GUI sends a fixed `createwallet` shape:
`wallet_name`, `disable_private_keys=false`, `blank=true`, plus `passphrase` when
provided. A blank encrypted wallet starts locked, then the GUI unlocks it for
the import.

### Driving `BitcoinCore.initialize`

`wallet_setup._Answer` only answers choices already made by the operator:

- `[y/N]` becomes `y` only for the exact chosen quoted wallet name;
- a numbered prompt gets the number assigned to that exact name by the library;
- anything else raises `Offer` and returns the library's choices to the GUI.

Unexpected or stale state therefore fails closed rather than selecting another
wallet. `_Answer.tell` also rejects terminal-only “press Ctrl-C” waits.

## Differences from `ms32`

- GUI repair does not require Bitcoin Core. If `_best` leaves a tie, the GUI
  reports ambiguity instead of using the CLI's fingerprint tie-breaker.
- The GUI can create a blank Bitcoin Core wallet; `ms32 create` does not.
- The GUI uses account 0. Other accounts require `ms32 wallet --account N`.
- The GUI has no checksum-completer action. The low-discrimination route is
  still reachable through correction and uses the same warning gate.
- Restore asks the operator to compare wallet identity with the existing record
  and does not show a new creation date.
- A corrected card is never reported as intact.
- `xprv`, Core Lightning, BIP39 worksheet profiles, and the generic `codex32`
  façade remain command-line only.

## Known limits

- Long cards scroll horizontally because entry uses one `Gtk.Entry`.
- Empty-wallet lists refresh on request, not continuously.
- Widget construction is covered by `tools/gui_walkthrough.py`, not pytest.
- On X11, selecting entry text briefly exposes it through the primary selection.
- Enabling GTK accessibility exposes GUI text to other processes on that bus.
- A running spinner page cannot be left; correction and `bitcoin-cli` operations
  are bounded by their configured deadlines.

## Desktop identity and artwork

The six home actions use six crops from the MIT-licensed Codex32 book cover.
`artwork/LICENSE` carries the attribution and source. The Codex32 orb is also
installed as the `io.github.benwestgate.codex32` launcher icon beside the matching
desktop file. Packaging tests verify both assets are present.
