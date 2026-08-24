# Accepted-risk register

This register records consciously retained release risks. Acceptance does not
turn a checksum into authentication or remove the verification gates in the
[production-ready v1 plan](production-ready-v1.md).

| ID | Risk and exposure | Disposition and controls | Review trigger |
|---|---|---|---|
| AR-001 | Pending BIP93 PR #2258 changes the checksum boundary for expanded HRPs. `ms` strings carrying 44--46-byte seeds can be incompatible with software implementing only the currently published BIP93 rule. | Accepted pending-standard compatibility risk. Follow the frozen PR head and boundary vectors; do not add ambiguous dual decoding. Fresh CLI generation permits only 16 or 32 bytes. The API and imported existing seeds retain all 16--64-byte BIP93 sizes. | Recheck the exact upstream revision before the RC and final release; reassess if the PR changes, closes, or merges differently. |
| AR-002 | Root-key and wallet derivation rely on `bip32` and Coincurve/libsecp256k1, which this project does not independently audit. Published `bip32` 5.0.0 metadata has a stale Coincurve `<21` limit. | Accepted architecture boundary. Keep all interaction in `_bip32.py`; retain official BIP32, BIP48, descriptor, wallet, and large differential fixtures. The tested CLI resolution carries owner-authored upstream PR #53 and hash-pins Coincurve 21 wheels for Python 3.12/3.13. Python 3.14 remains non-blocking. | Any resolved dependency or adapter change, vector failure, advisory, upstream PR change, or unsupported release artifact. |
| AR-003 | A fresh unshared `ms` identifier reveals 20 bits of the BIP32 fingerprint. Identifiers and checksums are public metadata, not authentication. | Accepted BIP93 usability/privacy tradeoff. Shared sets, supplied raw seeds, re-sharing, and CL generation instead use random or explicit identifiers. | Any workflow starts treating an identifier as secret, unique, or proof of wallet identity. |
| AR-004 | Python and terminal environments cannot guarantee secret zeroization, locked memory, constant-time execution, or removal from scrollback and editor memory. | Accepted implementation-platform limitation. Keep protected material out of argv and machine stdout, disable automatic line history, and document offline use. | A supported runtime or interface adds a stronger secret-memory or terminal boundary. |

These dispositions were accepted by the production-ready v1 roadmap. New or
materially changed risks require explicit human acceptance; agents may record
evidence but do not broaden an acceptance.
