# Gate 3 structural-correction threat model

## Scope and boundaries

Gate 3 handles protected backup text supplied by an offline operator. It emits
untrusted correction suggestions, never authenticated wallet input. The human
must compare any suggestion with the written backup.

The damaged text and presentation spaces are untrusted. Profile, target length,
immutable prefix, and excluded share indices are program-controlled context.
The first immutable prefix is the HRP plus separator. An interactive recovery
may extend it with threshold and identifier only after a share has passed normal
validation and the operator confirms it. Suggested corrections cannot establish
or mutate context.

The immutable prefix is outside the correction domain: no insertion, deletion,
erasure, substitution, or structural shift crosses its boundary. Its symbols do
not enter alignment or capture counts. Every final result crosses the ordinary
`parse_codex32` boundary.

The ownership invariant is: `indel.py` enumerates alignments;
`correction.py` performs all symbol repair. The structural adapter contains no
checksum, finite-field, or substitution solver.

## False reconstruction

An incorrect checksum-valid reconstruction could rank before the intended text.
For each compatible length delta, the implementation conservatively sums all
supported structural/BCH classes whose primary capture volume is no worse than
the candidate. A structural-ranked result is eligible only when its cumulative
probability bound is strictly below `1e-5`. Integer arithmetic prevents
rounding at the boundary.

There are exactly two non-mixed structural families: up to four arbitrary
character omissions/insertions, or up to two whole four-character group
omissions/insertions. The group phase follows canonical output grouping and is
valid because group-only length changes preserve that phase. Spaces themselves
are never trusted as evidence. Character search does not use group boundaries.

Explicit unknown characters may be retained as fixed erasures or deleted as
structural extras. Omitted values appear only in fixed-core capture volume, not
again in the structural multiplier. Higher-substitution results naturally rank
worse; there is no hand-maintained substitution rejection table.

Exact-length input with more than eight consecutive explicit erasures is a
separate fixed-core case, not a structural class. Regular Codex32 retains its
13-consecutive-erasure guarantee and Long retains 15. That path returns the
unique fixed reconstruction without enumerating insertion/deletion alignments;
more than eight nonconsecutive arbitrary erasures remain outside Gate 3. This
fixed, known-location completion is explicitly exempt from the structural
capture envelope and remains an untrusted suggestion rather than authenticated
recovery input.

An above-eight burst combined with extra-character alignment is not silently
promoted into that guarantee. The CLI may stop once two distinct parsed,
context-allowed completions prove ambiguity, because no further search can make
the input unique. Neither witness is displayed as a correction suggestion.

Bech32 addend Hamming weight is a secondary transcription hint. Generation CRC
and the fingerprint identifier of an unshared seed are still lower-priority CLI
hints. None enlarges the capture envelope or makes a worse primary rank win.

## Ambiguity and early stopping

Equivalent alignment views are deduplicated before BCH work. Different paths
that reconstruct the same final canonical string count once. The public API
retains every reconstruction at the best primary rank.

A found candidate does not justify stopping. The search exhausts every class
whose theoretical floor can tie or beat the current best. It stops early only
when every unsearched class has a strictly worse floor. The CLI applies Hamming,
CRC, and fingerprint refinements in that order; if a tie remains, it reports
ambiguity rather than selecting by enumeration or lexical order.

## Resource exhaustion

Input length is bounded before enumeration. Each admitted class has a finite
combinatorial count, generators stream their views, and repeated reductions use
a canonical earliest embedding plus a small capped cache. Memory therefore does
not scale with the million-view search space. The primary 48-character
benchmark is `2O + 2I`, approximately one million alignments.

The CLI gives 48-character correction a ten-second reference target and
finishes the class it starts. If another potentially competitive class remains
when the deadline is reached, it rejects all provisional results. Longer valid
profiles use the same finite families without a deadline and remain normally
interruptible.

Multiprocessing is intentionally absent. CPython threads do not accelerate the
CPU-bound loop, while worker processes replicate secret-bearing buffers and BCH
tables, complicate deterministic frontier coordination, and add cross-platform
failure modes. The measured single-process generic pipeline meets the reference
target without those costs.

## Context and candidate promotion

Immutable text is supplied by the program, never inferred from damaged input.
Outside that prefix, profile-header pruning is a lossless lower bound: a known
mismatch consumes available substitution capacity, while an erasure remains
repairable. Already-used share indices are checked again on parsed artifacts.

Suggestions remain immutable artifacts paired with edits and rank evidence, but
callers must explicitly choose to reuse them. The simple CLI writes suggestions
and warnings to stderr, returns nonzero, and emits no machine-consumable secret
on stdout.

## Severity calibration

- **Critical:** an unchecked or ambiguous result reaches recovery, derivation,
  or wallet output; or protected text leaks through an unintended channel.
- **High:** a result outside the approved capture envelope is silently selected,
  or structural correction changes immutable text.
- **Medium:** bounded input exceeds the documented work/memory envelope, a
  provisional frontier is accepted, or context/group phase is inconsistent.
- **Low:** deterministic diagnostics differ without hiding candidates, leaking
  text, or changing accepted results.

Gate 3 findings are mitigated and retested. If a necessary fix would remove an
existing important API or user feature, implementation stops for explicit human
approval of a separate removal plan.
