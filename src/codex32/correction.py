# fmt: off
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

"""Fixed BCH correction derived from PR #70, with reverse-indexed coordinates."""
# ruff: noqa: I001

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cache
from math import comb
from typing import Literal

from codex32.bech32 import CHARSET, _chars_to_u5, _u5_to_chars, _validate_single_case_ascii
from codex32.bech32 import bech32_hrp_expand
from codex32.bip93 import IDX_SORT, Header, Secret, Share, _checksum_for_encoded_length, parse_codex32
from codex32.checksums import _CODEX32, _CODEX32_LONG, _Checksum
from codex32.errors import CodexError, InvalidCorrectionInput
from codex32.gf32 import _inverse as _gf32_inverse
from codex32.gf32 import _multiply as _gf32_multiply
from codex32.profiles import Profile, _profile_rules
from codex32.profiles.ms32 import MasterSeed, _has_generation_padding
@dataclass(frozen=True, slots=True)
class WorksheetCorrection:
    reverse_index: int; addend: str
@dataclass(frozen=True, slots=True)
class CorrectionContext:
    profile: Profile; expected_length: int | None = None
    immutable_prefix: str | None = None; excluded_indices: tuple[str, ...] = ()
@dataclass(frozen=True, slots=True)
class CorrectionEdit:
    kind: Literal["substitution", "erasure", "insertion", "deletion"]; reverse_index: int
    observed: str; replacement: str
@dataclass(frozen=True, slots=True)
class CorrectionCandidate:
    artifact: Share | Secret; edits: tuple[CorrectionEdit, ...]; capture_volume: int
    erasures_filled: int; addend_hamming_weight: int; crc_padding_match: bool | None
# --- Direct P70-derived field, polynomial, BCH, and linear algebra. ---
# A GF(1024) value a + b*zeta is packed as a | b << 5, with
# zeta^2 = zeta + 1.
def _gf1024(a: int, b: int = 0) -> int:
    return a | (b << 5)
def _gf1024_mul_raw(left: int, right: int) -> int:
    a0, b0 = left & 31, left >> 5
    a1, b1 = right & 31, right >> 5
    b0b1 = _gf32_multiply(b0, b1)
    return _gf1024(
        _gf32_multiply(a0, a1) ^ b0b1,
        _gf32_multiply(a0, b1) ^ _gf32_multiply(a1, b0) ^ b0b1,
    )
def _field_tables() -> tuple[tuple[int, ...], tuple[int, ...]]:
    values = [1]
    for _ in range(1022):
        values.append(_gf1024_mul_raw(values[-1], _gf1024(2, 1)))
    logarithms = [0] * 1024
    for exponent, value in enumerate(values):
        logarithms[value] = exponent
    return tuple(values * 2), tuple(logarithms)
_GF1024_EXP, _GF1024_LOG = _field_tables()
def _gf1024_mul(left: int, right: int) -> int:
    return 0 if not left or not right else _GF1024_EXP[_GF1024_LOG[left] + _GF1024_LOG[right]]
def _gf1024_inv(value: int) -> int:
    return _GF1024_EXP[1023 - _GF1024_LOG[value]]
def _gf1024_pow(value: int, exponent: int) -> int:
    return 0 if not value else _GF1024_EXP[(_GF1024_LOG[value] * exponent) % 1023]
def _poly_sum(left: list[int], right: list[int]) -> list[int]:
    size = max(len(left), len(right))
    return [
        (left[index] if index < len(left) else 0) ^ (right[index] if index < len(right) else 0)
        for index in range(size)
    ]
def _poly_mul(left: list[int], right: list[int], multiply: Callable[[int, int], int]) -> list[int]:
    if not left or not right:
        return []
    result = [0] * (len(left) + len(right) - 1)
    for left_index, left_value in enumerate(left):
        for right_index, right_value in enumerate(right):
            result[left_index + right_index] ^= multiply(left_value, right_value)
    return result
def _horner(polynomial: list[int] | tuple[int, ...], value: int,
            multiply: Callable[[int, int], int]) -> int:
    result = 0
    for coefficient in reversed(polynomial):
        result = multiply(result, value) ^ coefficient
    return result
def _poly_diff(polynomial: list[int]) -> list[int]:
    return [coefficient if power & 1 else 0 for power, coefficient in enumerate(polynomial[1:], 1)]
