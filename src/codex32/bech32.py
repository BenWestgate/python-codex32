# fmt: off
"""Bech32 character, container, and bit-conversion helpers."""
# ruff: noqa: I001

from codex32.checksums import _Checksum
from codex32.errors import InvalidCase, InvalidCharacter, InvalidChecksum, InvalidLength
from codex32.errors import InvalidPadding, MissingSeparator

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_MAX_LENGTH = 1024


def bech32_hrp_expand(hrp: str) -> list[int]:
    """Expand the HRP into values for checksum computation."""
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _u5_to_chars(values: list[int] | tuple[int, ...]) -> str:
    for index, value in enumerate(values):
        if not 0 <= value < 32:
            raise InvalidCharacter(f"u5 value {value} at index {index} is outside 0..31")
    return "".join(CHARSET[value] for value in values)


def _chars_to_u5(value: str, first_position: int = 1) -> list[int]:
    result: list[int] = []
    for index, character in enumerate(value.lower()):
        position = CHARSET.find(character)
        if position < 0:
            label = "Apostrophe (')" if character == "'" else f"The character {character!r}"
            raise InvalidCharacter(
                f"{label} is not allowed in a codex32 string (position {first_position + index})."
            )
        result.append(position)
    return result


def _validate_single_case_ascii(value: str) -> bool:
    if not isinstance(value, str):
        raise TypeError("codex32 input must be str")
    if len(value) > _MAX_LENGTH:
        raise InvalidLength(f"codex32 input exceeds {_MAX_LENGTH} characters")
    for index, character in enumerate(value):
        codepoint = ord(character)
        if not 33 <= codepoint <= 126:
            raise InvalidCharacter(f"non-printable U+{codepoint:04X} at position {index}")
    if value.upper() != value and value.lower() != value:
        raise InvalidCase("Use either all uppercase or all lowercase letters.")
    return value.isupper()


def bech32_encode(hrp: str, data: list[int], spec: _Checksum) -> str:
    """Compute a Bech32 string given HRP and data values."""
    checksum = spec.create(bech32_hrp_expand(hrp) + list(data))
    return f"{hrp}1{_u5_to_chars([*data, *checksum])}"


def bech32_verify_checksum(hrp: str, data: list[int], spec: _Checksum) -> bool:
    """Verify the checksum selected by the calling application."""
    return spec.verify(bech32_hrp_expand(hrp) + list(data))


def bech32_decode(value: str, spec: _Checksum | None = None) -> tuple[str, list[int]]:
    """Validate a Bech32 string, optionally including its checksum."""
    _validate_single_case_ascii(value)
    separator = value.rfind("1")
    if separator < 0:
        raise MissingSeparator("No separator (1) was found.")
    if separator == 0:
        raise MissingSeparator("The application prefix before 1 is missing.")
    lowered = value.lower()
    hrp = lowered[:separator]
    data = _chars_to_u5(lowered[separator + 1 :], separator + 2)
    if spec is None:
        return hrp, data
    if len(data) < spec.length or not bech32_verify_checksum(hrp, data, spec):
        raise InvalidChecksum(f"invalid {spec.kind} checksum")
    return hrp, data[: -spec.length]


def convertbits(
    data: bytes | list[int] | tuple[int, ...],
    frombits: int,
    tobits: int,
    *,
    pad: bool,
    pad_value: int = 0,
    accept_any_padding: bool = False,
) -> list[int]:
    """General power-of-two base conversion derived from ``segwit_addr.py``."""
    acc = 0
    bits = 0
    result: list[int] = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or value >> frombits:
            raise InvalidCharacter(f"value {value} is outside {frombits}-bit range")
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            result.append((acc >> bits) & maxv)
    if not pad:
        if bits >= frombits:
            raise InvalidLength(
                f"incomplete conversion group leaves {bits} bits; at most {frombits - 1} allowed"
            )
        if bits and not accept_any_padding and acc & ((1 << bits) - 1):
            raise InvalidPadding("nonzero discarded padding")
        return result
    if not bits:
        if pad_value:
            raise InvalidPadding("padding value supplied when no padding is present")
        return result
    padding_bits = tobits - bits
    if not 0 <= pad_value < (1 << padding_bits):
        raise InvalidPadding(f"padding value {pad_value} does not fit in {padding_bits} bits")
    result.append(((acc << padding_bits) | pad_value) & maxv)
    return result
