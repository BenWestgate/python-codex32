# Security model

This document defines codex32's security boundaries and required controls for
technical reviewers and Python developers. A **validated artifact** is an
immutable Python object created after all required checks pass.

The [security invariants](invariants.md) are the mandatory high-level contract.
This document gives their controls, limitations, and verification evidence.

This model covers generic opaque-HRP codex32 artifacts, the `ms` master-seed
profile, the `cl` Core Lightning profile, and supported BIP39 migration artifacts. Creation and wallet controls
focus on Bitcoin master seeds. User safety and vulnerability reporting belong
in [SECURITY.md](../../SECURITY.md); procedures belong in the
[user guide](../user/guide.md).

## Protected assets and trust boundaries

The protected assets are master seeds, complete secrets, shares, root extended
private keys (xprvs), private descriptors, and any correction candidate that
might reveal them. Public descriptors, extended public keys (xpubs), wallet
fingerprints, and wallet history cannot spend funds but remain privacy-sensitive.

| Boundary | Security requirement |
|---|---|
| Untrusted text | Text remains untrusted until a parser or profile factory returns a validated artifact. |
| Package API | Recovery, derivation, sharing, and wallet operations accept validated artifacts, not unchecked text. |
| Python process | Secret objects remain in process memory; normal output must not reveal them unintentionally. |
| Operator and paper | The operator controls transcription, physical recovery cards, wallet records, and acceptance of correction suggestions. |
| Entropy and root keys | The operating-system cryptographically secure random-number generator (OS-CSPRNG) and Python stdlib HMAC/SHA-512 primitives are trusted. codex32 performs only BIP32 root validation and root xprv/tprv serialization in process. |
| Bitcoin Core | The selected `bitcoin-cli`, its configuration, the selected local Core instance, and the destination computer are trusted for fingerprints, hardened/public-key derivation, and wallet initialization. |

## Operator assumptions

A **trusted computer** is under the operator's exclusive control, is not known
or suspected to be compromised, and runs an operating system and other software
the operator trusts for the operation. For codex32 wallet work, that trusted
software includes the Python environment, codex32, the terminal, `bitcoin-cli`,
Bitcoin Core, and their relevant configuration. An offline trusted computer
remains disconnected from every network before, while, and after it handles
private recovery or signing material. Wallet encryption, application
permissions, and RPC authentication do not make a compromised computer trusted.

The operator must:

- use only Bitcoin Core descriptor wallets to sign with keys derived from a
  codex32 master seed;
- use only trusted computers as defined above for codex32 operations, wallet
  initialization, and signing with Bitcoin Core;
- disconnect every computer used for offline codex32 or signing work from all
  network paths, including Ethernet, internet, Tor, Wi-Fi, Bluetooth, and
  cellular;
- synchronize Bitcoin Core on the networked computer before trusting its
  balances or history;
- protect recovery cards and store shared cards in different trusted places;
- confirm every newly recorded secret or share;
- keep wallet records separate from shares and compare recovered fingerprints,
  addresses, account, policy, and history with those records;
- compare every correction suggestion with the original codex32 string and stop
  when recovered information and wallet records disagree; and
- never put recovery text in command arguments or transfer a master seed,
  share, xprv, or private descriptor through QR or a network service.

`create`, `secret`, `share`, `correct`, and `xprv` can intentionally display
secret-bearing recovery material because producing or exporting that material is
their purpose. This is distinct from accidental disclosure: unrelated status,
diagnostic, logging, and wallet-integration output must not reveal secrets.
Prompted input and standard-input redirection keep recovery text out of process
arguments, but the operator must also keep the text out of shell command text;
shell history, terminal logging, wrappers, or process tooling may retain it.

## Security limitations

- Python cannot guarantee zeroization, constant-time execution, locked memory,
  or absence of copies in runtime memory, swap, hibernation data, or crash dumps.
- Terminal input may remain in line-editing buffers or scrollback. codex32
  disables automatic Readline history, writes no history file, and cannot
  guarantee that its best-effort terminal and scrollback clearing succeeds.
- The installed Python package does not load a third-party secp256k1
  implementation. Elliptic-curve public-key derivation used for fingerprints,
  xpubs, and public descriptors is delegated to the separately running Bitcoin
  Core process.
- Separate OS-CSPRNG calls provide opportunities to mix fresh noise but cannot
  guarantee new physical entropy between calls.
