# Production-ready v1 completion plan

Status: active implementation roadmap. The mandatory new-session scan and
Gates 0--4 and 6 passed by 2026-08-25. Gate 5's local artifacts are complete;
its moderated human validation remains open, so Gate 7 has not started.

This plan turns the current reference implementation into a narrowly scoped
real-funds release. It does not add a GUI, networking, RPC, secret storage,
arbitrary descriptor parsing, runtime profile registration, BIP39 mnemonic
conversion, or complete multisig-policy construction.

## Current baseline

The plan was written against revision
`6edab4fe2007aac24656c4d00f3d00b3ce87ce6a`:

- 441 tests pass under ordinary and optimized Python 3.13;
- strict mypy, Ruff, and the frozen PR #70 differential corpus pass;
- sdist and wheel build successfully and pass Twine checks;
- the installed package contains 2,999 physical Python lines;
- the public version is locally `0.6.0`, while `0.6.1` already exists on PyPI;
- the runtime dependency is `bip32>=5,<6` and its native dependency stack;
- a read-only security review found one medium compatibility issue: the
  implementation follows pending BIP93 PR #2258 for 44--46-byte `ms` seeds.

PR #2258 behavior is an accepted pending-standard risk. Keep it, freeze its
vectors, document the affected lengths, and do not add a dual decoder. Fresh
CLI generation is restricted to the established 16- and 32-byte sizes; the API
continues to support every BIP93 size from 16 through 64 bytes.

The supported v1 claim is:

> A small, auditable, safety-first codex32 reference library and offline CLI
> that provides strong recovery and Bitcoin Core interoperability for its
> documented wallet types.

Do not claim that it is universally the safest cold-storage system, the best
possible security/ease/cost tradeoff, a complete multisig coordinator, or a
replacement for ecosystem-wide wallet and hardware support.

## Mandatory new-session security precondition

The human reviewer explicitly authorizes delegated workers for the next
repository security scan. The scan must run in a newly started session, not as
a continuation of the current four-thread session.

Before Gate 0:

1. Run the Codex Security `security_scan` configuration preflight.
2. Require `delegation_available=true`.
3. Require `usable_worker_slots_6` to pass with an actual value of at least six.
   Native V2 counts the root separately, so the session cap must be at least
   seven.
4. Confirm TAC status once immediately before substantive scan work.
5. Use one independent baseline auditor and focused investigators. Six usable
   slots are capacity, not a requirement to keep every worker busy.
6. Complete and seal the repository scan before changing production code.

The user configuration currently requests
`features.multi_agent_v2.max_concurrent_threads_per_session = 7`, but a new
session must confirm the effective runtime value. A warning, a static config
value, or six workers run sequentially under a smaller cap is not equivalent to
the required preflight result.

No implementation gate starts if this precondition fails.

### Completed precondition evidence

At revision `8aa17dcd4fea76f1a37b43f8155e060493d02aa7`, the configuration
preflight returned `status: ready`, `delegated_workers: pass`, and
`usable_worker_slots_6: pass` with six actual delegated slots under a total
seven-thread cap. TAC status was refreshed exactly once immediately before the
scan and was granted.

One independent baseline auditor and five focused investigators completed the
repository-wide standard scan. It produced one low-severity availability
finding: string share-index selectors were copied and normalized before their
31-index limit was enforced. Gate 0 bounds every selector before either step
and adds a regression across all three public generation APIs. No reportable
medium-or-higher finding remained. The previously accepted PR #2258
compatibility exposure remains tracked separately as AR-001.

## Public interface to complete

Add immutable public correction records and export them from `codex32`:

```python
@dataclass(frozen=True, slots=True)
class CorrectionContext:
    profile: Profile
    expected_length: int | None = None
    immutable_prefix: str | None = None
    excluded_indices: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class CorrectionEdit:
    kind: Literal["substitution", "erasure", "insertion", "deletion"]
    reverse_index: int
    observed: str
    replacement: str

@dataclass(frozen=True, slots=True)
class CorrectionCandidate:
    artifact: Share | Secret
    edits: tuple[CorrectionEdit, ...]
    capture_volume: int
    erasures_filled: int
    addend_hamming_weight: int
    crc_padding_match: bool | None

def correct(
    context: CorrectionContext,
    damaged_text: str,
) -> tuple[CorrectionCandidate, ...]
```

Contract:

- `expected_length` is the complete canonical string length; structural search
  requires an unambiguous expected length, while fixed-length correction may
  use the supplied string length;
- `immutable_prefix`, when present, is program-supplied text outside all
  correction and capture accounting; it is either the profile prefix or that
  prefix plus a validated, operator-confirmed threshold and identifier;
- edit reverse index zero is the final character of the corrected data/checksum
  part; an empty `observed` or `replacement` distinguishes insertion from
  deletion without involving the HRP;
- the public API completes its documented bounded search and returns all
  equally best candidates in deterministic order;
- it never returns a provisional or timed-out candidate set;
- a valid unchanged string returns one candidate with no edits;
- no correction returns `()`; malformed context raises
  `InvalidCorrectionInput`;
- all four profiles are accepted by the API; BIP39 full-string correction
  remains unavailable in the CLI;
- HRP and separator are immutable and never corrected;
- every candidate passes normal `parse_codex32` validation;
- `correct_worksheet_residue` retains its existing application-agnostic API.

Extend Bitcoin Core descriptor timestamps to accept a nonnegative Unix time or
the literal `"now"`. Keep `0` as the recovery-safe CLI default.

## Gate 0 -- Honest contract and release baseline

Objective: make documentation, metadata, and release claims match the code.

Work:

- correct stale `SECURITY.md` claims: raw seeds and re-sharing receive random
  identifiers by default, and fresh CL generation is implemented;
- record PR #2258 as accepted pending-upstream behavior;
- restrict new CLI `ms` generation to 16 or 32 bytes without restricting the
  API or imported existing seeds;
