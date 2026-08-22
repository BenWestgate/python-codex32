# Public API

The package root exports 19 names:

- types: `Profile`, `Header`, `Share`, `Secret`, `MasterSeed`,
  `CoreLightningSecret`, `Bip39Secret`, and `WorksheetCorrection`;
- format/sharing: `parse_codex32`, `complete_checksum`, `recover_secret`, and
  `derive_share`;
- generation: `generate_master_seed` and `split_secret`;
- correction: `correct_worksheet_residue`;
- wallet: `master_xprv`, `multisig_account_xpub`, and `core_descriptors`; and
- the base `CodexError`.

Focused exception types remain in `codex32.errors` rather than expanding the
package root.

Unsafe earlier interfaces have no compatibility shim:

| Removed | Replacement |
|---|---|
| mutable `Codex32String` | immutable result from `parse_codex32` |
| generic encode/decode and arbitrary HRPs | four fixed profiles |
| byte construction/access on shares | `Share.payload_symbols` only |
| generic `from_seed` and padding control | `MasterSeed.from_seed` |
| `_interpolate_at` | `recover_secret`, `derive_share` |
| CLI-owned generation | `generate_master_seed`, `split_secret` |
| correction search/result framework | fixed BCH adapter and residue API |
| generic descriptor/policy parser | three fixed wallet functions |

`recover_secret` requires exactly k ordinary shares. `derive_share` accepts an
exact basis, including S, but rejects S or an existing target. Generation
returns `(secret, shares)` and never sorts requested or sampled output order.

Errors from malformed external input derive from `CodexError`. Supplying raw
strings to typed domain APIs is programmer misuse and raises `TypeError`.
