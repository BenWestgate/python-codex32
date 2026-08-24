"""Canonical arithmetic for the Bech32 finite field GF(32)."""


def _multiply_raw(left: int, right: int) -> int:
    result = 0
    for bit in range(5):
        if right & (1 << bit):
            result ^= left
        left <<= 1
        if left & 32:
            left ^= 41  # x^5 + x^3 + 1
    return result


_MULTIPLICATION = tuple(tuple(_multiply_raw(left, right) for right in range(32)) for left in range(32))
_INVERSE = tuple(
    next(
        (candidate for candidate in range(32) if _MULTIPLICATION[value][candidate] == 1),
        0,
    )
    for value in range(32)
)


def _multiply(left: int, right: int) -> int:
    """Multiply two u5 field elements."""
    return _MULTIPLICATION[left][right]


def _inverse(value: int) -> int:
    """Return a u5 multiplicative inverse, with zero mapped to zero."""
    return _INVERSE[value]
