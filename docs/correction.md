# Fixed-length BCH correction

The current implementation provides only the algebraic, fixed-length correction
boundary. A bounded structural adapter is a cuttable pre-v1 gate in
[the production-ready v1 plan](production-ready-v1.md). If it cannot satisfy
the plan's completeness, performance, size, and audit requirements, v1 remains
fixed-length-only and structural correction moves to v1.1.

## Public full-string API

`correct(CorrectionContext(...), damaged_text)` accepts every fixed registered
profile. Its context may constrain the complete canonical length, the
five-symbol threshold-plus-identifier header, and ordinary share indices that
are already in use. The HRP and separator are immutable. A differing expected
length receives no structural search in the current fixed-length
implementation.

The function returns an immutable tuple of `CorrectionCandidate` records in
deterministic rank order. A valid unchanged string returns one candidate with
no edits; no valid correction returns `()`. Malformed context raises
`InvalidCorrectionInput`. Every candidate contains an ordinary parsed `Share`
or `Secret`; the decoder never exposes a checksum-only result.

Fixed correction emits only `substitution` and `erasure` edits. Insertions,
deletions, and transpositions are reserved record kinds for the cuttable
structural gate. Edit coordinates are zero-based from the end of the
data/checksum body. `observed` and `replacement` preserve string case.
`estimated_search_bits` is zero for fixed decoding, `erasures_filled` and
`addend_hamming_weight` expose the deterministic secondary ranking inputs, and
`crc_padding_match` is a boolean only for an `ms` S candidate. It is `None` for
shares and other profiles and never affects validity.

The API completes its fixed search without a deadline or provisional result.
All four profiles are available to API callers. The CLI deliberately offers
full-string correction only for `ms` and `cl`.

## Candidate structural-correction gate

A future `indel.py` may search bounded insertion and deletion candidates, but
must remain separate from the fixed-length BCH core. Its primary ordering must
come from an evidence-backed transcription-error model and estimated search
cost, not from checksum-validity alone.

The structural layer distinguishes extra text from fixed-length errors. An
erroneous four-character group remains BCH damage. A duplicated or inserted
group is extra text removed before BCH, while an omitted group is restored as
four erasures.

If the gate ships, its minimum envelope is:

- at least two arbitrary individual omissions and insertions;
- at least two adjacent-character transpositions;
- two arbitrary omitted, group-aligned four-character groups, represented by
  eight erasures;
- three omitted group-aligned groups when contiguous, represented by twelve
  consecutive erasures;
- four arbitrary inserted four-character groups, including candidates that
  still require BCH correction after deletion; and
- up to four exact adjacent duplicated groups through a dedicated fast path.

General mixed damage retains the BCH guarantee
`2 * substitutions + erasures <= 8`. The consecutive-erasure path instead
guarantees up to 13 regular-checksum or 15 Long-checksum erasures. Eight
insertion-only groups were searchable in an initial development benchmark, but
that unlikely human-error mode is not a required v1 contract. Broader coverage
may be retained only if it adds little code and passes the complete platform
budget.

Rank complete candidates by an estimated negative log likelihood of the
observed transcription. The model must account for the structural operation,
estimated search-space bits, and the number of unknown erasures filled. Among
otherwise comparable candidates, prefer the lower sum of
`addend.value.bit_count()` over known-character substitutions. This uses the
Bech32 alphabet's bit ordering as a small confusion prior without claiming that
Hamming distance is a measured human-error probability.

For an `ms` S candidate with generation padding, a CRC-padding match may be used
only as a secondary ordering hint after structural evidence. A match must never
make a candidate valid, prune the search, establish completeness, or remove a
nonmatching candidate from API results. Parsed and hand-generated BIP93 secrets
may legally use arbitrary padding, and ordinary shares have no CRC semantics.
The candidate record should expose whether this hint was applicable and whether
it matched so callers can audit the ordering.

Known profile, length, immutable header, and unused-index information constrain
candidate construction before ranking; they are not score bonuses. The complete
API result remains deterministic and retains every candidate in rank order,
including non-CRC candidates and exact ties.

Before selecting a ranking formula, test it against a frozen, independently
labelled corpus of realistic transcription damage. Compare at least omitted and
duplicated characters or groups, transpositions, repeated adjacent characters,
visual substitutions, case mistakes, explicit erasures, and combinations of
these errors. Record top-1 and top-k recovery rates, ties, search work, and
timeouts; do not tune and evaluate on the same examples. Ranking tests must also
prove that lower addend Hamming weight wins only after stronger structural
evidence, a CRC match cannot outrank a structurally better candidate, and a CRC
mismatch never removes an otherwise valid candidate.

## Coordinates and trust boundary

All algebra uses PR #70's native zero-based reverse coordinates: index 0 is the
last data/checksum character. This convention is never converted using an HRP,
separator, payload length, or complete-string length.

