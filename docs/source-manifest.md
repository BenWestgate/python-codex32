# Source manifest through Gate 4

Frozen on 2026-08-08. A commit-pinned URL is authoritative over its moving
branch URL. For a document without a public source revision, the SHA-256 below
identifies the HTTP response reviewed during planning. Downloaded copies were
kept outside the repository and are not vendored.

## Normative source

| Source | Frozen revision | Role |
|---|---|---|
| [BIP93](https://github.com/bitcoin/bips/blob/ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e/bip-0093.mediawiki) | `bitcoin/bips@ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e` | Normative `ms` format, checksum, recovery, sharing, correction capacity, master-seed semantics, and official vectors |
| [BIP93 checksum-boundary PR #2258](https://github.com/bitcoin/bips/pull/2258) | head `7c5251d29acc1446b1b7ed86cc1ab2327bf78271` | Accepted pending BIP93 update: checksum selection covers the expanded HRP, rejects expanded lengths 94/95, and bounds Long codex32 at 1023 symbols |

BIP93 is Draft. This implementation freezes the cited text for reproducible
review; later upstream changes require an explicit traceability review.

## Supporting functional and design sources

| Source | Frozen revision or digest | Role |
|---|---|---|
| [Wallet integration guidance](https://github.com/BlockstreamResearch/codex32/blob/1a1c22aa895d78f2d385303feb9491d155e14cf7/docs/wallets.md) | `BlockstreamResearch/codex32@1a1c22aa895d78f2d385303feb9491d155e14cf7` | Import UX, error-correction worksheets, and wallet integration guidance |
| [Illustrated booklet](https://secretcodex32.com/docs/2023-03-07--bw.pdf) | SHA-256 `0370ea863d2eae692408aeefa9b13c14283e520f45a00f7373ad933ccf418f2e` | Manual 128-bit generation, checksum, sharing, and recovery workflow |
| [secretcodex32.com](https://secretcodex32.com/) | 2026-08-08 response SHA-256 `a2ae9d231b29e15d88865fd197f384e6f1c91598fdf149a31a923404c91787d6` | Published application/profile and worksheet catalogue |
| [Correction PR #70](https://github.com/BlockstreamResearch/codex32/pull/70) | head `610cbad30258c80cd862b3773a20f8099d25e36e`; patch SHA-256 `11ef7d8a857d38b496068db4e44382825f0209ee7895d335daba122cfb1b77b8` | Provenance and differential reference for BCH correction |
| [PR #70 reverse-coordinate commentary](https://github.com/BlockstreamResearch/codex32/pull/70#issuecomment-3422320796) | GitHub issue comment `3422320796`, reviewed 2026-08-10 | Privacy-preserving worksheet design: count from the string end without supplying length |
| [Incomplete Rust reference](https://github.com/BlockstreamResearch/codex32/tree/1a1c22aa895d78f2d385303feb9491d155e14cf7/reference/rust-codex32) | `BlockstreamResearch/codex32@1a1c22aa895d78f2d385303feb9491d155e14cf7` | API-shape comparison only; incompleteness and unsafe divergences are not normative |
| [BIP388](https://github.com/bitcoin/bips/blob/ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e/bip-0388.mediawiki) | `bitcoin/bips@ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e` | Trusted wallet-policy template semantics |
| [Core Lightning `exposesecret`](https://docs.corelightning.org/reference/exposesecret) | 2026-08-08 response SHA-256 `2cda6ea83ddbe288fc7069c854915079fcac7a81296498969b84630fe7b0b334` | `cl` profile size, custom identifier, and examples; implementation repository HEAD observed as `5a56a976b4583a7fb6dce33e49e71e6bc12a0305` |
| [Core Lightning codex32 implementation](https://github.com/ElementsProject/lightning/blob/5a56a976b4583a7fb6dce33e49e71e6bc12a0305/common/codex32.c) | `ElementsProject/lightning@5a56a976b4583a7fb6dce33e49e71e6bc12a0305` | Exact 32-byte encoding, zero construction padding, and decoding treatment of discarded bits |
| [12-word BIP39 worksheet](https://secretcodex32.com/docs/checksum-bip39-12w.pdf) | SHA-256 `d9ee46e8665f588aba3c82547bc7785da3d7bf5fcee53263135f5dd57bf9af5c` | Migration-only `bip39_12w` profile length/checksum context |
| [24-word BIP39 worksheet](https://secretcodex32.com/docs/checksum-bip39-24w.pdf) | SHA-256 `3cd40bf41facda1931b83a5bb6c112b99155cf6eaa4d8a8da065705bc45e683a` | Migration-only `bip39_24w` profile length/checksum context |
| [BIP39](https://github.com/bitcoin/bips/blob/ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e/bip-0039.mediawiki) | `bitcoin/bips@ed4ffcb6a48d4dc4fdfc11cdba783c233db8c66e` | Embedded entropy-checksum calculation only; not authority to add mnemonic or wallet compatibility |
| [secretcodex32 website source](https://github.com/apoelstra/volvelle-website/tree/9096b331733d2b6bfb22ae9b545c84261e2e0c72) | `apoelstra/volvelle-website@9096b331733d2b6bfb22ae9b545c84261e2e0c72` | Reproducible source for the published worksheet catalogue and “NOT RECOMMENDED” BIP39 labels |
| [Python `random`](https://docs.python.org/3/library/random.html), [`secrets`](https://docs.python.org/3/library/secrets.html), and [`os.urandom`](https://docs.python.org/3/library/os.html#os.urandom) | Python 3 documentation reviewed 2026-08-09 | OS-backed entropy and `SystemRandom` public behavior |
| CPython `random.py` at [3.12.12](https://github.com/python/cpython/blob/v3.12.12/Lib/random.py), [3.13.12](https://github.com/python/cpython/blob/v3.13.12/Lib/random.py), and [3.14.3](https://github.com/python/cpython/blob/v3.14.3/Lib/random.py) | named CPython release tags | `SystemRandom.getrandbits` → rejection-based `_randbelow` → ordered `sample` implementation chain for supported runtimes |
| [Koopman CRC catalogue](https://users.ece.cmu.edu/~koopman/crc/index.html), [CRC-3](https://users.ece.cmu.edu/~koopman/crc/crc3.html), and [CRC-4](https://users.ece.cmu.edu/~koopman/crc/crc4.html) | pages reviewed 2026-08-09 | Polynomial catalogue context only; no human-transcription optimality claim |

These sources supplement BIP93 but cannot silently override it. Any deliberate
deviation is recorded in [divergences.md](divergences.md).

The local source-derived correction corpus is
`tests/data/p70_correction_vectors.json`, SHA-256
`6aa552b34c0bb2878d45dee2655c331d52e40e41e61cef523415d314ad9948e5`.
Its deterministic cases instantiate the error/erasure distributions and
position rules in PR #70 at the frozen head. The review environment did not
contain GHC, Cabal, Nix, or Docker, so the repository does not claim that the
Haskell property suite was executed locally. The offline verifier combines
this source-derived evidence with official checksum vectors and mandatory
normal-parser validation rather than adding a duplicate polymod oracle.

## Non-authoritative context

| Source | Frozen revision | Treatment |
|---|---|---|
| [Generalized HRP draft PR #2040](https://github.com/bitcoin/bips/pull/2040) | head `afd70b7063d27a8e10923060d07c35b20622e7dc` | Context only. Unknown HRPs remain rejected. |
| [Length-restriction PR #2077](https://github.com/bitcoin/bips/pull/2077) | head `c286c2c5a7385113d33b3dd8cbda806bd371523f` | Closed/unmerged research context only. It does not restrict BIP93's 16–64-byte range. |
| Repository `README.md` | dirty working-tree version based on local `6b02914047c2eb3771f61faa41ba5241faeac6d2` | WIP context only; never requirements evidence. |

## Local assessment snapshot

The assessed base commit is
`6b02914047c2eb3771f61faa41ba5241faeac6d2`. The assessment intentionally
includes the pre-existing tracked and untracked working-tree files listed in
[baseline.md](baseline.md). Later gates must preserve unrelated user changes
and update this manifest when source revisions change.

## Precedence and ambiguity rule

1. Apply BIP93's normative language to the `ms` profile.
2. Apply a registered application's own frozen rules only inside that profile.
3. Apply supporting UX guidance only where it does not weaken a normative
   invariant.
4. Record a conflict or ambiguity before choosing behavior. Do not infer
   compliance from names, apparent intent, or behavior in an incomplete
   reference implementation.
