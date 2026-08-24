# python-codex32

[codex32](https://github.com/bitcoin/bips/blob/master/bip-0093.mediawiki)
helps you write down a Bitcoin wallet seed in a form designed to detect common
copying mistakes. It can also split the backup into shares, so only a chosen
number of shares together can recover the seed.

This project provides a command-line tool and Python library for:

- creating and checking codex32 master-seed backups;
- splitting a backup into shares and recovering it;
- suggesting corrections for damaged backup text;
- checking or recovering supported older Core Lightning and BIP39 worksheet
  backups; and
- producing Bitcoin wallet import information from a recovered master seed.

This is not a Bitcoin wallet and it does not store your backup. It has no
graphical interface, does not connect to the Bitcoin network, cannot show
balances or send bitcoin, and does not produce BIP39 mnemonic words.

This is security-critical reference software. Use it offline and have it
reviewed by someone you trust before relying on it with funds. See
[SECURITY.md](SECURITY.md) and the direct
[specification-to-code map](docs/traceability.md).

## Install and test

Supported Python versions are 3.12 through 3.14.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python -m mypy src/codex32
python -m ruff check .
```

The installed command is `codex32`.

## CLI usage

Secret inputs are read from a terminal prompt or stdin, not command arguments.
Avoid shell commands containing literal secrets because shell history and
process inspection may retain them.

```bash
codex32 check
codex32 secret
codex32 share d
codex32 create 3cash
codex32 correct
codex32 wallet multisig-xpub --account 0
```

On a terminal, recovery commands request one secret or the required shares in
sequence. Redirected stdin may instead contain bounded whitespace-separated
inputs for automation.

`correct` prints its suggestion to stderr and exits nonzero. A correction is not
proof that the result belongs to your wallet; always compare it with the
physical backup.

See [docs/cli.md](docs/cli.md) for the complete command/profile matrix.

## Create a Bitcoin Core watch-only wallet

This example creates a wallet that can find balances but cannot sign
transactions:

```bash
bitcoin-cli -named createwallet \
  wallet_name=codex32-watchonly \
  disable_private_keys=true \
  blank=true \
  descriptors=true \
  load_on_startup=true

codex32 wallet bitcoin-core watch-only |
  bitcoin-cli -rpcwallet=codex32-watchonly -stdin importdescriptors
```

codex32 prompts for the backup on the terminal. Its stdout goes directly to
Bitcoin Core as one `importdescriptors` argument; prompts and status remain on
stderr.

Private restoration has additional security requirements; see the
[CLI documentation](docs/cli.md#private-bitcoin-core-restoration).
For recovery by someone who did not create the wallet, see
[Restoring an inherited backup](docs/inheritance.md).

## API example

```python
from codex32 import MasterSeed, Share, derive_share, parse_codex32, recover_secret

a = parse_codex32("MS12NAMEA320ZYXWVUTSRQPNMLKJHGFEDCAXRPP870HKKQRM")
c = parse_codex32("MS12NAMECACDEFGHJKLMNPQRSTUVWXYZ023FTR2GDZMPY6PN")
assert isinstance(a, Share) and isinstance(c, Share)

secret = recover_secret([a, c])
assert isinstance(secret, MasterSeed)
additional = derive_share([a, c], "d")
```

Worksheet residue correction is also available without disclosing the backup's
profile or length:

```python
from codex32 import correct_worksheet_residue

corrections = correct_worksheet_residue("2ppjkw73qdjvc")
if corrections is None:
    raise ValueError("no unique correction")

for correction in corrections:
    print(correction.reverse_index + 1, correction.addend)
```

Ordinary shares expose canonical text and u5 payload symbols, never bytes.
Only profile-specific secret types expose semantic bytes. Public construction,
sharing, correction, generation, and wallet functions are listed in the
authoritative [package exports](src/codex32/__init__.py).

## Review map

Start with these small, one-owner modules:

| Concern | Owner |
|---|---|
| bounded text and checksum boundary | `bech32.py`, `checksums.py` |
| fixed application rules | `profiles.py`, `bip39.py` |
| immutable artifacts and BIP93 interpolation | `bip93.py` |
| generation and OS entropy | `generation.py` |
| fixed BCH correction | `correction.py`, `gf32.py` |
| typed BIP32 boundary and wallet interoperability | `_bip32.py`, `wallet.py` |
| bounded stdin and TTY entry | `_cli_input.py` |
| command grammar and presentation only | `_cli_parser.py`, `cli.py` |

The installed package is under 3,000 physical Python lines, excluding tests.
Tests use official vectors, frozen external fixtures, negative boundary cases,
and property checks without replacing production entropy.

The reviewed runtime dependency boundary is recorded in
[docs/dependencies.md](docs/dependencies.md).
