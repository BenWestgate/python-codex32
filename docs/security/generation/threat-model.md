# Gate 3 generation threat model and invariant proof

## Scope and actors

We are protecting electronically generated BIP93/CL secrets and shares against
biased masks, accidental unsafe API use, ambiguous set metadata, and accidental
reuse of incompatible shares. The caller is trusted to run supported CPython
on a functioning operating system. CLI input can be malformed or low entropy.
An attacker may later obtain public codex32 headers and fewer than the threshold
number of shares, and may perform offline candidate testing.

We do not claim to protect secret material from a compromised interpreter,
operating system, hardware RNG, terminal, or process memory. CPython does not
provide reliable zeroization of all copies.

## Security boundaries

1. `generation.py` is the only owner of fresh entropy and basis construction.
2. `bip93.py` remains the only owner of immutable artifact construction,
   recovery, and interpolation.
3. The CLI parses policy, calls the public generation API, and presents the
   returned order unchanged.
4. Ordinary shares remain symbol-only masks. CRC and byte semantics belong
   only to generated `MasterSeed` S values.

## Entropy and index proofs

For a uniform byte `b`, `b & 31` has exactly eight preimages for every value in
`0..31`. Applying this map to one batch of CSPRNG bytes therefore introduces no
modulo bias. The independence of symbols is inherited from the operating-system
CSPRNG assumption; making one `token_bytes` call rather than many calls does not
create a new deterministic relationship between returned bytes.

On supported CPython versions, `secrets.SystemRandom` is
`random.SystemRandom`. `sample` calls the instance's rejection-based
`_randbelow`, which obtains fresh bits through `SystemRandom.getrandbits` and
the operating-system random source. Sampling a fixed tuple of 31 distinct
indices is therefore a uniform ordered sample without replacement. Sampling
all 31 is a uniform permutation. We preserve that order and never sort it.

Index selection occurs only after the interpolation basis has been accepted.
It can select which public evaluations are returned, but cannot affect the
already fixed polynomial or S.

## Padding-rejection proof

Let `P` be the degree-at-most-`k-1` payload polynomial defined by `k` independent
uniform payload vectors and let `S=P(s)`. Fix any projection containing fewer
than `k` ordinary shares. At least one basis vector remains free, and its
nonzero Lagrange coefficient makes the map from that free vector to S a
bijection over the full payload-symbol space.

For each allowed seed-byte prefix, both policies admit exactly one discarded
padding value: `_crc_pad(prefix)` for `ms`, or zero for CL. Consequently the
number of accepting assignments of the free vector is the same for every fixed
sub-threshold projection. Conditioning on acceptance leaves every such
projection uniform. It also leaves seed-byte prefixes uniform because each
prefix has exactly one accepted padding value.

This argument applies only when all `k` fresh masks are sampled uniformly.
Completing a partial basis, especially `k-1` supplied shares, does not satisfy
the premise and remains unsupported.

## Identifier disclosure

A full-fingerprint default is a public predicate of about 20 seed-derived bits.
The 10+10 shared-set identifier exposes ten master-fingerprint bits directly.
With `k-1` genuine shares and a guessed S, the guess supplies the final point
needed to determine the polynomial; an attacker can derive the canonical
A/C/D... payloads and test the other ten tag bits offline. The tag therefore
does not require `k` genuine shares to evaluate.

These deterministic identifiers are weaker than independent random metadata
and do not satisfy an information-theoretic statement that fewer than `k`
shares reveal nothing about S. For a uniformly generated seed of at least 128
bits, no practical key-recovery attack follows from the reviewed 20-bit
predicate alone, but the entropy margin and unlinkability are reduced. We
retain this as a medium accepted usability divergence, never describe it as a
security enhancement, and require raw bytes of unknown provenance to supply an
explicit identifier at the immediate generation entry point.

That provenance rule is not a type-level proof. A caller can first invoke
`MasterSeed.from_seed` and later pass the typed S to `split_secret`; the latter
cannot distinguish that object from a parsed, securely generated S. The public
documentation must state that `split_secret` trusts the provenance of its typed
secret input.

## Collision and denial-of-service controls

Exclusions compare exactly `threshold + identifier`; `2test` and `3test` are
different set headers. An explicit collision fails before new mask entropy is
drawn. A derived-default collision never rejects the accepted basis. Instead,
we sample only four replacement identifier symbols, reheader and re-checksum
the unchanged payloads, and return the same secret polynomial.

`excluded_headers` is copied and validated before entropy, rejects text as a
collection, and is capped at 1,024 entries. The normalized frozen set bounds
memory and ensures a fallback draw succeeds with probability at least
`1 - 1024 / 32^4` on every attempt. This avoids both an exhausted identifier
space and attacker-controlled near-saturation retry cost.

`split_secret` accepts thresholds 2–9 only. This avoids an undefined unshared
10+10 policy and a source-header collision exemption. Threshold-zero creation
belongs exclusively to the two profile-specific generation APIs.

## Residual risks

- Deterministic identifiers leak/link metadata as described above.
- The design depends on supported CPython and the host OS entropy source.
- `bip32` v5 accepts the long share-payload serialization used by the legacy
  set tag even though it exceeds the normal BIP32 seed recommendation.
- Rejection loops have no deterministic iteration limit. Under the CSPRNG
  assumption their expected work is tightly bounded, but OS failure propagates.
- Secret bytes and intermediate Python objects are not guaranteed to be wiped.
