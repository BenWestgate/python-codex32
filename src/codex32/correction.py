# Copyright (c) 2025 Blockstream
# Copyright (c) 2026 Ben Westgate <benwestgate@protonmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""Fixed-length codex32 BCH correction, derived from codex32 PR #70.

Polynomial coefficients are least-significant first unless a helper says
otherwise. Correction locations are zero-based indices counted from the final
data/checksum symbol. Product-level indel search lives separately in
:mod:`codex32.indel`.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from functools import reduce
from typing import Literal

from codex32.bech32 import (
    CHARSET,
    _chars_to_u5,
    _checksum_for_encoded_length,
    _hrp_expand,
    _u5_to_chars,
    _validate_single_case_ascii,
)
from codex32.bip93 import Secret, Share, parse_codex32
from codex32.checksums import _CODEX32, _CODEX32_LONG, _Checksum
from codex32.errors import CodexError, InvalidCorrectionInput
from codex32.gf32 import _inverse as _gf32_inverse
from codex32.gf32 import _multiply as _gf32_multiply
from codex32.profiles import Profile, _profile_spec


@dataclass(frozen=True, slots=True)
class WorksheetCorrection:
    """One reverse-indexed GF(32) addend for a worksheet residue."""

    reverse_index: int
    addend: str


@dataclass(frozen=True, slots=True)
class _CorrectionAddend:
    reverse_index: int
    value: int


@dataclass(frozen=True, slots=True)
class _FixedCorrectionSuccess:
    artifact: Share | Secret
    addends: tuple[_CorrectionAddend, ...]


@dataclass(frozen=True, slots=True)
class _FixedCorrectionFailure:
    stage: Literal["text", "prefix", "profile", "algebra", "body", "reparse"]
    detail: str
    erasure_count: int = 0
    guaranteed_error_budget: int | None = None
    bch_failure: str | None = None
    linear_failure: str | None = None


@dataclass(frozen=True, slots=True)
class _AlgebraFailure:
    bch_failure: str
    linear_failure: str


# --- Direct P70-derived field, polynomial, BCH, and linear algebra. ---


# A GF(1024) value a + b*zeta is packed as a | b << 5, with
# zeta^2 = zeta + 1.
def _gf1024(a: int, b: int = 0) -> int:
    return a | (b << 5)


def _gf1024_mul(left: int, right: int) -> int:
    a0, b0 = left & 31, left >> 5
    a1, b1 = right & 31, right >> 5
    b0b1 = _gf32_multiply(b0, b1)
    return _gf1024(
        _gf32_multiply(a0, a1) ^ b0b1,
        _gf32_multiply(a0, b1) ^ _gf32_multiply(a1, b0) ^ b0b1,
    )


def _field_pow(value: int, exponent: int, multiply) -> int:
    result = 1
    while exponent:
        if exponent & 1:
            result = multiply(result, value)
        value = multiply(value, value)
        exponent >>= 1
    return result


def _gf1024_inv(value: int) -> int:
    a, b = value & 31, value >> 5
    denominator = _gf32_multiply(a, a) ^ _gf32_multiply(b, b) ^ _gf32_multiply(a, b)
    inverse = _gf32_inverse(denominator)
    return _gf1024(
        _gf32_multiply(a ^ b, inverse),
        _gf32_multiply(b, inverse),
    )


def _gf1024_pow(value: int, exponent: int) -> int:
    return _field_pow(value, exponent, _gf1024_mul)


def _poly_sum(left: list[int], right: list[int]) -> list[int]:
    size = max(len(left), len(right))
    return [
        (left[index] if index < len(left) else 0)
        ^ (right[index] if index < len(right) else 0)
        for index in range(size)
    ]


def _poly_mul(left: list[int], right: list[int], multiply) -> list[int]:
    if not left or not right:
        return []
    result = [0] * (len(left) + len(right) - 1)
    for left_index, left_value in enumerate(left):
        for right_index, right_value in enumerate(right):
            result[left_index + right_index] ^= multiply(left_value, right_value)
    return result


