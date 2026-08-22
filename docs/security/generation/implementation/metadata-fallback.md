# Selected design handoff: metadata-only collision fallback

## Ownership

`src/codex32/generation.py` exclusively owns generation validation, CSPRNG
calls, hidden-basis construction, padding acceptance, identifier derivation and
fallback, output-index selection, and returned ordering. It must use the
immutable construction and Gate 2 sharing primitives in `src/codex32/bip93.py`.

## Validation before entropy

1. Validate profile-specific byte input and length.
2. Validate threshold. `split_secret` permits only 2–9; `generate_*` additionally
   permits zero.
3. For threshold zero reject both selectors. For shared generation require
   exactly one of `share_count` or an ordered explicit index sequence.
4. Normalize and validate an explicit identifier.
5. Copy `excluded_headers` as a stable, non-text Collection of at most 1,024
   values; normalize each five-symbol header and freeze the set.
6. If the identifier is explicit, reject its exact target set header before any
   new mask entropy. Different-threshold reuse is allowed.

## Entropy sites

- Fresh unshared secret bytes: one direct `secrets.token_bytes(byte_length)`.
- One attempted mask basis: one direct
  `secrets.token_bytes(mask_count * payload_length)` followed by `byte & 31`.
- Derived-default fallback: direct OS-random bytes mapped to exactly four u5
  symbols; retry metadata only.
- Output selection: direct
  `secrets.SystemRandom().sample(ORDINARY_INDICES, share_count)`.

There is no adapter, callback, seed, wrapper, fallback PRNG, or deterministic
mode. OS errors propagate.

## Basis and identifier sequence

Fresh shared generation samples `k` canonical ordinary masks and rejects the
whole attempt only until recovered S has the profile's generation padding.
Existing-secret generation reheaders S and adds `k-1` masks without padding
rejection. It preserves the parsed S payload exactly.

Fresh `ms` uses the first four u5 symbols of the BIP32 master fingerprint.
Parsed/typed shared `MasterSeed` uses two master-fingerprint symbols plus two
symbols from the BIP32 fingerprint of the concatenated lowercase payload text
of canonical A/C/D... through the threshold. The serialization is deliberately
the existing non-domain-separated form. CL always requires an explicit ID.

If derived metadata collides, only the identifier changes. Rebuild each artifact
with the same profile, threshold, index, and payload; then regenerate its outer
checksum and reparse it. The implementation must not reconstruct shares from
bytes.

## Rare BIP32 failures

`BIP32.from_seed` may reject an invalid master scalar. For newly sampled fresh
secret material, the implementation may restart the complete fresh-secret
attempt because the result cannot serve wallet workflows. Supplied/parsed S
must fail explicitly rather than silently selecting another seed.

After masks are accepted, failure while calculating the 10-bit share-set tag
must either use independent metadata fallback on the unchanged basis or fail
without resampling masks. It must never return to mask entropy.

## Output

Resolve the final identifier before selecting output indices. Existing hidden
basis points may be returned directly; other requested points use
`derive_share`. Explicit order and `SystemRandom.sample` order are returned
unchanged. The returned S is the final reheadered S even though shared CLI
presentation prints only shares.

## Required independent implementation checks

- Inspect every direct entropy call and exception path.
- Confirm one mask batch per attempted basis and no entropy injection.
- Confirm CRC/zero-pad rejection is the only fresh-basis rejection.
- Force derived collision and compare every before/after payload symbol.
- Confirm exclusions and explicit collisions are resolved before mask entropy.
- Confirm source set headers are automatically excluded by `split_secret`.
- Confirm random selection follows basis/metadata acceptance and is never sorted.
- Confirm raw-byte and CL identifier requirements.
- Confirm partial-basis input remains unreachable.
