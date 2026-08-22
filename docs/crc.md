# Generation-only CRC padding

BIP93 permits arbitrary discarded bits in an `ms` S payload. Parsed strings
remain valid for every legal pad value. Electronic generation uses those bits
as a small private CRC hint that may help a future recovery tool distinguish
some damaged candidates. CRC is not part of BIP93 validity and never applies to
ordinary shares.

## Frozen convention

For `p = (-8 * len(seed)) mod 5`, `_crc_pad` uses the following compact table:

| `p` | Generator |
|---:|---|
| 0 | no CRC; padding zero |
| 1 | `x + 1` |
| 2 | `x^2 + x + 1` |
| 3 | `x^3 + x + 1` |
| 4 | `x^4 + x + 1` |

The reproducible bit convention matters as much as the polynomial name:

- seed bytes enter most-significant bit first;
- each input value is one bit;
- the initial register residue is `1`;
- the generator integers encode the lower polynomial coefficients (`1` for
  CRC1 and `0b11` for CRC2–CRC4); the leading `x^p` coefficient is implicit;
- `p` zero bits are appended before reading the result;
- the final XOR/residue constant is zero;
- the `p` result bits are emitted register-most-significant bit first and become
  the otherwise discarded payload bits.

Representative all-zero seed outputs for lengths 16 through 20 bytes are
`2, 6, 1, 2, 0`, corresponding to `2, 4, 1, 3, 0` padding bits.

The polynomials appear in the [Koopman CRC catalogue](https://users.ece.cmu.edu/~koopman/crc/index.html),
including its [CRC-3](https://users.ece.cmu.edu/~koopman/crc/crc3.html) and
[CRC-4](https://users.ece.cmu.edu/~koopman/crc/crc4.html) tables. Those rankings
model low, independent bit errors. They do not establish that these choices are
optimal for insertions, deletions, substitutions, or correlated human
transcription damage. We therefore freeze the compact implementation without
an optimality claim or polynomial-search tool.

Fresh shared generation uses rejection sampling so the recovered S has this
padding while all `k` initial shares remain complete uniform masks before
conditioning. Direct `MasterSeed.from_seed` encodes the same convention.