def _horner(
    polynomial: list[int] | tuple[int, ...],
    value: int,
    multiply,
) -> int:
    result = 0
    for coefficient in reversed(polynomial):
        result = multiply(result, value) ^ coefficient
    return result


def _poly_diff(polynomial: list[int]) -> list[int]:
    return [
        coefficient if power & 1 else 0
        for power, coefficient in enumerate(polynomial[1:], 1)
    ]


def _monic_mul(
    left: tuple[int, ...],
    right: tuple[int, ...],
) -> tuple[int, ...]:
    """Multiply big-endian monic GF(32) polynomials sans their leading one."""
    result = [0] * (len(left) + len(right) + 1)
    for left_index, left_value in enumerate((1,) + left):
        for right_index, right_value in enumerate((1,) + right):
            result[left_index + right_index] ^= _gf32_multiply(left_value, right_value)
    if result[0] != 1:
        raise AssertionError("product of monic polynomials was not monic")
    return tuple(result[1:])


def _minimal_poly(value: int) -> tuple[int, ...]:
    a, b = value & 31, value >> 5
    if not b:
        return (a,)
    conjugate = _gf1024(a ^ b, b)
    norm = _gf1024_mul(value, conjugate)
    if norm >> 5:
        raise AssertionError("GF(1024) norm was not in GF(32)")
    return b, norm & 31


def _poly_mod(
    polynomial: list[int],
    modulus: tuple[int, ...],
) -> list[int]:
    """Reduce a little-endian GF(32) polynomial by a big-endian monic one."""
    degree = len(modulus)
    work = list(polynomial)
    if len(work) < degree:
        work.extend([0] * (degree - len(work)))
    modulus_le = list(reversed((1,) + modulus))
    for top in range(len(work) - 1, degree - 1, -1):
        coefficient = work[top]
        if coefficient:
            offset = top - degree
            for index, value in enumerate(modulus_le):
                work[offset + index] ^= _gf32_multiply(coefficient, value)
    return work[:degree]


def _poly_powers(
    modulus: tuple[int, ...],
    count: int,
) -> list[list[int]]:
    """Return little-endian x^i modulo a big-endian monic modulus."""
    degree = len(modulus)
    powers: list[list[int]] = []
    value = [1] + [0] * (degree - 1)
    modulus_le = list(reversed(modulus))
    for _ in range(count):
        powers.append(value)
        carry = value[-1]
        value = [0] + value[:-1]
        if carry:
            value = [
                coefficient ^ _gf32_multiply(carry, reduction)
                for coefficient, reduction in zip(value, modulus_le)
            ]
    return powers


@dataclass(frozen=True, slots=True)
class _Spec:
    checksum: _Checksum
    base: int
    first_root: int
    distance: int
    target: tuple[int, ...]
    roots: tuple[int, ...]
    generator: tuple[int, ...]
    period: int

    @property
    def degree(self) -> int:
        return len(self.generator)

    @property
    def bias(self) -> tuple[int, ...]:
        return tuple(reversed(self.target))


def _multiplicative_order(value: int) -> int:
    for candidate in (1, 3, 11, 31, 33, 93, 341, 1023):
        if _gf1024_pow(value, candidate) == 1:
            return candidate
    raise AssertionError("zero has no multiplicative order")


def _make_spec(
    checksum: _Checksum,
    base: int,
    first_root: int,
    target: str,
) -> _Spec:
    roots = tuple(_gf1024_pow(base, first_root + index) for index in range(8))
    generator = reduce(_monic_mul, map(_minimal_poly, roots))
    target_values = tuple(_chars_to_u5(target))
    if len(generator) != len(target_values):
        raise AssertionError("checksum target and generator degrees differ")
    return _Spec(
        checksum,
        base,
        first_root,
        8,
        target_values,
        roots,
        generator,
        _multiplicative_order(base),
    )


_SHORT_SPEC = _make_spec(_CODEX32, _gf1024(0, CHARSET.index("g")), 77, "secretshare32")
_LONG_SPEC = _make_spec(
    _CODEX32_LONG,
    _gf1024(CHARSET.index("e"), CHARSET.index("x")),
    1019,
    "secretshare32ex",
)


