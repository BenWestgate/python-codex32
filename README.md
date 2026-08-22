# python-codex32

A small, typed reference implementation of [BIP93 codex32](https://github.com/bitcoin/bips/blob/master/bip-0093.mediawiki) for Python 3.12–3.14.

The project deliberately does less so its security boundary can be reviewed:

- immutable parsing for `ms`, legacy Core Lightning `cl`, and the two
  migration-only BIP39 worksheet profiles;
- exact-threshold BIP93 recovery and fresh-share derivation;
- reviewed `ms` generation and splitting with no injectable entropy source;
- fixed-length BCH correction and private worksheet-residue correction;
- a small stdin-oriented CLI; and
- a stateless `MasterSeed`-only Bitcoin wallet adapter.

It does not provide a GUI, networking, RPC, a wallet database, arbitrary
descriptor parsing, runtime profile registration, structural insertion/deletion
search, partial-basis generation, BIP39 mnemonics, or Core Lightning generation.

This is security-critical reference software. Review it and its dependencies
before using it with funds. See [SECURITY.md](SECURITY.md) and the direct
[specification-to-code map](docs/traceability.md).

## Install and test

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python -m mypy src/codex32
python -m ruff check .
```

The installed command is `codex32`.

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

Ordinary shares expose canonical text and u5 payload symbols, never bytes.
Only profile-specific secret types expose semantic bytes. Public construction,
sharing, correction, generation, and wallet functions are listed in
[docs/api-migration.md](docs/api-migration.md).

## CLI safety

Secret inputs are read from a terminal prompt or stdin, not command arguments.
Avoid shell commands containing literal secrets because shell history and
process inspection may retain them.

```bash
codex32 verify < backup.txt
codex32 secret < shares.txt
codex32 share d < shares.txt
codex32 create 3cash --shares 5
codex32 correct < damaged.txt
codex32 xpub --account 0 < shares.txt
```

`correct` prints a checksum-valid suggestion to stderr and exits nonzero.
Correction is not authentication; always compare the result with the physical
backup. `descriptors --private` outputs the root xprv and therefore grants root
authority.

See [docs/cli.md](docs/cli.md) for the complete command/profile matrix.

## Review map

Start with these small, one-owner modules:

| Concern | Owner |
|---|---|
| bounded text and checksum boundary | `bech32.py`, `checksums.py` |
| fixed application rules | `profiles.py`, `bip39.py` |
| immutable artifacts and BIP93 interpolation | `bip93.py` |
| generation and OS entropy | `generation.py` |
| fixed BCH correction | `correction.py`, `gf32.py` |
| wallet interoperability | `wallet.py` |
| presentation only | `cli.py` |

The production package is under 3,000 physical Python lines; no production
module exceeds 650 lines. Tests use official vectors, frozen external fixtures,
negative boundary cases, and property checks without replacing production
entropy.