def _poly_mod(polynomial: list[int], modulus: tuple[int, ...]) -> list[int]:
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
def _poly_powers(modulus: tuple[int, ...], count: int) -> list[list[int]]:
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
    base: int
    first_root: int
    target: tuple[int, ...]
    roots: tuple[int, ...]
    generator: tuple[int, ...]
    period: int
_SHORT_SPEC = _Spec(
    256,
    77,
    (16, 25, 24, 3, 25, 11, 16, 23, 29, 3, 25, 17, 10),
    (99, 24, 992, 462, 11, 320, 66, 16),
    (25, 27, 17, 8, 0, 25, 25, 25, 31, 27, 24, 16, 16),
    93,
)
_LONG_SPEC = _Spec(
    217,
    1019,
    (16, 25, 24, 3, 25, 11, 16, 23, 29, 3, 25, 17, 10, 25, 6),
    (890, 643, 545, 164, 1, 217, 669, 245),
    (15, 10, 25, 26, 9, 25, 21, 6, 23, 21, 6, 5, 22, 4, 23),
    1023,
)
def _spec_for_checksum(checksum: _Checksum) -> _Spec:
    if checksum is _CODEX32:
        return _SHORT_SPEC
    if checksum is _CODEX32_LONG:
        return _LONG_SPEC
    raise AssertionError("registered profile selected a non-codex32 checksum")
def _residue(spec: _Spec, hrp: str, body: list[int]) -> list[int]:
    initial_and_hrp = [1, *bech32_hrp_expand(hrp)]
    return _poly_mod(list(reversed(initial_and_hrp + body)), spec.generator)
def _syndromes(spec: _Spec, residue: list[int], *, target: bool) -> tuple[int, ...]:
    coefficients = [
        _gf1024(value ^ bias)
        for value, bias in zip(residue, reversed(spec.target) if target else (0,) * len(residue))
    ]
    return tuple(_horner(coefficients, root, _gf1024_mul) for root in spec.roots)
def _pack_syndromes(values: tuple[int, ...]) -> int:
    return sum(value << (10 * index) for index, value in enumerate(values))
@cache
def _syndrome_alignment(spec: _Spec, hrp: str,
                        length: int) -> tuple[int, tuple[tuple[int, ...], ...]]:
    base = _pack_syndromes(_syndromes(spec, _residue(spec, hrp, [0] * length), target=True))
    powers = _poly_powers(spec.generator, length)
    effects = tuple(
        tuple(
            _pack_syndromes(
                _syndromes(
                    spec,
                    [_gf32_multiply(value, coefficient) for coefficient in powers[length - position - 1]],
                    target=False,
                )
            )
            for value in range(32)
        )
        + (0,)
        for position in range(length)
    )
    return base, effects
def _aligned_syndromes(
    alignment: tuple[int, tuple[tuple[int, ...], ...]],
    body: Sequence[int],
    degree: int,
) -> list[int]:
    packed, effects = alignment
    for position, value in enumerate(body):
        packed ^= effects[position][value]
    return [(packed >> (10 * index)) & 1023 for index in range(degree)]
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
        updated = _poly_sum(coefficients, [_gf1024_mul(discrepancy, value) for value in adjustment])
    else:
        updated = coefficients
    if len(updated) == len(coefficients):
        updated_adjustment = [0] + adjustment
    else:
        inverse = _gf1024_inv(discrepancy)
        updated_adjustment = [_gf1024_mul(value, inverse) for value in [1] + coefficients]
    return updated, updated_adjustment
