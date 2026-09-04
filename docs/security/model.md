# Security model

This document defines codex32's security boundaries and required controls for
technical reviewers and Python developers. A **validated artifact** is an
immutable Python object created after all required checks pass.

The [security invariants](invariants.md) are the mandatory high-level contract.
This document gives their controls, limitations, and verification evidence.

This model covers the `ms` master-seed profile, the `cl` Core Lightning
profile, and supported BIP39 migration artifacts. Creation and wallet controls
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
| Entropy and cryptography | The operating-system cryptographically secure random-number generator (OS-CSPRNG), BIP32, and Coincurve are trusted dependencies. |
| Bitcoin Core | The selected `bitcoin-cli`, its configuration, the selected local Core instance, and the destination computer are trusted for wallet initialization. |

## Operator assumptions

The operator must:

- use only Bitcoin Core descriptor wallets to sign with keys derived from a
  codex32 master seed;
- use computers believed malware-free and whose other software is trusted for
  all codex32 operations and for wallet initialization and signing with Bitcoin
  Core;
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

## Security limitations

- Python cannot guarantee zeroization, constant-time execution, locked memory,
  or absence of copies in runtime memory, swap, hibernation data, or crash dumps.
- Terminal input may remain in line-editing buffers or scrollback. codex32
  disables automatic Readline history, writes no history file, and cannot
  guarantee that its best-effort terminal and scrollback clearing succeeds.
- BIP32 and Coincurve are trusted cryptographic dependencies and are not
  independently audited by this project.
- Separate OS-CSPRNG calls provide opportunities to mix fresh noise but cannot
  guarantee new physical entropy between calls.
- A checksum, generation-padding hint, fingerprint, or correction candidate
  does not authenticate a backup or prove the operator's intent.
- Creation feedback can locate transcription errors but cannot prove that the
  operator corrected the physical recovery card.
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
Profile dispatch is fixed: unknown HRPs have no fallback. Recovery, derivation,
sharing, and wallet APIs do not accept raw strings.

Every derived, recovered, or corrected result is reparsed through the same
boundary. This prevents internal arithmetic from bypassing format, header,
checksum, length, padding, or application validation.

## Creation, sharing, and recovery controls

Fresh shared creation generates *k* random initial shares. Each uses a separate
full-payload OS-CSPRNG request. The current share string must be re-entered
exactly, ignoring case and whitespace, before the next request. Confirmation
text is never reparsed as the source secret and contributes no entropy.

The CLI may align and highlight substitutions, insertions, and deletions in the
entered text, but never supplies expected character values or applies a repair.
Retries are unlimited; only exact canonical equality confirms a card.

The API accepts neither caller-provided entropy nor padding values, partial
bases, or resumable ceremony state. Fresh creation rejects final-share
candidates whose generation padding is invalid. Master-seed creation also
rejects candidates that cannot form a valid BIP32 root. The original ceremony
result, not re-entered text, remains the source for automatic wallet setup.

Sharing an existing secret generates and confirms *k−1* random initial shares
before deriving the remaining shares. Recovery requires exactly the declared
threshold of compatible shares with distinct indices. Derivation requires a
new share index not used by its inputs. Every output is reparsed before release.

## Correction controls

Correction accepts damaged text outside the validated-artifact boundary. Its
output is an untrusted proposal, never authenticated recovery material.

| Control | Required behavior |
|---|---|
| Context | The HRP, separator, and program-supplied context are immutable and outside the correction domain. |
| Target lengths | `ms` searches only 48, 54, 61, 67, 74, or 127 characters; an accepted first string fixes the length of later strings in that recovery set. |
| Character indels | Automatic first-string search permits up to four total character insertions and deletions for targets 48, 74, and 127, and three for 54, 61, and 67. |
| Group indels | Every `ms` target permits up to two total insertions and deletions of complete four-character groups. |
| Fixed erasures | The BCH core supports `E + 2S <= 8`; exact-length consecutive erasures retain separate guarantees of 13 symbols for regular codex32 and 15 for Long codex32. |
| False reconstruction | The cumulative bound for every eligible structural rank must be strictly below `1e-5`. |
| Ambiguity | Equal best candidates, multiple consecutive-erasure witnesses, or an incomplete competitive frontier produce no suggestion. |
| Resources | Input and retained caches are bounded, structural views stream, and a deadline may reject automatic 48-character searches without accepting provisional results. |
| Output | Suggestions are reparsed, written to standard error, require explicit confirmation, and leave the command with a nonzero status and no secret on standard output. |

## Bitcoin Core controls

Automatic initialization applies to fresh Bitcoin master-seed creation,
sharing an existing master seed, and `codex32 wallet bitcoin-core` restoration.
Watch-only mode initializes a private-keys-disabled destination with public
descriptors.

| Control | Required behavior |
|---|---|
| Preflight | Before entropy or recovery input, explicit chain arguments probe the five standard local networks for Bitcoin Core 30 or newer. One response is selected automatically; multiple responses require operator selection. |
| Process boundary | codex32 invokes the reviewed `bitcoin-cli` from `PATH` as a child without a shell, direct RPC socket, wallet database, or wallet-creation operation. Every call uses loopback and the selected chain. |
| Destination | Only an empty descriptor wallet of the requested private-key type, with no external signer, transactions, descriptors, keypool entries, or active scan, is eligible. One eligible wallet is offered directly; multiple wallets are selected by number. New wallets are detected by polling, and rejection returns to every eligible wallet. The escaped name is confirmed exactly. |
| Seed source | Account 0 BIP44, BIP49, BIP84, and BIP86 descriptors are derived from the original ceremony result or validated recovered master seed for Core's reported chain. |
| Secret channel | Private descriptor JSON is sent only through the child's standard input. It is absent from arguments, ordinary output, and diagnostics. codex32 has no passphrase channel and suppresses raw Core errors. |
| Revalidation | Public descriptors are expanded before requesting an unlock. Every destination property is checked again immediately before import. Every import must succeed, and the exact eight expected public external/internal descriptors must match Core's accepted set. |
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
| CLI channels and input | [`test_cli.py`](../../tests/test_cli.py) and [`test_recovery_materials.py`](../../tests/test_recovery_materials.py) |
