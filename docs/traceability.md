# Requirements traceability

Source abbreviations are defined in [source-manifest.md](source-manifest.md).
Every implemented claim identifies one code owner and direct evidence.

| ID | Source requirement | Code owner | Direct tests/evidence | Status |
|---|---|---|---|---|
| R01 | B93 lexical format and header | `bech32._parse`, `Header` | official valid/invalid corpus, case/header tests | Implemented |
| R02 | common short/long checksum selection | `bech32._checksum_for_encoded_length` | PR #2258 43–47-byte boundaries | Implemented; accepted pending-standard risk |
| R03 | regular ≤93, gap 94/95, Long ≤1023 expanded symbols | same format helper, checksum specs | generic vectors and exact endpoints | Implemented; accepted pending-standard risk |
| R04 | `ms` API and imports accept every 16–64-byte seed and legal pad | `MasterSeed` | all 49 lengths, every pad value, and CLI imported-size boundaries | Implemented |
| R05 | k=0/S; k=2–9/S or ordinary index | `Header` | header abuse and B93 invalid vectors | Implemented |
| R06 | invalid checksum cannot enter domain APIs | `parse_codex32` artifact boundary | negative parser/public API tests | Implemented |
| R07 | recover from exactly k compatible distinct shares | `recover_secret` | B93 vectors 2/3, k=2–9, mismatch properties | Implemented |
| R08 | derive only a fresh ordinary share | `derive_share` | every target and existing/S rejection | Implemented |
| R09 | fresh shared S uses k uniform u5 masks | `generation._masks` and basis loop | mask invariants, recovery, no entropy injection | Implemented |
| R10 | splitting S uses S plus k−1 masks | `split_secret` | exact recovery and threshold properties | Implemented for `ms` and `cl` |
| R11 | four errors, `2e+v≤8`, eight erasures, bursts | public `correct` over `correction.py` | P70 corpus, all-profile API tests, and Hypothesis positions | Implemented |
| R12 | correction is an untrusted suggestion | CLI `correct` | stderr/nonzero and no-correction tests | Implemented |
| R13 | subsequent share input uses an immutable confirmed prefix/header | `_cli_input.read_artifacts`, correction context | suffix/full paste, retry, immutable-domain and mismatch tests | Implemented |
| R14 | bounded structural correction/timeout UX | `indel.py`, CLI `correct` | exact capture analysis, 979,110-call benchmark, structural/boundary and incomplete-search tests | Implemented in Gate 3 |
| R15 | only `ms` S enters wallet workflows | `wallet._master` | all non-`MasterSeed` types rejected | Implemented |
| R16 | electronic generation defaults to 128 bits; fresh CLI `ms` is 16/32 bytes while the API remains 16–64 | generation API and CLI `create` | API all-length tests; CLI accepted/rejected/imported-size boundaries | Implemented |
| R17 | worksheet checksum sizes and private residue correction | CLI `checksum`, residue API | ms/cl sizes, short/long and BIP39 residues | Implemented |
| R18 | identifier selection is public metadata | `generation` identifier helpers | k=0 fixture, random defaults, explicit override | Accepted divergence |
| R19 | `cl` custom ID, 32-byte payload, import and generation | `Profile.CL`, `CoreLightningSecret`, `generate_core_lightning_secret` | published examples, import evidence, generation/recovery and padding tests | Implemented |
| R20 | BIP39 fixed migration profiles | isolated `bip39.py` | 12/24 fixtures and invalid implied-S tests | Implemented migration subset |
| R21 | unknown HRPs receive no application semantics | fixed `Profile` lookup after checksum | valid generic unknown-HRP rejection | Implemented |
| R22 | generated S uses CRC padding; parsed S need not | private `_crc_pad` | frozen CRC and arbitrary parsed-pad tests | Accepted divergence |
| R23 | electronic sets use random distinct output indices | generation selector | order, uniqueness, all-31 tests | Accepted divergence |
| R24 | partial-basis completion | none | absence from API/CLI | Deliberately omitted |
| R25 | xprv, coordinator xpub, descriptors in reusable API | `wallet.py`; goal-oriented CLI tree | official xprv, frozen BIP48/descriptor and nested-command tests | Implemented |
| R26 | explicit account/timestamp, mandatory Core mode, root-xprv warning | wallet API and CLI | deterministic records, public/private separation and warning tests | Implemented |
| R27 | no arbitrary security parser for descriptors | fixed templates in `wallet.py` | module/API absence and template fixtures | Implemented by removal |
| R28 | safe typed installable reference surface | 25-name `__all__`, project script | public abuse tests, mypy, wheel/CLI checks | Implemented |
| R29 | explicit share-index selectors are bounded before copying or normalizing elements | `generation._indices` | oversized string pre-normalization regression across all three public generation APIs | Implemented from standard security scan |
| R30 | malformed untrusted boundaries fail closed under bounded work | parser, completion, interpolation, correction, and CLI adapters | frozen malformed corpus and 4,096-byte structured fuzz target | Implemented in Gate 1 |
| R31 | wallet derivation uses a reviewed, reproducible Python 3.12/3.13 dependency resolution | `_bip32.py`; pinned CLI requirement files | complete upstream suite, official vectors, 536 local tests, 6,272-record Coincurve 20/21 differential corpus, and required CI matrix | Implemented in Gate 2 |
| R32 | structural false-reconstruction bound is below `1e-5` | exact integer capture policy in `indel.py` | `gate3_capture.py`, frozen `2GO`/unsafe-result boundaries, and threat model | Implemented in Gate 3 |
| R33 | all 14 character classes, led by `2O + 2I`, meet the 48-character runtime gate without a second repair implementation | `indel.py` enumeration; `correction.py` symbol core | per-delta benchmark, family recovery tests, and ownership checks | Implemented in Gate 3 |
| R34 | immutable recovery context, lossless pruning, and global primary-rank completion | correction context and `indel._search` frontier | immutable-domain, header-budget, and tied-frontier regressions | Implemented in Gate 3 |
| R35 | all five independent whole-group classes preserve automatic four-character phase | group generator in `indel.py` | exact first/subsequent counts, spaced/unspaced equivalence, and recovery tests | Implemented in Gate 3 |

The expanded checksum rule from PR #2258 is the only pending-upstream behavior.
Its 44--46-byte compatibility exposure is explicitly accepted, has direct
boundary fixtures, and is isolated in one format-layer function. The controls
and review trigger are in the [accepted-risk register](accepted-risks.md). All
remaining production-release work and gate dependencies are recorded in the
[production-ready v1 completion plan](production-ready-v1.md).