- reserve `1.0.0rc1`; update to `1.0.0` only at final release;
- update traceability, profile capabilities, source manifest, dependency
  record, and accepted-risk register;
- preserve the installed-package budget below 3,000 lines without minifying,
  merging unrelated statements, or hiding complexity in generated code.

Success criteria:

- no contradictory security or capability claim remains;
- all existing behavior outside the explicit CLI-size restriction is covered
  by tests;
- ordinary and optimized tests, mypy, Ruff, differential verification, build,
  Twine, and `git diff --check` pass.

Dependency: successful new-session scan precondition.

## Gate 1 -- Public correction and malformed-input hardening

Objective: expose a safe wallet-facing correction boundary and harden all
untrusted-text entry points.

Work:

- adapt the fixed BCH implementation to the public correction records without
  copying codec, checksum, profile, or GF(32) logic;
- preserve PR #70 substitution/erasure guarantees and semantic reparsing;
- add frozen malformed-input corpora for parsing, checksum completion,
  interpolation, correction, and CLI tokenization;
- add structured fuzz targets with bounded inputs and no runtime dependency;
- fuzz maximum-length inputs, invalid Unicode/ASCII, separators, mixed case,
  headers, profile lengths, duplicate indices, and correction erasures.

Success criteria:

- every returned artifact reparses and satisfies its profile semantics;
- fuzzing finds no crash, hang, uncontrolled allocation, or artifact-boundary
  bypass;
- fixed correction remains differential-compatible with the frozen P70 corpus;
- all four registered profiles are covered by public API tests.

Completion evidence (2026-08-24): 499 ordinary, optimized, and
Hypothesis-statistics tests pass; the two 4,096-byte fuzz targets complete 250
generated examples each; 28 frozen malformed cases and all 57 differential PR
#70 cases pass; mypy and Ruff pass; and the installed package remains at 2,999
physical Python lines.

Dependency: Gate 0.

## Gate 2 -- Generation and dependency assurance

Objective: independently establish that electronic generation and wallet-key
derivation are suitable for real funds.

Work:

- independently review OS CSPRNG use, batch mask sampling, rejection sampling,
  CRC/CL padding, identifiers, random index selection, and re-sharing;
- retain fingerprint identifiers only for freshly generated threshold-zero
  `ms` secrets; shared, supplied, re-shared, and CL secrets use random or
  explicit identifiers;
- publish a tested hash-pinned CLI installation constraint while retaining a
  compatible library dependency range;
- reconcile the documented and tested versions of `bip32`, coincurve, CFFI,
  libsecp256k1 bindings, and transitive dependencies;
- run BIP32 and wallet vectors on Python 3.12 and 3.13 across supported Linux,
  macOS, and Windows wheels;
- keep Python 3.14 as a non-blocking CI probe until the selected Coincurve
  release publishes the required wheels and the full platform matrix passes.

Do not replace `bip32` merely to work around stale dependency metadata. A
bounded `cryptography` prototype must be materially smaller and easier to audit,
fit the 3,000-line budget, match every official vector and a large differential
corpus, handle invalid scalars explicitly, and have wheels on every supported
platform before replacement is reconsidered. Bitcoin Core currently has no
interface that accepts raw seed bytes and returns this project's root key,
account xpubs, or descriptors.

Success criteria:

- no injectable or fallback entropy source exists;
- masks and selected indices remain unbiased and independent;
- shares retain symbol-only semantics;
- an independent reviewer records no unresolved medium-or-higher generation
  finding;
- exact dependency artifacts, hashes, licenses, and known-risk checks are
  reproducible.

Dependency: Gate 1.