def _small_locator(sequence: list[int], maximum: int) -> list[int] | None:
    if not any(sequence):
        return [1]
    if maximum < 2:
        if maximum < 1 or not sequence[0]:
            return None
        coefficient = _gf1024_mul(sequence[1], _gf1024_inv(sequence[0]))
        if all(
            sequence[index] == _gf1024_mul(coefficient, sequence[index - 1])
            for index in range(2, len(sequence))
        ):
            return [1, coefficient]
        return None
    first_row = sequence[1], sequence[0], sequence[2]
    second_row = sequence[2], sequence[1], sequence[3]
    a, b, target = first_row
    c, d, other_target = second_row
    determinant = _gf1024_mul(a, d) ^ _gf1024_mul(b, c)
    if determinant:
        inverse = _gf1024_inv(determinant)
        first = _gf1024_mul(_gf1024_mul(target, d) ^ _gf1024_mul(b, other_target), inverse)
        second = _gf1024_mul(_gf1024_mul(a, other_target) ^ _gf1024_mul(target, c), inverse)
        valid = all(
            sequence[index]
            == _gf1024_mul(first, sequence[index - 1]) ^ _gf1024_mul(second, sequence[index - 2])
            for index in range(4, len(sequence))
        )
        if not valid:
            return None
        if second:
            return [1, first, second]
        return [1, first] if sequence[1] == _gf1024_mul(first, sequence[0]) else None
    if sequence[0]:
        coefficient = _gf1024_mul(sequence[1], _gf1024_inv(sequence[0]))
        if all(
            sequence[index] == _gf1024_mul(coefficient, sequence[index - 1])
            for index in range(2, len(sequence))
        ):
            return [1, coefficient]
    coefficients, _adjustment = _synthesize_rec(list(reversed(sequence)))
    return [1, *coefficients] if len(coefficients) <= maximum else None
def _locator_poly(
    syndromes: list[int], erasure_poly: list[int], maximum: int | None,
    erasure_products: tuple[tuple[int, ...], ...] | None = None,
) -> list[int] | None:
    degree = len(erasure_poly) - 1
    if degree == 2 and erasure_products is not None:
        first, second = erasure_products
        modified = [
            syndromes[index - 2] ^ first[syndromes[index]] ^ second[syndromes[index - 1]]
            for index in range(2, len(syndromes))
        ]
    else:
        modified = []
        for output_index in range(degree, len(syndromes)):
            value = syndromes[output_index - degree]
            products = erasure_products
            for index, coefficient in enumerate(erasure_poly[:-1]):
                syndrome = syndromes[output_index - index]
                value ^= _gf1024_mul(coefficient, syndrome) if products is None else products[index][syndrome]
            modified.append(value)
    if maximum is not None and maximum <= 2:
        return _small_locator(modified, maximum)
    coefficients, _adjustment = _synthesize_rec(list(reversed(modified)))
    return [1] + coefficients
@cache
def _word_roots(spec: _Spec, length: int) -> tuple[int, ...]:
    return tuple(_gf1024_inv(_gf1024_pow(spec.base, index)) for index in range(length))
def _erasure_state(spec: _Spec, length: int,
                   indices: tuple[int, ...]) -> tuple[tuple[int, ...], list[int]]:
    word_roots = _word_roots(spec, length)
    roots = tuple(word_roots[index] for index in indices)
    polynomial = [1]
    for root in roots:
        polynomial = _poly_mul(polynomial, [root, 1], _gf1024_mul)
    return roots, polynomial
def _bch_syndrome_corrections(
    spec: _Spec, erasure_indices: list[int], syndromes: list[int], word_length: int,
    max_substitutions: int | None,
    erasure_state: tuple[tuple[int, ...], list[int]] | None = None,
    erasure_products: tuple[tuple[int, ...], ...] | None = None,
) -> list[tuple[int, int]] | None:
    word_roots = _word_roots(spec, word_length)
    erasure_roots, erasure_poly = (
        _erasure_state(spec, word_length, tuple(erasure_indices)) if erasure_state is None else erasure_state
    )
    locator = _locator_poly(syndromes, erasure_poly, max_substitutions, erasure_products)
    if locator is None or max_substitutions is not None and len(locator) - 1 > max_substitutions:
        return None
    errors = [
        (index, root) for index, root in enumerate(word_roots) if _horner(locator, root, _gf1024_mul) == 0
    ]
    if len(locator) != 1 + len(errors):
        return None
    full_locator = _poly_mul(locator, erasure_poly, _gf1024_mul)
    omega = _poly_mul(syndromes, full_locator, _gf1024_mul)[: len(spec.roots)]
    derivative = _poly_diff(full_locator)
    positions = [*errors, *zip(erasure_indices, erasure_roots)]
    if len({root for _index, root in positions}) != len(full_locator) - 1:
        return None
    corrections: list[tuple[int, int]] = []
    for index, inverse_root in positions:
        numerator = _horner(omega, inverse_root, _gf1024_mul)
        numerator = _gf1024_mul(numerator, _gf1024_pow(inverse_root, spec.first_root - 1))
        denominator = _horner(derivative, inverse_root, _gf1024_mul)
        error = _gf1024_mul(numerator, _gf1024_inv(denominator))
        if error >> 5:
            return None
        corrections.append((index, error & 31))
    return corrections
