"""Bounded codex32 text and checksum codec."""

from codex32.checksums import _CODEX32, _CODEX32_LONG, _Checksum
from codex32.errors import (
    InvalidCase,
    InvalidCharacter,
    InvalidChecksum,
    InvalidLength,
    InvalidPadding,
    InvalidShareIndex,
    InvalidThreshold,
    MissingSeparator,
)

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_MAX_CODEX32_LENGTH = 1024


def _hrp_expand(hrp: str) -> list[int]:
    return (
        [ord(character) >> 5 for character in hrp]
        + [0]
        + [ord(character) & 31 for character in hrp]
    )


def _u5_to_chars(values: list[int] | tuple[int, ...]) -> str:
    for index, value in enumerate(values):
        if not 0 <= value < 32:
            raise InvalidCharacter(
                f"u5 value {value} at index {index} is outside 0..31"
            )
    return "".join(CHARSET[value] for value in values)


def _chars_to_u5(value: str) -> list[int]:
    result: list[int] = []
    for index, character in enumerate(value.lower()):
        position = CHARSET.find(character)
        if position < 0:
            raise InvalidCharacter(
                f"non-Bech32 character {character!r} at data position {index}"
            )
        result.append(position)
    return result


def _validate_single_case_ascii(
    value: str, *, max_length: int = _MAX_CODEX32_LENGTH
) -> bool:
    """Validate the shared bounded lexical envelope and report uppercase."""
    if not isinstance(value, str):
        raise TypeError("codex32 input must be str")
    if len(value) > max_length:
        raise InvalidLength(f"codex32 input exceeds {max_length} characters")
    for index, character in enumerate(value):
        codepoint = ord(character)
        if not 33 <= codepoint <= 126:
            raise InvalidCharacter(
                f"non-printable U+{codepoint:04X} at position {index}"
            )
    if value.upper() != value and value.lower() != value:
        raise InvalidCase("mixed upper/lower case codex32 string")
    return value.isupper()


def _parse(
    value: str, *, max_length: int = _MAX_CODEX32_LENGTH
) -> tuple[str, list[int]]:
    """Perform bounded lexical parsing without interpreting a profile."""
    _validate_single_case_ascii(value, max_length=max_length)
    separator = value.rfind("1")
    if separator < 0:
        raise MissingSeparator("'1' separator not found")
    if separator == 0:
        raise MissingSeparator("empty HRP")
    lowered = value.lower()
    return lowered[:separator], _chars_to_u5(lowered[separator + 1 :])


def _checksum_for_body_length(hrp: str, body_length: int) -> _Checksum:
    """Select the checksum from the expanded codeword before its checksum."""
    expanded_hrp_length = 2 * len(hrp) + 1
    return _CODEX32 if expanded_hrp_length + body_length <= 80 else _CODEX32_LONG


def _checksum_for_encoded_length(hrp: str, encoded_length: int) -> _Checksum:
    """Select and bound the checksum covering an encoded data part."""
    expanded_codeword_length = 2 * len(hrp) + 1 + encoded_length
    if expanded_codeword_length <= 93:
        return _CODEX32
    if expanded_codeword_length < 96:
        raise InvalidLength("expanded codex32 lengths 94 and 95 are invalid")
    if expanded_codeword_length <= 1023:
        return _CODEX32_LONG
    raise InvalidLength("expanded codex32 codeword exceeds 1023 symbols")


def _validate_header(data: list[int] | tuple[int, ...]) -> None:
    """Validate the common six-symbol codex32 header."""
    if len(data) < 6:
        raise InvalidLength("codex32 data part is shorter than its six-symbol header")
    header = _u5_to_chars(tuple(data[:6]))
    if header[0] not in "023456789":
        raise InvalidThreshold(f"invalid threshold symbol {header[0]!r}")
    if header[0] == "0" and header[5] != "s":
        raise InvalidShareIndex("threshold 0 requires share index S")


def _encode(hrp: str, data: list[int] | tuple[int, ...]) -> str:
    """Encode a common-header-valid body with the format-selected checksum."""
    _validate_header(data)
    spec = _checksum_for_body_length(hrp, len(data))
    checksum = spec.create(_hrp_expand(hrp) + list(data))
    return f"{hrp}1{_u5_to_chars([*data, *checksum])}"


def _verify(hrp: str, data_with_checksum: list[int], spec: _Checksum) -> bool:
    return spec.verify(_hrp_expand(hrp) + data_with_checksum)


def _decode(value: str) -> tuple[str, tuple[int, ...], _Checksum]:
    """Validate codex32 format before any application-profile lookup."""
    if len(value) < 21:
        raise InvalidLength("codex32 string must contain at least 21 characters")
    hrp, encoded = _parse(value)
    checksum = _checksum_for_encoded_length(hrp, len(encoded))
    _validate_header(encoded[: -checksum.length])
    if not _verify(hrp, encoded, checksum):
        raise InvalidChecksum(f"invalid {checksum.kind} checksum")
    return hrp, tuple(encoded), checksum


def _convert_bits(
    data: bytes | list[int] | tuple[int, ...],
    from_bits: int,
    to_bits: int,
    *,
    pad: bool,
    pad_value: int = 0,
    accept_any_padding: bool = False,
) -> list[int]:
    """Convert power-of-two groups with explicit integer padding only."""
    accumulator = 0
    bits = 0
    result: list[int] = []
    output_mask = (1 << to_bits) - 1
    accumulator_mask = (1 << (from_bits + to_bits - 1)) - 1
    for value in data:
        if value < 0 or value >> from_bits:
            raise InvalidCharacter(f"value {value} is outside {from_bits}-bit range")
        accumulator = ((accumulator << from_bits) | value) & accumulator_mask
        bits += from_bits
        while bits >= to_bits:
            bits -= to_bits
            result.append((accumulator >> bits) & output_mask)
    if not pad:
        if bits >= from_bits:
            raise InvalidLength(
                f"incomplete conversion group leaves {bits} bits; at most {from_bits - 1} allowed"
            )
        if bits and not accept_any_padding and accumulator & ((1 << bits) - 1):
            raise InvalidPadding("nonzero discarded padding")
        return result
    if not bits:
        if pad_value:
            raise InvalidPadding("padding value supplied when no padding is present")
        return result
    padding_bits = to_bits - bits
    if not 0 <= pad_value < (1 << padding_bits):
        raise InvalidPadding(
            f"padding value {pad_value} does not fit in {padding_bits} bits"
        )
    result.append(((accumulator << padding_bits) | pad_value) & output_mask)
    return result


def _payload_bytes(symbols: tuple[int, ...]) -> tuple[bytes, int, int]:
    """Decode payload symbols, returning bytes, padding value and bit count."""
    padding_bits = (len(symbols) * 5) % 8
    if padding_bits > 4:
        raise InvalidLength("payload leaves more than four discarded bits")
    decoded = bytes(_convert_bits(symbols, 5, 8, pad=False, accept_any_padding=True))
    padding = symbols[-1] & ((1 << padding_bits) - 1) if padding_bits else 0
    return decoded, padding, padding_bits