- A checksum, generation-padding hint, fingerprint, or correction candidate
  does not authenticate a backup or prove the operator's intent.
- Creation feedback identifies correct groups but does not prove the recovery card was corrected.
- A fresh unshared master seed exposes a public 20-bit BIP32 fingerprint in its
  default identifier; fingerprints are metadata, not secrets.
- Private Bitcoin Core descriptors contain the root xprv and temporarily exist
  in Python objects, serialized JSON, and the child process's standard input.
- Wallet encryption belongs to Bitcoin Core. codex32 accepts an eligible
  unencrypted or unlocked encrypted wallet and never evaluates or handles a
  passphrase.
- A malicious or failing `bitcoin-cli`, Core instance, configuration, or host
  can violate the destination boundary. Process termination, power loss, or a
  Core failure can prevent application cleanup; codex32 reports when locking
  cannot be verified but cannot force an external wallet to lock.

## Validated-artifact and parsing controls

Parsing first checks the generic Bech32 container, selects the checksum type
from the generic encoded length, and validates the common codex32 header. It
then verifies the codex32 checksum. Only after checksum verification may the
human-readable part (HRP) select a profile or may codex32 enforce application
lengths or interpret payload semantics.

Only parsers and profile-specific factories construct immutable validated
artifacts. A share has symbol semantics and cannot be converted to bytes.
Default `str()` and `repr()` rendering of artifacts is redacted; callers must
use `.text` explicitly when they intentionally need the serialized recovery
string. This reduces accidental disclosure through logs and interpolation but
does not make `.text` safe to expose.
Registration adds semantics but is not required for generic parsing, recovery,
derivation, or correction. Wallet and profile-specific generation APIs do not
accept opaque artifacts or raw strings.

Every derived, recovered, or corrected result is reparsed through the same
boundary. This prevents internal arithmetic from bypassing format, header,
checksum, length, padding, or application validation.

Interactive `ms32` check, correction, sharing, `xprv`, and wallet recovery display a frozen initial `MS1`; later
entries display the validated set header. A pasted complete string keeps its
case, while suffix-only input re-cases the reconstructed frozen header to the
suffix. The displayed header is uppercase only when every accepted artifact is
uppercase and lowercase otherwise. Correction uses the effective entered-case
context, not an assumption that display case and entry case match. Prompts
without a frozen prefix require the HRP and separator. In particular,
`create --existing` tries raw hexadecimal first and otherwise requires a
complete explicit `ms1` string.

## Creation, sharing, and recovery controls

Fresh shared creation generates *k* random initial shares. Each uses a separate
full-payload OS-CSPRNG request. The current share string must be re-entered
exactly, ignoring case and whitespace, before the next request. Confirmation
text is never reparsed as the source secret and contributes no entropy. Existing
complete Bitcoin master seeds are confirmed unchanged and initialize the wallet
without new entropy. The `ms32` façade rejects CL; CL generation remains
Python-API-only. Generic sharing, recovery, inspection, and correction are
available through `codex32`.

Creation retries show only entered text in contiguous regions: bold red means review the card, with reverse video added for the active region. Original card formatting is display-only; editable prefills retain entered case and spacing.
Complete matching canonical groups freeze; local alignment preserves entered group ownership before edit minimization and proceeds without crossing frozen boundaries (see the API alignment rules).
Empty retries fail; retries are unlimited. Correct full-string retries confirm; incorrect recognizable full-string retries preserve progress and clarify the active region. Only complete case/whitespace-normalized equality confirms, with no expected characters, error classifications, prescribed edits, or repairs.
Progressive group-level correctness feedback is explicitly accepted and does not change the confirmation boundary.

Confirmation shows that the operator can produce the correct recovery string during setup. It cannot prove that the physical backup was corrected rather than reconstructed using confirmation feedback.

The API accepts neither caller-provided entropy nor padding values, partial
bases, or resumable ceremony state. Fresh creation rejects final-share
candidates whose generation padding is invalid. Master-seed creation also
rejects candidates that cannot form a valid BIP32 root. This check uses only
stdlib HMAC-SHA512 plus the secp256k1 scalar-order bound; it performs no point
multiplication. The original ceremony result, not re-entered text, remains the
source for automatic wallet setup.

