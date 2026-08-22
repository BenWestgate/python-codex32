# Public API migration through Gate 4

Gate 1 intentionally removes unsafe APIs without compatibility shims.

| Removed pattern | Safe replacement |
|---|---|
| `Codex32String(text)` | `parse_codex32(text)` |
| `Codex32String.from_unchecksummed_string(text)` | `complete_checksum(text)` for registered `ms` or `cl` only |
| `Codex32String.from_seed(bytes, prefix, padding)` | `MasterSeed.from_seed(bytes, identifier=..., threshold=...)` |
| CL bytes through generic `from_seed` | `CoreLightningSecret.from_secret_bytes(bytes, identifier=..., threshold=...)` |
| `.s`, `.hrp`, `.k`, `.ident`, `.share_idx` | `.text`, `.profile`, and immutable `.header` |
| `.data` on every string | `.seed_bytes` on `MasterSeed` or `.secret_bytes` on `CoreLightningSecret` |
| `.payload` and `.pad_val` | `.payload_symbols` on all artifacts; no public padding value |
| mutation followed by automatic rechecksumming | construct a new validated artifact through an allowed factory |
| private `_interpolate_at(items, "s")` | `recover_secret(shares)`; ordinary shares only and exactly `k` |
| private `_interpolate_at(items, index)` | `derive_share(basis, index)`; fresh ordinary target only |
| CLI/private `_basis_for_fresh_seed` | `generate_master_seed(...)` or `generate_core_lightning_secret(...)` |
| CLI/private `_basis_for_seed` | `split_secret(secret, threshold, ...)` for authenticated `ms`/CL S only |
| canonical first-N electronic outputs | `share_count=N` for a random ordered sample, or `indices="7cad"` for exact order |
| excluded identifier | five-symbol `excluded_headers`, API-only and bounded to 1,024 entries |
| `corrections_from_residue(residue, length=...)` | `correct_worksheet_residue(residue, erasure_indices=...)`; reverse index 0 is final |
| root-exported correction search/result records | no Gate 4 replacement; structural search is internal pending Gate 5 |

Example:

```python
from codex32 import MasterSeed, Share, parse_codex32

artifact = parse_codex32(recorded_text)
if isinstance(artifact, MasterSeed):
    bip32_seed = artifact.seed_bytes
elif isinstance(artifact, Share):
    symbols = artifact.payload_symbols
```

Parsed text preserves a valid uppercase or lowercase representation. New
factories emit lowercase. BIP39 migration artifacts deliberately have no raw
entropy, mnemonic, checksum-completion, generation, or wallet API.

`recover_secret` and `derive_share` accept authenticated artifacts, not strings.
Parse each input first. Legacy interpolation exception names are removed; the
public errors distinguish count, compatibility, duplicate, recovery-S, and
target failures. Existing targets are errors rather than idempotent lookups.

Generation functions return `(secret, shares)`. `generate_*` permits threshold
zero and then rejects either share selector. `split_secret` is deliberately a
threshold-2–9 operation. Shared generation requires exactly one of
`share_count` or `indices`; neither result path is sorted.

`generate_master_seed(seed_bytes=...)` requires an explicit identifier because
raw entropy provenance is unknown. `split_secret(MasterSeed, ...)` may apply the
reviewed deterministic default, but the typed artifact cannot prove how its
seed was originally created. CL always requires an explicit identifier.
`byte_length` applies only to fresh generation and cannot accompany supplied
bytes.

`InvalidShareSelection` reports selector, exclusion, and unsupported-generation
shape errors. `HeaderCollision` reports an explicitly selected target set header
that matches a source or caller exclusion. No exception contains pending secret
or mask state.

`correct_worksheet_residue` accepts only a 13-symbol regular or 15-symbol Long
codex32 residue. It deliberately accepts neither profile nor string length.
Results are immutable `(reverse_index, addend)` records; `()` means already
correct and `None` means there is no unique correction. Invalid residue shapes
and erasure coordinates raise `InvalidCorrectionInput`.

Full-string fixed correction is internal until Gate 5 defines the complete
candidate API. Its mandatory `suspected_profile` is not inferred, its failure
record identifies the validation/decoder stage, and a success contains a
normally parsed immutable artifact.
