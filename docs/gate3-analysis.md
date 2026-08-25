# Gate 3 capture-volume and performance evidence

Gate 3 admits exactly two structural families: arbitrary character edits with
`I + O <= 4`, and independent whole-group edits with `GI + GO <= 2`. Only
classes matching the observed-to-target length difference are generated.

## Independent arithmetic

`tools/gate3_capture.py` reproduces the production policy without importing
`indel.py`. For target mutable length `N` and observed mutable length `M`, the
conservative alignment counts are:

```text
characters: C(M, I) * C(N, O)
groups:     C(observed_groups, GI) * C(target_groups, GO)
```

The exact primary volume is the alignment count times the fixed BCH decoder's
capture volume. The BCH term includes erasure completion, so omitted symbols
are not counted twice. For each length delta, every supported class no worse
than a proposed result contributes to the cumulative union bound. Runtime and
the evidence tool use the strict integer test:

```text
100_000 * cumulative_volume < 2 ** checksum_bits
```

The regular checksum has 65 bits and Long has 75. The `2GO` class has
`55 * 32**8` volume for a 48-character first share, about `1.64e-6` of the
regular checksum space before lower-ranked classes. It remains below the
approved `P_false < 1e-5` cumulative boundary. Conversely, `2O + 2I + 2S`
alone exceeds that boundary and is not returned.

`tools/gate3_capture.py --erasures N` independently includes explicit
erasures in the fixed volume. Structural classes never borrow the fixed core's
separate consecutive-erasure solver: arbitrary erasures remain bounded by
`E + 2S <= 8`.

## Frozen 48-character alignment counts

The first-share immutable prefix is `ms1`, leaving 45 mutable positions.

| Class | Alignments | Class | Alignments |
|---|---:|---|---:|
| `4O` | 148,995 | `3O + 1I` | 610,170 |
| `3O` | 14,190 | `2O` | 990 |
| `2O + 1I` | 43,560 | `1O` | 45 |
| `1O + 1I` | 2,025 | `2O + 2I` | 980,100 |
| `1I` | 46 | `1O + 2I` | 46,575 |
| `2I` | 1,081 | `1O + 3I` | 729,675 |
| `3I` | 17,296 | `4I` | 211,876 |

The group counts are 11 for `GO`, 12 for `GI`, 55 for `2GO`, 121 for
`GO + GI`, and 78 for `2GI`. With confirmed `ms1` plus threshold and
identifier, they reduce to 10, 11, 45, 100, and 66. The immutable symbols are
outside both alignment and BCH capture counts.

## Implementation evidence

`indel.py` generates only alignment views. It contains no checksum, field, or
symbol-repair algorithm. Every view reaches `_FixedCorrector` in
`correction.py`; there is no special zero-substitution repair path.

The largest class outer-loops its omission positions, allowing the fixed core
to reuse erasure state across deletion choices. Repeated observed reductions
are deduplicated before correction, and reconstructed canonical strings are
deduplicated before rank and ambiguity handling. Header pruning computes only a
lower bound on required fixed substitutions and therefore cannot remove a
repairable view.

The deterministic no-result benchmark now fails if a candidate appears or the
search is incomplete, so it cannot stop after a successful reconstruction. On
the AMD Ryzen 7 7735U reference laptop with Linux and CPython 3.13.12, final
uninstrumented verification measured:

| Measure | Result |
|---|---:|
| raw `2O + 2I` alignments | 980,100 |
| canonical alignments | 979,110 |
| duplicate reductions removed | 990 |
| fixed-core calls | 979,110 |
| alignment generation | 1.64 s |
| complete delta-zero search | 9.24 s |
| slowest nonzero delta | 8.63 s (`1O + 3I`) |

Every supported observed-length delta completed; the slowest final-code run was
9.24 seconds. `tracemalloc` is measured separately because its instrumentation
materially changes wall time. The ten-second requirement applies to complete
48-character classes. Longer registered strings retain the same bounded
families without a deadline and may take longer.

Allocation-instrumented delta-zero search peaked at 1.18 MB. The one-pass `4I`
class originally retained every reduction and peaked at 158 MB. Canonical
constant-memory deduplication reduced its measured peak to 0.38 MB; its normal
wall time was 6.07 seconds. A cache capped at 20,000 small reductions keeps the
48-character `1O + 3I` class under the runtime target without allowing memory
to scale with longer alignment spaces. Instrumented wall times are not
runtime-gate measurements.

With confirmed `ms10test` immutable context, the delta-zero class fell to
607,620 canonical alignments and completed in 5.48 seconds. Every confirmed-
context delta also completed; this is performance evidence for excluding the
program-supplied prefix from structural and BCH work, not permission to derive
that prefix from a proposed correction.

Regression coverage replaces every possible mutable start position with each
contiguous erasure length from 9 through 13 under an exact 48-character target.
The frozen vector with four extras and a 13-marker run has many distinct valid
alignment completions; the CLI now proves and reports ambiguity instead of
mislabeling it as having no valid correction.

The fixed core plus structural adapter remains below 1,500 physical lines, and
the complete installed package remains below 3,000. Normal and optimized test
suites, strict mypy, Ruff, manifest hashes, arithmetic tests, performance runs,
and the security diff scan close the local Gate 3 evidence set.
