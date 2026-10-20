# Alignment correction benchmark evidence

Informational only: these timings help set correction limits on slower devices. They are not timing guarantees.

Measured 2026-09-10 with one shared **inclusive capture-mass ceiling `<=1`**.

Host: **AMD Ryzen 7 7735U with Radeon Graphics**, Python **3.13.12**, `Linux-7.0.10+deb14-amd64-x86_64-with-glibc2.42`. Cached syndrome tables persist within each process. Timed calls retain the ten-second deadline.

## Public required-depth measurements

All 1156 cases requested `A<=2` and `G<=2`: 1152 completed and none returned candidates. Maximum elapsed time was **10.001 seconds**; maximum admitted mass was **0.992777219241**.

The exhaustive sweep stopped after 1120 of 1980 planned cases because it was impractically slow on this host. The additional 36 representative cases cover every existing public profile length, known/unknown targets, and frozen/unfrozen five-character headers at offset zero with no explicit erasures. The partial matrix additionally exercises offsets -8/-4/-3/-2/-1/0/1/2/3/4/8 and erasures 0/1/2/4/8. Inputs use valid header syntax and deterministic random remaining symbols. Some offsets have no reachable required layer. No-candidate status is recorded rather than assumed.

| Profile | Displayed D | Full body B | Mutable M (frozen / unfrozen) | Completed | Maximum seconds |
|---|---:|---:|---:|---:|---:|
| ms | 48 | 45 | 40 / 45 | 224/224 | 2.288 |
| ms | 54 | 51 | 46 / 51 | 224/224 | 2.768 |
| ms | 61 | 58 | 53 / 58 | 224/224 | 3.860 |
| ms | 67 | 64 | 59 / 64 | 224/224 | 4.616 |
| ms | 74 | 71 | 66 / 71 | 224/224 | 6.005 |
| ms | 127 | 124 | 119 / 124 | 20/24 | 10.001 |
| cl | 74 | 71 | 66 / 71 | 4/4 | 5.589 |
| bip39_12w | 56 | 46 | 41 / 46 | 4/4 | 2.158 |
| bip39_24w | 82 | 72 | 67 / 72 | 4/4 | 5.821 |

The implementation requires `A<=2` / `G<=2` before surfacing suggestions. Required-phase interruption suppresses suggestions. Character depths 3/4 remain best effort.

## Deeper public search

0/16 depth-3/4 probes completed within the deadline at displayed ms lengths 48 and 127, with both target-knowledge and header-freezing states. No deeper cutoff is promoted. Long-profile probes may expire in the required phase before deeper work begins.

## Coordinates and synthetic kernels

`B = D - len(hrp + "1")`; checksum selection uses `X = len(bech32_hrp_expand(hrp)) + B`. Mutable length excludes the frozen header, while reverse indices and the syndrome retain full-body coordinates. Public profile validation is unchanged.

Synthetic kernels use **body lengths** 40/66/93/127/1015/1023 with explicit short/long period selection. They need not form valid public application strings and never promote public cutoffs. Character depths 2/3/4 sample 32 hypotheses per structural class. Group depth 2 completes the structural-generation and incremental-syndrome sphere; this is distinct from complete BCH decoding of that sphere.

| Body | Target known | Complete group hypotheses | Generation + syndrome seconds |
|---:|:---:|---:|---:|
| 40 | yes | 415 | 0.002 |
| 40 | no | 1,173 | 0.004 |
| 66 | yes | 1,353 | 0.005 |
| 66 | no | 3,707 | 0.084 |
| 93 | yes | 2,830 | 0.010 |
| 93 | no | 7,662 | 0.099 |
| 127 | yes | 5,178 | 0.017 |
| 127 | no | 13,922 | 0.117 |
| 1015 | yes | 351,165 | 5.200 |
| 1015 | no | 928,007 | 12.486 |
| 1023 | yes | 356,746 | 5.020 |
| 1023 | no | 648,466 | 8.897 |

The `--kernel` output records generation/syndrome throughput, BCH throughput for E=0/1/2/4/8 and S=0..4 wherever E+2S<=8, root scans of degrees 1..4, sampled full-result dedup cost, retained allocation counts and traced peaks. BCH microcases exercise successful locators; public timings primarily exercise failed hypotheses. Allocations cover sampled batches, not a retained complete sphere.

Separate public tracemalloc runs had a maximum peak of 116,160 bytes. Tracing results are neither timing evidence nor process RSS.

## Implementation and artifacts

Incremental syndromes compose small piece-table segments from shifted prefixes. Full candidate bodies materialize only after BCH survival. Repeated two-erasure product-table construction was removed after profiling identified it as a dominant cost; changing erasure locations use direct field multiplication. Constant locators avoid unnecessary root scans. Search follows admitted capture-volume layers. No MITM is used.

The raw kernel JSON from these runs is in git history at commit `753cf61`. Reproduce with:

```sh
.venv/bin/python -m tools.alignment_benchmark --public --depths 2
.venv/bin/python -m tools.alignment_benchmark --public --lengths 48 127 --depths 3 4 --deltas 0 --erasures 0
.venv/bin/python -m tools.alignment_benchmark --kernel --samples 32 --complete-groups
.venv/bin/python -m tools.alignment_benchmark --public --lengths 48 --depths 2 --deltas 0 --erasures 0 --memory
```

Commands emit JSON Lines with a host header. Full 13/15 consecutive-erasure completion at mass exactly 1 is additionally covered by API tests.