def _spec_for_checksum(checksum: _Checksum) -> _Spec:
    if checksum is _CODEX32:
        return _SHORT_SPEC
    if checksum is _CODEX32_LONG:
        return _LONG_SPEC
    raise AssertionError("registered profile selected a non-codex32 checksum")


def _residue(spec: _Spec, hrp: str, body: list[int]) -> list[int]:
    initial_and_hrp = [1, *_hrp_expand(hrp)]
    return _poly_mod(
        list(reversed(initial_and_hrp + body)),
        spec.generator,
    )


def _generate_next(coefficients: list[int], values: list[int]) -> int:
    result = 0
    for coefficient, value in zip(coefficients, values):
        result ^= _gf1024_mul(coefficient, value)
    return result


def _synthesize_rec(values: list[int]) -> tuple[list[int], list[int]]:
    if not values:
        return [], [0]
    newest, older = values[0], values[1:]
    coefficients, adjustment = _synthesize_rec(older)
    discrepancy = newest ^ _generate_next(coefficients, older)
    if discrepancy:
        updated = _poly_sum(
            coefficients,
            [_gf1024_mul(discrepancy, value) for value in adjustment],
        )
    else:
        updated = coefficients
    if len(updated) == len(coefficients):
        updated_adjustment = [0] + adjustment
    else:
        inverse = _gf1024_inv(discrepancy)
        updated_adjustment = [
            _gf1024_mul(value, inverse) for value in [1] + coefficients
        ]
    return updated, updated_adjustment


def _locator_poly(
    syndromes: list[int],
    erasure_poly: list[int],
) -> list[int]:
    degree = len(erasure_poly) - 1
    modified = []
    for output_index in range(degree, len(syndromes)):
        value = 0
        for index, coefficient in enumerate(erasure_poly):
            value ^= _gf1024_mul(
                coefficient,
                syndromes[output_index - index],
            )
        modified.append(value)
    coefficients, _adjustment = _synthesize_rec(list(reversed(modified)))
    return [1] + coefficients


def _solve_word10(polynomial: list[int]) -> list[int]:
    return [
        value for value in range(1024) if _horner(polynomial, value, _gf1024_mul) == 0
    ]


def _bch_error_corrections(
    spec: _Spec,
    erasure_indices: list[int],
    residue: list[int],
) -> list[tuple[int, int]] | None:
    if len(erasure_indices) > len(spec.roots):
        return None
    erasure_roots = [
        _gf1024_inv(_gf1024_pow(spec.base, index)) for index in erasure_indices
    ]
    erasure_poly = [1]
    for root in erasure_roots:
        erasure_poly = _poly_mul(
            erasure_poly,
            [root, 1],
            _gf1024_mul,
        )

    checksum_error = [value ^ bias for value, bias in zip(residue, spec.bias)]
    syndromes = [
        _horner(
            [_gf1024(value) for value in checksum_error],
            root,
            _gf1024_mul,
        )
        for root in spec.roots
    ]
    locator = _locator_poly(syndromes, erasure_poly)
    roots = _solve_word10(locator)
    if len(locator) != 1 + len(roots):
        return None

    full_locator = _poly_mul(locator, erasure_poly, _gf1024_mul)
    omega = _poly_mul(syndromes, full_locator, _gf1024_mul)[: len(spec.roots)]
    derivative = _poly_diff(full_locator)
    wanted_roots = set(roots + erasure_roots)
    if len(wanted_roots) != len(full_locator) - 1:
        return None
    corrections: list[tuple[int, int]] = []
    for index in range(spec.period - 1, -1, -1):
        inverse_root = _gf1024_inv(_gf1024_pow(spec.base, index))
        if inverse_root not in wanted_roots:
            continue
        wanted_roots.remove(inverse_root)
        numerator = _horner(omega, inverse_root, _gf1024_mul)
        numerator = _gf1024_mul(
            numerator,
            _gf1024_pow(inverse_root, spec.first_root - 1),
        )
        denominator = _horner(derivative, inverse_root, _gf1024_mul)
        error = _gf1024_mul(numerator, _gf1024_inv(denominator))
        if error >> 5:
            return None
        corrections.append((index, error & 31))
    return None if wanted_roots else corrections


