# Recovery and additional-share derivation

BIP93 interpolation has one implementation in `bip93.py` for the four fixed
applications. No unknown HRP can reach this code.

## Public operations

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

## Validation and interpolation order

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

## Why the checksum is interpolated

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

## BIP39 migration profiles

Ordinary BIP39 shares are validated only as exact-length codex32 symbol masks.
A recovered S must additionally have zero outer padding and a valid embedded
BIP39 checksum. Derivation validates the implied S before propagating the set.
The public API may recover or derive codex32 artifacts; it never exposes BIP39
entropy, a mnemonic, construction, checksum completion, or wallet derivation.
The CLI exposes BIP39 recovery but deliberately does not expose derivation.

## Deliberate Rust-reference differences

- Exactly `k` artifacts are required; extra points are not silently accepted.
- A requested target that is already present is rejected rather than returned.
- Profile-specific S semantics, including BIP39, are applied after recovery.
- The target header is constructed from validated common fields rather than
  obtained by interpolating constant header columns.

These differences implement the accepted API contract and the BIP93 wording
that an additional share uses a fresh index.
