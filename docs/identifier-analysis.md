# Identifier policy

The four-character identifier is public metadata, not authentication.

- A fresh unshared (`k=0`) machine-generated `ms` secret uses the first 20
  bits of its BIP32 fingerprint. The seed is already present wherever this
  artifact is handled, but independently publishing the identifier still gives
  an offline 20-bit predicate against candidate seeds.
- A fresh shared set uses four independent random u5 symbols. It leaks no
  seed-derived fingerprint bits.
- Raw seed bytes and re-sharing require an explicit identifier. This prevents
  the library from silently turning unknown-provenance seed material into a
  fingerprint oracle and keeps different sharing ceremonies visibly distinct.

Changing a header does not authenticate a polynomial. Users must not combine
same-header shares from separate ceremonies. Partial-basis completion remains
unsupported.
