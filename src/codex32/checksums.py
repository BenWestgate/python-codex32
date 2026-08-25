# fmt: off
"""Immutable checksum specifications used by codex32 and descriptors."""

from dataclasses import dataclass

_CODEX32_GEN = (
    0x19DC500CE73FDE210, 0x1BFAE00DEF77FE529, 0x1FBD920FFFE7BEE52,
    0x1739640BDEEE3FDAD, 0x07729A039CFC75F5A,
)
_CODEX32_LONG_GEN = (
    0x3D59D273535EA62D897, 0x7A9BECB6361C6C51507, 0x543F9B7E6C38D8A2A0E,
    0x0C577EAECCF1990D13C, 0x1887F74F8DC71B10651,
)
_DESCSUM_GEN = (0xF5DEE51989, 0xA9FDCA3312, 0x1BAB10E32D, 0x3706B1677A, 0x644D626FFD)

@dataclass(frozen=True, slots=True)
class _Checksum:
    kind: str
    generators: tuple[int, ...]
    length: int
    constant: int
    maximum_length: int | None = None

    def polymod(self, values: list[int] | tuple[int, ...], residue: int = 1) -> int:
        shift = len(self.generators) * (self.length - 1)
        mask = (1 << shift) - 1
        for value in values:
            top = residue >> shift
            residue = ((residue & mask) << len(self.generators)) ^ value
            for index, generator in enumerate(self.generators):
                if (top >> index) & 1:
                    residue ^= generator
        return residue

    def verify(self, values: list[int] | tuple[int, ...]) -> bool:
        bounded = self.maximum_length is None or len(values) <= self.maximum_length
        return bounded and self.polymod(values) == self.constant

    def create(self, values: list[int] | tuple[int, ...]) -> list[int]:
        residue = self.polymod([*values, *([0] * self.length)]) ^ self.constant
        width = len(self.generators)
        mask = (1 << width) - 1
        return [(residue >> (width * (self.length - 1 - index))) & mask for index in range(self.length)]


_CODEX32 = _Checksum("codex32", _CODEX32_GEN, 13, 0x10CE0795C2FD1E62A, 93)
_CODEX32_LONG = _Checksum("Long codex32", _CODEX32_LONG_GEN, 15, 0x43381E570BF4798AB26, 1023)

# Descriptor checksum remains an independently specified, non-codex32 helper.
DESCSUM = _Checksum("Descriptor", _DESCSUM_GEN, 8, 1)

_CRC = (
    None,
    # ``_Checksum`` consumes input bits most-significant bit first.  With its
    # implicit leading term, these generator values spell x+1, x^2+x+1,
    # x^3+x+1, and x^4+x+1 respectively.
    _Checksum("CRC1", (1,), 1, 0),
    _Checksum("CRC2", (3,), 2, 0),
    _Checksum("CRC3", (3,), 3, 0),
    _Checksum("CRC4", (3,), 4, 0),
)

def _crc_pad(data: bytes) -> int:
    """Return generation-only CRC padding; this private hint is not validity semantics."""
    bit_length = len(data) * 8
    padding_bits = (-bit_length) % 5
    if not padding_bits:
        return 0
    bits = [(byte >> bit) & 1 for byte in data for bit in range(7, -1, -1)]
    checksum = _CRC[padding_bits]
    assert checksum is not None
    crc_bits = checksum.create(bits)
    return sum(bit << (padding_bits - 1 - index) for index, bit in enumerate(crc_bits))
