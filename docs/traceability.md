# Requirements traceability

Source abbreviations are defined in [source-manifest.md](source-manifest.md).
Every implemented claim identifies one code owner and direct evidence.

| ID | Source requirement | Code owner | Direct tests/evidence | Status |
|---|---|---|---|---|
| R01 | B93 lexical format and header | `bech32._parse`, `Header` | official valid/invalid corpus, case/header tests | Implemented |
| R02 | common short/long checksum selection | `bech32._checksum_for_encoded_length` | PR #2258 43–47-byte boundaries | Implemented pending upstream PR |
| R03 | regular ≤93, gap 94/95, Long ≤1023 expanded symbols | same format helper, checksum specs | generic vectors and exact endpoints | Implemented pending upstream PR |
| R04 | `ms` accepts every 16–64-byte seed and legal pad | `MasterSeed` | all 49 lengths and every pad value | Implemented |
| R05 | k=0/S; k=2–9/S or ordinary index | `Header` | header abuse and B93 invalid vectors | Implemented |
| R06 | invalid checksum cannot enter domain APIs | `parse_codex32` artifact boundary | negative parser/public API tests | Implemented |
| R07 | recover from exactly k compatible distinct shares | `recover_secret` | B93 vectors 2/3, k=2–9, mismatch properties | Implemented |
| R08 | derive only a fresh ordinary share | `derive_share` | every target and existing/S rejection | Implemented |
| R09 | fresh shared S uses k uniform u5 masks | `generation._masks` and basis loop | mask invariants, recovery, no entropy injection | Implemented |
| R10 | splitting S uses S plus k−1 masks | `split_secret` | exact recovery and threshold properties | Implemented for `ms` |
| R11 | four errors, `2e+v≤8`, eight erasures, bursts | `correction.py` | P70 corpus and Hypothesis positions | Implemented fixed-length only |
| R12 | correction is an untrusted suggestion | CLI `correct` | stderr/nonzero and no-correction tests | Implemented |
| R13 | subsequent share input uses known prefix/header | `_cli_input.read_artifacts`, BIP93 prefix validators | suffix/full paste, retry, duplicate/mismatch and stream tests | Implemented |
| R14 | structural correction/timeout UX | none | explicit scope assertions/docs | Deliberately omitted |
| R15 | only `ms` S enters wallet workflows | `wallet._master` | all non-`MasterSeed` types rejected | Implemented |
| R16 | electronic generation defaults to 128 bits | generation API and CLI `create` | default and complete creation matrix | Implemented |
| R17 | worksheet checksum sizes and private residue correction | CLI `checksum`, residue API | ms/cl sizes, short/long and BIP39 residues | Implemented |
| R18 | identifier selection is explicit public metadata | `generation` identifier helpers | k=0 fixture, shared random, raw/re-share rules | Accepted divergence |
| R19 | legacy `cl` custom ID and 32-byte payload | `Profile.CL`, `CoreLightningSecret` | three published examples and length/pad tests | Implemented; no generation |
| R20 | BIP39 fixed migration profiles | isolated `bip39.py` | 12/24 fixtures and invalid implied-S tests | Implemented migration subset |
| R21 | unknown HRPs receive no application semantics | fixed `Profile` lookup after checksum | valid generic unknown-HRP rejection | Implemented |
| R22 | generated S uses CRC padding; parsed S need not | private `_crc_pad` | frozen CRC and arbitrary parsed-pad tests | Accepted divergence |
| R23 | electronic sets use random distinct output indices | generation selector | order, uniqueness, all-31 tests | Accepted divergence |
| R24 | partial-basis completion | none | absence from API/CLI | Deliberately omitted |
| R25 | xprv, coordinator xpub, descriptors in reusable API | `wallet.py`; goal-oriented CLI tree | official xprv, frozen BIP48/descriptor and nested-command tests | Implemented |
| R26 | explicit account/timestamp, mandatory Core mode, root-xprv warning | wallet API and CLI | deterministic records, public/private separation and warning tests | Implemented |
| R27 | no arbitrary security parser for descriptors | fixed templates in `wallet.py` | module/API absence and template fixtures | Implemented by removal |
| R28 | safe typed installable reference surface | 19-name `__all__`, project script | public abuse tests, mypy, wheel/CLI checks | Implemented |

The expanded checksum rule from PR #2258 is the only pending-upstream behavior.
It has direct boundary fixtures and is isolated in one format-layer function.
