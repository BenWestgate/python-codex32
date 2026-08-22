# Architecture through Gate 4: validated artifacts, sharing, generation, and BCH correction

The public security boundary is `parse_codex32` or a profile-specific secret
factory. Domain code does not accept unchecked strings, generic byte payloads,
or mutable authenticated metadata.

```text
str
 └─ bounded lexical parser (bech32.py)
     └─ common header + format checksum selection (bech32.py)
         └─ outer checksum (checksums.py)
             └─ fixed profile lookup + exact payload length (profiles.py)
                 └─ immutable Header (bip93.py)
                     └─ profile S semantics
                         ├─ ms: MasterSeed
                         ├─ cl: CoreLightningSecret
                         ├─ bip39_* S: isolated bip39.py validator
                         └─ ordinary index: Share (u5 symbols only)
```

## Specification-to-code map

| Specification concept | Authoritative code owner | Direct tests |
|---|---|---|
| Lexical ASCII, separator, case and data alphabet | `bech32._parse` | `test_bech32.py` |
| Format checksum boundary | `bech32._checksum_for_encoded_length` | PR #2258 boundary tests in `test_profiles.py` |
| Registered applications and exact payload lengths | `profiles._ProfileSpec` | `test_profiles.py` |
| Outer checksum arithmetic | immutable `_Checksum` values | official generic vectors in `test_profiles.py` |
| Header rules | `bip93.Header` | `test_public_api.py`, official invalid vectors |
| `ms` S byte semantics | `bip93.MasterSeed` | official vectors and exhaustive length/padding test |
| `cl` S byte semantics | `bip93.CoreLightningSecret` | Core Lightning examples and padding tests |
| BIP39 migration S semantics | `bip39._validate_bip39_secret` | `test_bip39.py` |
| Ordinary share boundary | `bip93.Share` | negative public-API and BIP39-mask tests |
| Share-set compatibility | `bip93._validate_share_set` | `test_sharing.py` mismatch tests |
| GF(32) Lagrange arithmetic | `bip93._lagrange_weights`, `_interpolate_tail` | official BIP93 vectors 2 and 3 |
| Exact-threshold recovery | `bip93.recover_secret` | threshold, permutation, and subset tests |
| Fresh-index derivation | `bip93.derive_share` | all-index, exclusion, replacement, and profile fixtures |
| BIP39 implied-S boundary | `bip93.derive_share` then `parse_codex32` | invalid implied-S fixtures |
| Generation option/header validation | `generation` validation helpers | `test_generation.py` selection and collision cases |
| Complete-mask entropy | `generation` batched `secrets.token_bytes` path | mapping/invariant tests plus independent source audit |
| Fresh padding acceptance | `generation` basis loop + `bip93._has_generation_padding` | `test_generation.py`, `test_crc.py`, algebraic balance proof |
| Identifier derivation/fallback | `generation` metadata helpers | frozen full-20/10+10 fixtures and payload-preservation collision test |
| Output-index selection/order | `generation` fixed `ORDINARY_INDICES` and `SystemRandom.sample` | explicit-order, distinct-count, and all-31 tests plus source audit |
| Canonical GF(32) arithmetic | `gf32._multiply`, `gf32._inverse` | official sharing vectors and correction corpus |
| BCH errors and erasures | `correction` P70-derived algebra | `test_correction_bch.py`, frozen P70-derived corpus |
| Fixed-string profile boundary | `correction._correct_fixed` | every profile plus failure-stage tests |
| Private worksheet residue correction | `correction.correct_worksheet_residue` | short/long periods and published BIP39 worksheet residues |

## Trust boundaries

- The format layer validates the common header and outer checksum before an
  HRP selects one of the four supported application profiles. Unknown HRPs do
  not acquire any application's payload semantics.
- Profile payload semantics are interpreted only after the outer checksum
  succeeds. Checksum completion is the explicit exception: it first
  validates all unchecksummed structure and is available only to `ms` and `cl`.
- A share contains complete u5 payload symbols. It is never decoded to or
  constructed from bytes.
- `MasterSeed.from_seed` can create only index S and accepts no padding or RNG
  controls. Its CRC padding helper is private and generation-only.
- Sharing interpolates payload and outer-checksum symbols together, constructs
  the target header explicitly, and reparses the result. There is no second
  production interpolation path and no checksum regeneration in sharing.
- Profiles must explicitly opt into linear sharing. Unknown or future profiles
  cannot inherit this behavior accidentally.
- `generation.py` is the sole entropy owner. It accepts only `ms` and CL,
  samples complete payload masks, and exposes no RNG, padding, or partial-basis
  control.
- Set-header exclusions are bounded and snapshotted before entropy. An explicit
  collision fails early; a derived collision reheaders unchanged payloads and
  never feeds back into basis generation.
- Output selection follows basis acceptance. Explicit and CSPRNG sample order
  cross the API boundary unchanged.
- Correction never edits the HRP or separator. The format layer selects the
  checksum from expanded length, and every fixed candidate crosses
  the normal parser boundary again.
- Worksheet residues use native reverse coordinates and reveal only whether the
  residue selects regular or Long codex32. The adapter has no profile, HRP,
  payload-length, or shortened-string-length input.
- Structural search is isolated in internal `indel.py`; it consumes the fixed
  decoder but cannot change its algebra or profile validation.

Python cannot make underscore-prefixed internals inaccessible to a determined
caller. The supported boundary is the package export list and documented
types; direct use of private modules is unsupported and reviewed as internal
code.
