# Security model

This document is the technical security reference for reviewers and API
developers. The user-facing policy and reporting instructions are in the
repository root `SECURITY.md`.

## Required properties

- Unchecked text cannot enter sharing, generation, correction output, or wallet
  operations as a validated artifact.
- Parsing verifies the generic codex32 format and checksum before an HRP
  selects application length or payload rules. Header and application payload
  semantics are applied afterward.
- Artifacts and headers are immutable. Shares have symbol semantics only and
  cannot be constructed from or converted to bytes.
- Recovery requires exactly the declared threshold of compatible, distinct
  ordinary shares. Derivation requires a fresh ordinary index.
- Shared creation draws each complete mask separately from the operating-system
  CSPRNG and requires confirmation before the next mask. It exposes no entropy
  injection, padding control, or caller-supplied partial-basis completion, and
  ceremony state cannot be copied or serialized through supported Python
  protocols. Fresh `ms` ceremonies retry a final share if the recovered seed
  does not form a valid BIP32 root or fails the generation-only CRC convention.
- Wallet operations accept only `MasterSeed`.
- Fresh Bitcoin creation requires an interactive terminal and a successful
  Bitcoin Core 30+ loopback preflight before entropy is drawn. The original
  in-memory ceremony result, never re-entered confirmation text, is the source
  for wallet derivation.
- Automatic Core initialization offers only empty user-created descriptor
  wallets with private keys enabled, no external signer, transactions,
  descriptors, keypool, or active scan. The selected name and every property
  are checked again immediately before import.
- Private descriptor JSON reaches `bitcoin-cli` only through its standard
  input. Core passphrases never enter Python. Every import must succeed, the
  exact accepted public descriptor set must match, and an encrypted wallet is
  relocked after every success, failure, or interruption once Core reports it
  unlocked.
- Correction returns untrusted suggestions. It never authenticates input,
  edits the HRP or separator, accepts an incomplete rank class, or chooses among
  equally ranked reconstructions.
- `indel.py` enumerates alignments; `correction.py` alone repairs symbols. The
  immutable prefix is program-supplied and outside the correction domain.

## Known limitations

- Python cannot guarantee secret zeroization, constant-time execution, locked
  memory, or absence of copies in the runtime, operating system, terminal, or
  caller.
- A rejected terminal entry may remain temporarily available for editing and
  visible in scrollback. Automatic Readline history is disabled and the project
  does not write a history file.
- `bip32>=5,<6` and Coincurve are security-sensitive dependencies. Only the
  `ms32` profile module imports BIP32, and the project verifies official BIP32
  and wallet vectors, but it does not independently audit their cryptographic
  implementations.
- Python 3.12 and 3.13 are supported.
- Fresh unshared `ms` identifiers expose 20 bits of the BIP32 fingerprint.
  Shared sets, supplied raw seeds, re-sharing, and CL generation use random or
  explicit identifiers.
- Generation-only CRC padding is a small recovery hint, not authentication or a
  codex32 validity requirement.
- Separate CSPRNG requests and confirmation pauses let the operating system mix
  fresh noise between direct shares, but cannot guarantee that new physical
  entropy arrives between calls. Re-entered text is confirmation, not entropy.
- Correction can suggest checksum-valid text but cannot establish that a
  candidate was intended. The HRP and separator are never corrected.
- Exact-length consecutive erasures retain the fixed core's separate guarantee:
  13 symbols for regular codex32 and 15 for Long. This does not admit more than
  eight arbitrary erasures into structural correction.
- Private Bitcoin Core descriptors contain the root xprv by design.
- Fresh initialization trusts the `bitcoin-cli` executable resolved from
  `PATH`, its configuration, and the connected local Bitcoin Core instance.
  codex32 opens no RPC socket and cannot establish that those components or
  the destination computer are benign.
- Private descriptors exist temporarily in Python objects, JSON text, and the
  child process's stdin. The usual Python, process-memory, swap, hibernation,
  and crash-dump limitations apply even though codex32 neither saves nor echoes
  the records.
- Wallet encryption is recommended but belongs to Bitcoin Core. codex32 accepts
  an eligible unencrypted wallet, does not verify passphrase policy, and can
  only request and verify `walletlock` for a wallet Core reports as encrypted.
- The implementation follows frozen BIP93 PR #2258 commit
  `5117f5831bcbf0485949e5951d2954b792eded28`. Parsing and every construction
  boundary accept exactly 16, 20, 24, 28, 32, or 64 `ms` seed bytes; there is
  no legacy decoder.

## Bitcoin Core initialization boundary

The fresh-Bitcoin CLI adapter invokes `bitcoin-cli` as a child process with
`-rpcconnect=127.0.0.1`; it has no RPC library, socket client, shell invocation,
wallet database, or wallet-creation operation. Preflight reads
`getnetworkinfo` and `getblockchaininfo`, requires Core 30 or newer, and derives
mainnet versus test-network BIP32 serialization from Core's reported chain.