def _solve_linear(
    vectors: list[list[int]],
    target: list[int],
) -> list[int] | None:
    """Return the unique GF(32) coefficients spanning target, if any."""
    columns = len(vectors)
    if not columns:
        return [] if not any(target) else None
    matrix = [
        [vectors[column][row] for column in range(columns)] + [target[row]]
        for row in range(len(target))
    ]
    pivot_rows: list[int] = []
    next_row = 0
    for column in range(columns):
        pivot = next(
            (row for row in range(next_row, len(matrix)) if matrix[row][column]),
            None,
        )
        if pivot is None:
            return None
        matrix[next_row], matrix[pivot] = matrix[pivot], matrix[next_row]
        inverse = _gf32_inverse(matrix[next_row][column])
        matrix[next_row] = [
            _gf32_multiply(value, inverse) for value in matrix[next_row]
        ]
        for row_index in range(len(matrix)):
            if row_index == next_row or not matrix[row_index][column]:
                continue
            scale = matrix[row_index][column]
            matrix[row_index] = [
                value ^ _gf32_multiply(scale, pivot_value)
                for value, pivot_value in zip(
                    matrix[row_index],
                    matrix[next_row],
                )
            ]
        pivot_rows.append(next_row)
        next_row += 1
    for matrix_row in matrix:
        if not any(matrix_row[:columns]) and matrix_row[-1]:
            return None
    return [matrix[row][-1] for row in pivot_rows]


def _linear_error_corrections(
    spec: _Spec,
    erasure_indices: list[int],
    residue: list[int],
) -> list[tuple[int, int]] | None:
    if len(erasure_indices) > spec.degree:
        return None
    checksum_error = [value ^ bias for value, bias in zip(residue, spec.bias)]
    powers = _poly_powers(
        spec.generator,
        max(erasure_indices, default=-1) + 1,
    )
    solution = _solve_linear(
        [powers[index] for index in erasure_indices],
        checksum_error,
    )
    if solution is None:
        return None
    return list(zip(erasure_indices, solution))


def _error_corrections(
    spec: _Spec,
    erasure_indices: list[int],
    residue: list[int],
) -> list[tuple[int, int]] | _AlgebraFailure:
    bch = _bch_error_corrections(spec, erasure_indices, residue)
    if bch is not None and _corrections_reach_target(spec, residue, bch):
        return bch
    bch_failure = (
        "known erasures exceed the BCH distance"
        if len(erasure_indices) > spec.distance
        else "no bounded BCH solution"
    )
    if len(erasure_indices) > spec.degree:
        return _AlgebraFailure(
            bch_failure,
            "known erasures exceed the checksum degree",
        )
    linear = _linear_error_corrections(spec, erasure_indices, residue)
    if linear is not None and _corrections_reach_target(spec, residue, linear):
        return linear
    return _AlgebraFailure(
        bch_failure,
        "erasure system has no unique consistent solution",
    )


def _corrections_reach_target(
    spec: _Spec,
    residue: list[int],
    corrections: list[tuple[int, int]],
) -> bool:
    powers = _poly_powers(
        spec.generator,
        max((index for index, _addend in corrections), default=-1) + 1,
    )
    corrected = list(residue)
    for reverse_index, addend in corrections:
        corrected = _poly_sum(
            corrected,
            [_gf32_multiply(addend, value) for value in powers[reverse_index]],
        )
    return corrected == list(spec.bias)


# --- Small local adapters over the P70-derived algebra. ---


