# Runtime dependency review

The package has one direct runtime dependency: `bip32>=5,<6`. The compatible
range permits bug-fix releases, but a release must record and review the exact
resolved dependency set. A resolved-version change requires the full BIP32 and
wallet-vector suite before publication.

The metadata now reserves `1.0.0rc1`; it is not authorization to publish. The
compatible library range remains deliberate. Gate 2 must add a tested,
hash-pinned CLI installation constraint and reconcile native wheels across
Python 3.12--3.14 before the release candidate can be considered dependency-
assured. Bitcoin Core cannot replace this boundary because it has no interface
that derives this project's root key and wallet records from raw seed bytes.

## Reviewed resolution

Reviewed on 2026-08-22 with Python 3.13 on Linux x86-64:

| Package | Version | Purpose |
|---|---:|---|
| `bip32` | 5.0.0 | BIP32 root keys, fingerprints, and path derivation |
| `coincurve` | 20.0.0 | secp256k1 implementation selected by `bip32` |
| `asn1crypto` | 1.5.1 | transitive `coincurve` dependency |
| `cffi` | 2.1.1 | Python/native boundary used by `coincurve` |
| `pycparser` | 3.0 | transitive `cffi` dependency |

`bip32` 5.0.0 declares `coincurve>=15,<21`. It does not publish `py.typed` or
type stubs. Only `src/codex32/_bip32.py` imports it; that adapter defines the
three operations used by this project and converts its invalid-seed exception
to `CodexError`. The rest of the package is checked by strict mypy without
import suppression.

Published `bip32` 5.0.0 artifact SHA-256 hashes:

- sdist: `4caa1f74eed9f2cd4624b55f34a4094f52542552fe3d0cc52e1179b8d6e9f21e`
- wheel: `b20872795ae2bb4e5fac351f53ccdf2b998f82e927413922a2c5473a004bd6d0`

The project verifies the official BIP93 BIP32 vectors, mainnet and testnet
extended keys, BIP48 account xpubs, and public/private Bitcoin Core descriptor
fixtures. This is dependency-boundary evidence, not an independent audit of
`bip32`, `coincurve`, or libsecp256k1.

Sources: [`bip32` on PyPI](https://pypi.org/project/bip32/) and the installed
wheel metadata captured by the clean-environment release check.

## Development-tool baseline

Most development tools remain compatible ranges or unpinned extras rather than
a reproducible release environment. Ruff is pinned to 0.16.2 because it defines
the formatting baseline. On 2026-08-24 the existing Python 3.13.12 environment
also contained pytest 8.4.2, Hypothesis 6.165.2, mypy 2.3.0, build
1.2.2.post1, and Twine 6.2.0. Ruff 0.16.2 reports formatting drift already
present at the Gate 0 starting revision, despite lint passing. A mechanical
110-column Ruff baseline reconciles that drift at 2,970 production lines; a
100-column probe produced 3,021 and was rejected. Gate 2 must freeze the final
cross-platform release-tool and dependency evidence.
