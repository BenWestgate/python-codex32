# codex32 graphical user interface

`codex32-gui` provides the main `ms32` jobs in a graphical user interface.
Recovery text stays on screen only while it is needed.

| Task | Command |
|---|---|
| Set up a new wallet | `ms32 create` |
| Restore my wallet | `ms32 wallet` |
| Check a card | `ms32 check` |
| Repair a damaged card | `ms32 correct` |
| Replace a lost card | `ms32 share` |
| Show my master seed | `ms32 secret` |

`ms32 xprv`, Core Lightning secrets, and BIP39 worksheet profiles remain
command-line tasks.

## Install

GTK 4 and libadwaita come from the operating system:

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

If those packages are already installed, skip that step. Then create the virtual
environment and install codex32:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install 'codex32[gui]'
.venv/bin/codex32-gui
```

`--system-site-packages` lets the virtual environment import the system PyGObject
package. The base `codex32` install still has no third-party runtime dependency.

`codex32-gui` takes no arguments. Never put a secret in one.

The GUI disables GTK's accessibility bus by default because it can expose seed
text and passphrases to other desktop processes. Screen-reader users can opt in
with `GTK_A11Y=atspi codex32-gui`.

## Before you start

Start Bitcoin Core first. Wallet setup and restore discover it before any card is
created or entered. Practise on signet with `bitcoin-qt -signet -server`.

Checking, repairing, replacing a card, and showing the master seed do not open a
Bitcoin Core wallet.

## Entering cards

A card never contains **B**, **I**, **O**, or **1**. If one is entered, the GUI
reports the likely look-alike instead of silently deleting it.

When recovering from several cards, use `?` for a header or card-index character
you genuinely cannot read. **Check a card** requires the printed character.

## Making a backup

The recommended layout is three cards where any two recover the wallet. One card
can be lost, and one card alone reveals nothing.

Copy each card to paper, hide the on-screen original, then type the paper copy
back. Read-back starts completely empty, including `MS1`. A mismatch highlights
only the groups you typed differently; the expected text stays hidden.

After all cards are confirmed, write the displayed master fingerprint on your
wallet record, then re-enter it in the GUI. Wallet selection stays unavailable
until the re-entered fingerprint matches. Then choose an empty Bitcoin Core
wallet or create a new blank one. A passphrase protects the wallet on this
computer; the recovery cards still recover the seed if that passphrase is lost.

Copy the final wallet details to the
[wallet record](wallet-verification-record.html) and store it separately from the
cards.

## Repairing a damaged card

Type what you can read and `?` for each unknown character. The repair field
preserves damaged headers and explicit `?` characters so the correction engine
sees what is actually on the card. **Suggest a repair** appears whenever the
input is within the supported correction bounds, including missing or extra
characters.

A repair candidate may highlight groups that changed. Those are changes, not
proven error locations. Hold your card next to the screen and compare the entire
string, character by character.

When too little checksum remains, the GUI requires literal `YES` before showing a
candidate. Completing new hand-written data can lock earlier transcription
errors in; recovery from a damaged card can produce a valid-looking but wrong
guess. Never erase or replace a card's ending just to make it validate. If the
funds matter, stop and get help.

If more than one repair fits, none is shown. A repaired card is always presented
as a guess; copy it to a fresh card and verify the restored wallet's master
fingerprint.

## What the graphical user interface never claims

A share records its recovery threshold and its own index, not how many shares
exist. The GUI can say “any 2 cards recover the wallet”; it cannot infer “2 of
3”. `ms32 share` can add another card at any time.

A valid checksum shows that a card is internally consistent. It does not prove
that the card belongs to your wallet. Before restoring into Bitcoin Core, type
the master fingerprint from your separate wallet record; a mismatch stops before
any wallet is opened or created. If you have no record, the GUI instead shows the
recovered fingerprint and what the backup identifier says about the seed, then
requires a separate **Restore anyway** choice. This fallback detects some
mistakes but does not authenticate the intended wallet; check its history and
addresses before sending funds.

## Secret handling

The GUI writes no settings, recent-file list, log, or clipboard data containing
recovery text. Card text is cleared when its page is left. Bitcoin Core secrets
go to `bitcoin-cli` on standard input, not command arguments.

On X11, selecting entry text briefly owns the primary selection, which some
clipboard managers persist. Avoid selecting recovery text.

Ordinary entry supplies and protects `MS1` and blocks forward typing after an
invalid header unless you explicitly choose to keep damaged text. **Repair a
damaged card** accepts damaged headers. Read-back supplies nothing and performs
no correction.

## If something goes wrong

GUI failure does not alter a paper card. Fix Bitcoin Core, then use **Restore my
wallet** with the existing cards; do not create a new backup.

Restore asks you to compare wallet identity, especially the master fingerprint,
with your wallet record. The GUI always uses account 0. For another account, use
`ms32 wallet --account N`.