def _correct_fixed(
    damaged_text: str,
    *,
    suspected_profile: Profile,
) -> _FixedCorrectionSuccess | _FixedCorrectionFailure:
    if not isinstance(suspected_profile, Profile):
        raise TypeError("suspected_profile must be Profile")
    try:
        uppercase = _validate_single_case_ascii(damaged_text)
    except TypeError:
        raise
    except CodexError as error:
        return _FixedCorrectionFailure("text", str(error))

    prefix = f"{suspected_profile.value}1"
    if not damaged_text.lower().startswith(prefix):
        return _FixedCorrectionFailure(
            "prefix",
            f"input must start with suspected prefix {prefix!r}",
        )
    body_text = damaged_text[len(prefix) :]
    body = [CHARSET.find(character.lower()) for character in body_text]
    try:
        profile = _profile_spec(suspected_profile)
        checksum = _checksum_for_encoded_length(suspected_profile.value, len(body))
        profile.validate_payload_length(len(body) - checksum.length - 6)
    except CodexError as error:
        return _FixedCorrectionFailure("profile", str(error))
    spec = _spec_for_checksum(checksum)
    erasures = [index for index, value in enumerate(reversed(body)) if value < 0]
    zeroed = [max(value, 0) for value in body]
    result = _error_corrections(
        spec,
        erasures,
        _residue(spec, suspected_profile.value, zeroed),
    )
    if isinstance(result, _AlgebraFailure):
        budget = max(0, (spec.distance - len(erasures)) // 2)
        return _FixedCorrectionFailure(
            "algebra",
            "checksum decoder found no permitted correction",
            len(erasures),
            budget,
            result.bch_failure,
            result.linear_failure,
        )

    corrected_reversed = list(reversed(zeroed))
    if any(index >= len(corrected_reversed) for index, _value in result):
        return _FixedCorrectionFailure(
            "body",
            "correction points outside the visible data part",
            len(erasures),
        )
    for index, addend in result:
        corrected_reversed[index] ^= addend
    corrected = prefix + _u5_to_chars(list(reversed(corrected_reversed)))
    if uppercase:
        corrected = corrected.upper()
    try:
        artifact = parse_codex32(corrected)
    except CodexError as error:
        return _FixedCorrectionFailure(
            "reparse",
            str(error),
            len(erasures),
        )
    addends = tuple(_CorrectionAddend(index, value) for index, value in sorted(result))
    return _FixedCorrectionSuccess(artifact, addends)


def correct_worksheet_residue(
    residue: str,
    *,
    erasure_indices: Sequence[int] = (),
) -> tuple[WorksheetCorrection, ...] | None:
    """Correct a final worksheet residue without learning its source length."""
    try:
        _validate_single_case_ascii(residue, max_length=15)
        values = list(reversed(_chars_to_u5(residue)))
    except TypeError:
        raise
    except CodexError as error:
        raise InvalidCorrectionInput(str(error)) from error
    if len(values) == _SHORT_SPEC.degree:
        spec = _SHORT_SPEC
    elif len(values) == _LONG_SPEC.degree:
        spec = _LONG_SPEC
    else:
        raise InvalidCorrectionInput(
            "worksheet residue must contain 13 or 15 Bech32 symbols"
        )
    if isinstance(erasure_indices, (str, bytes)) or not isinstance(
        erasure_indices, Sequence
    ):
        raise InvalidCorrectionInput("erasure_indices must be an ordered sequence")
    if len(erasure_indices) > spec.degree:
        return None
    indices = list(erasure_indices)
    if any(isinstance(index, bool) or not isinstance(index, int) for index in indices):
        raise InvalidCorrectionInput("erasure indices must be integers")
    if len(set(indices)) != len(indices):
        raise InvalidCorrectionInput("erasure indices must be distinct")
    if any(index < 0 or index >= spec.period for index in indices):
        raise InvalidCorrectionInput(
            f"erasure indices must be between 0 and {spec.period - 1}"
        )
    if len(indices) > spec.degree:
        return None
    result = _error_corrections(spec, indices, values)
    if isinstance(result, _AlgebraFailure):
        return None
    return tuple(
        WorksheetCorrection(index, CHARSET[addend]) for index, addend in sorted(result)
    )
