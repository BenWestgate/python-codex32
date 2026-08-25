# BCH and bounded structural correction

Correction produces checksum-valid, untrusted suggestions. It cannot prove the
operator's intended wallet, and a suggestion never flows automatically into
sharing, recovery, or wallet APIs.

## Public full-string API

`correct(CorrectionContext(...), damaged_text)` supports every registered
profile. The context fixes the profile and may supply:

- `expected_length`, the complete canonical string length;
- `immutable_prefix`, program-supplied text outside the correction domain; and
- `excluded_indices`, ordinary share indices already accepted in a recovery.

Without `expected_length`, the API attempts only fixed-length BCH correction.
An exact expected length enables bounded structural correction. The public API
has no deadline and returns every final reconstruction tied at the best primary
rank. A valid unchanged string returns one candidate with no edits, no result
returns `()`, and malformed context raises `InvalidCorrectionInput`.

The HRP and separator are immutable. For a first share, `immutable_prefix` is
the profile prefix, such as `ms1`. After a share has been validated and the
operator confirms it, an interactive recovery may prefill `ms1` plus its
threshold and identifier. That longer prefix admits no structural edits,
erasures, or substitutions, and its symbols do not enter alignment or capture
counts. A suggested correction never establishes or changes this context.

Every candidate crosses the ordinary `parse_codex32` validation boundary.
`capture_volume` is its exact integer primary rank. `addend_hamming_weight` is
a secondary transcription hint, `erasures_filled` counts recovered unknown
symbols, and `crc_padding_match` exposes the generation-padding hint when
applicable. Edit positions count backward from the final data/checksum symbol.

## Structural promise

Corrects up to four arbitrary missing or extra characters, including mixtures;
up to two skipped or extra four-character groups, including one of each.

There are exactly two independent structural families:

- arbitrary characters with `inserted + omitted <= 4`; and
- whole four-character groups with `inserted + omitted <= 2`.

Only a class whose net length change reaches the expected target is generated.
The families are never mixed. There are no special burst, duplication, or
transposition generators. An adjacent swap remains two fixed substitutions.

Group phase is derived from the canonical four-character display layout; input
spaces are not evidence and are optional. Because group search admits only
whole-group edits, its phase cannot shift. Character-indel search never relies
on group boundaries.

An invalid body character such as `?` is considered both ways when the length
permits: it may be an extra character deleted by structural alignment, or an
explicit erasure retained for fixed correction. Equivalent structural views
are deduplicated before BCH work. Final reconstructions are deduplicated again
before ambiguity handling.

The ownership invariant is:

```text
indel.py enumerates alignments
correction.py performs all symbol repair
```

An omitted character becomes one BCH erasure and an omitted group becomes four.
Deleting extra text consumes no BCH capacity after alignment. The fixed core
continues to enforce `erasures + 2 * substitutions <= 8` for mixed errors. Its
13-consecutive-erasure regular and 15-consecutive-erasure Long behavior remains
a separate fixed-length feature. For exact-length input, that solver returns its
unique checksum-valid completion directly when 9 through 13 (regular) or 15
(Long) explicit erasures are contiguous. It never admits nonconsecutive
erasures above eight or an insertion/deletion hypothesis.

## Capture bound and ordering

For one exact correction class, the primary decoder-capture volume is:

```text
structural alignments * fixed-core BCH capture volume
```

The fixed-core term already includes erased symbol values, so omissions are not
multiplied by `32` a second time. For each observed-to-target length delta, the
runtime sums every admitted class with primary volume no worse than a proposed
structural result. Structural eligibility requires the strict integer bound:

```text
100_000 * cumulative_volume < 2 ** checksum_bits
```

This is a conservative `P_false < 1e-5` envelope. The checksum space is 65 bits
for regular codex32 and 75 bits for Long. Optional profile semantics, CRC, and
fingerprint hints do not enlarge it. In particular, two omitted groups remain
inside the regular envelope at a conservative class bound of about `1.97e-6`.

The separately guaranteed consecutive-erasure completion is not a structural
capture-ranked result and is explicitly exempt from that envelope. Its erased
locations are supplied, its fixed linear system has one checksum-valid
completion, and it remains an untrusted, nonzero-exit CLI suggestion requiring
comparison with the backup.

Combining an above-eight burst with extra-character deletion is not part of the
fixed guarantee. The CLI may nevertheless prove that such input is ambiguous
by finding two distinct parsed completions through the same fixed core. It then
reports ambiguity rather than selecting or emitting either completion.

Search classes are ordered by their theoretical minimum primary volume. A best
candidate does not stop the search: every remaining class with a floor equal to
or better than that rank is exhausted. A class may be skipped only when its
floor is strictly worse. Thus an early result cannot hide a tied reconstruction.

The API retains all primary-volume ties. The interactive CLI first refines such
ties by Bech32 addend Hamming weight, then by generation CRC, then by matching
the BIP32 fingerprint identifier of an unshared master seed. If a tie remains,
the CLI reports ambiguity instead of selecting by enumeration or lexical order.

## Runtime boundary

The 48-character reference target must complete every advertised class within
ten seconds on the documented fast-laptop CPU. The largest class is two missing
plus two extra arbitrary characters, with about one million alignments. The
generic pipeline parses once, reuses erasure state, prunes only provably
impossible profile headers, and calls the same fixed corrector for every class.

The API has no deadline. The CLI finishes any class it starts; if the ten-second
boundary is reached before another 48-character class, it accepts no provisional
result. Longer strings retain the same finite structural families without a
deadline and may take longer. They are interruptible normally.

CLI `ms` correction defaults to 48- and 74-character targets. `--bytes 16..64`
selects an unusual imported master-seed size. CL targets 74 characters. BIP39
full-string correction remains API-only.

## Worksheet residue API

`correct_worksheet_residue` accepts only a 13- or 15-symbol residue and uses
zero-based reverse positions. It has no profile, HRP, or complete-string length.
`()` means already correct, a tuple contains unique addends, and `None` means no
unique correction. The CLI alone converts displayed positions to one-based.

The frozen PR #70 corpus, malformed corpus, arithmetic evidence, structural
tests, and benchmarks are indexed in [source-manifest.md](source-manifest.md)
and [gate3-analysis.md](gate3-analysis.md).