Sharing an existing secret generates and confirms *k−1* random initial shares
before deriving the remaining shares. Recovery requires exactly the declared
threshold of compatible shares with distinct indices. Derivation requires a
new share index not used by its inputs. Every output is reparsed before release.

## Correction controls

Correction accepts damaged text outside the validated-artifact boundary. Its
output is an untrusted proposal, never authenticated recovery material.

| Control | Required behavior |
|---|---|
| Context | The syntactically present HRP, separator, and program-supplied context are immutable and outside the correction domain. Unknown HRPs are never corrected or ranked toward registered namespaces. |
| Target lengths | `ms` searches only 48, 54, 61, 67, 74, or 127 characters; an accepted first string fixes the length of later strings in that recovery set. |
| Character alignment | `A = I + O + AT + 2*T <= 4`; the public API retains its `A<=2` required baseline. CLI scheduling prioritizes single structural mistakes, paired indels, then other combinations. |
| Group alignment | `G = GI + GO + GS + GAT + 2*GT <= 2`; only complete displayed four-character groups participate, and character/group families never mix. |
| Fixed erasures | BCH repairs substitutions and explicit/generated erasures after alignment, with `E + 2S <= 8`; fixed consecutive erasures retain the 13/15-symbol linear path. |
| False reconstruction | All target lengths and all admitted fixed/character/group layers share cumulative mass at or below `1`, including fixed consecutive erasures. |
| Ambiguity | API required work must complete. CLI searches may return one primary-best-so-far eligible candidate at the deadline; incomplete primary ties are suppressed. Completeness metadata remains accurate, with no CLI search warning or uniqueness claim. |
| Resources | One ten-second deadline covers preparation and search, without restarting when a candidate is found. CLI competitors share one CPU and run until none can improve the result or the deadline expires. Piece tables and shifted syndrome prefixes avoid whole-body scans per alignment. No MITM is used. |
| Output | Operational candidates require explicit whole-card confirmation before acceptance; isolated Bitcoin reconstruction may only preview a fingerprint. `correct` suggestions remain nonzero-status stderr output. `check` never suggests repairs. |

Command eligibility and recovery-set compatibility are checked before a
candidate can affect CLI ranking or pruning. Fixed BCH runs first; a usable
candidate found through alignment receives the same competitor search. Every
reachable target length remains eligible under the one shared admission ledger.
Equal-volume competitors remain searchable because secondary ranking can matter.

Pruning must preserve both discovery and ranking. Fixed BCH coverage includes
explicit erasures and residual substitutions. The minimum-distance proof uses
only candidates with the same HRP and length; it never excludes another
length. A layer that cannot discover another artifact can still improve a known
artifact's capture volume or Hamming rank. Directed swap classification preserves
those explanations; unproven scoring work is retained. Repeated masks and
cancelled operations are removed only with a coverage proof. Pruning does not
reallocate the ledger's mass to additional hypotheses.

`codex32` checks, corrects, recovers, and derives shares for compatible CL,
BIP39, and opaque-HRP sets. `ms32` applies an `ms` input filter and alone owns
Bitcoin creation, xprv, and wallet commands. Both façades offer worksheet-residue
correction; only `ms32 correct` offers `--bytes`.

### Low-discrimination correction disclosure

The disclosure gate uses the cumulative conservative volume of every admitted
class ranked equal to or better than the candidate, including classes that
yielded nothing, were pruned, or remain unsearched at the deadline. It excludes
worse-ranked classes. Overlap remains conservatively charged. Short and long
checksum spaces use the admission ledger's integer scaling; no application
validation, CRC, or fingerprint adds discrimination to this calculation.

With scaled volume `C` and checksum exponent `B`, disclosure requires recovery
confirmation exactly when `32*C > 2**B`. Equality leaves five bits. This is a
union-bound engineering measure, not authentication, an entropy estimate, or a
posterior probability that the candidate is correct.

All HRPs, including `ms`, use the gate. The CLI privately computes the candidate
before printing any candidate text, metadata, fingerprint, or residue addends.
It then prints a conspicuous warning covering both deliberate completion of
newly transcribed data and recovery with many missing characters. Literal
uppercase `YES` is required before disclosure; other case variants, blank input,
or EOF terminate the command with status 1. Redirected damaged data may still
reach this gate, but disclosure requires an interactive terminal channel. If no
such channel is available, the sole message is `codex32: interactive confirmation
required` (or `ms32:`). Output formatting and `--plain` cannot bypass the gate.
Existing whole-card `[y/N]` acceptance remains required after disclosure when a
workflow will consume the corrected artifact. `correct` only displays the
suggestion, so it has no second acceptance prompt. The gate does not verify the
operator's answer.

