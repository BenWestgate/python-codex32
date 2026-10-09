"""Re-derive the frozen BCH specifications kept out of the installed package."""

from functools import reduce

from codex32.bech32 import CHARSET, _chars_to_u5
from codex32.correction import (
    _LONG_SPEC,
    _SHORT_SPEC,
    _gf1024,
    _gf1024_mul,
    _gf1024_pow,
    _Spec,
)
from codex32.gf32 import _multiply as _gf32_multiply


def _monic_mul(left: tuple[int, ...], right: tuple[int, ...]) -> tuple[int, ...]:
    result = [0] * (len(left) + len(right) + 1)
    for left_index, left_value in enumerate((1, *left)):
        for right_index, right_value in enumerate((1, *right)):
            result[left_index + right_index] ^= _gf32_multiply(left_value, right_value)
    assert result[0] == 1
    return tuple(result[1:])


def _minimal_poly(value: int) -> tuple[int, ...]:
    a, b = value & 31, value >> 5
    if not b:
        return (a,)
    norm = _gf1024_mul(value, _gf1024(a ^ b, b))
    assert norm < 32
    return b, norm


def _order(value: int) -> int:
    candidates = (1, 3, 11, 31, 33, 93, 341, 1023)
    return next(candidate for candidate in candidates if _gf1024_pow(value, candidate) == 1)


def _derive(base: int, first_root: int, target: str) -> _Spec:
    roots = tuple(_gf1024_pow(base, first_root + index) for index in range(8))
    return _Spec(
        base,
        first_root,
        tuple(_chars_to_u5(target)),
        roots,
        reduce(_monic_mul, map(_minimal_poly, roots)),
        _order(base),
    )


def verify() -> None:
    assert _derive(_gf1024(0, CHARSET.index("g")), 77, "secretshare32") == _SHORT_SPEC
    long_base = _gf1024(CHARSET.index("e"), CHARSET.index("x"))
    assert _derive(long_base, 1019, "secretshare32ex") == _LONG_SPEC


if __name__ == "__main__":
    verify()
