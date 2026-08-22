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
| `xprv`, `xpub`, `descriptors` | S only | no | no |

`correct --residue` is application-agnostic: 13 symbols select regular codex32
and 15 select Long codex32.

`create` accepts a positional set header. `0test` and `ms10test` are equivalent;
`3cash` requests a 3-of-N set. `--indices 7cad` preserves exact order.
`--shares N` samples distinct indices and preserves sample order. Raw seeds and
re-sharing require an explicit new header.

TTY recovery asks for one share at a time and prefills the known HRP, threshold,
and identifier. Redirected input accepts at most nine whitespace-separated
artifacts and is bounded before parsing.

`--pretty` is local to commands producing a codex32 artifact. It groups uppercase
text and public header fields. Pretty `ms` S may show its BIP32 fingerprint;
shares never do.

A fixed correction suggestion goes only to stderr and exits nonzero. A valid
input needing no correction exits zero. Always verify a suggestion against the
physical backup.

Wallet commands are stateless. `--account`, `--testnet`, and descriptor
`--timestamp` are explicit; timestamp defaults to zero. `descriptors --private`
warns that the output contains the root xprv.
