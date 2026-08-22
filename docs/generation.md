# Electronic generation and splitting

Gate 3 has one generation owner: `src/codex32/generation.py`. Parsing,
immutable artifacts, interpolation, recovery, and additional-share derivation
remain in `src/codex32/bip93.py`.

## Public operations

- `generate_master_seed` creates a fresh `ms` secret or accepts raw seed bytes.
- `generate_core_lightning_secret` creates or accepts a fixed 32-byte CL secret.
- `split_secret` shares an authenticated `MasterSeed` or
  `CoreLightningSecret` at threshold 2–9.

Threshold-zero creation belongs only to the two profile-specific generation
functions. Shared generation requires exactly one selector: an explicit ordered
index sequence, or a count sampled without replacement. The returned first
element is the final target-header S; returned shares preserve the explicit or
CSPRNG selection order.

Raw `ms` bytes and every CL operation require an explicit identifier. A typed
or parsed `MasterSeed` may use the reviewed deterministic shared-set default.
This is a policy trust boundary, not proof of provenance: a caller can construct
a typed `MasterSeed` from weak bytes before calling `split_secret`.
`byte_length` is a fresh-generation selector and is rejected whenever
`seed_bytes` is supplied, even if the two lengths happen to match; callers must
provide one source of truth.

## Basis construction

Fresh shared generation samples `k` complete ordinary payload masks at the
canonical A/C/D... points. Existing-secret splitting uses reheadered S plus
`k-1` freshly sampled canonical masks. A single attempted basis obtains all
mask bytes in one direct `secrets.token_bytes` call and maps each byte with
`value & 31`.

Fresh `ms` rejects an entire basis until recovered S has the generation CRC
padding. Fresh CL rejects until recovered S has zero discarded padding.
Existing parsed S payloads, including arbitrary legal discarded bits, are
preserved exactly. The proof that this acceptance rule preserves every
sub-threshold share distribution is in
[`security/generation/threat-model.md`](security/generation/threat-model.md).

Output indices are selected only after accepting and reheadering the basis.
`share_count` uses `secrets.SystemRandom().sample` over one frozen tuple of all
31 unique ordinary indices. The implementation preserves sample order and
does not sort it.

## Set headers and collision handling

Exclusions contain five symbols: `threshold + identifier`. Index is not part of
the set header, so `2test` and `3test` are distinct. The API snapshots at most
1,024 exclusions before entropy. `split_secret` automatically excludes its
source set header.

An explicit target collision fails before new mask entropy. A derived-default
collision keeps the accepted secret and every mask payload, samples only a new
four-symbol identifier, and recreates headers and checksums. No continuation,
TTY prompt, pending secret state, or mask resampling is exposed.

## Unsupported operations

- BIP39 generation or splitting
- generation from ordinary shares or a partial basis
- injectable/deterministic entropy
- public padding or CRC control
- sorting generated output
- arbitrary profiles

Partial-basis completion is neither recovery nor either BIP93 generation
procedure. It can create incompatible polynomials under one header and remains
deliberately deferred.