Full-string correction requires a `CorrectionContext` with an exact registered
profile. The adapter accepts that HRP and its separator as an immutable prefix. Printable
non-Bech32 characters after that boundary are erasures, including a later `1`.
The format layer owns checksum selection. A correction outside the visible body is
rejected, and every candidate must pass the ordinary `parse_codex32` boundary.
This means a BIP39 S must also satisfy its embedded SHA-256 checksum and outer
padding, while an ordinary BIP39 share retains mask semantics.

Corrections are checksum-valid suggestions, not proof of the intended wallet.
They must be compared with the physical backup before use.

The CLI infers `ms` or `cl` only from the literal undamaged prefix of a complete
string. It does not expose a profile option, guess another prefix, or correct the
HRP. BIP39 full-string correction remains available to API code but is not
offered by the CLI.

## Worksheet residue API

`correct_worksheet_residue` accepts only the final worksheet residue:

- 13 characters select regular codex32, whose reverse-coordinate period is
  93 symbols;
- 15 characters select Long codex32, whose period is 1023 symbols.

The API receives no profile, HRP, or string length. It therefore cannot tell
whether the residue represents an `ms`, CL, BIP39, or other application of the
same codex32 checksum. It also cannot decide whether a returned period-relative
position lies outside an undisclosed shortened string. That decision belongs to
the person or application holding the string.

`()` means the residue is already correct. A sorted tuple contains the unique
reverse-indexed addends. `None` means no unique correction was found. The CLI
displays positions as one-based and performs only `position - 1` conversion.

## Algebra-to-code map

| P70 concept | Code owner |
|---|---|
| GF(32) scalar arithmetic shared with BIP93 interpolation | `gf32.py` |
| Packed quadratic extension GF(1024) | `_gf1024*` helpers |
| Minimal polynomials and generator construction | `_minimal_poly`, `_monic_mul`, `_make_spec` |
| Short/Long target symbols | `_SHORT_SPEC`, `_LONG_SPEC` explicit `secretshare32*` constants |
| Residue modulo the checksum generator | `_residue`, importing `_hrp_expand` |
| Syndrome recurrence and locator synthesis | `_synthesize_rec`, `_locator_poly` |
| Error-plus-erasure BCH decoding | `_bch_error_corrections` |
| Unique arbitrary/consecutive erasure fallback | `_solve_linear`, `_linear_error_corrections` |
| Root-subgroup and final target verification | `_bch_error_corrections`, `_corrections_reach_target` |
| Public registered-profile adapter | `correct`, over `_correct_fixed` |
| Application-agnostic residue adapter | `correct_worksheet_residue` |

The target constants are checked against the imported checksum constants. No
second polymod implementation exists in tests: official codec vectors already
anchor checksum arithmetic, the frozen corpus anchors correction outcomes, and
full candidates are reparsed through the production codec.

## Guaranteed capacity

For both checksum variants the BCH path guarantees every nonzero distribution
with `2 * errors + erasures <= 8`, including four substitutions and eight
arbitrary erasures. The linear fallback additionally covers every legal start
for 13 consecutive regular-checksum erasures and 15 consecutive Long-checksum
erasures. Other uniquely solvable erasure patterns may succeed but are not a
guarantee.

Lexical, prefix, profile-shape, algebra, visible-body, and semantic-reparse
failures all collapse to no public candidate. This avoids presenting one
internal decoder stage as a diagnosis of the physical transcription error.

Decoder success is fail-closed twice: every synthesized locator root must map
to a legal reverse position in the selected checksum period, and the complete
set of proposed addends must algebraically transform the residue to the exact
target. This prevents an out-of-subgroup locator from being silently truncated
into a plausible partial correction.

The two checks above are deliberate hardening beyond literal PR #70 behavior.
The direct P70 routine checked the number of roots in GF(1024), but not whether
every regular-code root belonged to the shortened code's order-93 position
subgroup. This implementation adds that check explicitly and the frozen
regression corpus exercises it.

## Evidence and provenance

The implementation carries the MIT notice from Blockstream's PR #70 head
`610cbad30258c80cd862b3773a20f8099d25e36e`. The frozen patch digest is
`11ef7d8a857d38b496068db4e44382825f0209ee7895d335daba122cfb1b77b8`.
The source-derived offline corpus and its limitations are recorded in
`source-manifest.md`; `tools/differential_correction.py --verify` checks it
without network or Haskell dependencies.

The frozen malformed corpus exercises parsing, checksum completion,
interpolation, correction, and CLI tokenization. The dependency-free structured
targets at `tools/fuzz_untrusted_boundaries.py` and
`tools/fuzz_correction_context.py` bound each input to 4,096 bytes;
`tests/test_fuzz_targets.py` supplies deterministic boundary seeds and
Hypothesis smoke campaigns.