Completion evidence (2026-08-24): upstream `bip32`'s complete seven-test suite and
all 499 project tests pass with Coincurve 21. The inspected Coincurve 20-to-21
APIs used by `bip32` are behaviorally unchanged. A 6,272-record wallet corpus
matches exactly under both versions. The owner-authored upstream range-only PR
#53 is carried by exact commit and archive hash, and all published Python 3.12
and 3.13 Coincurve wheel hashes are pinned. A bounded `cryptography` prototype
matched the vectors and corpus but failed the size, audit-surface, performance,
and wheel-coverage cut conditions, so the roadmap retains the narrow adapter.
GitHub Actions
[run 32729045916](https://github.com/BenWestgate/python-codex32/actions/runs/32729045916)
passed the required Python 3.12/3.13 matrix on Ubuntu, macOS, and Windows at
revision `aa10d59b60c375f4abbf4df241a8bf3c6ae46507`. Its non-blocking Python
3.14 probe stopped at the expected unavailable Coincurve 21 wheel.

## Gate 3 -- Bounded structural correction (passed)

Objective: reduce realistic transcription burden while keeping the BCH core
small and independently auditable.

Local implementation completed on 2026-08-25. The exact contract and evidence are in
[correction.md](correction.md), [gate3-analysis.md](gate3-analysis.md), and
[gate3-threat-model.md](gate3-threat-model.md).

The ownership invariant is: `indel.py` enumerates alignments;
`correction.py` performs all symbol repair. The adapter supplies compact
fixed-length symbol buffers and must not reimplement checksum arithmetic,
profile rules, parsing, BCH decoding, or substitution repair.

The approved user promise is: corrects up to four arbitrary missing or extra
characters, including mixtures; up to two skipped or extra four-character
groups, including one of each. Character and group structural families are
independent and never mixed. The strict cumulative false-reconstruction bound
is `P_false < 1e-5`.

The immutable prefix is outside the correction domain. It begins as the HRP
plus separator and may be extended by an interactive recovery only after a
share is validated and operator-confirmed. Suggested corrections never
establish context.

At 48 characters, every advertised class must complete within ten seconds on
the documented fast-laptop reference CPU. Longer valid strings retain the same
finite classes without a deadline. The API preserves all best-primary-volume
reconstructions. The CLI refines primary ties by Hamming weight, CRC, and then
the unshared-secret fingerprint identifier; any remaining tie is ambiguous.

Completion evidence (2026-08-25): all 557 ordinary and optimized tests pass;
the frozen 57-case differential corpus, independent constants, capture
arithmetic, strict mypy, Ruff, build, and Twine checks pass. Every final-code
48-character delta completed on the reference laptop, led by the 979,110-call
delta-zero search at 9.24 seconds. The installed package is 2,998 physical
Python lines. A six-delegate security diff scan found two Medium bounded-memory
issues; both were fixed and two fresh bypass reviews found no remaining
reportable finding. The sealed final snapshot reports complete coverage and
zero unresolved findings.

<!-- Superseded Gate 3 design history retained for audit provenance.

### Capacity model

After structural normalization, the fixed core guarantees:

- arbitrary mixed corruption with `2 * substitutions + erasures <= 8`;
- up to 13 consecutive erasures for regular codex32;
- up to 15 consecutive erasures for Long codex32.

An erroneous four-character group is fixed-length BCH damage, not an indel.
A duplicated/inserted group is extra text removed by the structural adapter.

### Design history and implemented envelope

# Gate 3 Handoff — Bounded Structural Correction Design

## Objective

Update Gate 3 so structural correction is governed by a **false-reconstruction risk model**, not by arbitrary maximum indel counts or unit edit distance.

`indel.py` remains a small structural adapter around the fixed BCH correction core.

It may generate candidate alignments and invoke fixed correction, but MUST NOT reimplement:

* checksum arithmetic;
* BCH decoding;
* Codex32 parsing;
* profile rules;
* substitution correction;
* erasure solving.

---

## Core recovery model

The simple CLI is optimized for this outcome:

```text
0 reconstructions
    correction failed

1 best reconstruction
    present it for explicit confirmation

>1 equally preferred reconstructions
    report ambiguity
    do not choose automatically
```

A dedicated recovery tool may eventually enumerate many candidates and compare them against known xpubs, descriptors, fingerprints, or addresses.

The simple CLI should not depend on such external metadata.

---

## Correct risk quantity

Do NOT use birthday-collision probability as the primary model.

Do NOT ask only whether an intermediate structural candidate is already checksum-valid.

The relevant failure event is:

> Given that the true reconstruction is within the supported envelope, what is the probability that an incorrect final Codex32 reconstruction exists with rank no worse than the true reconstruction?

Every structural candidate generated by `indel.py` is passed to the fixed BCH correction API.

Therefore each structural hypothesis has a **decoder capture volume** containing every valid reconstruction reachable through the allowed BCH substitutions/erasures.

The Gate must bound the cumulative capture volume of incorrect reconstructions that could rank before or alongside the true one.

---

## Normative safety bound

Use this initial Gate 3 target:

```text
P_false < 1e-5
```

Meaning:

> For every advertised correction class, the conservative probability bound for any distinct incorrect reconstruction ranking at least as highly as the true reconstruction must remain below 1 in 10,000.

This is a release/design bound, not necessarily a runtime probability computation.

The threshold may be tightened later.

Do not loosen it without an explicit design decision.

---

# Ranking model

## Primary ranking: decoder capture volume

Correction classes MUST be ranked by conservative decoder capture/search volume.

For a class `c`:

```text
V(c) = conservative decoder capture volume
```

A convenient mathematical score is:

```text
B(c) = log2(V(c))
```

Since logarithm is monotonic, implementations and analysis SHOULD compare exact integer volumes where practical and avoid floating-point arithmetic.

For a true class `t`, define cumulative volume:

```text
V_cumulative(t)
    = sum V(c)
      for every correction class c whose primary rank
      is no worse than t
```

Then:

```text
P_false <= V_cumulative / checksum_space
```

For regular Codex32:

```text
checksum_space = 2^65
```

For Long Codex32:

```text
checksum_space = 2^75
```

Use a conservative union bound.

Do not assume structural hypotheses are statistically independent.

---

# Why capture volume replaces raw edit count

Do NOT normatively assign:

```text
insertion     = 1
omission      = 1
substitution  = 1
```

or even:

```text
insertion     = 1
omission      = 2
substitution  = 2
```

Those are only intuition.

Actual uncertainty differs by error type.

For a roughly 48-character input:

```text
known-position erasure:
    unknown symbol value
    ~32 possibilities

accidental insertion:
    identify which observed character to delete
    ~48 possibilities

substitution:
    identify position and replacement value
    ~48 * 31 possibilities

omission:
    identify missing position and missing value
    ~49 * 32 possibilities
```

Therefore:

```text
insertion ≈ erasure
omission  ≈ substitution
```

in logarithmic uncertainty.

However, for multiple errors, combinatorial counts matter.

For example:

```text
2 arbitrary insertions
    C(n,2)

3 arbitrary insertions
    C(n,3)
```

not `n^2` and `n^3`.

The actual combinatorial capture volume therefore supersedes fixed integer weights.

---

# Structural error classes

Gate 3 should support and analyze these separately:

```text
1. arbitrary character insertion
2. arbitrary character omission
3. group-aligned insertion
4. group-aligned omission
```

Substitutions and explicit erasures remain owned by the fixed core.

Duplicated characters require no special class if already covered by insertion handling.

Adjacent transpositions require no special structural generator if fixed substitution correction already handles them.

---

# Equal-length input model

For the 48-character reference case:

```text
observed length = 48
true length     = 48
prefix          = ms1
```

If only character-level structural edits are considered, total omissions and insertions must balance:

```text
I = O
```

Examples:

```text
1 omission + 1 insertion
2 omissions + 2 insertions
3 omissions + 3 insertions
...
```

However, the search MUST remain cumulative.

For example, even if the true corruption is:

```text
2 omissions + 2 insertions
```

all lower-ranked structural/BCH explanations that could produce another reconstruction must contribute to the false-reconstruction bound.

---

# Fixed-core capacity remains independent

Structural ranking and BCH decoding capacity are separate constraints.

If `O` omissions have been hypothesized by `indel.py`, those positions are presented to the fixed core as erasures.

The fixed arbitrary-error core therefore remains constrained by:

```text
O + E + 2*S <= 8
```

where:

* `O` = hypothesized omitted characters, now represented as erasures;
* `E` = explicit user-known erasures;
* `S` = BCH substitutions.

Do not replace this with the outer capture-volume rank.

Both constraints apply:

```text
1. structural/BCH class must fit the fixed decoder;
2. cumulative false-reconstruction probability must remain below Gate 3 bound.
```

---

# Arbitrary character candidate generation

## Omission

For an omitted character, do NOT enumerate all 32 values in `indel.py`.

Insert an erasure at each candidate position:

```text
input:
    abcdf

candidates:
    ?abcdf
    a?bcdf
    ab?cdf
    abc?df
    abcd?f
    abcdf?
```

Then delegate value recovery to fixed correction.

`indel.py` discovers alignment.

The BCH core discovers values.

## Insertion

For an accidental inserted character, delete each candidate observed character:

```text
input:
    abxcdef

candidates:
    bxcdef
    axcdef
    abxdef
    abxcef
    abxcdf
    abcdef
```

Each resulting candidate is passed to fixed correction.

---

# Group-aligned correction

If recovery material is transcribed or displayed in 4-character groups, preserve those boundaries long enough for correction.

Example:

```text
ABCD EFGH IJKL MNOP ...
```

Whole-group loss, duplication, or skipping is a realistic human transcription error.

Group-level candidates SHOULD therefore be generated separately.

Examples:

```text
missing one group
    insert "????" at each plausible group boundary

extra/repeated group
    delete each observed 4-character group

missing group + extra group
    combine one group insertion with one group deletion
```

A missing group becomes four consecutive erasures passed to the fixed core.

This is especially useful because regular Codex32 has strong consecutive-erasure capability.

---

# Group errors are not equivalent to four arbitrary indels

Group formatting provides positional side information.

Example for a 48-character string divided into 12 groups:

```text
1 missing group + 1 extra group
```

has roughly:

```text
12 * 12 = 144
```

structural alignments.

The corresponding four arbitrary omissions plus four arbitrary insertions have vastly more possible alignments.

Therefore group-aligned errors MUST receive their own capture-volume calculation.

Do not charge:

```text
1 omitted 4-char group
```

the same ambiguity cost as:

```text
4 arbitrary omitted characters
```

The same applies to inserted groups.

The normative rule remains:

> Rank every error class by its actual conservative decoder capture volume.

No special exception is needed for groups.

Their lower uncertainty naturally gives them a better rank.

---

# Group-boundary handling

Do not discard presentation structure too early.

Bad:

```text
ABCD EFGH IJKL
    ↓ normalize immediately
ABCDEFGHIJKL
```

Better:

```text
parse / preserve group boundaries
    ↓
generate structural hypotheses
    ↓
normalize fixed candidate
    ↓
fixed correction
```

Grouping is side information used only for candidate generation.

It MUST NOT change checksum semantics.

---

# Substitution Hamming-distance refinement

The Bech32/Codex32 alphabet is arranged so commonly confused characters tend to have small bitwise Hamming distance.

Use this information, but do NOT replace primary capture-volume ranking with raw total Hamming distance.

Example:

```text
Candidate A:
    same structural hypothesis
    4 substitutions
    Hamming distances = 1,1,1,1
    total H = 4

Candidate B:
    same structural hypothesis
    1 substitution
    Hamming distance = 5
    total H = 5
```

Candidate B MUST rank higher.

Four separate substitutions represent a vastly larger correction/capture class than one substitution.

Raw Hamming sum would incorrectly prefer A.

---

## Correct use of Hamming distance

Hamming distance is a **secondary human-confusion prior**.

It refines candidate likelihood only after the primary structural/BCH capture class has been established.

Recommended ordering:

```text
primary:
    conservative decoder capture volume

secondary:
    substitution Hamming profile

tertiary:
    deterministic tie-break
```

For candidates in otherwise equivalent substitution classes, prefer smaller total Hamming distance.

Example:

```text
Candidate A:
    2 substitutions
    H = 1 + 1

Candidate B:
    2 substitutions
    H = 3 + 4
```

Prefer A.

---

## Do not let Hamming override the safety Gate

Example:

```text
Class A:
    cumulative P_false = 2e-5
    H = 5

Class B:
    cumulative P_false = 4e-3
    H = 1
```

Class B MUST NOT become eligible merely because its substitution looks visually plausible.

The hard envelope is still determined by false-reconstruction risk.

Hamming operates only within the approved search space.

---

# Hamming scoring detail

If desired, expose from fixed correction:

```text
substitution position
observed symbol
corrected symbol
```

Then compute:

```text
h_i = popcount(observed_value XOR corrected_value)
```

for every substituted symbol.

Candidate secondary score may use:

```text
H_total = sum(h_i)
```

or preserve the sorted Hamming profile if a more discriminating deterministic ordering is useful.

Example:

```text
[1,1,4]
```

versus:

```text
[2,2,2]
```

A simple v1 policy may use total Hamming sum.

Do not make `indel.py` understand BCH arithmetic.

It only consumes substitution metadata returned by fixed correction.

---

# False-reconstruction versus Hamming probability

Do not attempt to convert Hamming distance directly into the normative false-reconstruction bound unless an empirically justified human-error probability model is introduced.

The alphabet design establishes Hamming distance as useful confusion evidence, but not a calibrated probability distribution.

Therefore:

```text
capture volume
    normative safety/ranking quantity

Hamming distance
    human-likelihood refinement
```

Keep these separate in v1.

---

# Search behavior

Search classes in increasing primary capture-volume rank.

For each complete rank layer:

```text
0 distinct reconstructed strings
    continue

1 distinct reconstructed string
    propose it to user

>1 distinct reconstructed strings
    report ambiguity
```

Do NOT stop after finding the first structural path.

Finish the entire current rank layer so tied reconstructions are detectable.

Deduplicate by final reconstructed Codex32 string, not structural path.

Multiple structural hypotheses producing the same final string count as one reconstruction.

---

# Confirmation requirement

A corrected result MUST NOT automatically flow into secret recovery, xprv derivation, descriptor creation, or wallet operations without explicit user confirmation.

The simple CLI should clearly present the proposed correction first.

---

# Performance Gate

Probability safety and computational feasibility are independent.

Gate 3 MUST satisfy both.

For 48→48 arbitrary character correction:

```text
1O + 1I:
    small

2O + 2I:
    approximately ~1 million structural alignments
    feasible; benchmark

3O + 3I:
    approximately hundreds of millions of structural alignments
    likely infeasible within the desired simple-adapter architecture
```

Do NOT enlarge the implementation architecture solely to reach a mathematically safe class if doing so violates the objective of keeping `indel.py` small and independently auditable.

If a class passes the ambiguity Gate but fails the runtime/reviewability Gate, cut that class.

---

# Gate 3 release criteria

Gate 3 ships only if all of the following pass.

## 1. Mathematical safety

For every advertised class:

```text
P_false < 1e-4
```

using the conservative cumulative decoder-capture model.

Include:

* arbitrary character indels;
* group-aligned indels;
* supported burst cases;
* substitutions;
* explicit erasures;
* mixed classes.

## 2. Completeness

All structural hypotheses inside the advertised class are generated.

No lower-ranked class is skipped.

## 3. Fixed-core isolation

`indel.py` contains no:

* checksum arithmetic;
* BCH decoder;
* field arithmetic;
* substitution solving;
* erasure solving;
* duplicated parser/profile logic.

## 4. Deduplication

Distinct structural paths resulting in the same corrected Codex32 string are deduplicated before ambiguity handling.

## 5. Hamming refinement

Substitution metadata may refine ranking only after primary capture-volume ranking.

Hamming must never expand the approved safety envelope.

## 6. Performance

Every advertised worst-case class completes within the defined consumer-CPU budget.

Use an explicit reference target, e.g.:

```text
<= 10 seconds worst-case correction search
```

on the documented baseline consumer system.

## 7. Bounded resources

Worst-case runtime and memory are statically bounded by the supported envelope.

Untrusted input cannot trigger unbounded structural search.

## 8. Corpus

Test:

* generated valid Codex32 strings;
* substitutions;
* explicit erasures;
* arbitrary insertions;
* arbitrary omissions;
* balanced equal-length indels;
* group omissions;
* group insertions;
* repeated groups;
* mixed structural + BCH corruption;
* boundary classes immediately inside/outside the envelope.

Measure:

```text
true candidate recovered
distinct false reconstructions
ambiguous cases
runtime
memory
```

## 9. Independent review

The structural adapter and its candidate generators must be reviewable independently from the BCH implementation.

The mathematical envelope SHOULD be reproducible from a small analysis program separate from runtime code.

---

# Recommended implementation split

```text
analysis/
    structural_capture.py
    generate_gate3_envelope.py

codex32/
    correction.py
    indel.py

tests/
    test_indel_character.py
    test_indel_groups.py
    test_indel_mixed.py
    test_indel_hamming_rank.py
    test_gate3_envelope.py
    test_gate3_boundary.py
    test_gate3_performance.py
```

The analysis code may calculate large integers, logarithms, cumulative bounds, and tables.

Runtime `indel.py` SHOULD consume a small frozen policy or simple generated constants.

Do not put probabilistic modeling or floating-point ranking machinery into the security-critical runtime unless necessary.

---

# Updated Gate 3 principle

Replace wording based on raw limits such as:

```text
supports up to N omissions and N insertions
```

with:

> Gate 3 supports bounded character-level, and group-level structural correction only for corruption classes whose cumulative decoder capture volume keeps the conservative probability of an incorrect reconstruction at equal or better primary rank below the Gate threshold, while also meeting the runtime and reviewability budgets.

Use:

```text
P_false < 1e-5
```

as the initial safety threshold.

Primary rank is decoder capture volume.

Substitution Hamming distance is a secondary human-confusion refinement.

Group structure is legitimate positional side information and reduces capture volume accordingly.

The implementation should remain intentionally smaller than a general recovery search engine.

Eight insertion-only groups were measured as searchable on one development
machine, but that is an unlikely human-error mode and is not a required v1
contract. Broader coverage may be retained only when it adds little code and
passes every platform budget.

### Superseded likelihood handoff

The following likelihood/work notes were an earlier handoff. Runtime does not
implement them: exact integer capture volume is primary, addend Hamming weight
is secondary, and CRC/fingerprint agreement affects display order only.

### Historical search and ranking

- constrain candidates using the known profile, target length, immutable
  five-symbol set header, and excluded indices before ranking, but count
  repairable header disagreements against the remaining substitution capacity;
- deduplicate fixed-length candidates before invoking BCH;
- rank first by exact decoder-capture volume, then by known-substitution
  addend Hamming weight;
- use generation CRC match only as a final secondary hint for applicable `ms`
  S candidates; it never validates, prunes, or hides a candidate;
- retain all exact acceptance-rank ties; CRC and fingerprint agreement only
  order their presentation.

### API and CLI completeness

- the API exhaustively completes the published envelope without a deadline;
- the CLI targets ten seconds for the complete common 48-character search;
- longer valid targets retain the same bounded classes without that deadline;
- CL has one fixed expected length; `ms` defaults to the established 48- and
  74-character targets, while an unusual imported BIP93 size requires an
  explicit expected byte length;
- a CLI timeout reports failure and does not display or accept a provisional
  candidate;
- corrections are never silent and always require comparison with the written
  backup.

### Gate result

Gate 3 passed these cut conditions:

- fixed plus structural correction is below 1,500 physical lines;
- the installed package is below 3,000 physical Python lines;
- API search is deterministic and completes every class that can affect its
  result;
- the larger grouped worst-case 48-character envelope, including the complete
  979,110-call `2O + 2I` generator, takes 8.75--8.96 seconds across three runs
  on the documented Ryzen 7 7735U reference laptop;
- `2O + 2I + 0S/1S/2S` use one fixed-core path and complete within the same
  ten-second envelope;
- the safe one-group, grouped-plus-character, and contiguous two-group-pair
  classes use that fixed core and fit the same aggregate envelope;
- lossless trusted-header pruning and global-frontier early stopping have
  direct regressions;
- longer valid strings are never refused merely because their bounded search
  takes longer;
- structural, mixed, group, rank, malformed, and boundary tests pass; and
- `indel.py` remains a narrow structural adapter over the fixed symbol core.

-->

Dependency: Gates 1--2.

## Gate 4 -- CLI and Bitcoin Core workflow (passed)

Objective: complete the supported ordinary-user recovery paths without growing
into a wallet or coordinator.

Work:

- during TTY recovery, try supported correction after validation failure and
  show candidates for explicit comparison with the written backup;
- never correct redirected stdin automatically;
- preserve `stdin = protected input`, `stderr = interaction`, and
  `stdout = requested machine result`;
- add `--timestamp now` while keeping timestamp zero as the recovery default;
- automate Bitcoin Core integration for watch-only import and balance discovery,
  encrypted private restore, signing and broadcast, mainnet/testnet vectors,
  and multisig origin-qualified xpubs;
- describe `multisig-xpub` as a single-purpose coordinator export, not a full
  policy builder.

Success criteria:

- an installed wheel completes supported single-key recovery with Bitcoin Core;
- watch-only output contains no private key and restore requires an explicit
  private mode plus warning;
- no protected material appears in argv, logs, machine stdout, or fixtures;
- CLI prompts, interrupts, retries, correction confirmation, and exit statuses
  have exact subprocess coverage.

Dependency: Gate 3, whether implemented or cleanly cut.

Completion evidence (2026-08-25): interactive correction is available only
with program-supplied immutable-prefix context, requires explicit operator
confirmation, and is never attempted for redirected stdin. `--timestamp now`
is accepted by the API, CLI, and Bitcoin Core. Exact parser/TTY tests cover
first and subsequent confirmations, declined input, immutable context,
redirection, prompts, and stream separation. `tools/bitcoin_core_regtest.py`
passed against Bitcoin Core 31.1.0 from clean wheel and sdist environments: it
imported timestamp-zero and `now` watch-only records, discovered a balance,
proved spend refusal, imported private records into an encrypted wallet,
unlocked, signed, broadcast, confirmed, and relocked. Mainnet/testnet extended
keys and the origin-qualified BIP48 coordinator export were checked in the same
run. No protected value entered argv or machine stdout.

## Gate 5 -- Recovery card, inheritance, and usability appraisal (human validation incomplete)

Objective: let an owner or heir recover without remembering this repository.

Artifacts:

- a one-page printable share card with blank protected-text area, BIP93/codex32
  identification, threshold, identifier, share index, network and wallet-policy
  fields, offline warnings, and concise recovery steps;
- a manual fallback pointing to a durable, versioned offline copy of the
  Codex32 Book Recovery Wheel and Translation Worksheet;
- a separate optional wallet-verification record containing fingerprint or
  address, account, derivation, multisig policy, coordinator, and cosigner
  information;
- no fingerprint or address duplicated beside every share;
- watch-only verification before private restoration.

Validation uses dummy secrets only:

- at least ten moderated participants;
- at least five unfamiliar with this repository;
- at least three heir scenarios where the participant did not create the
  backup;
- estimate successful recovery rate without an online secret disclosure;
- estimate the under-one-hour setup target for the current workflow;
- exclude Bitcoin Core synchronization and recovery rescans from setup time;
- record the earlier reported Bails beta testing as context, not as a substitute
  for this card-specific validation: 24 testers, including at least three who
  did not create the backup, reportedly completed the workflow in under 30
  minutes.

Success criteria:

- every participant should be able to identify the correct recovery path from
  the card;
- no critical intervention is needed;
- failed or confusing steps cause documentation/UI changes and another gate
  iteration;
- claims use measured results and avoid absolute superlatives.

Dependency: Gate 4.

Local evidence (2026-08-25): the printable one-page share card, separate
wallet-verification record, manual fallback identifier/digest, inheritance
workflow, static separation tests, and moderated-study protocol are complete.
The share card has 32 blank four-character groups and contains neither a
fingerprint nor receiving address. The separate record contains the wallet and
multisig verification fields and no protected-text area. Gate 5 remains open
until the required moderated participants complete this specific workflow; the
reported earlier Bails testing is context, not fabricated replacement evidence.

## Gate 6 -- Human reviewability refactor (passed)

## Purpose

Before work is considered finished, spend a fixed amount of time reducing the
amount and complexity of installed code that a human must review for safety and
functionality.

The goal is not merely fewer physical lines. The goal is a smaller, more direct,
more obviously correct implementation. That matches the style of BIP93 and Bech32
reference.

Prefer deletion and simplification over abstraction.

## Timebox

Spend **45 minutes maximum** on this reviewability pass.

The 45-minute limit applies to analysis and editing. Time required to run the
required test, lint, type-check, and build commands does not count against the
editing timebox.

Stop making refactoring changes when the timebox expires. Do not extend the
timebox merely to reach a line-count target.

Reserve the final part of the pass for a separate human-reader self-review.

## Hard constraints

The following constraints override line-count reduction:

* Preserve existing CLI behavior.

  * Do not change commands, options, defaults, prompts, exit status, output
    meaning, or stdout/stderr separation.
  * Existing CLI tests define behavior where applicable.
* Preserve the public Python API during this pass.

  * Potential API removals belong in `/docs`, not in this refactor.
* Preserve every security property documented in `SECURITY.md`.
* Preserve normative BIP93 behavior and the project's documented divergences
  and accepted risks.
* Do not weaken, delete, skip, or rewrite tests merely to make a refactor pass.
* Do not replace explicit validation with assertions.
* Do not make correction output trusted input.
* Do not weaken validated-artifact boundaries.
* Do not introduce new dependencies for the purpose of reducing source code.
* Do not mix an unrelated feature or behavior change into this pass.

If reducing code requires crossing one of these boundaries, document the
candidate instead of implementing it.

## Primary objective

Reduce installed Python source under `src/codex32/`.

Measure physical Python source lines before and after the pass.

```sh
find src/codex32 -type f -name '*.py' -exec cat {} + | wc -l

find src/codex32 -type f -name '*.py' \
    ! -name correction.py \
    ! -name indel.py \
    -exec cat {} + | wc -l

wc -l src/codex32/*.py | sort -n
```

Targets:

1. Installed package: **must not grow** and should decrease.
2. Installed package: **prefer below 2,000 lines**.
3. Installed package excluding `correction.py` and `indel.py`:
   **prefer below 1,000 lines**.
4. A pass does not require reaching the preferred targets if doing so would
   make the implementation denser, less explicit, less safe, or behaviorally
   incompatible.

Physical line count is a review-cost signal, not the objective by itself.

Do **not** reduce line count by removing useful whitespace, chaining statements,
using dense comprehensions, introducing metaprogramming, hiding logic behind
generic helpers, or otherwise making individual lines harder to audit.

## Secondary objective

Reduce files a user may encounter while trying to understand or code review this project. If files can be combined without a loss of needed modularity or beneficial separation of concerns and it makes understanding and discovering multiple components or concepts in one view faster do so. Too many separate files can be overwhelming for humans to view and can make logic difficult to follow.
This applies to src/ tests/ tools/  For example 3 different CLI files seem created to stay under an arbitrary line limit rather than actual need or review benefit.
Another project should be able to import any module from this project and do something useful with it.


## Refactoring priority

Work in this order:

1. Delete code that is unnecessary.
2. Remove duplicated logic.
3. Remove unnecessary wrappers, forwarding methods, aliases, and indirection.
4. Collapse abstractions that exist only to serve one caller and do not enforce
   a meaningful safety boundary.
5. Move duplicated domain behavior out of the CLI rather than maintaining two
   implementations.
6. Simplify conditionals and data flow.
7. Reduce unnecessary conversions between equivalent representations.
8. Remove unused exports and implementation-only public surface where doing so
   does not change the documented public API.
9. Improve misleading or inconsistent names.
10. Remove comments and docstrings that merely repeat the code.
11. Add or retain comments where they explain a non-obvious reason, invariant,
    compatibility constraint, security boundary, or upstream divergence.

Prefer a direct three-line implementation over a reusable ten-line abstraction
when there is only one real use case.

Do not apply DRY mechanically. Two small pieces of security-sensitive logic may
be easier to audit separately than one generalized helper with flags and
multiple modes.

## Reference style and terminology

Where this project implements concepts directly derived from BIP93 or Bech32,
prefer terminology and structure that makes comparison with the reference
material straightforward.

In particular:

* Prefer the vocabulary used by BIP93 and the Bech32 reference implementation.
* Preserve recognizable names such as `CHARSET`, checksum/polymod terminology,
  shares, threshold, identifier, payload, HRP, and related normative concepts.
* When a function closely implements a reference algorithm, prefer a similarly
  direct functional structure instead of wrapping it in unnecessary objects.
* Use `snake_case` for Python functions, methods, arguments, variables, and
  modules.
* Use `CapWords` for Python types.
* Use `UPPER_CASE` for constants.
* Use a leading underscore for implementation-private helpers.
* Prefer small functions with explicit inputs and return values.
* Avoid wildcard imports.
* Use type hints where they improve reviewability or catch mistakes.
* Keep multi-name imports predictable and sorted.
* Give test modules a short module-level explanation of the behavior and
  evidence being tested.

Prefer lines under **100 characters** when that improves or preserves
readability. Longer lines are acceptable when breaking them would make the
code less clear.

Do not contort code merely to satisfy a line-length number.

## Comments

Comments should normally answer **why**, not **what**.

Good reasons for a comment include:

* why behavior intentionally differs from an obvious alternative;
* why an upstream algorithm is reproduced in a particular form;
* why a validation must happen before another operation;
* why two apparently similar cases cannot be combined;
* why an apparently redundant check is security-relevant;
* why compatibility requires unusual behavior;
* why a particular representation or boundary exists.

Remove comments such as:

```python
# Increment the counter.
counter += 1
```

Prefer code whose names make the operation apparent.

When a non-obvious decision comes from BIP93, Bech32, Bitcoin Core, a frozen
upstream revision, or an accepted project divergence, leave enough context for
a human reviewer to locate the reason without reverse-engineering it.

## Human-reader self-review

Before finishing, stop editing and review the resulting code as though you were
a security-conscious human seeing the project for the first time.

Do not review it from the perspective of the person or agent that just wrote
the code.

Explicitly look for:

* duplicated logic;
* unnecessary abstractions;
* unnecessary classes or dataclasses;
* one-use helpers that obscure rather than clarify;
* wrapper functions that add no invariant;
* overly generic functions with flags or mode parameters;
* repeated validation or conversion logic;
* confusing differences in terminology from BIP93 or Bech32;
* public names that should actually be private;
* private implementation details unnecessarily exported from `__init__.py`;
* needless state or mutation;
* functions that mix parsing, validation, policy, formatting, and I/O;
* domain behavior duplicated inside `cli.py`;
* comments that explain syntax instead of rationale;
* tests coupled to implementation details instead of observable behavior;
* error handling that has become more complicated than the operation itself;
* code that became shorter but harder to verify;
* code whose safety depends on a subtle interaction between distant modules.

For each abstraction, ask:

> Would a human reviewer understand this code faster if the abstraction did not
> exist?

For each helper, ask:

> Does this helper enforce a real invariant or remove meaningful duplication,
> or does it merely move lines elsewhere?

For each non-obvious branch, ask:

> Can a reviewer tell why this case exists?

For every changed security-sensitive path, ask:

> Can I demonstrate from the tests and surrounding code that the refactor
> preserved the original safety boundary?

If the shorter version requires more explanation than the longer version,
prefer the clearer version.

## Future removals

During the pass, do not silently preserve features or APIs simply because
removing them is outside the current compatibility constraints.

Record significant simplification opportunities in:

`docs/reviewability-removals.md`

For each candidate, record:

* feature, API, command, compatibility layer, or abstraction proposed for
  removal;
* files and modules it affects;
* approximate source lines or concepts that could disappear;
* why removal would make human safety/functionality review easier;
* compatibility cost;
* security implications;
* tests and documentation that could disappear with it;
* whether deprecation is required;
* recommended release or migration boundary.

Prioritize candidates that would remove entire concepts, states, compatibility
paths, or modules rather than merely shorten individual functions.

Do not implement those removals as part of this gate unless they were already
approved as part of the task.

## Verification

After the editing timebox ends, run the repository's normal verification:

```sh
python -m pytest -q
python -O -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy src/codex32
python -m build
python -m twine check dist/*
```

Where applicable, also run the installed-wheel verification and relevant
offline differential tests.

A refactor is not successful merely because unit tests pass. Confirm that the
CLI contract and documented security invariants remain unchanged.

## Gate result

Finish with a compact reviewability report containing:

**Before**

* total installed Python lines;
* installed Python lines excluding `correction.py` and `indel.py`;
* largest installed modules.

**After**

* the same measurements;
* net lines removed;
* modules/functions deleted, merged, or simplified.

**Human review**

* duplicated logic found and removed;
* unnecessary complexity found and removed;
* non-obvious decisions documented;
* any places deliberately left less compact because the explicit form is
  easier to audit.

**Compatibility**

* confirmation that CLI behavior was preserved;
* confirmation that no public API was intentionally removed;
* confirmation that security invariants were preserved.

**Future reduction**

* significant feature/API removal candidates added to
  `docs/reviewability-removals.md`.

The gate passes when verification succeeds and either:

1. installed review surface is measurably reduced; or
2. the timebox finds no safe further reduction, and the remaining significant
   opportunities are explicitly documented because they require an API,
   behavior, security-model, or compatibility decision.

Never manufacture a line-count reduction merely to make the gate pass.

Dependency: Gate 4.

Completion evidence (2026-08-25): the timeboxed pass reduced installed Python
from 2,998 to 2,997 physical lines without changing the public API or existing
CLI contract. It removed duplicated correction deadline setup and small
forwarding/alias overhead while preserving explicit module boundaries. The
three CLI modules were considered for consolidation and retained because they
separate grammar, protected terminal input, and dispatch/presentation. Full
ordinary and optimized tests, Hypothesis, strict mypy, Ruff, differential
checks, package builds, Twine, clean installed-artifact checks, and Bitcoin Core
31.1.0 integration pass. Repeated builds with `SOURCE_DATE_EPOCH` produce
byte-identical wheels and sdists. The full before/after and human-reader review
is in `docs/gate6-reviewability.md`; product-level removal candidates are in
`docs/reviewability-removals.md`.


## Gate 7 -- Final independent audit and release candidate (blocked by Gate 5)

Objective: review the final artifact rather than an intermediate design.

Required evidence:

- independent correction audit, including `indel.py` only if Gate 3 ships;
- independent specification-to-code review of every traceability row;
- repository security scan using the required six usable delegated slots;
- extended malformed-input and fuzz campaigns;
- clean Bitcoin Core integration from both wheel and sdist;
- reproducible build, dependency manifest, and package-content comparison;
- clean installation and CLI smoke tests on supported Python 3.12 and 3.13,
  with Python 3.14 reported separately as non-blocking compatibility evidence.

Release criteria:

- no unresolved, unaccepted medium-or-higher finding;
- PR #2258 remains documented with exact upstream revision and vectors;
- all tests, optimized tests, mypy, Ruff, formatting check, differential
  correction, fuzzing, Core integration, build, Twine, size checks, and
  `git diff --check` pass;
- publish `1.0.0rc1` for at least 30 days of public human review;
- resolve all RC findings before `1.0.0`;
- only the human maintainer pushes, opens a PR, publishes packages, writes
  maintainer comments, or authorizes use with real funds.

Dependencies: Gates 0--6

## Verification commands

Each behavior-changing commit and every completed gate runs the applicable
focused tests plus this final set:

```bash
python -m pytest -q
python -O -m pytest -q
python -m pytest -q --hypothesis-show-statistics
python -m mypy src/codex32
python -m ruff check .
python -m ruff format --check .
python tools/differential_correction.py --verify
python -m build
python -m twine check dist/*
python -c "from pathlib import Path; assert sum(len(p.read_text().splitlines()) for p in Path('src/codex32').glob('*.py')) < 3000"
git diff --check
```

Gate-specific fuzz, correction-budget, dependency, and Bitcoin Core commands
must be checked into the repository before their gate can complete. Tests may
not be skipped, weakened, regenerated from production code, or changed merely
to accept a regression.

## Work and publication discipline

- Preserve unrelated work and the validated-artifact security boundaries.
- Keep formatting, file moves, refactoring, and behavior changes in separate
  local commits.
- Every local commit must build and pass its focused and regression tests.
- Do not begin a later gate while any success criterion is unmet.
- Do not reinterpret a failed gate as complete; Gate 3 alone has the explicit
  clean-removal path.
- Agents do not push, publish, open pull requests, or speak for maintainers.