Residue mode has no application length. It conservatively accounts over the
full checksum period and all equal-or-better decoder classes, including the
supplied erasure positions. It uses the same threshold before releasing addends.
The Python API remains an expert, noninteractive primitive: candidate objects
carry cumulative volume and its denominator exponent for clients to inspect.

BIP39 worksheet profiles are compatibility formats and are not recommended
for creation. New Bitcoin backups should use the secure random generation in
`ms32 create`.

## Bitcoin Core controls

Automatic initialization applies to fresh Bitcoin master-seed creation,
sharing an existing master seed, and direct `ms32 wallet` restoration. The CLI
initializes only private-key-enabled descriptor wallets; watch-only and offline
signing setup belong to Bitcoin Core's maintained v32 workflow.

| Control | Required behavior |
|---|---|
| Preflight | Before entropy or recovery input, explicit chain arguments probe the five standard local networks for Bitcoin Core 32 or newer. One response is selected automatically; multiple responses require operator selection. |
| Process boundary | codex32 invokes the reviewed `bitcoin-cli` from `PATH` as a child without a shell, direct RPC socket, wallet database, or wallet-creation operation. Every call uses loopback and the selected chain. |
| Destination | Only an empty descriptor wallet with private keys enabled, no external signer, transactions, descriptors, keypool entries, or active scan is eligible. One eligible wallet is offered directly; multiple wallets are selected by number. New wallets are detected by polling, and rejection returns to every eligible wallet. The escaped name is confirmed exactly. |
| Seed source | The original ceremony result or validated recovered master seed supplies root-xprv private descriptors for Core's reported chain. After import, Core v32's wallet HD-key RPCs derive the requested BIP44, BIP49, BIP84, and BIP86 account xpubs. |
| Secret channel | Private descriptor JSON is sent only through the child's standard input. It is absent from arguments, ordinary output, and diagnostics. codex32 has no passphrase channel and suppresses raw Core errors. |
| Revalidation | Every destination property is checked again immediately before import. Every private import must succeed before public verification begins. `gethdkeys` must expose one private wallet root; `derivehdkey` must return the requested hardened account paths with one consistent fingerprint and the correct network xpub/tpub version. `getdescriptorinfo` then validates and expands the fixed public templates, and the exact eight active descriptors must match Core's accepted set. |
| Relocking | Once Core reports an encrypted private-key wallet unlocked, a `finally`-protected obligation requests `walletlock` and verifies the locked state after success, failure, state change, or interruption. |

The unlock command is entered in Bitcoin-Qt. Its
[console](https://github.com/bitcoin/bitcoin/blob/master/src/qt/rpcconsole.cpp)
filters `walletpassphrase` arguments from the command displayed after submission
and from retained history; codex32 only polls wallet state.

Wallet and Core output are untrusted data. They must be parsed, type-checked,
and escaped for presentation; they never become shell syntax. A failure after
share-string confirmation leaves valid shares but an incomplete wallet
initialization.

## Verification map

| Boundary | Focused evidence |
|---|---|
| Parsing and profiles | [`test_bech32.py`](../../tests/test_bech32.py), [`test_bip93.py`](../../tests/test_bip93.py), and [`test_profiles.py`](../../tests/test_profiles.py) |
| Creation, sharing, and recovery | [`test_generation.py`](../../tests/test_generation.py), [`test_sharing.py`](../../tests/test_sharing.py), and the BIP93 vectors under `tests/data/` |
| Correction | [`test_correction_bch.py`](../../tests/test_correction_bch.py), [`test_correction_indel.py`](../../tests/test_correction_indel.py), [`correction_capture.py`](../../tools/correction_capture.py), and [`differential_correction.py --verify`](../../tools/differential_correction.py) |
| Bitcoin Core and wallets | [`test_bitcoin_core.py`](../../tests/test_bitcoin_core.py), [`test_wallet.py`](../../tests/test_wallet.py), [`bitcoin_core_regtest.py`](../../tools/bitcoin_core_regtest.py), and [`differential_wallet.py`](../../tools/differential_wallet.py) |
| CLI channels and input | [`test_cli.py`](../../tests/test_cli.py) |
