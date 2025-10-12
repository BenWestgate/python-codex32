# python-codex32

Python implementation of BIP-0093 (codex32): checksummed, SSSS-aware BIP32 seed strings.

This repository implements the codex32 string format described by BIP-0093.
It provides encoding/decoding, short/long ms32 checksums, CRC padding for convertbits,
Shamir-share interpolation helpers and helpers to build codex32 strings from seed bytes.

## Features
- Encode/decode codex32 data via `from_string` and `from_unchecksummed_string`.
- Short checksum (13 chars) and long checksum (15 chars) support.
- CRC-based default padding scheme for `convertbits`.
- Construct codex32 strings from raw seed bytes via `from_seed`.
- Parse codex32 strings and access parts via `Parts`.
- Interpolate/recover shares via `interpolate_at`.

## Installation
```bash
pip install codex32
```

## Quick usage
```python
from codex32.codex32 import Codex32String as ms32

# Create a codex32 string from seed bytes (16..64 bytes).
s = ms32.from_seed(
    data=bytes.fromhex('ffeeddccbbaa99887766554433221100'), # seed bytes, length 16..64
    ident="cash",         # 4-character identifier
    hrp="ms",             # human readable part, default 'ms'
    k=3,                  # threshold 0 or 2..9 (0 special: share index must be 's')
    share_idx='s',        # single-char share index (or 's' for k=0)
    pad_val=0             # -1 -> CRC padding, otherwise integer padding value
)
print(c.s)                # codex32 string

# Parse & validate an existing codex32 string
a = ms32.from_string("ms13casha320zyxwvutsrqpnmlkjhgfedca2a8d0zehn8a0t")
parts = c2.parts()       # Parts object
data_bytes = parts.data()  # encoded seed bytes

# Create from unchecksummed data-part (will append checksum)
c = ms32.from_unchecksummed_string("ms13cashcacdefghjklmnpqrstuvwxyz023")

# Interpolate shares to obtain target share index:
# shares is a list of Codex32String objects containing compatible shares
shares = [s, a, c]
derived_share_d = ms32.interpolate_at(shares, target='d')
print(derived_share_d.s)
```
