# Command-line interface

The installed `codex32` command reads protected material from a terminal prompt
or stdin. Secret material is never a command argument.

| Command | `ms` | `cl` | `bip39_12w/24w` |
|---|---:|---:|---:|
| `check` | yes | yes | yes |
| `secret` | yes | yes | yes |
| `share` | yes | yes | no |
| `create` | yes | yes | no |
| `checksum` | published Book worksheets | fixed application worksheet | no |
| `correct` | fixed BCH | fixed BCH | no |
| `xprv`, `wallet ...` | S only | no | no |

`check` confirms the supported codex32 format, checksum, and application rules.
It does not prove that a string belongs to the intended wallet.

`secret` displays the complete recovered secret. Doing so removes the protection
provided by keeping the backup split into separate shares.

`checksum` completes only a filled-out Codex32 Book checksum worksheet. Before
using it, follow the Book's dice-debiasing steps exactly, then enter the non-pink
bold squares requested by the command. It intentionally does not explain payload
sizes or help turn arbitrary text, raw dice rolls, seed words, hexadecimal data,
or passwords into a checksummed wallet backup.

`correct --residue` is application-agnostic: 13 symbols select regular codex32
and 15 select Long codex32. Its repeatable `--erasure` positions are one-based
and counted backward from the end. For a complete string, use `?` for an
erasure; any other invalid data character is treated as an erasure as well.
The complete-string command recognizes an undamaged `ms1` or `cl1` prefix and
never guesses or corrects the prefix.

`create` accepts either a sharing threshold or a complete backup header.
`3` requests a 3-of-N Bitcoin master-seed set with a random identifier, while
`3cash` uses the explicit identifier `cash`. `0test` and `ms10test` are
equivalent. The `cl1` prefix selects Core Lightning; its identifier may also be
random or explicit. `--indices 7cad` preserves exact order.
`--shares N` samples distinct indices and preserves sample order. Raw seeds and
re-sharing use random identifiers when none is supplied. Bare interactive
`create` immediately generates an unshared Bitcoin master seed. Generation
never prompts for protected input. Fresh `ms` generation accepts 16 or 32 bytes;
the default is 16. `--existing` instead reads one existing codex32 secret or
hexadecimal seed from the terminal or bounded stdin and retains every 16--64
byte BIP93 `ms` size. Nonempty redirected input without that flag is rejected
rather than ignored. Without a share selector, a shared set contains two more
shares than are needed for recovery; threshold zero remains unshared.
Hexadecimal input must already contain securely generated entropy; a random
backup identifier does not make a weak seed safe.
After creation, the CLI reminds the user to test recovery using what was
written down rather than copying strings directly from the same screen.
Newly generated CL secrets use the zero-padding convention emitted by CLN.
Parsed CL secrets with other legal discarded bits remain valid and preserve
those bits when split.

TTY recovery asks first for a complete secret or share. After the first ordinary
share, it displays the immutable `hrp1` plus threshold and identifier inline.
The user may type only the remaining suffix or paste a complete string. Invalid
entries repeat the same prompt. Where Python provides Readline, the most recent
rejected entry is restored for editing without being added to history. After a
prefix is known, only a safely matching suffix is editable; an entry with a
conflicting prefix or an already-used share index is not restored. Platforms
without Readline repeat an empty prompt. The temporary editor hook is removed
after every attempt, and protected input is never written to a history file.
Ctrl-D exits 2 and Ctrl-C exits 130 without a traceback. “Accepted” means
checksum-valid and compatible with the entries collected so far; it does not
prove that they belong to the intended wallet.
A direct secret proceeds immediately to the command result. Recovery sets use
`Share 1 of 3 accepted.` while more input is needed. A derivation basis may
contain a secret or ordinary shares, so the neutral `String 1 of 3 accepted.`
is used there. The final accepted input proceeds directly to the result without
a redundant status line.

`share INDEX` validates INDEX before requesting protected input. During terminal
entry, a basis string already using the requested index is rejected immediately
and is not restored for editing.

Interactive editor display goes to stderr, including when stdout is piped to
another program. A rejected entry remains temporarily visible in terminal
scrollback and may remain in Python or native editor memory; neither can be
reliably erased by this program.

