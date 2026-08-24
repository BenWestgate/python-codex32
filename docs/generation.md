# Secret generation

`generation.py` is the only module that draws entropy. It generates BIP93
master seeds and Core Lightning HSM secrets, and splits either validated S type.
Core Lightning now defaults to mnemonic recovery, but retains a codex32 HSM
secret import path for recovery on an unused node.

Fresh unshared seeds default to 16 bytes and use the first 20 bits of their
BIP32 fingerprint as public identifier metadata. Fresh shared sets use four
independent random u5 identifier symbols. Raw bytes, re-shared secrets, and CL
generation also use an independent random identifier unless one is supplied.
Random re-sharing never repeats the source set header; an explicitly repeated
source header is rejected.

The Python API generates every BIP93 `ms` size from 16 through 64 bytes. Fresh
CLI generation is deliberately narrower: `codex32 create --bytes` accepts only
16 or 32 bytes. `--existing` continues to import every 16--64-byte hexadecimal
seed, including unusual sizes that must remain recoverable.

Shared generation follows the two BIP93 constructions:

- a fresh set draws `k` independent complete u5 masks;
- an existing S uses S plus `k-1` independent complete u5 masks.

All masks for one attempted basis come from one `secrets.token_bytes` call.
Each byte is mapped with `value & 31`, which maps exactly eight byte values to
each u5 value. Fresh `ms` bases are rejected until recovered S has the private
CRC padding convention. Fresh CL bases are rejected until recovered S has zero
discarded bits, matching CLN's emitted encoding. Neither rule is validity:
parsed S strings may use any application-valid discarded bits, which re-sharing
preserves exactly. CRC never applies to shares.

Explicit output indices preserve caller order. A share count uses
`SystemRandom.sample` over the 31 ordinary indices and preserves sample order.
There is no entropy injection, sorting, partial-basis completion, or BIP39
generation.

## Independent Gate 2 review record

The delegated standard security scan on 2026-08-24 independently reviewed the
OS CSPRNG boundary, one-call mask sampling, unbiased u5 mapping, rejection
sampling, CRC/zero padding, identifier policy, random distinct-index selection,
and re-sharing. It found no medium-or-higher generation issue. Its one low
availability finding was that a string index selector was copied and normalized
before enforcing the 31-index maximum. Gate 0 fixed that ordering in
`generation._indices` and added a regression through every public generation
API. No injectable or fallback entropy source was added.
