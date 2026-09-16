"""Independent codex32 encoder used only to construct test fixtures."""

from codex32.bech32 import CHARSET

_SHORT_GENERATORS = (
    0x19DC500CE73FDE210,
    0x1BFAE00DEF77FE529,
    0x1FBD920FFFE7BEE52,
    0x1739640BDEEE3FDAD,
    0x07729A039CFC75F5A,
)
_LONG_GENERATORS = (
    0x3D59D273535EA62D897,
    0x7A9BECB6361C6C51507,
    0x543F9B7E6C38D8A2A0E,
    0x0C577EAECCF1990D13C,
    0x1887F74F8DC71B10651,
)


def _polymod(values: list[int], generators: tuple[int, ...], length: int) -> int:
    residue = 1
    shift = 5 * (length - 1)
    mask = (1 << shift) - 1
    for value in values:
        top = residue >> shift
        residue = ((residue & mask) << 5) ^ value
        for index, generator in enumerate(generators):
            if (top >> index) & 1:
                residue ^= generator
    return residue


def oracle_encode(hrp: str, body: str, *, force_long: bool | None = None) -> str:
    use_long = 2 * len(hrp) + 1 + len(body) > 80 if force_long is None else force_long
    generators = _LONG_GENERATORS if use_long else _SHORT_GENERATORS
    length = 15 if use_long else 13
    constant = 0x43381E570BF4798AB26 if use_long else 0x10CE0795C2FD1E62A
    values = (
        [ord(character) >> 5 for character in hrp]
        + [0]
        + [ord(character) & 31 for character in hrp]
        + [CHARSET.index(character) for character in body]
    )
    residue = _polymod(values + [0] * length, generators, length) ^ constant
    checksum = "".join(CHARSET[(residue >> (5 * (length - 1 - index))) & 31] for index in range(length))
    return f"{hrp}1{body}{checksum}"
