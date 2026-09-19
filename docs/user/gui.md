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

When every card is confirmed, choose the Bitcoin Core wallet that will hold the
keys. Only empty wallets are offered, so no wallet you already use can be
overwritten. If you have none, the window can ask Bitcoin Core to create one:
give it a name and a passphrase, and codex32 fills it in and locks it again.

Forgetting that passphrase does not lose your bitcoin. Your cards still recover
the seed. It protects the wallet on this computer.

Finally, copy the wallet details onto your
[wallet record](wallet-verification-record.html) and keep it apart from every
card. The window shows exactly the fields that record asks for.

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

The window asks for a Bitcoin Core wallet passphrase, which the command line
deliberately does not; see [the security model](../security/model.md). It is sent
straight to `bitcoin-cli` and is never stored.

## If something goes wrong

The window stops and says so, and your cards remain valid. A failure while the
keys are being written leaves the wallet locked and your recovery cards
unchanged; run **Restore my wallet** again once Bitcoin Core is healthy.

The command line remains the fuller tool: `ms32 --help` lists everything,
including the parts this window leaves out.
