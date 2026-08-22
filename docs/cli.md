# Command-line interface

The installed `codex32` command reads protected material from a terminal prompt
or stdin. Secret material is never a command argument.

| Command | `ms` | `cl` | `bip39_12w/24w` |
|---|---:|---:|---:|
| `verify` | yes | yes | yes |
| `secret` | yes | yes | yes |
| `share` | yes | yes | no |
| `create` | yes | no | no |
| `checksum` | 128/256-bit worksheet | fixed 32-byte payload | no |
| `correct` | fixed BCH | fixed BCH | no |
| `xprv`, `wallet ...` | S only | no | no |

`correct --residue` is application-agnostic: 13 symbols select regular codex32
and 15 select Long codex32.

`create` accepts a positional set header. `0test` and `ms10test` are equivalent;
`3cash` requests a 3-of-N set. `--indices 7cad` preserves exact order.
`--shares N` samples distinct indices and preserves sample order. Raw seeds and
re-sharing require an explicit new header.

TTY recovery asks first for a complete secret or share. After the first ordinary
share, it displays the immutable `hrp1` plus threshold and identifier inline.
The user may type only the remaining suffix or paste a complete string. Invalid
entries are discarded and the same prompt is repeated; rejected text is never
inserted into an editable history buffer. The display uses no readline,
terminal-editing, or cursor-control machinery. Ctrl-D exits 2 and Ctrl-C exits
130 without a traceback. “Accepted” means checksum-valid and compatible with
the entries collected so far; it does not authenticate the intended wallet.

Redirected input accepts at most nine bounded whitespace-separated artifacts
without prompts or status. In both modes, stdin is recovery material, stderr is
human interaction, and stdout is only the requested result.

Recovery commands stop immediately on a direct S. `share` instead collects an
exact interpolation basis and may include S plus compatible ordinary shares.

`--pretty` is local to commands producing a codex32 artifact. It groups uppercase
text and public header fields. Pretty `ms` S may show its BIP32 fingerprint;
shares never do.

A fixed correction suggestion goes only to stderr and exits nonzero. A valid
input needing no correction exits zero. Always verify a suggestion against the
physical backup.

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
aliases.

## Private Bitcoin Core restoration

Private restoration emits descriptors containing the root xprv and therefore
grants secret root authority. First create and load a blank, encrypted descriptor
wallet named `recovery`. Bitcoin Core is responsible for wallet creation,
encryption, passphrase handling, and persistent storage.

Unlock the wallet, pipe the private descriptors directly into Bitcoin Core, and
immediately relock it:

```bash
bitcoin-cli -rpcwallet=recovery \
  -stdinwalletpassphrase walletpassphrase 60

codex32 wallet bitcoin-core restore --timestamp 0 |
  bitcoin-cli -rpcwallet=recovery -stdin importdescriptors

bitcoin-cli -rpcwallet=recovery walletlock
```