After all cards are confirmed, the adapter uses `listwallets`,
`getwalletinfo`, and public `listdescriptors` to find eligible destinations.
Wallet names and Core responses are untrusted input. Names are displayed as
escaped JSON, selected by number, confirmed exactly, and shell-quoted only in
the optional public export command. A newly created choice must appear in a
new wallet-list snapshot; list order or a Bitcoin-Qt selection never implies
consent.

The adapter derives account 0 BIP44, BIP49, BIP84, and BIP86 multipath records
from the original generated seed with timestamp `"now"`. It asks public
`getdescriptorinfo` to expand the expected descriptors, then revalidates the
target and sends the private import JSON through `bitcoin-cli -stdin
importdescriptors`. It requires four successful results and compares public
`listdescriptors` output with all eight expected external/internal expansions.
Raw Core failures are suppressed because a diagnostic could repeat a private
descriptor.

An encrypted locked wallet must be unlocked directly in Bitcoin Core before
Retry; no passphrase channel exists in codex32. Selecting an encrypted wallet
establishes one `finally`-protected relock obligation before the unlock prompt.
It covers eligibility changes, public descriptor expansion, immediate
revalidation, private import, exact public verification, failure, and
interruption. An interrupt during cleanup is deferred until `walletlock` runs
and its locked state is checked. An interruption before card confirmation
invalidates the partial set; an interruption afterward leaves valid cards but
an incomplete wallet initialization.

## Structural-correction threat model

### Scope and boundaries

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

### False reconstruction

An incorrect checksum-valid reconstruction could rank before the intended text.
For each compatible length delta, the implementation conservatively sums all
supported structural/BCH classes whose primary capture volume is no worse than
the candidate. A structural-ranked result is eligible only when its cumulative
probability bound is strictly below `1e-5`. Integer arithmetic prevents
rounding at the boundary.

An unknown-length first `ms` card searches the six valid target lengths under
one cumulative bound. Automatic search permits up to four character indels for
48-, 74-, and 127-character targets and up to three for 54, 61, and 67; all six
permit up to two whole-group indels. A confirmed first card fixes the exact
length for later cards. Numeric `--bytes` requests one full exact-length search;
`--bytes ?` requests full search of all six lengths.

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
separate fixed-core case, not a structural class. Regular codex32 retains its
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

### Ambiguity and early stopping

Equivalent alignment views are deduplicated before BCH work. Different paths
that reconstruct the same final canonical string count once. The public API
retains every reconstruction at the best primary rank.

A found candidate does not justify stopping. The search exhausts every class
whose theoretical floor can tie or beat the current best. It stops early only
when every unsearched class has a strictly worse floor. The CLI applies Hamming,
CRC, and fingerprint refinements in that order; if a tie remains, it reports
ambiguity rather than selecting by enumeration or lexical order.

### Resource exhaustion

Input length is bounded before enumeration. Each admitted class has a finite
combinatorial count, generators stream their views, and repeated reductions use
a canonical earliest embedding plus a small capped cache. Memory therefore does
not scale with the million-view search space. The primary 48-character
benchmark is `2O + 2I`, approximately one million alignments.

The CLI gives automatic searches compatible with the 48-character target a
ten-second reference target and finishes the class it starts. If another
potentially competitive class remains when the deadline is reached, it rejects
all provisional results. Explicit-length and `--bytes ?` searches have no
deadline and remain normally interruptible.

Multiprocessing is intentionally absent. CPython threads do not accelerate the
CPU-bound loop, while worker processes replicate secret-bearing buffers and BCH
tables, complicate deterministic frontier coordination, and add cross-platform
failure modes. The measured single-process generic pipeline meets the reference
target without those costs.

### Context and candidate promotion

Immutable text is supplied by the program, never inferred from damaged input.
Outside that prefix, profile-header pruning is a lossless lower bound: a known
mismatch consumes available substitution capacity, while an erasure remains
repairable. Already-used share indices are checked again on parsed artifacts.

Suggestions remain immutable artifacts paired with edits and rank evidence, but
callers must explicitly choose to reuse them. The simple CLI writes suggestions
and warnings to stderr, returns nonzero, and emits no machine-consumable secret
on stdout.

### Severity calibration

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

## Capture-volume and performance evidence

Gate 3 admits exactly two structural families: arbitrary character edits with
`I + O <= 4`, and independent whole-group edits with `GI + GO <= 2`. Only
classes matching the observed-to-target length difference are generated.

### Independent arithmetic

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

### Frozen 48-character alignment counts

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

### Implementation evidence

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

The fixed core plus structural adapter remains below 1,500 physical lines. The
complete installed package remains below 3,000 logical review lines, excluding
blank and comment-only lines while counting subpackages recursively. Normal and
optimized test suites, strict mypy, Ruff, manifest hashes, arithmetic tests,
performance runs, and the security diff scan close the local Gate 3 evidence
set.
