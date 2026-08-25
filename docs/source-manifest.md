# Source manifest

The implementation is reviewed against frozen source revisions where available.
BIP93 is Draft; later upstream changes require an explicit traceability review.

| Source | Frozen evidence | Use |
|---|---|---|
| [BIP93](https://github.com/bitcoin/bips/blob/ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e/bip-0093.mediawiki) | `bitcoin/bips@ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e` | normative `ms`, sharing, recovery, correction, vectors |
| [checksum-boundary PR #2258](https://github.com/bitcoin/bips/pull/2258) | head `7c5251d29acc1446b1b7ed86cc1ab2327bf78271` | accepted pending-standard expanded-HRP short/long selection and 94/95 gap |
| [wallet guidance](https://github.com/BlockstreamResearch/codex32/blob/1a1c22aa895d78f2d385303feb9491d155e14cf7/docs/wallets.md) | `BlockstreamResearch/codex32@1a1c22aa895d78f2d385303feb9491d155e14cf7` | import and worksheet UX |
| [illustrated booklet](https://secretcodex32.com/docs/2023-03-07--bw.pdf) | SHA-256 `0370ea863d2eae692408aeefa9b13c14283e520f45a00f7373ad933ccf418f2e` | manual generation/checksum/sharing |
| [secretcodex32.com](https://secretcodex32.com/) | response reviewed 2026-08-08 | profile and worksheet catalogue |
| [correction PR #70](https://github.com/BlockstreamResearch/codex32/pull/70) | head `610cbad30258c80cd862b3773a20f8099d25e36e`; patch SHA-256 `11ef7d8a857d38b496068db4e44382825f0209ee7895d335daba122cfb1b77b8` | BCH provenance and differential fixtures |
| [Rust reference](https://github.com/BlockstreamResearch/codex32/tree/1a1c22aa895d78f2d385303feb9491d155e14cf7/reference/rust-codex32) | same repository revision | incomplete API comparison only |
| [Core Lightning implementation](https://github.com/ElementsProject/lightning/blob/5a56a976b4583a7fb6dce33e49e71e6bc12a0305/common/codex32.c) | `ElementsProject/lightning@5a56a976b4583a7fb6dce33e49e71e6bc12a0305` | legacy `cl` size, padding, examples |
| [Core Lightning recovery](https://docs.corelightning.org/reference/recover) | reviewed 2026-08-23 | codex32 HSM-secret import path on an unused node |
| [12-word](https://secretcodex32.com/docs/checksum-bip39-12w.pdf) / [24-word](https://secretcodex32.com/docs/checksum-bip39-24w.pdf) worksheets | SHA-256 `d9ee46e8665f588aba3c82547bc7785da3d7bf5fcee53263135f5dd57bf9af5c` / `3cd40bf41facda1931b83a5bb6c112b99155cf6eaa4d8a8da065705bc45e683a` | migration profile lengths and residue fixtures |
| [BIP39](https://github.com/bitcoin/bips/blob/ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e/bip-0039.mediawiki) | `bitcoin/bips@ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e` | embedded checksum only |
| [Python `secrets`](https://docs.python.org/3/library/secrets.html) and [`random`](https://docs.python.org/3/library/random.html) | CPython 3.12–3.14 docs/source reviewed 2026-08-09 | OS entropy and `SystemRandom.sample` |
| [Koopman CRC catalogue](https://users.ece.cmu.edu/~koopman/crc/index.html) | reviewed 2026-08-09 | polynomial context, not human-error optimality |
| [Bitcoin Core 30 `createwallet`](https://bitcoincore.org/en/doc/30.0.0/rpc/wallet/createwallet/) and [`bitcoin-cli` stdin options](https://github.com/bitcoin/bitcoin/blob/master/src/bitcoin-cli.cpp) | Core 30 RPC documentation and master client source reviewed 2026-08-22 | blank watch-only wallet, encrypted restore prerequisite, one-line stdin arguments |
| [`bip32` 5.0.0](https://github.com/darosior/python-bip32/tree/8aa611536f3ae19670f9847f356a33c4008b8cbe) and [Coincurve 21 range PR #53](https://github.com/darosior/python-bip32/pull/53) | tag commit `8aa611536f3ae19670f9847f356a33c4008b8cbe`; PR head `45db547bdf5a5bc19a8c55ef447dbf9169928792` | complete upstream suite, carried dependency-range metadata, official BIP32 vectors |
| [Coincurve 20.0.0](https://github.com/ofek/coincurve/tree/1e47583d86f5580cb6f6d53e851cabe91f1b4f12) and [21.0.0](https://github.com/ofek/coincurve/tree/428504536bd7851354468c66ccf98d4bd6130338) | exact release tags and PyPI wheel metadata reviewed 2026-08-24 | used-API comparison, Python/platform wheels, differential wallet corpus |

The frozen correction corpus at `tests/data/p70_correction_vectors.json` has
SHA-256 `6aa552b34c0bb2878d45dee2655c331d52e40e41e61cef523415d314ad9948e5`.
`tools/differential_correction.py --verify` checks it offline. The repository
does not claim that the upstream Haskell property suite was executed locally.

Gate 3's independent integer capture analysis and production-path benchmark
have SHA-256 digests
`52cde9a2278e340405e097e7fd73dae045cc0a4eaefe66163063297c73a1492d`
and `a21ba3630398bb52abdf3ef5c31b38ca551ce8b4082075a80b2b4a73775d0180`.
They are evidence generators, not runtime dependencies. The obsolete prototype
was removed when the final two-family model superseded its burst and mixed
classes. Production structural correction remains in `indel.py`;
`correction.py` alone repairs symbols through the PR #70-derived fixed core.

`tools/verify_correction_constants.py` re-derives the installed short and Long
BCH roots, generators, targets, and periods. Its SHA-256 digest is
`4e37f851ea00c9ca6d10cd8897541b88cb9a835105a9880195f7ea7886f3bf04`.

`tools/bitcoin_core_regtest.py` exercises the installed CLI against an isolated
Bitcoin Core 31.1.0 regtest. It covers descriptor import with timestamp zero and
`now`, watch-only discovery and spend refusal, encrypted private import,
unlock/sign/broadcast/relock, and network-specific extended keys. This is
integration evidence, not a runtime RPC dependency.

`build_backend.py` is the complete project-specific build layer. It delegates
to Setuptools and, only when `SOURCE_DATE_EPOCH` is supplied, normalizes sdist
archive timestamps and ownership. `tests/test_build_backend.py` freezes that
boundary. `MANIFEST.in` includes the backend, repository evidence, and both
printable recovery artifacts in the source distribution.

The independent rejection literals in `tests/data/malformed_inputs.json` have
SHA-256 `966403685d979999524318d752537b5fe2ff01c0189a8e919e040dfd0de3978f`.
They are fixed abuse cases, not outputs derived from production code. The two
checked-in fuzz targets accept at most 4,096 bytes and add no runtime
dependency. Their current digests are
`92dbcfd168bb8e3a8bd86fa4f7bd3b68d89a6aafa200f81946248180b21c0f8e`
and `44ba876848c2ce0b9ede352c6d82204febb0e4c7c401f64b842f247e9c149233`.

Generalized-HRP PR #2040 and length-restriction PR #2077 are non-authoritative
research context. The README is user documentation, never requirements evidence.

The implementation intentionally follows the frozen PR #2258 head rather than
adding a dual decoder. Relative to the currently published BIP93 boundary, the
known compatibility exposure is concentrated in `ms` strings carrying 44--46
bytes. Fresh CLI generation avoids those lengths by accepting only 16 or 32
bytes; library callers and imported existing seeds retain BIP93's full 16--64
byte range. The [accepted-risk register](accepted-risks.md) requires another
upstream status and revision check before both the RC and final release.
