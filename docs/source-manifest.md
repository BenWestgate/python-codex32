# Source manifest

The implementation is reviewed against frozen source revisions where available.
BIP93 is Draft; later upstream changes require an explicit traceability review.

| Source | Frozen evidence | Use |
|---|---|---|
| [BIP93](https://github.com/bitcoin/bips/blob/ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e/bip-0093.mediawiki) | `bitcoin/bips@ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e` | normative `ms`, sharing, recovery, correction, vectors |
| [checksum-boundary PR #2258](https://github.com/bitcoin/bips/pull/2258) | head `7c5251d29acc1446b1b7ed86cc1ab2327bf78271` | expanded-HRP short/long selection and 94/95 gap |
| [wallet guidance](https://github.com/BlockstreamResearch/codex32/blob/1a1c22aa895d78f2d385303feb9491d155e14cf7/docs/wallets.md) | `BlockstreamResearch/codex32@1a1c22aa895d78f2d385303feb9491d155e14cf7` | import and worksheet UX |
| [illustrated booklet](https://secretcodex32.com/docs/2023-03-07--bw.pdf) | SHA-256 `0370ea863d2eae692408aeefa9b13c14283e520f45a00f7373ad933ccf418f2e` | manual generation/checksum/sharing |
| [secretcodex32.com](https://secretcodex32.com/) | response reviewed 2026-08-08 | profile and worksheet catalogue |
| [correction PR #70](https://github.com/BlockstreamResearch/codex32/pull/70) | head `610cbad30258c80cd862b3773a20f8099d25e36e`; patch SHA-256 `11ef7d8a857d38b496068db4e44382825f0209ee7895d335daba122cfb1b77b8` | BCH provenance and differential fixtures |
| [Rust reference](https://github.com/BlockstreamResearch/codex32/tree/1a1c22aa895d78f2d385303feb9491d155e14cf7/reference/rust-codex32) | same repository revision | incomplete API comparison only |
| [Core Lightning implementation](https://github.com/ElementsProject/lightning/blob/5a56a976b4583a7fb6dce33e49e71e6bc12a0305/common/codex32.c) | `ElementsProject/lightning@5a56a976b4583a7fb6dce33e49e71e6bc12a0305` | legacy `cl` size, padding, examples |
| [12-word](https://secretcodex32.com/docs/checksum-bip39-12w.pdf) / [24-word](https://secretcodex32.com/docs/checksum-bip39-24w.pdf) worksheets | SHA-256 `d9ee46e8665f588aba3c82547bc7785da3d7bf5fcee53263135f5dd57bf9af5c` / `3cd40bf41facda1931b83a5bb6c112b99155cf6eaa4d8a8da065705bc45e683a` | migration profile lengths and residue fixtures |
| [BIP39](https://github.com/bitcoin/bips/blob/ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e/bip-0039.mediawiki) | `bitcoin/bips@ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e` | embedded checksum only |
| [Python `secrets`](https://docs.python.org/3/library/secrets.html) and [`random`](https://docs.python.org/3/library/random.html) | CPython 3.12–3.14 docs/source reviewed 2026-08-09 | OS entropy and `SystemRandom.sample` |
| [Koopman CRC catalogue](https://users.ece.cmu.edu/~koopman/crc/index.html) | reviewed 2026-08-09 | polynomial context, not human-error optimality |
| [Bitcoin Core 30 `createwallet`](https://bitcoincore.org/en/doc/30.0.0/rpc/wallet/createwallet/) and [`bitcoin-cli` stdin options](https://github.com/bitcoin/bitcoin/blob/master/src/bitcoin-cli.cpp) | Core 30 RPC documentation and master client source reviewed 2026-08-22 | blank watch-only wallet, encrypted restore prerequisite, one-line stdin arguments |

The frozen correction corpus at `tests/data/p70_correction_vectors.json` has
SHA-256 `6aa552b34c0bb2878d45dee2655c331d52e40e41e61cef523415d314ad9948e5`.
`tools/differential_correction.py --verify` checks it offline. The repository
does not claim that the upstream Haskell property suite was executed locally.

Generalized-HRP PR #2040 and length-restriction PR #2077 are non-authoritative
research context. The README is user documentation, never requirements evidence.
