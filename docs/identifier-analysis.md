# Identifier policy

The four-character identifier is public metadata, not authentication.

- A fresh unshared (`k=0`) machine-generated `ms` secret uses the first 20
  bits of its BIP32 fingerprint. The seed is already present wherever this
  artifact is handled, but independently publishing the identifier still gives
  an offline 20-bit predicate against candidate seeds.
- A fresh shared set uses four independent random u5 symbols. It leaks no
  seed-derived fingerprint bits.
- Raw seed bytes, re-sharing, and CL generation use an independent random
  identifier unless the caller supplies all four symbols. This avoids turning
  unknown-provenance seed material into a fingerprint oracle. A random
  identifier is public metadata and does not make a weak supplied seed safe.
- Random re-sharing rejects the source set header and draws another identifier.
  An explicitly repeated source header remains an error.

Changing a header does not authenticate a polynomial. Users must not combine
same-header shares from separate ceremonies. Partial-basis completion remains
unsupported.