def _repair_body(
    spec: _Spec, hrp: str, body: Sequence[int], max_substitutions: int | None,
    alignment: tuple[int, tuple[tuple[int, ...], ...]],
    erasure_indices: Sequence[int] | None,
    erasure_state: tuple[tuple[int, ...], list[int]] | None,
    erasure_products: tuple[tuple[int, ...], ...] | None,
) -> tuple[list[int], list[tuple[int, int]]] | None:
    erasures = (
        tuple(index for index, value in enumerate(reversed(body)) if value < 0)
        if erasure_indices is None
        else erasure_indices
    )
    result = (
        _bch_syndrome_corrections(
            spec, list(erasures), _aligned_syndromes(alignment, body, len(spec.roots)), len(body),
            max_substitutions, erasure_state, erasure_products,
        )
        if len(erasures) <= len(spec.roots)
        else None
    )
    if result is None and max_substitutions is not None and max_substitutions > 0:
        return None
    zeroed = [max(value, 0) for value in body]
    residue: list[int] | None = None
    if result is not None:
        residue = _residue(spec, hrp, zeroed)
        if not _corrections_reach_target(spec, residue, result):
            result = None
    if result is None and max_substitutions is None:
        residue = _residue(spec, hrp, zeroed) if residue is None else residue
        result = _linear_error_corrections(spec, list(erasures), residue)
        if result is not None and not _corrections_reach_target(spec, residue, result):
            result = None
    return None if result is None else (zeroed, result)
def _capture_volume(mutable_symbols: int, erasures: int, substitutions: int) -> int:
    """Return the fixed decoder volume without structural alignment cost."""
    known = mutable_symbols - erasures
    if known < substitutions:
        return 0
    return int(32**erasures * comb(known, substitutions) * 31**substitutions)
class _FixedCorrector:
    """Repair fixed-length symbols; structural alignment remains outside this class."""
    __slots__ = (
        "alignment", "erasure_indices", "erasure_products", "erasure_state", "max_substitutions",
        "mutable_start", "prefix", "profile", "spec", "uppercase",
    )
    def __init__(
        self, profile: Profile, body_length: int, uppercase: bool, max_substitutions: int | None,
        mutable_start: int = 0,
    ) -> None:
        profile_rules = _profile_rules(profile)
        checksum = _checksum_for_encoded_length(profile.value, body_length)
        profile_rules.validate_payload_length(body_length - checksum.length - 6)
        self.profile = profile
        self.prefix = f"{profile.value}1"
        self.spec = _spec_for_checksum(checksum)
        self.alignment = _syndrome_alignment(self.spec, profile.value, body_length)
        self.uppercase = uppercase
        self.max_substitutions = max_substitutions
        self.mutable_start = mutable_start
        self.erasure_indices: tuple[int, ...] | None = None
        self.erasure_products: tuple[tuple[int, ...], ...] | None = None
        self.erasure_state: tuple[tuple[int, ...], list[int]] | None = None
    def correct(
        self, body: list[int] | tuple[int, ...],
        unknowns: tuple[tuple[int, str], ...] = (),
        erasure_indices: Sequence[int] | None = None,
    ) -> CorrectionCandidate | None:
        values = body if isinstance(body, list) else list(body)
        if any(value < 0 for value in values[: self.mutable_start]):
            return None
        if erasure_indices is not None and erasure_indices != self.erasure_indices:
            if any(len(values) - index - 1 < self.mutable_start for index in erasure_indices):
                return None
            self.erasure_indices = tuple(erasure_indices)
            self.erasure_state = _erasure_state(self.spec, len(values), self.erasure_indices)
            coefficients = self.erasure_state[1][:-1]
            self.erasure_products = (
                tuple(
                    tuple(_gf1024_mul(coefficient, value) for value in range(1024))
                    for coefficient in coefficients
                )
                if len(coefficients) == 2
                else None
            )
        repair = _repair_body(
            self.spec, self.profile.value, values, self.max_substitutions, self.alignment, erasure_indices,
            self.erasure_state if erasure_indices is not None else None,
            self.erasure_products if erasure_indices is not None else None,
        )
        if repair is None:
            return None
        zeroed, result = repair
        corrected_reversed = list(reversed(zeroed))
        if any(
            index >= len(corrected_reversed)
            or len(corrected_reversed) - index - 1 < self.mutable_start
            for index, _value in result
        ):
            return None
        for index, addend in result:
            corrected_reversed[index] ^= addend
        corrected = self.prefix + _u5_to_chars(list(reversed(corrected_reversed)))
        corrected = corrected.upper() if self.uppercase else corrected
        try:
            artifact = parse_codex32(corrected)
        except CodexError:
            return None
        unknown_by_position = dict(unknowns)
        corrections = sorted(result)
        def observed(index: int) -> str:
            value = values[-index - 1]
            character = (
                CHARSET[value] if value >= 0 else unknown_by_position.get(len(values) - index - 1, "?")
            )
            return character.upper() if self.uppercase else character
        edits = tuple(
            CorrectionEdit(
                "substitution" if values[-index - 1] >= 0 else "erasure",
                index,
                observed(index),
                artifact.text[-index - 1],
            )
            for index, _value in corrections
        )
        substitutions = sum(edit.kind == "substitution" for edit in edits)
        mutable_values = values[self.mutable_start :]
        erasure_count = sum(value < 0 for value in mutable_values)
        return CorrectionCandidate(
            artifact,
            edits,
            _capture_volume(len(mutable_values), erasure_count, substitutions),
            erasure_count,
            sum(
                value.bit_count()
                for (_index, value), edit in zip(corrections, edits)
                if edit.kind == "substitution"
            ),
            _has_generation_padding(artifact) if isinstance(artifact, MasterSeed) else None,
        )
