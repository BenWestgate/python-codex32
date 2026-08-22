# Fixed-length BCH correction

V1 implements only the algebraic, fixed-length correction boundary. Structural
insertion/deletion search, deadlines, ranking, and concurrency are out of scope.

## Coordinates and trust boundary

All algebra uses PR #70's native zero-based reverse coordinates: index 0 is the
last data/checksum character. This convention is never converted using an HRP,
separator, payload length, or complete-string length.

Full-string correction requires a `suspected_profile`. The adapter accepts the
exact registered HRP and its separator as an immutable prefix. Printable
non-Bech32 characters after that boundary are erasures, including a later `1`.
The format layer owns checksum selection. A correction outside the visible body is
rejected, and every candidate must pass the ordinary `parse_codex32` boundary.
This means a BIP39 S must also satisfy its embedded SHA-256 checksum and outer
padding, while an ordinary BIP39 share retains mask semantics.

Corrections are checksum-valid suggestions, not authenticated recovery results.
They must be compared with the physical backup before use.

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
| Fixed registered-profile adapter | `_correct_fixed` |
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

Failure records distinguish lexical text, immutable prefix, selected-profile
shape, algebra, correction outside the visible body, and final semantic reparse.
Algebra failures retain both BCH and linear-stage diagnostics rather than
claiming that a mixed-corruption input failed for one inferred reason.

Decoder success is fail-closed twice: every synthesized locator root must map
to a legal reverse position in the selected checksum period, and the complete
set of proposed addends must algebraically transform the residue to the exact
target. This prevents an out-of-subgroup locator from being silently truncated
into a plausible partial correction.

The two checks above are deliberate hardening beyond literal PR #70 behavior.
The direct P70 routine checked the number of roots in GF(1024), but not whether
every regular-code root belonged to the shortened code's order-93 position
subgroup. The Gate 4 review found and remediated that gap; see
`security/correction/audit-record.md`.

## Evidence and provenance

The implementation carries the MIT notice from Blockstream's PR #70 head
`610cbad30258c80cd862b3773a20f8099d25e36e`. The frozen patch digest is
`11ef7d8a857d38b496068db4e44382825f0209ee7895d335daba122cfb1b77b8`.
The source-derived offline corpus and its limitations are recorded in
`source-manifest.md`; `tools/differential_correction.py --verify` checks it
without network or Haskell dependencies.
