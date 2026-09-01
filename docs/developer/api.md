# API and architecture

## Architecture and review order

The package uses one narrow dependency direction:

```text
text -> bounded format/checksum -> fixed profile module -> immutable artifact
                                                   |-> BIP93 sharing
                                                   |-> ms/cl generation
                                                   |-> bounded correction
                                                   `-> MasterSeed wallet adapter

CLI -> public APIs above -> private bitcoin-cli subprocess adapter
```

The format layer first validates ASCII, case, separator, characters, and the
absolute size bound. The application parser uses the literal registered HRP
only to reject impossible total and payload lengths before checking the outer
checksum. It then validates the common header, checksum, and S-only application
semantics. No artifact crosses the parsing boundary until every stage passes.

### Specification-to-code map

| Concept | Single owner | Evidence |
|---|---|---|
| Bech32 characters, container, and `convertbits` | `bech32.py` | `test_bech32.py` |
| codex32 checksum selection and header boundary | `bip93.py` | `test_profiles.py`, BIP93 vectors |
| checksum and CRC arithmetic | `checksums.py` | official vectors, `test_crc.py` |
| fixed application rules and S types | `profiles/ms32.py`, `cl32.py`, `bip39.py` | profile and BIP39 tests |
| immutable base artifacts and interpolation | `bip93.py` | BIP93 vectors, `test_sharing.py` |
| entropy, masks, identifiers, output indices | `generation.py` | `test_generation.py` |
| shared GF(32) arithmetic | `gf32.py` | sharing vectors and correction corpus |
| fixed BCH and worksheet correction | `correction.py` | `test_correction_bch.py` |
| structural alignment | `indel.py` | `test_correction_indel.py` |
| master-seed BIP32 adaptation | `profiles/ms32.py` | BIP32 and wallet vectors |
| fixed wallet derivation and descriptors | `wallet.py` | `test_wallet.py` |
| fresh Core target selection and subprocess state | `_bitcoin_core.py` | Core adapter and regtest |
| bounded stdin and fixed-prefix TTY entry | `_cli_input.py` | `test_cli.py` |
| command grammar, dispatch, and presentation | `_cli_parser.py`, `cli.py` | `test_cli.py` |

### Boundaries

- Only parsing and profile-specific factories construct artifacts.
- `bech32.py` keeps the recognizable BIP173 reference names and accumulator
  structure. Encoding takes an explicit checksum specification. Decoding
  without one returns the HRP and complete data part after checking only the
  Bech32 container rules; decoding with one also verifies and removes that
  checksum. The module does not select codex32 checksum lengths, validate
  codex32 headers, or decode application payloads.
- `profiles/__init__.py` only normalizes a fixed HRP and selects one of three
  application modules. Labels, lengths, padding, diagnostics, and S types stay
  with their application; there is no shared profile specification or runtime
  registration.
- Headers and artifacts are immutable; shares expose symbols, not bytes.
- Sharing interpolates payload and checksum together, explicitly constructs the
  target header, and reparses the result.
- `generation.py` is the only entropy owner and generates only `ms` and `cl`.
- Correction never edits the HRP or separator and reparses every candidate.
- `profiles/ms32.py` is the only direct importer of the untyped BIP32
  dependency. `wallet.py` accepts only `MasterSeed` and has no state or generic
  parser.
- `_cli_input.py` retains at most nine artifacts and delegates partial-set
  compatibility to `bip93.py`. Its optional Readline hook restores only the
  latest rejected entry, disables automatic history, and is removed after each
  attempt. While reading, stdout's file descriptor is synchronously redirected
  to the stderr terminal and restored in `finally`, keeping piped results clean.
  There is no persistent history or raw-terminal layer.
- `_cli_parser.py` owns the complete non-abbreviating command grammar.
- `_bitcoin_core.py` is the only Core process/state adapter. It invokes no
  shell, opens no socket, and keeps wallet selection and private import out of
  stateless `wallet.py`.
- `cli.py` contains presentation and dispatch, with no domain algorithm or
  hidden state.

Private Python names are convention rather than access control. The supported
surface is the 26-name package `__all__`; direct use of private helpers is
unsupported but remains in the review scope.

### Size budget

V1 keeps the installed package below 3,000 logical review lines, excluding
blank and comment-only lines while counting subpackages recursively. Exceeding
the budget requires removing or splitting scope, not merely updating the
number.

## Fixed profile capabilities

There is no unknown-profile fallback or runtime registration.

| Capability | `ms` | `cl` | `bip39_12w/24w` |
|---|---:|---:|---:|
| parse S/share | yes | yes | yes |
| semantic S bytes | 16, 20, 24, 28, 32, or 64 | exactly 32 | no |
| checksum completion API | yes | yes | no |
| recovery and API share derivation | yes | yes | yes |
| CLI share derivation | yes | yes | no |
| unshared generation / shared ceremony API | six supported sizes | exactly 32 bytes | no |
| fresh generation CLI | six supported sizes | exactly 32 bytes | no |
| existing-S splitting | yes | yes | no |
| fixed BCH API | yes | yes | yes |
| fixed BCH CLI | yes | yes | no |
| bounded structural API | yes | yes | yes |
| bounded structural CLI | yes | yes | no |
| wallet API | S only | no | no |

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
is required. `next_share()` returns one pending card, `confirm(text)` must accept
its independently re-entered text, and `finish()` returns the secret only after
every requested card is confirmed. There is no public one-shot sharing or
`split_secret` function. Fresh Bitcoin CLI creation requires interactive input
and output, preflights local Bitcoin Core before entropy, and initializes a
user-selected wallet after every card is confirmed. Fresh Core Lightning and
all `--existing` operations retain the backup-only path. Redirected recovery
workflows remain available.

The ceremony follows the two BIP93 constructions:

- a fresh set draws `k` independent complete u5 masks;
- an existing S uses S plus `k-1` independent complete u5 masks.

Each direct share uses a separate `secrets.token_bytes` request and cannot be
followed by another draw until its card is confirmed. The pause gives the OS an
opportunity to mix fresh noise; Python cannot guarantee that new physical
entropy arrives between calls. User input is never treated as entropy. Each
byte is mapped with `value & 31`, which maps exactly eight byte values to each
u5 value.

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

BIP93 interpolation has one implementation in `bip93.py` for the four fixed
applications. No unknown HRP can reach this code.

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
3. Require one profile, threshold, identifier, encoded length, payload length,
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

The enabled codex32 checksums form GF(32)-linear codewords. For a common HRP,
threshold, and identifier, Lagrange weights sum to one, so interpolating the
existing checksum symbols produces the checksum for the explicit target index
and interpolated payload. This keeps sharing visibly symbol-only and avoids a
second checksum-generation step. Reparsing the result is mandatory: it verifies
the checksum relationship, restores the immutable artifact boundary, and
applies the target profile's S semantics.

`tests/test_sharing.py` proves that recovery and derivation still work after
checksum creation is disabled. Official BIP93 vectors anchor the GF(32)
arithmetic. CL and BIP39 use compact frozen string/result fixtures rather than
a duplicate test implementation of interpolation or checksumming.

### BIP39 migration profiles

Ordinary BIP39 shares are validated only as exact-length codex32 symbol masks.
A recovered S must additionally have zero outer padding and a valid embedded
BIP39 checksum. Derivation validates the implied S before propagating the set.
The public API may recover or derive codex32 artifacts; it never exposes BIP39
entropy, a mnemonic, construction, checksum completion, or wallet derivation.
The CLI exposes BIP39 recovery but deliberately does not expose derivation.

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

### Structural promise

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

### Capture bound and ordering

For one exact correction class, the primary decoder-capture volume is:

```text
structural alignments * fixed-core BCH capture volume
```

The fixed-core term already includes erased symbol values, so omissions are not
multiplied by `32` a second time. For an exact-length request, the runtime sums
every admitted class with primary volume no worse than a proposed result. For
an unknown-length CLI request, all reachable target lengths share one cumulative
budget rather than receiving independent allowances. Structural eligibility
requires the strict integer bound:

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

### Runtime boundary

The 48-character reference target must complete every advertised class within
ten seconds on the documented fast-laptop CPU. The largest class is two missing
plus two extra arbitrary characters, with about one million alignments. The
generic pipeline parses once, reuses erasure state, prunes only provably
impossible profile headers, and calls the same fixed corrector for every class.

The API has no deadline. For a first `ms` card, the CLI searches all six valid
lengths. Automatic mode permits four character indels for 48-, 74-, and
127-character targets and three for 54, 61, and 67; every target permits two
whole-group indels. These searches share one capture frontier. After the first
card is accepted, its length is immutable for later cards.

Only an automatic search compatible with the 48-character target receives the
ten-second deadline. A numeric `--bytes` value performs one full exact-length
search, while `--bytes ?` performs full search of all six lengths without a
deadline. CL targets 74 characters. BIP39 full-string correction remains
API-only. Every no-deadline search is normally interruptible.

### Worksheet residue API

`correct_worksheet_residue` accepts only a 13- or 15-symbol residue and uses
zero-based reverse positions. It has no profile, HRP, or complete-string length.
`()` means already correct, a tuple contains unique addends, and `None` means no
unique correction. The CLI alone converts displayed positions to one-based.

The frozen PR #70 corpus, malformed corpus, arithmetic evidence, structural
tests, and benchmarks are described in the [security model](../security/model.md)
and kept under `tests/` and `tools/`.

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

The public adapter has three functions:

- `master_xprv(secret, testnet=False)` returns the BIP32 root extended private
  key.
- `multisig_account_xpub(secret, account=0, testnet=False)` returns a native
  SegWit BIP48 account xpub with origin information at
  `m/48h/coin_typeh/accounth/2h`.
- `core_descriptors(...)` returns fixed BIP44, BIP49, BIP84, and BIP86 Bitcoin
  Core `importdescriptors` records.

Public descriptors contain account xpubs. Private descriptors intentionally
follow Bitcoin Core's root-key form: they contain the root xprv followed by the
complete derivation path. They therefore grant authority over the entire root,
not only the selected account. The CLI warns before printing them.

Account, network, private/public mode, and timestamp are explicit inputs. The
timestamp defaults to `0` so recovery scans from genesis. A nonnegative Unix
time or the literal `now` may be supplied; `now` intentionally skips historical
discovery. There is no account database, descriptor parser, policy language,
RPC library, or network client.

Fresh `ms` creation has an additional private CLI adapter. Before entropy it
resolves `bitcoin-cli` from `PATH`, forces `-rpcconnect=127.0.0.1`, requires
Core 30 or newer, and reads the connected chain. After confirmation it offers
only loaded descriptor wallets with private keys enabled, no external signer,
descriptors, transactions, keypool, or active scan. The operator selects by
number and confirms the escaped exact name; the adapter never infers a wallet
from list order or Bitcoin-Qt state.

Immediately before import, every target property is checked again. The
original `CreationCeremony.finish()` result supplies BIP44, BIP49, BIP84, and
BIP86 account-0 private records with timestamp `"now"`. Confirmation text is
never reparsed into this source. Private JSON is a single `bitcoin-cli -stdin`
argument, raw Core errors are suppressed, and no passphrase interface exists.
The adapter requires four successful imports and compares public
`listdescriptors` output with the eight external/internal expansions returned
by public `getdescriptorinfo`. It relocks wallets Core reports as encrypted.

The Core calls are fixed: `getnetworkinfo`, `getblockchaininfo`, `listwallets`,
`getwalletinfo`, `listdescriptors`, `getdescriptorinfo`, `importdescriptors`,
and `walletlock`. Bitcoin Core alone creates wallets, selects encryption,
handles passphrases, stores keys, and provides normal wallet behavior.

The CLI makes the public/private choice a mandatory goal rather than a default:

```text
codex32 wallet bitcoin-core watch-only
codex32 wallet bitcoin-core restore
```

Both commands print exactly one compact JSON line suitable for Bitcoin Core's
`-stdin importdescriptors` input. Prompts stay on stderr. Before recovery input,
`watch-only` warns against entering shares on a networked computer merely to
create a public wallet. `restore` warns before recovery input and before
emitting root-xprv descriptors. These standalone exports remain for existing
wallet recovery; they do not select, inspect, or relock a destination.

`codex32 wallet multisig-xpub` emits only this seed's origin-qualified BIP48
coordinator key. It does not define cosigners, threshold, descriptor, address,
or complete multisig policy. The direct `codex32 xprv` primitive remains
top-level and carries an explicit secret-root warning.

`tools/bitcoin_core_regtest.py` is the repeatable integration check. It starts
an isolated Bitcoin Core regtest, exercises automatic fresh initialization and
the standalone exports, reimports the accepted public descriptors into a
watch-only wallet, proves matching address and balance discovery, refuses a
watch-only spend, signs and broadcasts, and verifies relocking. It also checks
mainnet/testnet key separation and the narrow BIP48 coordinator export.

## Deliberate divergences and non-goals

These choices are not presented as BIP93 requirements.

| Decision | Reason |
|---|---|
| `ms` accepts only six seed sizes | follows the frozen PR #2258 profile with no legacy decoder |
| random electronic output indices | reduces canonical index disclosure; explicit indices preserve requested order |
| generation-only CRC padding | small recovery hint; not validity or share semantics |
| fingerprint identifier only for fresh k=0 | shared sets, raw seeds, re-sharing, and CL generation use random IDs unless explicitly overridden |
| BIP39 profiles are migration-only in CLI | website marks them not recommended; API can recover/derive codex32 only |
| reject existing derivation targets | enforces BIP93's fresh-index wording |
| bounded structural correction is deliberately finite | exact capture safety, complete global rank layers, the 48-character ten-second target, and the package audit budget exclude a general recovery engine; longer valid strings keep the same bounded classes |
| private descriptors contain root xprv | matches Bitcoin Core behavior and carries an explicit authority warning |
| no caller-supplied partial-basis completion | unauthenticated points can create incompatible same-header polynomials |

Unknown HRPs, GUI, direct sockets, a general RPC client, secret storage,
runtime profiles, BIP39 mnemonics, and arbitrary descriptor parsing are
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
