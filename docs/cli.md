# Command-line interface

The CLI is a thin adapter over the public artifact, sharing, generation, and
fixed-correction APIs. It has no wallet state, descriptor parser, entropy
implementation, or correction search.

| Command | `ms` | `cl` | BIP39 profiles |
|---|---:|---:|---:|
| `verify` | Yes | Yes | Yes |
| `secret` | Yes | Yes | Yes |
| `share` | Yes | Yes | No |
| `create` | Yes | No | No |
| `checksum` | 128/256-bit worksheets | 32-byte payload | No |
| `correct` | Fixed BCH | Fixed BCH | No |
| `correct --residue` | 13/15-symbol application-agnostic residue |
| `xprv` | Root BIP32 private key | No | No |
| `xpub` | BIP48 coordinator account key | No | No |
| `descriptors` | Fixed Bitcoin Core templates | No | No |

`create` accepts an optional positional five-character set header. `0test` and
`ms10test` both select an unshared `ms` secret with identifier `test`;
`3cash` selects a 3-of-N set. `--indices 7cad` preserves that exact order,
while `--shares N` samples distinct indices and preserves sample order. A raw
hexadecimal seed and a re-sharing operation require an explicit header.

On a terminal, recovery asks for one share at a time and shows the already
known `hrp1` plus threshold and identifier. Redirected input accepts at most
nine whitespace-separated artifacts and is bounded before parsing.

Canonical output is suitable for piping only for operations that intentionally
produce an artifact. `correct` writes a checksum-valid suggestion to stderr and
returns nonzero. A valid input needing no correction returns zero. Worksheet
residue positions are displayed one-based from the end.

`--pretty` is command-local on artifact-producing commands. It groups uppercase
text for transcription and displays public header fields. Pretty `MasterSeed`
secrets include their BIP32 master fingerprint; shares never do.

Wallet commands accept only `ms` S. They have explicit account, network, and
timestamp options and no hidden state. Private descriptors contain the root
xprv and produce a root-authority warning on stderr.
