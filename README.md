# python-codex32

[codex32](https://github.com/bitcoin/bips/blob/master/bip-0093.mediawiki)
helps you write down a Bitcoin wallet seed in a form designed to detect common
copying mistakes. It can also split the backup into shares, so only a chosen
number of shares together can recover the seed.

This project provides a command-line tool and Python library for:

- creating and checking codex32 master-seed backups;
- splitting a backup into shares and recovering it;
- suggesting corrections for damaged backup text;
- checking or recovering other codex32 applications;
- completing or correcting checksum worksheets; and
- exporting Bitcoin Core wallet descriptors from a recovered master seed.

Creation adds the codex32 checksum. `codex32 check` detects damaged text;
`codex32 correct` only suggests a repair for comparison with the paper backup.
Shared backups use Shamir secret sharing. Splitting an existing secret creates
a new M-of-N share set with a new backup identifier.

This is not a Bitcoin wallet and it does not store your backup. It has no
graphical interface, does not connect to the Bitcoin network, cannot show
balances or send bitcoin, and does not produce BIP39 mnemonic words.

This is security-critical reference software. Use it offline and have it
reviewed by someone you trust before relying on it with funds. See
[SECURITY.md](SECURITY.md).

## Install

Python 3.12 or 3.13 is required. From this folder:

```bash
python -m venv .venv
source .venv/bin/activate

python -m pip install \
  --require-hashes \
  -r requirements/cli-build-dependencies.txt

python -m pip install \
  --no-build-isolation \
  --require-hashes \
  -r requirements/cli-dependencies.txt

python -m pip install \
  --no-build-isolation \
  --no-deps \
  .

python -m pip check
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.
The installed command is `codex32`.

## Common commands

Do not type recovery text on the same line as a command. Run the command first,
then enter the master seed or shares only when prompted.

```bash
codex32 check                 # check one backup or share
codex32 secret                # recover a complete secret
codex32 share d               # make share d from enough existing shares
codex32 create 3              # create 3-of-5 shares and initialize Bitcoin Core
codex32 correct               # suggest repairs for damaged text
codex32 wallet multisig-xpub  # export a public multisig key
```

Fresh Bitcoin wallet creation requires Bitcoin Core 30 or newer with local RPC
enabled. codex32 confirms each paper card before it asks you to select an empty
Bitcoin Core wallet.

A valid checksum means the text is internally consistent. It does not prove
that the backup belongs to your wallet. Compare recovered identifiers,
fingerprints, addresses, and wallet policy with wallet records kept separately
from the shares.

Correction results are suggestions. Always compare them with the physical
backup before using them.

See the [user guide](docs/user/guide.md) for setup, recovery, inheritance,
offline signing, and Bitcoin Core instructions. Printable forms:

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

Read [SECURITY.md](SECURITY.md) before reporting a vulnerability. Do not include
a real seed, share, wallet descriptor, or funded-wallet data in a report.