def _solve_linear(vectors: list[list[int]], target: list[int]) -> list[int] | None:
    columns = len(vectors)
    if not columns:
        return [] if not any(target) else None
    matrix = [
        [vectors[column][row] for column in range(columns)] + [target[row]] for row in range(len(target))
    ]
    for column in range(columns):
        pivot = next((row for row in range(column, len(matrix)) if matrix[row][column]), None)
        if pivot is None:
            return None
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        inverse = _gf32_inverse(matrix[column][column])
        matrix[column] = [_gf32_multiply(value, inverse) for value in matrix[column]]
        for row_index in range(len(matrix)):
            if row_index == column or not matrix[row_index][column]:
                continue
            scale = matrix[row_index][column]
            matrix[row_index] = [
                value ^ _gf32_multiply(scale, pivot_value)
                for value, pivot_value in zip(matrix[row_index], matrix[column])
            ]
    if any(not any(row[:columns]) and row[-1] for row in matrix):
        return None
    return [matrix[row][-1] for row in range(columns)]
def _linear_error_corrections(
    spec: _Spec, erasure_indices: list[int], residue: list[int]
) -> list[tuple[int, int]] | None:
    checksum_error = [value ^ bias for value, bias in zip(residue, reversed(spec.target))]
    powers = _poly_powers(spec.generator, max(erasure_indices, default=-1) + 1)
    solution = _solve_linear([powers[index] for index in erasure_indices], checksum_error)
    return None if solution is None else list(zip(erasure_indices, solution))
def _error_corrections(
    spec: _Spec,
    erasure_indices: list[int],
    residue: list[int],
    word_length: int | None = None,
    max_substitutions: int | None = None,
) -> list[tuple[int, int]] | None:
    length = spec.period if word_length is None else word_length
    bch = None
    if len(erasure_indices) <= len(spec.roots):
        bch = _bch_syndrome_corrections(
            spec,
            erasure_indices,
            list(_syndromes(spec, residue, target=True)),
            length,
            max_substitutions,
        )
    if bch is not None and _corrections_reach_target(spec, residue, bch):
        return bch
    if max_substitutions is not None and max_substitutions > 0:
        return None
    if len(erasure_indices) > len(spec.generator):
        return None
    linear = _linear_error_corrections(spec, erasure_indices, residue)
    return linear if linear is not None and _corrections_reach_target(spec, residue, linear) else None
