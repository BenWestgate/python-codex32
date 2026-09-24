# codex32 window

`codex32-gui` does the same Bitcoin master-seed jobs as the `ms32` command, in a
window. It is meant for someone who has never seen codex32 before: every screen
asks one question, in plain words, and the recovery text is only ever on the
screen while it is needed.

The window does the six things on its first page:

| Task | The command it matches |
|---|---|
| Set up a new wallet | `ms32 create` |
| Restore my wallet | `ms32 wallet` |
| Check a card | `ms32 check` |
| Repair a damaged card | `ms32 correct` |
| Replace a lost card | `ms32 share` |
| Show my master seed | `ms32 secret` |

`ms32 xprv`, Core Lightning secrets, and the BIP39 worksheet profiles stay in the
command line.

## Install

The window is drawn with GTK 4 and libadwaita, which arrive as system packages
rather than as Python wheels, so it is an optional extra:

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
python3 -m venv --system-site-packages .venv
.venv/bin/pip install 'codex32[gui]'
.venv/bin/codex32-gui
```

Tails 7 and Debian 13 already carry those three packages, so an amnesic session
needs no download. `--system-site-packages` is what lets the virtual environment
see them; without it PyGObject cannot be imported. The base `codex32` install
still has no third-party runtime dependency, and it still works without any of
this.

`codex32-gui` takes no arguments. Never put a secret in one.

The window turns off the desktop's accessibility bus, because GTK otherwise
offers every line on screen — your cards, your master seed and your wallet
passphrase — to any other program running as you. If you use a screen reader,
start it with `GTK_A11Y=atspi codex32-gui` instead; that gives the screen reader
what it needs, and everything else on that bus too.

## Before you start

Start Bitcoin Core first. Setting up and restoring a wallet both look for it
before anything else happens, so that you never write cards by hand only to find
that the last step cannot run. Practise on signet before you use mainnet: start
Bitcoin Core with `bitcoin-qt -signet -server`, and the window will ask which
network to use if more than one is running.

Checking a card, repairing a card, replacing a card, and showing your master seed
never open a Bitcoin Core wallet at all.

## Making a backup

Choose how many cards you want. Three cards where any two recover the wallet is
the recommended shape: one card can be lost, burned or stolen and your bitcoin is
still safe, and one card on its own tells a finder nothing.

Each card is shown once. Copy it onto paper with a pen, then type it back from
the paper with the original off the screen. That catches a slip of the pen now
rather than years from now. If a group does not match, the window says which one;
correct that group and try again, as many times as you like.

When every card is confirmed, the window shows the master fingerprint. Write it
on your [wallet record](wallet-verification-record.html), then type it back from
what you wrote. That catches a writing mistake while it can still be fixed.

Next, choose the Bitcoin Core wallet that will hold the
keys. Only empty wallets are offered, so no wallet you already use can be
overwritten. If you have none, the window can ask Bitcoin Core to create one:
give it a name and a passphrase, and codex32 fills it in and locks it again.

Forgetting that passphrase does not lose your bitcoin. Your cards still recover
the seed. It protects the wallet on this computer.

Finally, copy the wallet details onto your
[wallet record](wallet-verification-record.html) and keep it apart from every
card. The window shows exactly the fields that record asks for.

A card never contains **B**, **I**, **O** or **1**: those four are left out of
the alphabet precisely because handwriting confuses them with 8, J, L and 0. If
you type one, the window says so and names what the card probably says, rather
than quietly swallowing it.

## A card that is damaged

Type what you can still read, and `?` for each character you cannot make out.
When the line is full length, **Suggest a repair** appears. The window shows one
candidate with the guessed groups highlighted; hold it next to the card and
compare it character by character before you accept it.

If too much is missing, the window stops and asks you to type `YES` in capitals
first. That is not a formality: with that little checksum left, a repair can look
correct without being correct, and any earlier mistake gets locked in with
nothing left to detect it. If the funds matter, stop there and get help.

If more than one repair fits, the window shows none of them. Check the card again.

A repaired card is never called intact. The window says it is what the card
*should* say, marks it as guesswork, and tells you to copy it onto a fresh card
and prove it by restoring your wallet and checking the master fingerprint.

## What the window never claims

A card carries how many cards recovery needs, and its own letter. It does not
carry how many cards exist, nothing writes that number down, and `ms32 share` can
mint another card at any time. So the window will say "any 2 cards recover the
wallet"; it will never say "2 of 3". Only your own records know how many cards
you made.

A card that checks out is undamaged. That does not prove it belongs to your
wallet. Only restoring the wallet and comparing it with your wallet record shows
that.

## What it does with your text

Nothing is saved. There is no settings file, no recent-files list, no log, and
nothing is copied to the clipboard for you. The typed text lives in the field and
the card on screen, and both are cleared when you leave the page. The only
program codex32 starts is `bitcoin-cli`, on the loopback address, and secrets
reach it on standard input rather than in a command argument, so they never
appear in the list of running programs.

One thing is worth knowing: on X11, selecting text inside the entry field hands
it to the primary selection, which some clipboard managers copy to disk. The
window takes it back immediately, but the safest habit is not to select the text
of a card at all. You never need to: nothing here asks you to copy and paste.

The window asks for a Bitcoin Core wallet passphrase, which the command line
deliberately does not; see [the security model](../security/model.md). It is sent
straight to `bitcoin-cli` and is never stored.

## If something goes wrong

The window stops and says so, and it says in as many words that your cards are
unharmed and still recover the wallet. Nothing is ever written onto a card by
Bitcoin Core, so a failure here cannot damage one. Once Bitcoin Core is healthy,
choose **Restore my wallet** and enter the same cards — not **Set up a new
wallet**, which would make a different backup. If the wallet was part-filled
before it failed, it is no longer empty, so it will not be offered again: create
another one, or ask Bitcoin Core for a fresh blank wallet.

When you restore, the window first asks you to type the master fingerprint from
your wallet record. If it does not match, nothing is written to Bitcoin Core:
check what you typed, and if it still does not match, these cards are not that
wallet. If you have no record, **I have no wallet record** shows the master
fingerprint and whether the backup identifier was made from the recovered seed,
explains what that can and cannot prove, and restores only if you still choose
to. Check the balance and history before you send money to that wallet.

After the restore, **check** the remaining wallet details against your record
rather than copy them onto it. It shows no creation date on that screen, because the
real one is already on your record and today's would replace it.

The window always uses account 0, which is what it writes onto your wallet
record. If you are restoring a wallet whose record shows a different account
number, use `ms32 wallet --account N` instead.

The command line remains the fuller tool: `ms32 --help` lists everything,
including the parts this window leaves out.
