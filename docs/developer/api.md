# API and architecture

## Architecture and review order

The package uses one narrow dependency direction:

```text
text -> format/header/checksum -> optional profile module -> immutable artifact
                                                   |-> BIP93 sharing
                                                   |-> ms/cl generation
                                                   |-> bounded correction
                                                   `-> MasterSeed wallet adapter

CLI -> public APIs above -> private bitcoin-cli subprocess adapter
```

The format layer first validates ASCII, case, separator, characters, and the
absolute size bound. The application parser selects the checksum type from the
generic encoded length and validates the common header before verifying the
outer checksum. Only afterward may the HRP select a registered application
profile. The parser then checks its application length and payload semantics.
An unregistered HRP crosses the boundary only as an opaque base `Secret` or
`Share`, with normalized `hrp`, `profile is None`, and no invented payload meaning.

CLI input diagnostics preserve generic container, header, and length failures.
After a checksum failure, the CLI may report an unsupported profile text length
instead. This diagnostic does not validate the input or change parser ordering;
alignment correction remains available. Frozen-prefix hints do not override a
generic parse-length failure.

### Specification-to-code map

| Concept | Single owner | Evidence |
|---|---|---|
| Bech32 characters, container, and `convertbits` | `bech32.py` | `test_bech32.py` |
| codex32 checksum selection and header boundary | `bip93.py` | `test_profiles.py`, BIP93 vectors |
| checksum and CRC arithmetic | `checksums.py` | official vectors, `test_crc.py` |
| optional application rules and S types | `profiles/ms32.py`, `cl32.py`, `bip39.py` | profile and BIP39 tests |
| immutable base artifacts and interpolation | `bip93.py` | BIP93 vectors, `test_sharing.py` |
| entropy, masks, identifiers, output indices | `generation.py` | `test_generation.py` |
| shared GF(32) arithmetic | `gf32.py` | sharing vectors and correction corpus |
| fixed BCH and worksheet correction | `correction.py` | `test_correction_bch.py` |
| structural alignment and admission | `indel.py` | `test_correction_indel.py`, `test_correction_capture.py` |
| CLI competitor scheduling and pruning | `_competitors.py` | `test_competitors.py` |
| incremental alignment syndromes | `_alignment.py` | `test_alignment.py` |
| stdlib-only BIP32 root validation and serialization | `_bip32.py`, `profiles/ms32.py` | BIP32 and wallet vectors |
| fixed wallet derivation and descriptors | `wallet.py` | `test_wallet.py` |
| Core target selection and subprocess state | `_bitcoin_core.py` | Core adapter and regtest |
| bounded stdin, fixed-prefix TTY entry, and whole-card confirmation | `_cli_input.py` | `test_cli.py` |
| command grammar, dispatch, and presentation | `_cli_parser.py`, `cli.py` | `test_cli.py` |

### Boundaries

- Only parsing and profile-specific factories construct artifacts.
- `bech32.py` keeps the recognizable BIP173 reference names and accumulator
  structure. Encoding takes an explicit checksum specification. Decoding
  without one returns the HRP and complete data part after checking only the
  Bech32 container rules; decoding with one also verifies and removes that
  checksum. The module does not select codex32 checksum lengths, validate
  codex32 headers, or decode application payloads.
- `profiles/__init__.py` optionally selects one of the registered application
  modules. Labels, lengths, padding, diagnostics, and S types stay with their
  application; unknown HRPs remain opaque and there is no runtime registration.
- Headers and artifacts are immutable; shares expose symbols, not bytes.
- Sharing interpolates payload and checksum together, explicitly constructs the
  target header, and reparses the result.
- `generation.py` is the only entropy owner and generates only `ms` and `cl`.
- Correction never edits the HRP or separator and reparses every candidate.
- `_bip32.py` stops at HMAC-SHA512 root derivation, scalar validity, and root
  xprv/tprv Base58Check serialization. It performs no child derivation or
  secp256k1 point arithmetic. `wallet.py` accepts only `MasterSeed`; EC-dependent
  public derivation is supplied through an explicit wallet integration and the
  CLI uses Bitcoin Core for that boundary.
- `_cli_input.py` retains at most nine artifacts and delegates partial-set
  compatibility to `bip93.py`. Card confirmation clears the terminal and saved
  scrollback where supported, then displays only entered text after a mismatch.
  Canonical text removes whitespace for comparison; presentation state retains
  entered spacing and case. Grouped alignment preserves entered ownership;
  unspaced alignment minimizes character edits before disturbed groups.
  Codex32 entry uses a separate `> ` line; correction candidates use ordinary card formatting without a prompt marker;
  fixed prefixes follow that marker. The `xprv` and wallet recovery paths begin
  with a frozen `MS1`; complete pasted strings may include it, while suffix-only
  input is accepted only when a frozen prefix is displayed. Later set headers
  use uppercase only when every accepted string is uppercase, and suffix input
  re-cases the reconstructed header to match its own case. Wallet selection prompts stay inline.
  Recovery input keeps matching leading groups fixed while an optional
  Readline hook restores the exact editable suffix with its cursor at the end. The hook disables
  automatic history and is removed after each attempt. While reading, stdout's
  file descriptor is synchronously redirected to the stderr terminal and
  restored in `finally`, keeping piped results clean.
- `_cli_parser.py` owns the complete non-abbreviating command grammar.
- `_bitcoin_core.py` is the only Core process/state adapter. It invokes no
  shell, opens no socket, discovers standard local chains through explicit
  `bitcoin-cli` arguments, and keeps wallet selection and private import out of
  stateless `wallet.py`.
- `cli.py` contains presentation and dispatch, with no domain algorithm or
  hidden state.

Private Python names are convention rather than access control. The supported
surface is the 25-name package `__all__`; direct use of private helpers is
unsupported but remains in the review scope.

### Size budget

V1 keeps the installed package below 5,000 logical review lines, excluding
blank and comment-only lines while counting subpackages recursively. Changing
the budget requires explicit review and authorization together with the matching
documentation and enforcement update.

### The optional graphical package

`src/codex32_gui/` is a second distribution package in this repository,
installed as `codex32[gui]` and started by `codex32-gui`. It is a client of the
surface above and of the private Core adapter; nothing in `src/codex32/` imports
it, and the base install keeps its property of having no third-party runtime
dependency. It carries its own budget of 1,800 logical review lines, separate
from the 5,000 above. Its own boundaries are documented in
[`gui.md`](gui.md) and enforced by `tests/test_gui_boundaries.py`.

## Profile and opaque-HRP capabilities

There is no runtime registration. An unknown HRP uses generic codex32 rules and
base artifact types rather than falling back to a registered application.

| Capability | opaque HRP | `ms` | `cl` | `bip39_12w/24w` |
|---|---:|---:|---:|---:|
| parse S/share | yes | yes | yes | yes |
| semantic S bytes | no | 16, 20, 24, 28, 32, or 64 | exactly 32 | no |
| recovery and API share derivation | yes | yes | yes | yes |
| `codex32` recovery/share/correction | yes | yes | yes | yes |
| unshared generation / shared ceremony API | no | six supported sizes | exactly 32 bytes | no |
| fresh generation CLI (`ms32`) | no | six supported sizes | no | no |
| existing-S splitting | no | yes | yes | no |
| wallet API | no | S only | no | no |

Registered application semantics remain:

| Capability | `ms` | `cl` | `bip39_12w/24w` |
|---|---:|---:|---:|
| semantic S bytes | 16, 20, 24, 28, 32, or 64 | exactly 32 | no |
| fixed BCH API | yes | yes | yes |
| bounded structural API | yes | yes | yes |

`ms` payloads encode exactly 16, 20, 24, 28, 32, or 64 seed bytes and may have
any legal parsed trailing bits. Parsing, generation, ceremonies, raw-seed
import, and CLI `--bytes` enforce the same six sizes. `cl` has 52 payload symbols; parsed
discarded bits remain application data. BIP39 profiles have exactly 27/53
payload symbols; S requires zero outer padding and a valid embedded SHA-256
checksum. Ordinary BIP39 shares are random masks and receive structural
validation only.

CL generation is explicit and uses a random identifier unless one is supplied.
Current Core Lightning defaults to mnemonic recovery, but its recovery command
retains an import path for codex32 HSM secrets. Generated CL S strings use the
zero-padding convention emitted by CLN; parsed nonzero discarded bits remain
valid and are preserved when re-sharing.

The generic `codex32` façade supports CL and BIP39 inspection, correction,
recovery, and share derivation. The `ms32` façade accepts only `ms` artifacts.

## Secret generation

`generation.py` is the only module that draws entropy. It generates BIP93
master seeds and Core Lightning HSM secrets, and splits either validated S type.
Core Lightning now defaults to mnemonic recovery, but retains a codex32 HSM
secret import path for recovery on an unused node.

Fresh unshared seeds default to 16 bytes and use the first 20 bits of their
BIP32 fingerprint as public identifier metadata. Fresh shared sets use four
independent random u5 identifier symbols. Raw bytes, re-shared secrets, and CL
generation also use an independent random identifier unless one is supplied.
Random re-sharing never repeats the source set header; an explicitly repeated
source header is rejected.

The Python API and CLI accept the six PR #2258 `ms` sizes: 16, 20, 24, 28, 32,
and 64 bytes. Other byte lengths are rejected at every public construction
boundary; there is no legacy decoder.

One-shot functions create only unshared secrets:

```python
generate_master_seed(seed_bytes=None, *, byte_length=None, identifier=None)
generate_core_lightning_secret(secret_bytes=None, *, identifier=None)
```

Shared creation uses `CreationCeremony.master_seed(...)`,
`CreationCeremony.core_lightning(...)`, or
`CreationCeremony.from_secret(...)`. Exactly one of `share_count` and `indices`
is required. `next_share()` returns one pending share, `confirm(text)` must
accept its independently re-entered string, and `finish()` returns the secret
only after every requested share is confirmed. There is no public one-shot
sharing or `split_secret` function. Fresh and existing Bitcoin CLI creation
requires interactive input and output, preflights local Bitcoin Core before
entropy or recovery input, and initializes a user-selected wallet after every
share is confirmed. CLI creation does not accept Core Lightning profiles; CL
generation and sharing remain API-only.
Without `--existing`, omitting the Bitcoin header creates an unshared master
seed. With `--existing` and no sharing threshold, a supplied codex32 secret is
emitted and confirmed unchanged, and the original validated artifact initializes
the wallet. This neutral source prompt tries raw hexadecimal first and otherwise
requires a complete explicit `ms1` string; it never infers or corrects a missing
HRP or separator. No entropy is drawn for this path; raw hexadecimal seeds retain
the generation path. Existing imports use timestamp zero to include prior
history. Changing a supplied secret's identifier requires a sharing threshold.
Shared creation
uses an explicit threshold or full backup header. Without an explicit share
count or indices, thresholds 2 and 3 produce the reviewed 2-of-3 and 3-of-5
presets; thresholds 4 through 9 require an explicit selection.

The ceremony follows the two BIP93 constructions:

- a fresh set draws `k` independent complete u5 masks;
- an existing S uses S plus `k-1` independent complete u5 masks.

Each direct share uses a separate `secrets.token_bytes` request and cannot be
followed by another draw until its string is confirmed. The pause gives the OS an
opportunity to mix fresh noise; Python cannot guarantee that new physical
entropy arrives between calls. User input is never treated as entropy. Each
byte is mapped with `value & 31`, which maps exactly eight byte values to each
u5 value.

Creation confirmation preserves whitespace-separated entered groups as units,
even when moving characters between groups would reduce edits or red groups.
A token may span multiple canonical groups only when it exactly matches their
complete concatenation, ignoring case. Within those boundary constraints,
alignment minimizes character-edit distance with deterministic edit-order ties:
exact pairs, substitutions, observed insertions, then expected omissions.
Omitted canonical groups remain empty. Surplus tokens attach to the following
group, or the last group for suffix extras; there are no insertion-only regions.
Unspaced input retains character-edit distance, then disturbed-group scoring,
with the same edit-order ties and preference for already-disturbed neighbors.
Only entered text is displayed. Adjacent disturbed groups form contiguous retry
regions. Display formatting matches the original card: uppercase, single
spaces between groups, an extra space after every fourth group, and alternating
bold and normal weights for correct groups. Unresolved groups are bold red; the active region adds
reverse video. Only wholly omitted groups use display-only underscores,
matching their canonical width. Partially entered groups are not padded;
no character positions are implied, and extras are never truncated. Editable
prefills preserve entered case and internal whitespace without added placeholders.
When active text has no internal whitespace, prefill uses the displayed group
boundaries with single spaces; extras are not repartitioned into four characters.
Red means review this part of the recovery card. Anything corrected
stays corrected. Retries locally realign only the active region, preserving
case and useful spacing without crossing frozen boundaries. Every newly
matching complete group freezes immediately, and the leftmost remaining run
is next. Empty and unchanged retries are unsuccessful; retries are unlimited.
A completely correct full-string retry confirms through the same callback.
An incorrect retry beginning with the expected profile and separator and longer
than the active canonical region is recognized as a full-string attempt. It
preserves current progress, clarifies which region remains incorrect, and
redisplays that region. Other submissions are aligned locally.
No expected characters, error classifications, prescribed edits, or repairs
are supplied. Only complete case/whitespace-normalized equality confirms.
Progressive group-level correctness feedback is explicitly accepted and does
not change the confirmation boundary.

Confirmation shows that the operator can produce the correct recovery
string during setup. It cannot prove that the physical backup was
corrected rather than reconstructed using confirmation feedback.

For a fresh set, the final direct share is rejection-sampled until the recovered
S has the private CRC padding convention (`ms`) or zero discarded bits (CL).
The already confirmed `k-1` masks remain fixed. Neither padding rule is BIP93
validity: parsed S strings may use any application-valid discarded bits, which
re-sharing preserves exactly. CRC never applies to shares.

Explicit output indices preserve caller order. A share count uses
`SystemRandom.sample` over the 31 ordinary indices and preserves sample order.
There is no entropy injection, sorting, caller-supplied partial-basis
completion, or BIP39 generation. Ceremonies reject copying and serialization;
the CLI does not resume an interrupted ceremony.

## Recovery and additional-share derivation

codex32 interpolation has one implementation in `bip93.py` for registered and
opaque HRPs. Compatibility is based on the exact normalized HRP and generic
shape; registered semantics are reapplied when every output is reparsed.

### Public operations

```python
recover_secret(shares: Sequence[Share]) -> Secret