def _corrections_reach_target(spec: _Spec, residue: list[int],
                              corrections: list[tuple[int, int]]) -> bool:
    count = max((index for index, _addend in corrections), default=-1) + 1
    powers = _poly_powers(spec.generator, count)
    corrected = list(residue)
    for reverse_index, addend in corrections:
        corrected = _poly_sum(corrected, [_gf32_multiply(addend, value) for value in powers[reverse_index]])
    return corrected == list(reversed(spec.target))
def _correct_fixed(
    damaged_text: str,
    *,
    suspected_profile: Profile,
    max_substitutions: int | None = None,
    immutable_prefix: str | None = None,
) -> CorrectionCandidate | None:
    if not isinstance(suspected_profile, Profile):
        raise TypeError("suspected_profile must be Profile")
    try:
        uppercase = _validate_single_case_ascii(damaged_text)
    except TypeError:
        raise
    except CodexError:
        return None
    prefix = f"{suspected_profile.value}1"
    locked = prefix if immutable_prefix is None else immutable_prefix
    matches = damaged_text.lower().startswith(prefix) if immutable_prefix is None else damaged_text.startswith(locked)
    if not matches:
        return None
    body_text = damaged_text[len(prefix) :]
    body = [CHARSET.find(character.lower()) for character in body_text]
    try:
        solver = _FixedCorrector(
            suspected_profile,
            len(body),
            uppercase,
            max_substitutions,
            len(locked) - len(prefix),
        )
    except CodexError:
        return None
    return solver.correct(
        body,
        tuple((index, character) for index, character in enumerate(body_text) if body[index] < 0),
    )
def _validate_context(context: CorrectionContext) -> None:
    try:
        if not isinstance(context.profile, Profile):
            raise TypeError("profile must be Profile")
        length = context.expected_length
        if length is not None:
            if isinstance(length, bool) or not isinstance(length, int):
                raise TypeError("expected_length must be an integer or None")
            body_length = length - len(context.profile.value) - 1
            checksum = _checksum_for_encoded_length(context.profile.value, body_length)
            _profile_rules(context.profile).validate_payload_length(body_length - checksum.length - 6)
        prefix = context.immutable_prefix
        if prefix is not None:
            if not isinstance(prefix, str):
                raise TypeError("immutable_prefix must be str or None")
            _validate_single_case_ascii(prefix)
            base = f"{context.profile.value}1"
            if not prefix.lower().startswith(base) or len(prefix) not in (len(base), len(base) + 5):
                raise ValueError("immutable_prefix must be the profile prefix with an optional header")
            if len(prefix) > len(base):
                header = prefix[len(base) :]
                Header(int(header[0]), header[1:], "s")
            if length is not None and len(prefix) >= length:
                raise ValueError("immutable_prefix must be shorter than expected_length")
        indices = context.excluded_indices
        if not isinstance(indices, tuple) or len(indices) > 31:
            raise TypeError("excluded_indices must be a tuple of at most 31 ordinary indices")
        lowered = tuple(index.lower() if isinstance(index, str) else "" for index in indices)
        if any(len(index) != 1 or index not in IDX_SORT[1:] for index in lowered) or len(set(lowered)) != len(
            lowered
        ):
            raise ValueError("excluded_indices must contain distinct ordinary indices")
    except (CodexError, TypeError, ValueError) as error:
        raise InvalidCorrectionInput(str(error)) from error
def _allowed(context: CorrectionContext, candidate: CorrectionCandidate) -> bool:
    artifact = candidate.artifact
    return not (
        isinstance(artifact, Share)
        and artifact.header.index in (index.lower() for index in context.excluded_indices)
    )
def _fingerprint_match(candidate: CorrectionCandidate) -> bool | None:
    artifact = candidate.artifact
    if not isinstance(artifact, MasterSeed) or artifact.header.threshold:
        return None
    try:
        from codex32.generation import _fingerprint_identifier
        return _fingerprint_identifier(artifact.seed_bytes) == artifact.header.identifier
    except CodexError:
        return None
