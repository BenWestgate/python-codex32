# The graphical program, for a reviewer

`src/codex32_gui/` is a second distribution package in this repository,
installed as `codex32[gui]` and started by `codex32-gui`. It adds screens to
reviewed code. It adds no cryptography, draws no entropy, opens no socket, and
writes no file.

Design and screen mock-ups: `docs/planning/gui-plan.md` and
`docs/planning/gui-screens.html` (both untracked).

## What to open, and in what order

| File | Logical lines | What it holds |
|---|---:|---|
| `reading.py` | 108 | What a field of codex32 text means, and the repair policy. No toolkit. |
| `wallet_setup.py` | 165 | Every Bitcoin Core call, including the passphrase. No toolkit. |
| `work.py` | 41 | One background operation at a time. |
| `entry.py` | 52 | The `Gtk.Entry` subclass that applies `reading.py`. |
| `pages.py` | 1078 | One function per screen: widgets and wording, no decisions. |
| `app.py` | 43 | The window. |
| `style.py` | 40 | The stylesheet, as a string. |
| `__init__.py`, `__main__.py` | 18 | Version pinning and the entry point. |

The first three are where review effort belongs: they are the only modules that
decide anything, they total about 310 lines, and none of them imports a toolkit,
so `tests/test_gui_reading.py` and `tests/test_gui_wallet_setup.py` cover them
without a display and run in ordinary CI.

The package carries its own budget of 1,800 logical lines, separate from the
5,000 the installed library keeps, and `tests/test_gui_boundaries.py` enforces
it. The plan proposed 1,000 before the screens were written; the difference is
almost entirely user-facing wording in `pages.py`, which is the first priority
this program was built for.

## Claims, and how to check each one

`tests/test_gui_boundaries.py` checks the first four by parsing every module.

1. **No entropy and no arithmetic.** Nothing imports `secrets`, `random`,
   `hashlib`, or `hmac`. Entropy belongs to `CreationCeremony`.
2. **No network.** Nothing imports `socket`, `ssl`, `urllib`, or `http`, and no
   module imports `subprocess`. The only child process is the `bitcoin-cli` the
   library already starts.
3. **Nothing reaches disk.** Nothing imports `os`, `pathlib`, `io`, `tempfile`,
   `shutil`, `pickle`, `sqlite3`, or `logging`, and nothing calls `open`. There
   is no settings file, no recent list, no log, and no clipboard write.
4. **One module speaks to Bitcoin Core.** Only `wallet_setup.py` imports
   `codex32._bitcoin_core`; everything else receives an opaque client.
5. **Recovery text is cleared when its page is left.** `pages._forget_on_pop`
   connects to `AdwNavigationView::popped` and empties the entry field or the
   card labels for that page. A page replaced wholesale is dropped with
   everything it held.
6. **One worker, and no callback touches a page that is gone.** `work.run`
   refuses to start a second operation, delivers its result through
   `GLib.idle_add`, and drops it if the page has left the widget tree. It
   delivers from `finally`, so a failure no screen anticipated releases the
   program instead of leaving it spinning.

## The two deliberate departures from the command line

Both are confined to `wallet_setup.py`, and both are recorded in
`docs/security/invariants.md` (invariant 9) and `docs/security/model.md`.

**The passphrase.** The library has no passphrase channel and tells the operator
to unlock the wallet in Bitcoin-Qt. A person who has just written three cards by
hand should not have to open a second application and type a console command, so
the window asks. The passphrase reaches `bitcoin-cli` through
`-stdinwalletpassphrase`, never through an argument, so it is absent from
`/proc` and `ps`. It is not stored, not logged, and not written to disk. The
screen keeps "I would rather unlock it in Bitcoin Core myself", which is the
command line's behaviour unchanged. Import, verification, and relocking remain
`BitcoinCore.initialize`.

**Creating the blank wallet.** `createwallet` is issued with one fixed shape:
`wallet_name`, `disable_private_keys=false`, `blank=true`, and a `passphrase`
line only when one was given. No other option is ever sent. Bitcoin Core's
`CreateWallet` guards its unlock branch with `if (!create_blank)`, so a blank
encrypted wallet is created locked; the window already holds the passphrase, so
it unlocks immediately and the separate unlock screen appears only for a wallet
that already existed. A wallet the window has just created cannot be someone
else's funded wallet, which is a better position for invariant 7 than choosing
from a list.

## How the window drives `BitcoinCore.initialize` without guessing

`initialize` and `connect` ask their questions as free text. `wallet_setup._Answer`
answers them from a choice the operator has already made on screen, and it never
guesses:

- a `[y/N]` prompt is answered `y` only when the quoted name in the prompt is
  exactly the chosen one, and `n` otherwise;
- a numbered prompt is answered once, and only with the number the library's own
  listing gave for that exact name;
- anything else raises `Offer`, carrying the names the library listed, so that
  the operator chooses again on screen.

That means a wrong or stale list can only ever produce a refusal, never a wrong
wallet, and `_select`'s exact-name confirmation still stands behind it.

`_Answer.tell` also raises when the library announces that it is waiting for
something to be done in Bitcoin-Qt. Those waits are `sleep` loops meant for a
terminal with Ctrl-C; in a window they would hang. The window reaches them only
if a wallet stops being eligible or relocks between its own checks and the
library's.

## Deliberate differences from `ms32`

- Repairing a card does not need Bitcoin Core. The command line uses a
  fingerprint hint to break a tie between candidates, which requires a running
  node; the window uses the rest of `_best` and reports an unresolved tie as
  ambiguous instead. It can therefore say "more than one repair is possible"
  where `ms32 correct` would pick one.
- The window creates Bitcoin Core wallets; `ms32 create` still does not. Whether
  the command line should match is deliberately unresolved.
- `xprv`, Core Lightning, BIP39 worksheet profiles, and the generic `codex32`
  façade are not in the window.

## Known limits

- A 74- or 127-character card scrolls sideways in the entry field, because it is
  one `Gtk.Entry`. A 48-character card fits.
- The list of empty Bitcoin Core wallets refreshes when asked, not on its own.
- Widget construction is not covered by tests. It is kept thin enough that the
  parts worth testing are the ones that need no display.
