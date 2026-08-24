# Gate 3 structural-correction threat model

## Overview

Gate 3 may add bounded insertion and deletion search around the existing
fixed-length BCH decoder. The feature handles protected backup text supplied by
an offline operator. It produces correction suggestions, never authenticated
wallet input. The human must compare any suggestion with the written backup.

This model supplements the repository-wide properties in `SECURITY.md`. It
does not place structural correction in release scope by itself. That scope
change occurs only after the mathematical, performance, size, and review gates
pass.

## Threat model, trust boundaries, and assumptions

The protected codex32 text and any presentation spaces are untrusted input.
The selected profile, expected canonical length, optional expected header, and
excluded share indices are operator-controlled constraints. For recovery of a
set, a previously validated first artifact may supply the expected length.

The structural adapter may propose alignments and pass fixed-length candidates
to `correction.py`. It must not implement checksum arithmetic, field arithmetic,
BCH decoding, parsing, or profile rules. Every result crosses the ordinary
`parse_codex32` validation boundary before it becomes a `CorrectionCandidate`.
The resulting artifact remains an untrusted suggestion and cannot flow directly
into sharing, recovery, or wallet APIs.

The HRP and separator are immutable. Group structure means exactly the
four-character grouping emitted by the CLI. Presentation spaces may constrain
alignment generation but never alter checksum semantics.

The public API completes every supported rank class without a deadline. The
simple CLI checks its deadline only between classes, finishes any class already
started, and accepts a result only after every class that could rank as well has
completed. Faster machines may search more classes. An incomplete search never
produces an accepted candidate.

## Attack surface, mitigations, and attacker stories

### False reconstruction

An incorrect checksum-valid reconstruction could rank before or alongside the
intended text. Every supported class therefore needs an exact, conservative
decoder-capture volume. The cumulative union bound for an incorrect result at
equal or better rank must remain below `1e-4`. The runtime compares integer
volumes; it does not rank with floating-point estimates.

Hamming weight is a secondary transcription hint. CRC padding for `ms` secrets
and fingerprint-identifier agreement for unshared master seeds are lower
priority presentation hints. Neither hint validates, removes, or resolves an
otherwise ambiguous candidate.

### Ambiguity suppression

Different alignments can reach the same final text, while other alignments can
reach distinct texts. Paths are deduplicated by final canonical string. The CLI
returns a suggestion only when exactly one best reconstruction remains. It
reports ambiguity instead of selecting by enumeration order, CRC, fingerprint,
or lexical order.

### Resource exhaustion

Malformed or adversarial text could request a combinatorial search. Input is
bounded before candidate generation. Each supported class has a static
hypothesis count and memory bound. Candidate generation streams rather than
materializing the search space. The CLI starts another complete class only
while its deadline permits; the API searches only the frozen finite envelope.

### Boundary and context confusion

An attacker or mistaken operator could try to change the HRP, separator,
profile, target length, set header, or used share index during correction.
Structural edits are limited to the data/checksum body. Context constraints are
checked before ranking, and final artifacts pass the ordinary registered-profile
parser. A valid first artifact may constrain subsequent set entries but damaged
text can never establish its own trusted context.

### Candidate promotion

CLI prompts, logs, or API composition could accidentally treat a suggestion as
validated intent. Suggestions remain immutable ordinary artifacts paired with
their edits and rank evidence, but callers must explicitly choose to reuse the
artifact. The simple CLI writes suggestions and warnings to stderr, returns a
nonzero status, and emits no machine-consumable protected output.

## Severity calibration

- **Critical:** an unchecked or ambiguous reconstruction automatically reaches
  secret recovery, private-key derivation, or wallet output; or correction leaks
  protected text through an unintended public channel.
- **High:** the implementation can silently select an incorrect candidate
  outside the frozen probability envelope, or mutate the HRP/separator and pass
  the result as the requested profile.
- **Medium:** bounded input can force work or memory beyond the published
  envelope; a timeout accepts an incomplete rank layer; or grouping/context
  constraints are inconsistently applied.
- **Low:** deterministic presentation order or diagnostics differ without
  hiding candidates, changing acceptance, leaking protected text, or exceeding
  the resource bound.

Gate 3 findings are mitigated and retested. A medium-or-higher finding does not
by itself cut the feature. If mitigation eventually requires removing an
existing feature or important public API, implementation stops for explicit
human approval of a separate removal plan.