derive_share(
    basis: Sequence[Share | Secret],
    fresh_index: str,
) -> Share
```

Recovery accepts exactly `k` ordinary shares. Derivation accepts exactly `k`
artifacts and may include S, but its target must be an unused ordinary index.
Input collections are bounded before at most nine artifacts are copied.

### Validation and interpolation order

1. Require a bounded sequence containing only authenticated immutable artifacts.
2. Require threshold 2–9 and exactly `k` inputs.
3. Require one normalized HRP, threshold, identifier, encoded length, payload length,
   and checksum length.
4. Require distinct input indices.
5. For derivation, normalize and validate the target and reject an existing target.
6. Extract the complete payload-plus-checksum tail from each artifact.
7. Interpolate the tail in GF(32) at S or the fresh target.
8. Construct the target header explicitly and reparse the complete string.
9. For BIP39 derivation, first interpolate and validate the implied S.

The HRP and common threshold/identifier fields are not interpolated. The target
index is explicit. Output is uppercase only when every input is uppercase;
otherwise it is lowercase. Algebra and validation are independent of input
order.

### Why the checksum is interpolated

The enabled codex32 checksums form GF(32)-linear codewords. For an exact common normalized HRP,
threshold, and identifier, Lagrange weights sum to one, so interpolating the
existing checksum symbols produces the checksum for the explicit target index
and interpolated payload. This keeps sharing visibly symbol-only and avoids a
second checksum-generation step. Reparsing the result is mandatory: it verifies
the checksum relationship, restores the immutable artifact boundary, and
applies registered S semantics when the HRP has a profile.

`tests/test_sharing.py` proves that recovery and derivation still work after
checksum creation is disabled. Official BIP93 vectors anchor the GF(32)
arithmetic. CL and BIP39 use compact frozen string/result fixtures rather than
a duplicate test implementation of interpolation or checksumming.

### BIP39 migration profiles

Ordinary BIP39 shares are validated only as exact-length codex32 symbol masks.
A recovered S must additionally have zero outer padding and a valid embedded
BIP39 checksum. Derivation validates the implied S before propagating the set.
The public API may recover or derive codex32 artifacts; it never exposes BIP39
entropy, a mnemonic, generation, or wallet derivation. The generic `codex32`
CLI exposes BIP39 recovery and derivation. Derivation first reconstructs and
validates the implied BIP39 S. BIP39 construction, mnemonic output, and wallet
interpretation remain unavailable.

### Deliberate Rust-reference differences

- Exactly `k` artifacts are required; extra points are not silently accepted.
- A requested target that is already present is rejected rather than returned.
- Profile-specific S semantics, including BIP39, are applied after recovery.
- The target header is constructed from validated common fields rather than
  obtained by interpolating constant header columns.

These differences implement the accepted API contract and the BIP93 wording
that an additional share uses a fresh index.

## BCH and bounded structural correction

Correction produces checksum-valid, untrusted suggestions. It cannot prove the
operator's intended wallet, and a suggestion never flows automatically into
sharing, recovery, or wallet APIs.

### Public full-string API

`correct(CorrectionContext(hrp, ...), damaged_text)` supports registered and
opaque HRPs. `hrp` accepts a lowercase-insensitive string or `Profile` and is
stored as a normalized lowercase string. The context fixes that HRP and may supply:

- `expected_length`, the complete canonical string length;
- `immutable_prefix`, program-supplied text outside the correction domain; and
- `excluded_indices`, ordinary share indices already accepted in a recovery.

With or without `expected_length`, registered correction searches only valid
profile lengths reachable by a supported structural family. An opaque target
considers character offsets -4 through +4 and group offsets -8/-4/0/+4/+8,
filtered through generic codex32 shape validation. Registered profile length
and payload validation is unchanged. Every attempt has a ten-second deadline.

The HRP, separator, and any confirmed five-character threshold/identifier header
are immutable. Profile registration is never a candidate-ranking signal and
cannot transform one application namespace into another. Every returned
artifact crosses `parse_codex32`; suggestions remain untrusted and require
exact whole-string confirmation before operational use.

`capture_volume` is the integer primary rank; `addend_hamming_weight` and
`crc_padding_match` retain their secondary diagnostic meanings.
`cumulative_capture_volume` and `capture_space_bits` describe the conservative
equal-or-better admitted search, including unsuccessful and unsearched classes.
For included classes `(V, b)`, let `B = max(b)` and
`C = sum(V << (B - b))`. The fields store `C` and `B`.
`low_checksum_discrimination` is exactly `32*C > 2**B`; equality leaves five
bits and does not trigger. Candidate ranking remains based on its own volume.
No profile semantics, CRC, fingerprint, pruning, or timeout discount this sum.
The API remains noninteractive. Clients displaying candidates can use this
property to enforce the CLI's low-discrimination disclosure boundary.
`search_complete=False` identifies a unique-so-far result from interrupted
optional search. It does not establish uniqueness or global best rank. No
candidate is released if required search is interrupted, or if an interrupted
optional search already has multiple primary-rank ties. Completed searches
retain primary ties for the existing CLI tie-breakers. A valid unchanged input
returns a candidate with no edits; malformed context raises
`InvalidCorrectionInput`.

### Structural model

The families are disjoint:

- Character alignment: `A = I + O + AT + 2*T <= 4`.
- Displayed four-character groups: `G = GI + GO + GS + GAT + 2*GT <= 2`.

`I/GI` delete extra observed text; `O/GO` insert missing symbols as erasures;
`AT/GAT` swap adjacent units; `T/GT` swap nonadjacent units. `GS` masks a corrupted
four-character group as erasures. Group boundaries come from canonical display
positions, independent of entered spaces. Partial edge groups and immutable
prefix characters are never selected as whole-group operations.

Substitutions and explicit erasures belong to the fixed BCH decoder after
alignment. Ordinary mixed repair obeys `E + 2*S <= 8`. Exact-length consecutive
explicit erasures retain the fixed 13/15-symbol linear completion path.
Transpositions and removal of extra text consume alignment work but no BCH
erasures. Omitted or corrupted groups consume up to four erasures each.

The generator preserves operation order where it affects adjacency. It skips
identity swaps and canonicalizes equal-unit deletion runs; other duplicate
scripts are conservatively charged. Final corrected strings are deduplicated.

### Coordinates and incremental syndromes

For HRP `h`, displayed length `D`, and full BCH body length `B`:

- `B = D - len(h + "1")`, including header, payload and checksum.
- Expanded length is `len(bech32_hrp_expand(h)) + B`. The existing checksum
  selector chooses 13 checksum symbols through 93, rejects 94–95, and chooses
  15 checksum symbols through 1023.
- BCH `word_length` means `B`; reverse positions are `0..B-1`.
- Mutable body length is `D - immutable_length`. Freezing the five-character
  header shortens this domain, but preserves the full syndrome coordinates.

`_alignment.py` uses small piece tables and shifted prefix contributions.
Unchanged segments require two prefix lookups; moved units require only local
positional effects. No candidate-wide syndrome scan or full candidate tuple is
needed before a BCH hypothesis survives. `correction.py` performs the BCH work
and reparses survivors. No meet-in-the-middle search is used.

### Shared capture bound and computation

Each layer is charged `alignment_count * 32**E * C(M-E,S) * 31**S`, with `M`
the mutable body length. All fixed, character, group and target-length layers
share one admission ledger. Complete equal-volume batches are admitted only
while their cumulative mass is at or below `1`. Integer scaling handles
65-bit and 75-bit checksum spaces together. Consecutive fixed erasures are
included in this ledger, with no independent allowance. Profile validation,
CRC and fingerprint hints do not enlarge it.

The inclusive ceiling permits full 13/15-erasure completion, whose capture
volume occupies the entire selected checksum space. It is not a small
false-positive probability guarantee. It is an engineering accounting bound,
not authentication or a claim about the operator's intended backup. The admitted
bound includes unsearched portions, so it also bounds any optional search prefix.

Before revealing a candidate with fewer than five bits of cumulative checksum
discrimination, every CLI correction flow prints the high-risk warning and
requires literal uppercase `YES`. This includes `ms`, redirected damaged input,
and corrected existing-source entry. Candidate text, metadata, fingerprints,
and residue addends remain hidden until that confirmation succeeds. Ordinary
whole-card `[y/N]` acceptance still follows where the corrected artifact will be
consumed; the `correct` command only reports the suggestion and therefore does
not ask a second confirmation. If no interactive confirmation channel is
available, the CLI emits only the executable-named `interactive confirmation
required` error. `--plain` does not bypass the gate.

Fixed BCH repair runs first. Required character/group work precedes optional
character expansion, with lower capture-volume layers first within each
phase. A layer can be omitted once its rank is strictly worse than the
current best result. Otherwise the deadline is checked during enumeration.

The required baseline is `A<=2` and `G<=2` at every current public profile
length. Host restarts prevented an uninterrupted timing certification; the
recorded capped measurements do not promote a wall-time guarantee. Deeper `A=3/4` work is best effort within the deadline. No tentative
40/66/93/127 cutoff is a protocol constant or a promoted deeper guarantee.
See [alignment benchmark evidence](alignment-benchmarks.md) for measured public
workloads and hardware. Synthetic body/period experiments cannot promote a
public cutoff. Unexpected interruption of the required phase remains
fail-closed, including on slower or overloaded hardware.

The CLI uses a separate scheduler over the same admitted frontier. Fixed BCH
runs first, followed by single structural mistakes, paired insertion/omission
families, and other combinations. Within each tier, lower capture volumes run
first across all eligible lengths. Command-specific artifact eligibility and
set compatibility are applied before results can affect ranking or pruning.

Whether fixed BCH or alignment finds the first usable candidate, the CLI then
exhausts all admitted competitors capable of improving its rank. Equal-volume
layers remain eligible for secondary ranking. The cutoff tightens whenever a
better result appears. One ten-second deadline starts at entry, includes
preparation, and never restarts. There is no separate one-second cutoff. At the
deadline, a single primary-best-so-far candidate may be returned with
`search_complete=False`; incomplete primary ties are suppressed. CLI suggestions
omit search-completeness warnings, make no uniqueness claim, and retain the
whole-string acceptance boundary. Public Python search signatures and required
versus optional completion behavior are unchanged.

CLI pruning proves coverage using fixed BCH's `E + 2*S <= 8` sphere or the
minimum distance of nine at the same profile and length. It accounts for
residual substitutions, existing erasures, and cancelling structural edits.
Discovery coverage alone is insufficient: a redundant layer may give a known
artifact a lower capture volume or Hamming weight. Symbol-count and positional
bounds exclude impossible explanations; directed character-swap enumeration
scores the remaining known-artifact explanations through the ordinary decoder.
Its duplicate-state cache is capped at 4,096 entries. Other scoring work is
retained unless equivalence is proved, including useful group and indel work.
Completed simpler mask/deletion layers can cover repeated masks and masks removed
by deletion. The original mass ledger is preserved without expanding admission
to spend savings from redundant hypotheses. Execution remains on one CPU.

`tools/alignment_benchmark.py --public` exercises valid profile lengths, target
knowledge, header freezing, reachable offsets and explicit erasures.
`--kernel` separately samples BCH-body lengths 40/66/93/127/1015/1023, character
depths 2/3/4 and group depth 2, and reports generation, syndrome, BCH, locator,
dedup and allocation measurements. Kernel checksum selection is explicit and
may represent a synthetic word that is not a valid public application string.

### Worksheet residue API

`correct_worksheet_residue` accepts only a 13- or 15-symbol residue and uses
zero-based reverse positions. It has no profile, HRP, or complete-string length.
`()` means already correct, a tuple contains unique addends, and `None` means no
unique correction. The CLI alone converts displayed positions to one-based.

Before disclosing addends, the CLI applies the same five-bit recovery gate.
Residue accounting uses the full checksum period (93 or 1023 positions) and
`V(E,S) = 32**E * C(period-E,S) * 31**S`, summed over decoder-admitted classes
with volume no greater than the returned class. Specified erasure positions
count even when their solved addend is zero. The public residue API's return
type is unchanged.

The frozen PR #70 and malformed corpora are under `tests/data/`. Fixed and
structural correction are checked by `tests/test_correction_bch.py`,
`tests/test_correction_indel.py`, `tools/correction_capture.py`, and
`tools/differential_correction.py --verify`. Performance can be measured with
`tools/correction_benchmark.py`.

## Generation-only CRC padding

BIP93 permits arbitrary discarded bits in an `ms` S payload. Parsed strings
remain valid for every legal pad value. Electronic generation uses those bits
as a small private CRC hint that may help a future recovery tool distinguish
some damaged candidates. CRC is not part of BIP93 validity and never applies to
ordinary shares.

### Frozen convention

For `p = (-8 * len(seed)) mod 5`, `_crc_pad` uses the following compact table:

| `p` | Generator |
|---:|---|
| 0 | no CRC; padding zero |
| 1 | `x + 1` |
| 2 | `x^2 + x + 1` |
| 3 | `x^3 + x + 1` |
| 4 | `x^4 + x + 1` |

The reproducible bit convention matters as much as the polynomial name:

- seed bytes enter most-significant bit first;
- each input value is one bit;
- the initial register residue is `1`;
- the generator integers encode the lower polynomial coefficients (`1` for
  CRC1 and `0b11` for CRC2–CRC4); the leading `x^p` coefficient is implicit;
- `p` zero bits are appended before reading the result;
- the final XOR/residue constant is zero;
- the `p` result bits are emitted register-most-significant bit first and become
  the otherwise discarded payload bits.

Representative all-zero seed outputs for lengths 16 through 20 bytes are
`2, 6, 1, 2, 0`, corresponding to `2, 4, 1, 3, 0` padding bits.

The polynomials appear in the [Koopman CRC catalogue](https://users.ece.cmu.edu/~koopman/crc/index.html),
including its [CRC-3](https://users.ece.cmu.edu/~koopman/crc/crc3.html) and
[CRC-4](https://users.ece.cmu.edu/~koopman/crc/crc4.html) tables. Those rankings
model low, independent bit errors. They do not establish that these choices are
optimal for insertions, deletions, substitutions, or correlated human
transcription damage. We therefore freeze the compact implementation without
an optimality claim or polynomial-search tool.

Fresh shared generation uses rejection sampling so the recovered S has this
padding while all `k` initial shares remain complete uniform masks before
conditioning. Direct `MasterSeed.from_seed` encodes the same convention.

## Wallet interoperability

Public wallet operations accept only a validated `MasterSeed`. `wallet.py` is
stateless and never accepts shares, Core Lightning secrets, BIP39 migration
artifacts, or raw bytes.

The public adapter has two functions:

- `master_xprv(secret, testnet=False)` returns the BIP32 root extended private
  key.
- `core_descriptors(...)` returns fixed BIP44, BIP49, BIP84, and BIP86 Bitcoin
  Core `importdescriptors` records. Private records use stdlib-only root xprv
  serialization; public records require an explicit wallet integration and the
  Core wallet whose imported root key will perform hardened derivation.

No installed Python dependency performs secp256k1 operations. The private
Bitcoin Core adapter implements the wallet integration by sending root-xprv
descriptor material to `bitcoin-cli` over stdin and treating Core's returned
fingerprints, account xpubs, and normalized descriptors as untrusted external
data.

Public descriptors contain account xpubs. Private descriptors intentionally
follow Bitcoin Core's root-key form: they contain the root xprv followed by the
complete derivation path. They therefore grant authority over the entire root,
not only the selected account. The CLI warns before printing them.

Account, private/public mode, network serialization, and timestamp are explicit
API inputs. The `ms32 wallet` CLI takes only `--account` and `--timestamp`; the
selected Bitcoin Core chain is authoritative and there is no wallet
`--testnet` flag. `ms32 xprv --testnet` remains explicit because it directly
selects xprv versus tprv serialization. The timestamp defaults to `0` so
recovery scans from genesis. A nonnegative Unix time or the literal `now` may
be supplied; `now` intentionally skips historical discovery. There is no
account database, descriptor parser, policy language, RPC library, or network
client.

Bitcoin master-seed creation and restoration use a private CLI adapter. Before
entropy or recovery input it resolves `bitcoin-cli` from `PATH` and probes the
five standard chains with explicit `-chain` and `-rpcconnect=127.0.0.1`
arguments. It requires Core 32 or newer, automatically selects one responsive
chain, or asks the operator when several respond. Every later call retains the
selected chain. After confirmation or recovery it offers only loaded, empty
private-key-enabled descriptor wallets, with no external signer,
descriptors, transactions, keypool, or active scan. The operator selects by
number and confirms the escaped exact name; the adapter never infers a wallet
from list order or Bitcoin-Qt state.

Immediately before import, every target property is checked again. The original
`CreationCeremony.finish()` result or validated recovered master seed supplies
the four private multipath records. Confirmation text is never reparsed into
this source. Private descriptor material is sent only through
`bitcoin-cli -stdin`, raw Core errors are suppressed, and no passphrase
interface exists.

After all four private records import successfully, Core v32 exposes the one
wallet HD root with `gethdkeys`; `derivehdkey` performs the hardened
BIP44/49/84/86 account derivations. Python validates the returned origin paths,
fingerprint consistency, and network xpub/tpub versions, constructs only the
fixed descriptor templates, and asks `getdescriptorinfo` to validate and expand
their external/internal branches. The adapter then compares the exact eight
active public descriptors against `listdescriptors`. It relocks wallets Core
reports as encrypted. Before any of this, `initialize` calls `verify_identity`
with the required `expected_fingerprint`: bytes typed from the wallet record
(read with `parse_fingerprint`), or `None`, the operator's explicit choice to
restore without a record after seeing the fingerprint and `identifier_origin`.
A mismatch raises `FingerprintMismatch` before any wallet RPC. Master-fingerprint display is likewise delegated to Core:
a stateless root P2PKH descriptor is normalized, `deriveaddresses` derives its
address, and `validateaddress` returns the script hash whose first four bytes are
the BIP32 fingerprint.

The Core calls are fixed: `getnetworkinfo`, `getblockchaininfo`, `listwallets`,
`getwalletinfo`, `listdescriptors`, `getdescriptorinfo`, `deriveaddresses`,
`validateaddress`, `importdescriptors`, `gethdkeys`, `derivehdkey`, and
`walletlock`. Bitcoin Core alone creates wallets, selects encryption, handles
passphrases, stores keys, and provides normal wallet behavior.

The wallet CLI is one leaf command:

```text
ms32 wallet --account 0 --timestamp 0
```

It preflights Core before recovery input, recovers one validated master seed,
selects and revalidates an empty private-key-enabled destination, imports
through `bitcoin-cli -stdin`, verifies the exact accepted public descriptor
set, and relocks an encrypted destination after success, failure, or
interruption. It never handles a passphrase.

For offline signing/watch-only and multisig workflows, use Bitcoin Core v32's
maintained procedures. Until the final v32 release, see the versioned
[offline-signing tutorial](https://github.com/bitcoin/bitcoin/blob/v32.0rc1/doc/offline-signing-tutorial.md)
and [multisig tutorial](https://github.com/bitcoin/bitcoin/blob/v32.0rc1/doc/multisig-tutorial.md).
The direct `ms32 xprv` primitive remains top-level and carries an explicit
secret-root warning.

`tools/bitcoin_core_regtest.py` is the repeatable integration check. It requires
Bitcoin Core 32 or newer and exercises direct wallet restoration, account and
timestamp handling, Core-normalized public descriptors, balance discovery,
sign/broadcast behavior on regtest, relocking, and mainnet/test-network root
serialization. `tools/bitcoin_core_main_smoke.py` repeats the descriptor,
account, timestamp, and relocking checks against an isolated main-chain Core
instance without connecting to peers.

## Deliberate divergences and non-goals

These choices are not presented as BIP93 requirements.

| Decision | Reason |
|---|---|
| `ms` accepts only six seed sizes | follows the frozen PR #2258 profile with no legacy decoder |
| random electronic output indices | reduces canonical index disclosure; explicit indices preserve requested order |
| generation-only CRC padding | small recovery hint; not validity or share semantics |
| fingerprint identifier only for fresh k=0 | shared sets, raw seeds, re-sharing, and CL generation use random IDs unless explicitly overridden |
| BIP39 profiles have no construction or wallet CLI | migration artifacts may still be checked, corrected, recovered, and re-shared generically |
| reject existing derivation targets | enforces BIP93's fresh-index wording |
| bounded structural correction is deliberately finite | exact capture safety, complete global rank layers, the 48-character ten-second target, and the package audit budget exclude a general recovery engine; longer valid strings keep the same bounded classes |
| private descriptors contain root xprv | matches Bitcoin Core behavior and carries an explicit authority warning |
| no caller-supplied partial-basis completion | unauthenticated points can create incompatible same-header polynomials |

Unknown-HRP application interpretation, GUI, direct sockets, a general RPC
client, secret storage, runtime profiles, BIP39 mnemonics, and arbitrary descriptor parsing are
explicit v1 non-goals.
Structural correction is bounded as documented above; broader multi-candidate
recovery remains a separate-tool concern. Pending-standard compatibility, the
external BIP32 boundary, identifier privacy, and Python secret-memory
limitations are documented in the [security model](../security/model.md).

## Identifier policy

The four-character identifier is public metadata, not authentication.

- A fresh unshared (`k=0`) machine-generated `ms` secret uses the first 20 bits
  of its BIP32 fingerprint. Independently publishing the identifier gives an
  offline 20-bit predicate against candidate seeds.
- A fresh shared set uses four independent random u5 symbols and leaks no
  seed-derived fingerprint bits.
- Raw seed bytes, re-sharing, and CL generation use an independent random
  identifier unless the caller supplies all four symbols. A random identifier
  does not make a weak supplied seed safe.
- Random re-sharing rejects the source set header and draws another identifier.
  An explicitly repeated source header remains an error.

Changing a header does not authenticate a polynomial. Users must not combine
same-header shares from separate ceremonies. Caller-supplied partial-basis
completion remains unsupported.

Operational correction in `secret`, `share`, `xprv`, and `wallet` displays the
canonical uppercase candidate with ordinary alternating group weights, without
difference highlighting. Only `correct` highlights corrected four-character
windows; creation retains its separate transcription-error localization.
Acceptance requires “Does this entire string exactly match your recovery card?
[y/N]:” with explicit `y` or `yes`; rejection preserves the input flow. `check`
never searches for corrections. An intact first-entry profile prefix is immutable.

Bitcoin secret candidates display their master fingerprint above the card text.
Final-share candidates in recovery commands provisionally reconstruct an isolated
secret solely for this preview; share derivation and intermediate shares do not.
Preview failures reject the candidate. No candidate enters accepted state, key
export, descriptor construction, or wallet initialization before confirmation.

Interactive `create --existing` offers bounded correction for a mistyped codex32
secret of the selected profile. Compare the entire proposed string with the
original recovery card before answering yes. Bitcoin candidates show their master
fingerprint above the text. Declining or finding no usable correction returns to
source entry; hexadecimal seeds are never corrected. Confirmation of newly
created cards is a separate step after accepting the source.
