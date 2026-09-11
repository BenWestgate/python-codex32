# Alignment correction benchmark evidence

Measured 2026-09-10 with one shared **inclusive capture-mass ceiling `<=1`**.

Host: **AMD Ryzen 7 7735U with Radeon Graphics**, Python **3.13.12**, `Linux-7.0.10+deb14-amd64-x86_64-with-glibc2.42`.

## Execution conditions and limits

The host rebooted repeatedly during this task. Accessible user journals did not establish the cause; kernel journals and persistent crash records required administrator access. Remaining cases resumed under first a 50%, then a 25% single-core CPU quota, 1 GiB memory limit, low priority and pauses between cases. The final run also waits for a CPU sensor reading at or below 75°C before each case, stopping if cooling takes over one minute. Capped rows are marked and excluded from promotion evidence. These precautions are not a diagnosed hardware fix. **No public timing guarantee is promoted from this interrupted, mixed-condition run.**

Only complete JSON records were preserved across restarts. Cached syndrome tables persist within each process; restarted processes rebuild them. Timed calls retain the ten-second deadline. Cooldown pauses occur outside the timed call.

## Public required-depth measurements

All 1156 cases requested `A<=2` and `G<=2`: 1152 completed, 1156 returned no candidates, 284 were capped, and 872 uncapped cases completed without candidates below eight seconds. Maximum elapsed time was **10.001 seconds**; maximum admitted mass was **0.992777219241**.

The exhaustive sweep stopped after 1120 of 1980 planned cases because the temperature gate made it impractically slow. The additional 36 representative cases cover every existing public profile length, known/unknown targets, and frozen/unfrozen five-character headers at offset zero with no explicit erasures. The partial matrix additionally exercises offsets -8/-4/-3/-2/-1/0/1/2/3/4/8 and erasures 0/1/2/4/8. The tool retains the full matrix for a stable host. Inputs use valid header syntax and deterministic random remaining symbols. Some offsets have no reachable required layer. No-candidate status is recorded rather than assumed.

| Profile | Displayed D | Full body B | Mutable M (frozen / unfrozen) | Completed | Capped | Maximum seconds |
|---|---:|---:|---:|---:|---:|---:|
| ms | 48 | 45 | 40 / 45 | 224/224 | 4 | 2.288 |
| ms | 54 | 51 | 46 / 51 | 224/224 | 4 | 2.768 |
| ms | 61 | 58 | 53 / 58 | 224/224 | 4 | 3.860 |
| ms | 67 | 64 | 59 / 64 | 224/224 | 12 | 4.616 |
| ms | 74 | 71 | 66 / 71 | 224/224 | 224 | 6.005 |
| ms | 127 | 124 | 119 / 124 | 20/24 | 24 | 10.001 |
| cl | 74 | 71 | 66 / 71 | 4/4 | 4 | 5.589 |
| bip39_12w | 56 | 46 | 41 / 46 | 4/4 | 4 | 2.158 |
| bip39_24w | 82 | 72 | 67 / 72 | 4/4 | 4 | 5.821 |

The implementation requires `A<=2` / `G<=2` before surfacing suggestions. Required-phase interruption suppresses suggestions. Character depths 3/4 remain best effort. Runtime under a CPU quota must not be extrapolated into an uncapped guarantee.

## Deeper public search

0/16 depth-3/4 probes completed within the deadline at displayed ms lengths 48 and 127, with both target-knowledge and header-freezing states. No deeper cutoff is promoted. Under the CPU quota, long-profile probes may expire in the required phase before deeper work begins.

## Coordinates and synthetic kernels

`B = D - len(hrp + "1")`; checksum selection uses `X = len(bech32_hrp_expand(hrp)) + B`. Mutable length excludes the frozen header, while reverse indices and the syndrome retain full-body coordinates. The CSV records all eligible target body lengths and the selected checksum size. Public profile validation is unchanged.

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

The JSON records generation/syndrome throughput, BCH throughput for E=0/1/2/4/8 and S=0..4 wherever E+2S<=8, root scans of degrees 1..4, sampled full-result dedup cost, retained allocation counts and traced peaks. BCH microcases exercise successful locators; public timings primarily exercise failed hypotheses. Allocations cover sampled batches, not a retained complete sphere.

Separate public tracemalloc runs had a maximum peak of 116,160 bytes. Tracing results are neither timing evidence nor process RSS.

## Implementation and artifacts

Incremental syndromes compose small piece-table segments from shifted prefixes. Full candidate bodies materialize only after BCH survival. Repeated two-erasure product-table construction was removed after profiling identified it as a dominant cost; changing erasure locations use direct field multiplication. Constant locators avoid unnecessary root scans. Search follows admitted capture-volume layers. No MITM is used.

- [Public and deeper per-case results](alignment-public-benchmarks.csv).
- [Kernel, memory and measured runtime source hashes](alignment-kernel-benchmarks.json).

```sh
.venv/bin/python -m tools.alignment_benchmark --public --depths 2
.venv/bin/python -m tools.alignment_benchmark --public --lengths 48 127 --depths 3 4 --deltas 0 --erasures 0
.venv/bin/python -m tools.alignment_benchmark --kernel --samples 32 --complete-groups
.venv/bin/python -m tools.alignment_benchmark --public --lengths 48 --depths 2 --deltas 0 --erasures 0 --memory
```

Commands emit JSON Lines with a host header. Capped portions of these recorded runs used systemd `CPUQuota=50%` or `CPUQuota=25%` as recorded, `MemoryMax=1G`, `CPUWeight=10`, and `nice -n 10`; each case was followed by an untimed pause equal to its elapsed time, capped at ten seconds. These settings are execution precautions, not correction policy. Full 13/15 consecutive-erasure completion at mass exactly 1 is additionally covered by API tests.

## Validation

After failure cleanup, normal and optimized full pytest runs each pass **714 tests**. Both runs used a 25% single-core CPU quota, 1 GiB memory limit, cooling pauses, and the 75°C temperature gate. The CLI tests now observe prefills at the editable-input boundary and expect the current diagnostic text. The approved package size budget is **4,500** nonblank/noncomment lines, retaining recursive counting; the formatted package measures **4,088**.

Ruff lint and formatting, mypy (19 source files), all 57 frozen PR #70 correction cases, all 768 wallet differential records, and staged whitespace checks pass. No public timing cutoff is promoted by this validation.

The kernel artifact preserves the measured source hashes in `source_sha256` and records the subsequently formatted files in `post_cleanup_source_sha256`. The failure cleanup changed test expectations, formatting, and the approved package size budget; it did not change runtime semantics.
