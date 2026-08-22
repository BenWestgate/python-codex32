# Identifier policy and accepted disclosure

The four-character codex32 identifier is public metadata. Gate 3 retains two
deterministic `ms` defaults for usability and explicitly accepts their privacy
and entropy cost.

## Defaults

- A fresh machine-generated `ms` secret or set uses the first four u5 symbols
  (20 bits) of its BIP32 master fingerprint.
- Splitting a typed or parsed `MasterSeed` uses two fingerprint symbols (10
  bits) followed by two symbols (10 bits) from the BIP32 fingerprint of the
  concatenated lowercase payload characters of canonical A/C/D... shares
  through the threshold.
- Raw hexadecimal bytes cannot receive either default at the immediate API or
  CLI entry point; they require an explicit identifier.
- CL always requires an explicit identifier.

The set-tag serialization deliberately preserves the existing
non-domain-separated behavior. It depends on `bip32` v5 accepting metadata
longer than the normal BIP32 seed recommendation, which is one reason the
dependency is pinned to `bip32>=5,<6` and isolated behind this generation
boundary.

## Attacker capability

The full fingerprint identifier gives an offline seed candidate predicate of
about 20 bits. For the 10+10 form, an attacker holding `k-1` genuine shares can
test the complete identifier against a guessed S: the guess becomes the kth
interpolation point, fixes the polynomial, and permits derivation of the
canonical payloads used by the set tag. The attacker does not need `k` genuine
shares to evaluate the tag.

Accordingly, fingerprint identifiers are weaker than independent random
identifiers and violate a literal information-theoretic claim that fewer than
`k` shares reveal nothing about S. They also link backups that reproduce the
same fingerprint portion. For a uniformly generated seed of at least 128 bits,
this review found no practical key-recovery attack from the 20-bit predicate
alone, but the remaining brute-force margin is lower and weak seeds are exposed
to a useful oracle.

The project accepts this medium divergence for deterministic wallet/share-set
disambiguation. It must not be described as security-enhancing. Independent
random identifiers remain the preferred alternative if unlinkability or the
full entropy margin takes precedence.

## Collision policy

Collisions compare `threshold + identifier`, not identifiers alone. Explicit
collisions fail before new entropy. A colliding derived default is replaced by
a uniform random identifier while retaining every accepted S/share payload.
This avoids conditioning secret generation on public metadata. With the 1,024
entry exclusion cap, each fallback draw succeeds with probability at least
`1 - 1024/32^4`.

No header identifies or authenticates a polynomial. Users must not combine
same-header shares from different ceremonies, and partial-basis completion
remains unsupported.