Redirected input accepts at most nine bounded whitespace-separated artifacts
without prompts or status. In both modes, stdin is recovery material, stderr is
human interaction, and stdout is only the requested result.

Recovery commands stop immediately on a direct S. `share` instead collects an
exact interpolation basis and may include S plus compatible ordinary shares.

Commands producing a codex32 artifact use transcription formatting only when
their output goes to a terminal. It alternates bold and normal four-character
groups and adds extra separation after every four groups. Successful terminal
input is separated from results, and multiple formatted artifacts are separated
from one another. Redirected output is always the canonical codex32 string and
never contains terminal control codes.
`--plain` also requests canonical output at a terminal. Formatted `ms` S may show
its BIP32 fingerprint; shares never do. The application and artifact kind share
one heading, followed by the codex32 backup identifier.

A fixed correction suggestion goes only to stderr and exits nonzero. A valid
input needing no correction exits zero. A suggestion is not proof that the
result belongs to the intended wallet; always compare it with the physical
backup.

Wallet commands are deliberately goal-oriented:

```text
codex32 xprv [--testnet]
codex32 wallet multisig-xpub [--account N] [--testnet]
codex32 wallet bitcoin-core restore [--account N] [--timestamp N] [--testnet]
codex32 wallet bitcoin-core watch-only [--account N] [--timestamp N] [--testnet]
```

Every parser level requires its subcommand and rejects abbreviated options.
`restore` always emits private descriptors and warns that they contain the root
xprv. `watch-only` never emits private key material. Both modes write one compact
`importdescriptors` JSON line. Account and timestamp are explicit; timestamp
defaults to zero. The removed top-level `xpub` and `descriptors` commands have no
aliases. Root-authority warnings use a bold red `Warning:` label only when stderr
is a terminal; private keys and redirected output never contain styling codes.

## Air-gap transfer

Public descriptors and origin-qualified xpubs may leave the offline computer.
They cannot spend funds, but they reveal wallet structure and can expose all
associated balances and transaction history. Transfer them only to the intended
Bitcoin Core wallet or multisig coordinator.

The command output can be encoded optically with a locally installed
[`qrencode`](https://github.com/fukuchi/libqrencode) command:

```bash
codex32 wallet multisig-xpub |
  qrencode -l M -t ANSIUTF8 -o -
```

```bash
codex32 wallet bitcoin-core watch-only |
  qrencode -l M -t ANSIUTF8 -o -
```

Because stdout is piped, codex32 emits only its canonical public result while
prompts remain on the terminal. `qrencode` is an optional external tool, not a
Python standard-library facility or a dependency of this project. Use `UTF8`
instead of `ANSIUTF8` if the terminal does not display ANSI output correctly.
Large descriptor QRs may require a maximized terminal or image output.

These QRs contain the plain output expected by the receiving application. They
are not UR or BSMS records. Wallet support for QR payload formats varies. Do not
use an online QR service: public wallet data remains privacy-sensitive, and a
service could replace it. After scanning, compare the master fingerprint and
derivation path. For multisig, verify the complete policy and first receiving
address on independent devices as described by
[BIP129](https://github.com/bitcoin/bips/blob/master/bip-0129.mediawiki).

Descriptor and extended-key checksums detect accidental transfer errors, not an
attacker who replaces the complete output. Never transfer a codex32 secret or
share, xprv, or private descriptor to an online machine by QR or removable
media.

## Private Bitcoin Core restoration

Private restoration emits descriptors containing the root private key, which
can spend funds from every wallet derived from the seed. First create and load a
blank, encrypted descriptor wallet named `recovery`. Bitcoin Core is responsible
for wallet creation, encryption, passphrase handling, and persistent storage.

Unlock the wallet, pipe the private descriptors directly into Bitcoin Core, and
immediately relock it:

```bash
bitcoin-cli -rpcwallet=recovery \
  -stdinwalletpassphrase walletpassphrase 60

codex32 wallet bitcoin-core restore --timestamp 0 |
  bitcoin-cli -rpcwallet=recovery -stdin importdescriptors

bitcoin-cli -rpcwallet=recovery walletlock
```
