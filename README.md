# python-codex32

[codex32](https://github.com/bitcoin/bips/blob/master/bip-0093.mediawiki) is a
paper-backup format for Bitcoin master seeds. A master seed is the private
recovery secret from which a Bitcoin wallet derives its keys.

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

Python 3.12 or 3.13 is required. To install the project with its pinned
dependencies, run these commands from the project folder:

```bash
python -m venv .venv
source .venv/bin/activate

python -m pip install --require-hashes \
  -r requirements/cli-build-dependencies.txt
python -m pip install --no-build-isolation --require-hashes \
  -r requirements/cli-dependencies.txt
python -m pip install --no-build-isolation --no-deps .
python -m pip check
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.

The installed command is `codex32`.

## Start here

Start Bitcoin Core 30 or newer with local RPC enabled. codex32 detects and
reports the local Bitcoin Core network. To practice with Bitcoin-Qt on signet,
start it with:

```bash
bitcoin-qt -signet -server
```

Then run:

```bash
codex32 create 2
```

This creates three shares with a random identifier. Any two recover the seed, so
one can be lost. Once the shares are confirmed, codex32 initializes the
user-created blank Bitcoin Core wallet you select.

For a 3-of-6 backup with the identifier `cash`, run:

```bash
codex32 create 3cash --shares 6
```

Follow the [user guide](docs/user/guide.md) for the complete setup, shared
backups, recovery, inheritance, offline signing, and Bitcoin Core instructions.

## Recovery and maintenance

Run the command first. Enter the master seed or shares only when prompted;
never put recovery text on the command line.

```bash
codex32 check    # check one secret or share
codex32 secret   # recover a secret from shares
codex32 share d  # add share d to an existing set of shares
codex32 correct  # suggest repairs for damaged text
```

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
