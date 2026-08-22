# Runtime dependency review

The package has one direct runtime dependency: `bip32>=5,<6`. The compatible
range permits bug-fix releases, but a release must record and review the exact
resolved dependency set. A resolved-version change requires the full BIP32 and
wallet-vector suite before publication.

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
