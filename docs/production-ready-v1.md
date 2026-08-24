# Production-ready v1 completion plan

Status: accepted implementation roadmap; no gate may begin until the scan
precondition below passes in a new session.

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

## Public interface to complete

Add immutable public correction records and export them from `codex32`:

```python
@dataclass(frozen=True, slots=True)
class CorrectionContext:
    profile: Profile
    expected_length: int | None = None
    expected_header: str | None = None
    excluded_indices: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class CorrectionEdit:
    kind: Literal[
        "substitution", "erasure", "insertion", "deletion", "transposition"
    ]
    reverse_index: int
    observed: str
    replacement: str

@dataclass(frozen=True, slots=True)
class CorrectionCandidate:
    artifact: Share | Secret
    edits: tuple[CorrectionEdit, ...]
    estimated_search_bits: float
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
- `expected_header`, when present, is exactly threshold plus the four-character
  identifier; the share index remains a correction variable constrained by
  `excluded_indices`;
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
- run BIP32 and wallet vectors on Python 3.12--3.14 and supported Linux, macOS,
  and Windows wheels.

Do not replace `bip32` with locally implemented BIP32. Bitcoin Core currently
has no interface that accepts raw seed bytes and returns this project's root
key, account xpubs, or descriptors. A Core proposal belongs to a separate
project.

Success criteria:

- no injectable or fallback entropy source exists;
- masks and selected indices remain unbiased and independent;
- shares retain symbol-only semantics;
- an independent reviewer records no unresolved medium-or-higher generation
  finding;
- exact dependency artifacts, hashes, licenses, and known-risk checks are
  reproducible.

Dependency: Gate 1.

## Gate 3 -- Cuttable bounded structural correction

Objective: reduce realistic transcription burden while keeping the BCH core
small and independently auditable.

The structural adapter lives in `indel.py`. It generates fixed-length
candidates and calls the fixed correction API. It must not reimplement checksum
arithmetic, profile rules, parsing, or BCH decoding.

### Capacity model

After structural normalization, the fixed core guarantees:

- arbitrary mixed corruption with `2 * substitutions + erasures <= 8`;
- up to 13 consecutive erasures for regular codex32;
- up to 15 consecutive erasures for Long codex32.

An erroneous four-character group is fixed-length BCH damage, not an indel.
A duplicated/inserted group is extra text removed by the structural adapter.

### Minimum envelope if Gate 3 ships

- at least two arbitrary individual omissions;
- at least two arbitrary individual insertions;
- at least two adjacent transpositions;
- two arbitrary omitted, group-aligned four-character groups, restored as
  eight erasures;
- three omitted group-aligned groups when contiguous, restored as twelve
  consecutive erasures;
- four arbitrary inserted four-character groups, including cases that still
  need BCH correction after deletion;
- up to four exact adjacent duplicated groups through a duplicate-specific fast
  path.

Eight insertion-only groups were measured as searchable on one development
machine, but that is an unlikely human-error mode and is not a required v1
contract. Broader coverage may be retained only when it adds little code and
passes every platform budget.

### Search and ranking

- constrain candidates using the known profile, target length, immutable
  five-symbol set header, and excluded indices before ranking;
- deduplicate fixed-length candidates before invoking BCH;
- rank first by a frozen, evidence-backed negative-log structural likelihood
  and estimated search work;
- then use erasures filled and the sum of known substitution-addend Hamming
  weights;
- use generation CRC match only as a final secondary hint for applicable `ms`
  S candidates; it never validates, prunes, or hides a candidate;
- train and evaluate likelihood data on separate dummy-error corpora; retain all
  exact best-rank ties.

### API and CLI completeness

- the API exhaustively completes the published envelope without a deadline;
- the CLI has a ten-second default deadline;
- CL has one fixed expected length; `ms` defaults to the established 48- and
  74-character targets, while an unusual imported BIP93 size requires an
  explicit expected byte length;
- a CLI timeout may display the best candidate found on stderr as provisional,
  but cannot accept it into recovery or machine stdout;
- corrections are never silent and always require comparison with the written
  backup.

### Cut line

Gate 3 is removed wholesale and deferred to v1.1 if any condition fails:

- fixed plus structural correction exceeds 1,000 physical lines;
- the installed package reaches 3,000 lines;
- supported searches are nondeterministic or incomplete in the API;
- worst-case memory or CLI time exceeds its frozen budget;
- intended candidates are missing from the best-ranked ties in the independent
  holdout corpus;
- an independent reviewer finds the implementation too difficult to audit.

Dependency: Gates 1--2.

## Gate 4 -- CLI and Bitcoin Core workflow

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

## Gate 5 -- Recovery card, inheritance, and usability evidence

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
- 100% successful recovery without an online secret disclosure;
- measure the under-one-hour setup target for the current workflow;
- exclude Bitcoin Core synchronization and recovery rescans from setup time;
- treat earlier Bails beta testing as supporting, not substitutive, evidence.

Success criteria:

- every participant can identify the correct recovery path from the card;
- no critical intervention is needed;
- failed or confusing steps cause documentation/UI changes and a repeated trial;
- claims use measured results and avoid absolute superlatives.

Dependency: Gate 4.

## Gate 6 -- Final independent audit and release candidate

Objective: review the final artifact rather than an intermediate design.

Required evidence:

- independent correction audit, including `indel.py` only if Gate 3 ships;
- independent specification-to-code review of every traceability row;
- repository security scan using the required six usable delegated slots;
- extended malformed-input and fuzz campaigns;
- clean Bitcoin Core integration from both wheel and sdist;
- reproducible build, dependency manifest, and package-content comparison;
- clean installation and CLI smoke tests on Python 3.12--3.14.

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

Dependencies: Gates 0--5.

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