def _candidate_order(candidate: CorrectionCandidate) -> tuple[object, ...]:
    return (
        candidate.addend_hamming_weight,
        candidate.crc_padding_match is not True,
        _fingerprint_match(candidate) is not True,
        candidate.artifact.text.lower(),
        tuple(
            (edit.reverse_index, edit.kind, edit.observed, edit.replacement)
            for edit in candidate.edits
        ),
    )
def _primary(candidates: Sequence[CorrectionCandidate]) -> tuple[CorrectionCandidate, ...]:
    if not candidates:
        return ()
    rank = min(item.capture_volume for item in candidates)
    return tuple(sorted((item for item in candidates if item.capture_volume == rank), key=_candidate_order))
def _best(
    candidates: Sequence[CorrectionCandidate], *, prefer_common: bool = False,
) -> tuple[CorrectionCandidate, ...]:
    """Apply the CLI-only Hamming, CRC, and fingerprint tie breakers."""
    tied = list(_primary(candidates))
    if not tied:
        return ()
    if prefer_common and any(len(item.artifact.text) in (48, 74) for item in tied):
        tied = [item for item in tied if len(item.artifact.text) in (48, 74)]
    hamming = min(item.addend_hamming_weight for item in tied)
    tied = [item for item in tied if item.addend_hamming_weight == hamming]
    for hint in (lambda item: item.crc_padding_match, _fingerprint_match):
        if any(hint(item) is True for item in tied):
            tied = [item for item in tied if hint(item) is True]
    return tuple(sorted(tied, key=_candidate_order))
def _correct_complete(
    context: CorrectionContext, damaged_text: str, *, deadline: float | None = None
) -> tuple[tuple[CorrectionCandidate, ...], bool]:
    if not isinstance(context, CorrectionContext):
        raise TypeError("context must be CorrectionContext")
    if not isinstance(damaged_text, str):
        raise TypeError("damaged_text must be str")
    _validate_context(context)
    if context.expected_length is not None:
        from codex32.indel import _search_many

        return _search_many(
            (context,),
            damaged_text,
            primary=frozenset((context.expected_length,)),
            deadline=deadline,
        )
    fixed = _correct_fixed(damaged_text, suspected_profile=context.profile,
                           immutable_prefix=context.immutable_prefix)
    candidates = () if fixed is None or not _allowed(context, fixed) else (fixed,)
    return candidates, True
def correct(context: CorrectionContext, damaged_text: str) -> tuple[CorrectionCandidate, ...]:
    """Return every equally best complete correction as an untrusted candidate."""
    return _correct_complete(context, damaged_text)[0]
def correct_worksheet_residue(
    residue: str, *, erasure_indices: Sequence[int] = ()
) -> tuple[WorksheetCorrection, ...] | None:
    """Correct a 13/15-symbol residue; return ``()`` if valid and ``None`` if ambiguous."""
    if isinstance(residue, str) and len(residue) > 15:
        raise InvalidCorrectionInput("codex32 input exceeds 15 characters")
    try:
        _validate_single_case_ascii(residue)
        values = list(reversed(_chars_to_u5(residue)))
    except TypeError:
        raise
    except CodexError as error:
        raise InvalidCorrectionInput(str(error)) from error
    if len(values) == len(_SHORT_SPEC.generator):
        spec = _SHORT_SPEC
    elif len(values) == len(_LONG_SPEC.generator):
        spec = _LONG_SPEC
    else:
        raise InvalidCorrectionInput("worksheet residue must contain 13 or 15 Bech32 symbols")
    if isinstance(erasure_indices, (str, bytes)) or not isinstance(erasure_indices, Sequence):
        raise InvalidCorrectionInput("erasure_indices must be an ordered sequence")
    if len(erasure_indices) > len(spec.generator):
        return None
    indices = list(erasure_indices)
    if any(isinstance(index, bool) or not isinstance(index, int) for index in indices):
        raise InvalidCorrectionInput("erasure indices must be integers")
    if len(set(indices)) != len(indices):
        raise InvalidCorrectionInput("erasure indices must be distinct")
    if any(index < 0 or index >= spec.period for index in indices):
        raise InvalidCorrectionInput(f"erasure indices must be between 0 and {spec.period - 1}")
    result = _error_corrections(spec, indices, values)
    if result is None:
        return None
    return tuple(WorksheetCorrection(index, CHARSET[addend]) for index, addend in sorted(result))
