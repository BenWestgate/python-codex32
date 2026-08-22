# Master-seed generation

`generation.py` is the only module that draws entropy. It generates BIP93
master seeds and splits parsed `MasterSeed` artifacts. Core Lightning codex32
is a legacy recovery format in current Core Lightning, so v1 validates and
shares `cl` artifacts but does not generate them.

Fresh unshared seeds default to 16 bytes and use the first 20 bits of their
BIP32 fingerprint as public identifier metadata. Fresh shared sets use four
independent random u5 identifier symbols. Raw bytes and re-shared secrets
require an explicit identifier; re-sharing under the identical threshold and
identifier is rejected.

Shared generation follows the two BIP93 constructions:

- a fresh set draws `k` independent complete u5 masks;
- an existing S uses S plus `k-1` independent complete u5 masks.

All masks for one attempted basis come from one `secrets.token_bytes` call.
Each byte is mapped with `value & 31`, which maps exactly eight byte values to
each u5 value. Fresh bases are rejected until recovered S has the private CRC
padding convention. CRC is not validity and never applies to shares.

Explicit output indices preserve caller order. A share count uses
`SystemRandom.sample` over the 31 ordinary indices and preserves sample order.
There is no entropy injection, sorting, partial-basis completion, BIP39
generation, or CL generation.
