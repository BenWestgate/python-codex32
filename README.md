# python-codex32

[codex32](https://github.com/bitcoin/bips/blob/master/bip-0093.mediawiki) is a
checksummed, secret-sharing-aware Base32 format for Bitcoin master seeds. A
master seed is the private recovery secret from which a Bitcoin wallet derives
its keys.

This project provides a command-line tool and Python library that can:
- create an unshared master-seed backup or an M-of-N shared backup;
- check backup text and suggest possible repairs after damage;
- recover a master seed from the required shares;
- add or replace shares for an existing backup;
- set up a user-created blank Bitcoin Core wallet from a new or existing
  codex32 backup.

With an M-of-N backup, any M of the N paper shares can recover the master seed.
A set with fewer than M shares cannot recover it.

This is not a Bitcoin wallet. It has no graphical interface, cannot show
balances or send bitcoin, and does not produce BIP39 mnemonic words. codex32
makes no network connection; it communicates with a local Bitcoin Core
instance through `bitcoin-cli`.

This is security-critical reference software. Use it on a trusted computer and
obtain an independent review before relying on it with funds. See
[SECURITY.md](SECURITY.md).

## Install

Python 3.12 or 3.13 is required. The installed package has no third-party
runtime dependencies. To install it with the pinned build backend, run these
commands from the project folder:

```bash
python -m venv .venv
source .venv/bin/activate

python -m pip install --require-hashes \
  -r requirements/cli-build-dependencies.txt
python -m pip install --no-build-isolation --no-deps .
python -m pip check
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.

The installed commands are `codex32` and `ms32`.

`codex32` checks, corrects, recovers, and derives shares for registered or opaque
application prefixes. `ms32` additionally creates Bitcoin master-seed backups
and provides key and wallet setup.

BIP39 worksheet profiles are supported for existing-backup recovery but are
[not recommended for creating backups](https://secretcodex32.com/docs/index.html).
Powerful correction searches, including recovery of genuinely unreadable
characters, require interactive confirmation.

## Start here

Start Bitcoin Core 32 or newer with local RPC enabled. codex32 detects and
reports the local Bitcoin Core network. To practice with Bitcoin-Qt on signet,
start it with:

```bash
bitcoin-qt -signet -server
```

Then run:

```bash
ms32 create 2
```

This creates three shares with a random identifier. Any two recover the seed, so
one can be lost. Once the shares are confirmed, codex32 initializes the
user-created blank Bitcoin Core wallet you select.

For a 3-of-7 backup with the identifier `yete`, run:

```bash
ms32 create 3yete --shares 7
```

Any three shares recover the seed, so four can be lost. Each additional share
is another recovery card to protect.

Follow the [user guide](docs/user/guide.md) for the complete setup, shared
backups, recovery, inheritance, offline signing, and Bitcoin Core instructions.

## Recovery and maintenance

Run the command first. Enter the master seed or shares only when prompted;
never put recovery text on the command line.

```bash
ms32 check    # check one secret or share
ms32 secret   # recover a secret from shares
ms32 share d  # add share d to an existing set of shares
ms32 correct  # suggest repairs for damaged text
```

Use the corresponding `codex32` commands for generic human-readable part
codex32 strings.

Printable forms:

- [codex32 recovery card](docs/user/recovery-card.html)
- [wallet-verification record](docs/user/wallet-verification-record.html)

## For developers and reviewers

The public Python API is documented in the
[API and architecture guide](docs/developer/api.md). The detailed threat model
and security properties are in the [security model](docs/security/model.md).

To work on the project:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m mypy src/codex32
python -m ruff check .
python -m ruff format --check .
```

Read [SECURITY.md](SECURITY.md) before reporting a vulnerability.
