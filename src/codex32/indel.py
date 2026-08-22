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

"""Transitional Gate 5 structural search; not part of the public API."""

import math
import os
import time
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from itertools import combinations

from codex32.bech32 import CHARSET
from codex32.correction import _correct_fixed, _FixedCorrectionSuccess
from codex32.errors import CodexError, InvalidCorrectionInput
from codex32.profiles import Profile

DEFAULT_MASTER_SEED_STRING_LENGTHS = (48, 74, 127)
_MAX_EXTRA_CORRECTION_CHARACTERS = 8
_MAX_DAMAGED_CODEX32_LENGTH = (
    max(DEFAULT_MASTER_SEED_STRING_LENGTHS) + _MAX_EXTRA_CORRECTION_CHARACTERS
)


@dataclass(frozen=True)
class GroupCorrection:
    """A recognized error affecting complete four-character groups."""

    kind: str
    position: int
    other_position: int | None
    before: str
    after: str


@dataclass(frozen=True)
class CorrectionCandidate:
    """A corrected string and the edit path used to obtain it."""

    string: str
    search_space_bits: float
    inserted: tuple[tuple[int, str], ...]
    deleted: tuple[tuple[int, str], ...]
    substituted: tuple[tuple[int, str, str], ...]
    erased: tuple[tuple[int, str, str], ...]
    transposed: tuple[tuple[int, str, str], ...] = ()
    duplicated: tuple[tuple[int, str], ...] = ()
    groups: tuple[GroupCorrection, ...] = ()

    @property
    def weight_bits(self) -> float:
        """Return the search-space size retained for API compatibility."""
        return self.search_space_bits

    @property
    def edit_count(self) -> int:
        """Return the ordinary Levenshtein edit count for this path."""
        return (
            len(self.inserted)
            + len(self.deleted)
            + len(self.substituted)
            + len(self.erased)
            + len(self.transposed)
            + len(self.groups)
        )

    @property
    def changed_positions(self) -> set[int]:
        """Return candidate positions that should be highlighted."""
        return (
            {position for position, _character in self.inserted}
            | {position for position, _before, _after in self.substituted}
            | {position for position, _before, _after in self.erased}
            | {min(position, len(self.string)) for position, _character in self.deleted}
            | {
                position
                for start, _before, _after in self.transposed
                for position in (start, start + 1)
            }
            | {
                position
                for group in self.groups
                for start in (
                    (group.position,)
                    if group.other_position is None
                    else (group.position, group.other_position)
                )
                for position in range(start, start + 4)
            }
        )

    @property
    def rank(self) -> float:
        """Rank candidates solely by logical search-space size."""
        return self.search_space_bits


@dataclass(frozen=True)
class CorrectionSearchResult:
    """Result of a time-bounded correction search."""

    candidate: CorrectionCandidate | None
    timed_out: bool
    variants_tested: int


@dataclass(frozen=True)
class _StructuralVariant:
    value: str
    mapping: tuple[int | None, ...]
    deleted_indices: tuple[int, ...]
    structural_weight_bits: float
    duplicated: tuple[tuple[int, str], ...] = ()
    group_hints: tuple[tuple[str, int, int | None], ...] = ()


@dataclass(frozen=True)
class _StructuralConfiguration:
    """One deletion/insertion count pair for a target string length."""

    target_length: int
    deletions: int
    insertions: int
    structural_weight_bits: float

    def minimum_bits(self, erasure_bits: tuple[float, ...]) -> float:
        """Return a safe candidate-score lower bound for this class."""
        retained = max(0, len(erasure_bits) - self.deletions)
        return self.structural_weight_bits + sum(sorted(erasure_bits)[:retained])


def _decode_damaged_string(value: str) -> tuple[str, list[int | None], bool]:
    if len(value) > _MAX_DAMAGED_CODEX32_LENGTH:
        raise InvalidCorrectionInput(
            "Codex32 correction input must be at most "
            f"{_MAX_DAMAGED_CODEX32_LENGTH} characters"
        )
    if any(ord(char) < 33 or ord(char) > 126 for char in value):
        raise InvalidCorrectionInput("Codex32 input must contain printable ASCII")
    letters = [char for char in value if char.isalpha()]
    if letters and not (
        all(char.islower() for char in letters)
        or all(char.isupper() for char in letters)
    ):
        raise InvalidCorrectionInput("Codex32 input cannot mix upper and lower case")
    if len(value) < 3 or value[:3].lower() != "ms1":
        raise InvalidCorrectionInput("Codex32 correction input must start with 'ms1'")
    body = [CHARSET.find(char.lower()) for char in value[3:]]
    return "ms", [item if item >= 0 else None for item in body], value.isupper()


def _log2_choose(total: int, selected: int) -> float:
    if selected < 0 or selected > total:
        return math.inf
    return (
        math.lgamma(total + 1)
        - math.lgamma(selected + 1)
        - math.lgamma(total - selected + 1)
    ) / math.log(2)


def _closest_master_seed_lengths(source_length: int) -> tuple[int, ...]:
    """Return the nearest standard master-seed lengths, retaining ties."""
    distance = min(
        abs(source_length - target) for target in DEFAULT_MASTER_SEED_STRING_LENGTHS
    )
    return tuple(
        target
        for target in DEFAULT_MASTER_SEED_STRING_LENGTHS
        if abs(source_length - target) == distance
    )


def _structural_configurations(
    source_length: int,
    prefix_length: int,
    target_lengths: tuple[int, ...],
) -> list[_StructuralConfiguration]:
    """Return structural classes ordered by actual alignment search size."""
    configurations = []
    for total_length in target_lengths:
        target_length = total_length - prefix_length
        for deletions in range(source_length + 1):
            insertions = target_length - source_length + deletions
            if not 0 <= insertions <= target_length:
                continue
            if source_length - deletions != target_length - insertions:
                continue
            work_bits = _log2_choose(source_length, deletions) + _log2_choose(
                target_length, insertions
            )
            configurations.append(
                _StructuralConfiguration(
                    target_length,
                    deletions,
                    insertions,
                    work_bits + 5 * insertions,
                )
            )
    configurations.sort(
        key=lambda item: (
            item.structural_weight_bits,
            item.deletions + item.insertions,
            item.target_length,
        )
    )
    return configurations


def _structural_variants(
    prefix: str,
    body: str,
    configuration: _StructuralConfiguration,
    excluded_values: set[str] | None = None,
) -> Iterator[_StructuralVariant]:
    target_length = configuration.target_length
    source_indices = range(len(body))
    seen = set(excluded_values or ())
    for deleted in combinations(source_indices, configuration.deletions):
        deleted_set = set(deleted)
        kept = tuple(index for index in source_indices if index not in deleted_set)
        for inserted in combinations(range(target_length), configuration.insertions):
            inserted_set = set(inserted)
            kept_iterator = iter(kept)
            mapping = tuple(
                None if position in inserted_set else next(kept_iterator)
                for position in range(target_length)
            )
            candidate_body = "".join(
                "?" if source_index is None else body[source_index]
                for source_index in mapping
            )
            key = candidate_body.lower()
            if key in seen:
                continue
            seen.add(key)
            yield _StructuralVariant(
                prefix + candidate_body,
                mapping,
                deleted,
                configuration.structural_weight_bits,
            )


def _pure_deletion_variant(
    prefix: str,
    body: str,
    deleted: tuple[int, ...],
    weight_bits: float,
    duplicated: tuple[tuple[int, str], ...] = (),
) -> _StructuralVariant:
    """Construct a structural variant containing only deletions."""
    deleted_set = set(deleted)
    mapping = tuple(index for index in range(len(body)) if index not in deleted_set)
    return _StructuralVariant(
        prefix + "".join(body[index] for index in mapping),
        mapping,
        deleted,
        weight_bits,
        duplicated,
    )


def _complete_group_starts(total_length: int) -> tuple[int, ...]:
    """Return zero-based starts of complete groups after the fixed first one."""
    return tuple(range(4, total_length - 3, 4))


def _fast_structural_variants(
    prefix: str, body: str, target_lengths: tuple[int, ...]
) -> list[_StructuralVariant]:
    """Return cheap invalid-character and adjacent-duplication repairs."""
    variants: dict[str, _StructuralVariant] = {}
    source_total_length = len(prefix) + len(body)
    invalid_indices = tuple(
        index
        for index, character in enumerate(body)
        if character.lower() not in CHARSET
    )

    for total_length in target_lengths:
        excess = source_total_length - total_length
        if excess == 1 and invalid_indices:
            weight = _log2_choose(len(invalid_indices), 1)
            for deleted in combinations(invalid_indices, 1):
                variant = _pure_deletion_variant(prefix, body, deleted, weight)
                variants.setdefault(variant.value.lower(), variant)

        if excess > 0:
            duplicate_indices = []
            for start in range(len(body) - 2 * excess + 1):
                block = body[start : start + excess]
                if block.lower() == body[start + excess : start + 2 * excess].lower():
                    duplicate_indices.append((start, block))
            duplicate_weight = math.log2(max(1, len(duplicate_indices)))
            for start, block in duplicate_indices:
                first_deleted = start + excess
                deleted = tuple(range(first_deleted, first_deleted + excess))
                duplicate = ((len(prefix) + first_deleted + 1, block),)
                variant = _pure_deletion_variant(
                    prefix,
                    body,
                    deleted,
                    duplicate_weight,
                    duplicate,
                )
                previous = variants.get(variant.value.lower())
                if (
                    previous is None
                    or variant.structural_weight_bits < previous.structural_weight_bits
                ):
                    variants[variant.value.lower()] = variant

        if source_total_length == total_length:
            starts = _complete_group_starts(total_length)
            swap_weight = _log2_choose(len(starts), 2)
            for left, right in combinations(starts, 2):
                left_body = left - len(prefix)
                right_body = right - len(prefix)
                left_group = body[left_body : left_body + 4]
                right_group = body[right_body : right_body + 4]
                if left_group.lower() == right_group.lower():
                    continue
                mapping = list(range(len(body)))
                mapping[left_body : left_body + 4] = range(right_body, right_body + 4)
                mapping[right_body : right_body + 4] = range(left_body, left_body + 4)
                candidate_body = "".join(body[index] for index in mapping)
                variant = _StructuralVariant(
                    prefix + candidate_body,
                    tuple(mapping),
                    (),
                    swap_weight,
                    group_hints=(("transposed", left + 1, right + 1),),
                )
                variants.setdefault(variant.value.lower(), variant)

        if source_total_length + 4 == total_length:
            starts = _complete_group_starts(total_length)
            omission_weight = math.log2(max(1, len(starts))) + 20
            for start in starts:
                inserted_at = start - len(prefix)
                source = iter(range(len(body)))
                omission_mapping = tuple(
                    None if inserted_at <= position < inserted_at + 4 else next(source)
                    for position in range(total_length - len(prefix))
                )
                candidate_body = "".join(
                    "?" if index is None else body[index] for index in omission_mapping
                )
                variant = _StructuralVariant(
                    prefix + candidate_body,
                    omission_mapping,
                    (),
                    omission_weight,
                    group_hints=(("omitted", start + 1, None),),
                )
                variants.setdefault(variant.value.lower(), variant)

    return sorted(
        variants.values(),
        key=lambda item: (item.structural_weight_bits, item.value.lower()),
    )


_COMMON_CONFUSIONS = {
    "b": frozenset(("8",)),
    "o": frozenset(("0",)),
    "i": frozenset(("l",)),
}


def _erasure_search_bits(before: str, after: str) -> float:
    """Prefer common visual confusions without excluding other fillings."""
    if after.lower() in _COMMON_CONFUSIONS.get(before.lower(), ()):
        return 0.0
    return 5.0


def _minimum_erasure_search_bits(character: str) -> float:
    """Return the cheapest supported filling for one invalid character."""
    return 0.0 if character.lower() in _COMMON_CONFUSIONS else 5.0


def _variant_minimum_bits(original_body: str, variant: _StructuralVariant) -> float:
    """Return an exact erasure-aware lower bound for one alignment."""
    return variant.structural_weight_bits + sum(
        _minimum_erasure_search_bits(original_body[source_index])
        for source_index in variant.mapping
        if source_index is not None
        and original_body[source_index].lower() not in CHARSET
    )


def _classify_transpositions(
    substitutions: tuple[tuple[int, str, str], ...],
) -> tuple[
    tuple[tuple[int, str, str], ...],
    tuple[tuple[int, str, str], ...],
]:
    """Separate adjacent swaps from unrelated substitutions."""
    remaining = []
    transposed = []
    index = 0
    while index < len(substitutions):
        if index + 1 < len(substitutions):
            left = substitutions[index]
            right = substitutions[index + 1]
            if (
                right[0] == left[0] + 1
                and left[1].lower() == right[2].lower()
                and right[1].lower() == left[2].lower()
            ):
                transposed.append((left[0], left[1] + right[1], left[2] + right[2]))
                index += 2
                continue
        remaining.append(substitutions[index])
        index += 1
    return tuple(remaining), tuple(transposed)


def _classify_deleted_duplications(
    original_body: str,
    prefix_length: int,
    variant: _StructuralVariant,
) -> tuple[tuple[int, str], ...]:
    """Label deleted runs that repeat an adjacent retained run."""
    duplicated = list(variant.duplicated)
    already_classified = {
        body_index
        for position, block in duplicated
        for body_index in range(
            position - prefix_length - 1,
            position - prefix_length - 1 + len(block),
        )
    }
    retained = {
        source_index for source_index in variant.mapping if source_index is not None
    }
    deleted = tuple(
        index for index in variant.deleted_indices if index not in already_classified
    )
    runs: list[tuple[int, ...]] = []
    for index in deleted:
        if not runs or index != runs[-1][-1] + 1:
            runs.append((index,))
        else:
            runs[-1] += (index,)

    for run in runs:
        start = run[0]
        length = len(run)
        block = original_body[start : start + length]
        left_start = start - length
        right_start = start + length
        repeats_left = (
            left_start >= 0
            and all(index in retained for index in range(left_start, start))
            and original_body[left_start:start].lower() == block.lower()
        )
        repeats_right = (
            right_start + length <= len(original_body)
            and all(
                index in retained for index in range(right_start, right_start + length)
            )
            and original_body[right_start : right_start + length].lower()
            == block.lower()
        )
        repeated_key = len(set(block.lower())) == 1 and (
            (
                start > 0
                and start - 1 in retained
                and original_body[start - 1].lower() == block[0].lower()
            )
            or (
                start + length < len(original_body)
                and start + length in retained
                and original_body[start + length].lower() == block[0].lower()
            )
        )
        if repeats_left or repeats_right or repeated_key:
            duplicated.append((prefix_length + start + 1, block))
    return tuple(duplicated)


def _classify_erroneous_groups(
    substitutions: tuple[tuple[int, str, str], ...],
) -> tuple[
    tuple[tuple[int, str, str], ...],
    tuple[GroupCorrection, ...],
]:
    """Recognize four substitutions aligned to one transcription group."""
    remaining = []
    groups = []
    index = 0
    while index < len(substitutions):
        group = substitutions[index : index + 4]
        if (
            len(group) == 4
            and group[0][0] >= 5
            and (group[0][0] - 1) % 4 == 0
            and tuple(item[0] for item in group)
            == tuple(range(group[0][0], group[0][0] + 4))
        ):
            groups.append(
                GroupCorrection(
                    "erroneous",
                    group[0][0],
                    None,
                    "".join(item[1] for item in group),
                    "".join(item[2] for item in group),
                )
            )
            index += 4
            continue
        remaining.append(substitutions[index])
        index += 1
    return tuple(remaining), tuple(groups)


def _materialize_group_hints(
    original_body: str,
    prefix_length: int,
    corrected: str,
    hints: tuple[tuple[str, int, int | None], ...],
) -> tuple[GroupCorrection, ...]:
    """Attach input and candidate text to fast group-repair hints."""
    groups = []
    for kind, position, other_position in hints:
        if kind == "omitted":
            before = ""
            after = corrected[position - 1 : position + 3]
        else:
            left = position - 1 - prefix_length
            assert other_position is not None
            right = other_position - 1 - prefix_length
            before = original_body[left : left + 4] + original_body[right : right + 4]
            after = corrected[position - 1 : position + 3]
            after += corrected[other_position - 1 : other_position + 3]
        groups.append(GroupCorrection(kind, position, other_position, before, after))
    return tuple(groups)


def _evaluate_structural_variant(
    original_body: str,
    prefix_length: int,
    variant: _StructuralVariant,
    validator: Callable[[str], bool] | None,
) -> CorrectionCandidate | None:
    correction = _correct_fixed(
        variant.value,
        suspected_profile=Profile.MS,
    )
    if not isinstance(correction, _FixedCorrectionSuccess):
        return None
    corrected = correction.artifact.text
    if validator is not None:
        try:
            if not validator(corrected):
                return None
        except (CodexError, ValueError):
            return None

    corrected_body = corrected[prefix_length:]
    if len(corrected_body) != len(variant.mapping):
        return None
    inserted = tuple(
        (prefix_length + position + 1, corrected_body[position])
        for position, source_index in enumerate(variant.mapping)
        if source_index is None
    )
    deleted = tuple(
        (prefix_length + source_index + 1, original_body[source_index])
        for source_index in variant.deleted_indices
    )
    erased = tuple(
        (
            prefix_length + position + 1,
            original_body[source_index],
            corrected_body[position],
        )
        for position, source_index in enumerate(variant.mapping)
        if source_index is not None
        and original_body[source_index].lower() not in CHARSET
    )
    raw_substitutions = tuple(
        (
            prefix_length + position + 1,
            original_body[source_index],
            corrected_body[position],
        )
        for position, source_index in enumerate(variant.mapping)
        if source_index is not None
        and original_body[source_index].lower() in CHARSET
        and original_body[source_index].lower() != corrected_body[position].lower()
    )
    substituted, transposed = _classify_transpositions(raw_substitutions)
    substituted, erroneous_groups = _classify_erroneous_groups(substituted)
    hinted_groups = _materialize_group_hints(
        original_body,
        prefix_length,
        corrected,
        variant.group_hints,
    )
    groups = erroneous_groups + hinted_groups
    duplicated = _classify_deleted_duplications(original_body, prefix_length, variant)
    known_mapped_length = len(variant.mapping) - len(inserted) - len(erased)
    substitution_count = len(substituted)
    transposition_count = len(transposed)
    erroneous_group_count = len(erroneous_groups)
    complete_group_count = len(_complete_group_starts(len(corrected)))
    weight = (
        variant.structural_weight_bits
        + sum(
            _erasure_search_bits(before, after) for _position, before, after in erased
        )
        + _log2_choose(max(0, known_mapped_length - 1), transposition_count)
        + _log2_choose(
            max(0, known_mapped_length - 2 * transposition_count),
            substitution_count,
        )
        + substitution_count * math.log2(31)
        + _log2_choose(complete_group_count, erroneous_group_count)
        + 20 * erroneous_group_count
    )
    return CorrectionCandidate(
        corrected,
        weight,
        inserted,
        deleted,
        substituted,
        erased,
        transposed,
        duplicated,
        groups,
    )


def _candidate_beats_bounds(
    candidate: CorrectionCandidate | None,
    bounds: list[float],
) -> bool:
    """Return whether no unsearched class can produce a closer candidate."""
    if candidate is None:
        return False
    return all(
        candidate.search_space_bits <= lower_bound
        or math.isclose(candidate.search_space_bits, lower_bound, abs_tol=1e-12)
        for lower_bound in bounds
    )


def _search_result(
    candidates: dict[str, CorrectionCandidate],
    timed_out: bool,
    variants_tested: int,
) -> CorrectionSearchResult:
    """Build a result containing the closest candidate found."""
    best = min(candidates.values(), key=lambda item: item.rank, default=None)
    return CorrectionSearchResult(best, timed_out, variants_tested)


def search_codex32_corrections(
    value: str,
    *,
    max_seconds: float = 10.0,
    max_workers: int | None = None,
    validator: Callable[[str], bool] | None = None,
) -> CorrectionSearchResult:
    """Search insertion/deletion alignments and BCH-correct each alignment.

    Structural classes and candidates are ordered by logical search-space size,
    and the search is bounded to ten seconds. Insertions and deletions refer to
    edits applied to the supplied damaged string to obtain the returned
    candidate.
    """
    if not 0 < max_seconds <= 10:
        raise InvalidCorrectionInput(
            "search time must be greater than 0 and at most 10 seconds"
        )
    prefix_name, _body_values, _was_upper = _decode_damaged_string(value)
    if prefix_name != "ms":
        raise InvalidCorrectionInput("only the 'ms' codex32 prefix is supported")
    prefix = value[:3]
    body = value[3:]
    target_lengths = _closest_master_seed_lengths(len(value))
    configurations = _structural_configurations(len(body), len(prefix), target_lengths)
    erasure_bits = tuple(
        _minimum_erasure_search_bits(character)
        for character in body
        if character.lower() not in CHARSET
    )
    deadline = time.monotonic() + max_seconds
    worker_count = max_workers or min(32, max(2, os.cpu_count() or 1))
    worker_count = max(1, min(32, worker_count))
    best_by_string: dict[str, CorrectionCandidate] = {}
    variants_tested = 0
    timed_out = False

    def record(candidate: CorrectionCandidate | None) -> None:
        nonlocal variants_tested
        variants_tested += 1
        if candidate is None:
            return
        key = candidate.string.lower()
        previous = best_by_string.get(key)
        if previous is None or candidate.rank < previous.rank:
            best_by_string[key] = candidate

    direct = next(
        (
            configuration
            for configuration in configurations
            if not configuration.deletions and not configuration.insertions
        ),
        None,
    )
    if direct is not None:
        configurations.remove(direct)
        variant = next(_structural_variants(prefix, body, direct))
        record(_evaluate_structural_variant(body, len(prefix), variant, validator))

    fast_variants = _fast_structural_variants(prefix, body, target_lengths)
    fast_values: dict[tuple[int, int, int], set[str]] = {}
    for fast_index, variant in enumerate(fast_variants):
        best = min(best_by_string.values(), key=lambda item: item.rank, default=None)
        fast_bounds = [
            _variant_minimum_bits(body, item) for item in fast_variants[fast_index:]
        ]
        configuration_bounds = [
            configuration.minimum_bits(erasure_bits) for configuration in configurations
        ]
        if _candidate_beats_bounds(best, fast_bounds + configuration_bounds):
            break
        if time.monotonic() >= deadline:
            timed_out = True
            break
        record(_evaluate_structural_variant(body, len(prefix), variant, validator))
        key = (
            len(variant.mapping),
            len(variant.deleted_indices),
            sum(source_index is None for source_index in variant.mapping),
        )
        fast_values.setdefault(key, set()).add(variant.value[3:].lower())

    def remaining_bounds(start: int) -> list[float]:
        return [
            configuration.minimum_bits(erasure_bits)
            for configuration in configurations[start:]
        ]

    best = min(best_by_string.values(), key=lambda item: item.rank, default=None)
    if not timed_out and _candidate_beats_bounds(best, remaining_bounds(0)):
        return _search_result(best_by_string, False, variants_tested)

    executor = ThreadPoolExecutor(max_workers=worker_count)
    try:
        for config_index, configuration in enumerate(configurations):
            bounds = remaining_bounds(config_index)
            best = min(
                best_by_string.values(),
                key=lambda item: item.rank,
                default=None,
            )
            if _candidate_beats_bounds(best, bounds):
                break
            key = (
                configuration.target_length,
                configuration.deletions,
                configuration.insertions,
            )
            variants = _structural_variants(
                prefix,
                body,
                configuration,
                fast_values.get(key),
            )
            pending: set[Future[CorrectionCandidate | None]] = set()
            stop = False
            for variant in variants:
                while len(pending) >= worker_count * 2:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        stop = True
                        break
                    done, pending = wait(
                        pending,
                        timeout=remaining,
                        return_when=FIRST_COMPLETED,
                    )
                    if not done:
                        timed_out = True
                        stop = True
                        break
                    for future in done:
                        record(future.result())
                    best = min(
                        best_by_string.values(),
                        key=lambda item: item.rank,
                        default=None,
                    )
                    if _candidate_beats_bounds(best, bounds):
                        stop = True
                        break
                if stop:
                    break
                pending.add(
                    executor.submit(
                        _evaluate_structural_variant,
                        body,
                        len(prefix),
                        variant,
                        validator,
                    )
                )

            while pending and not stop:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                done, pending = wait(
                    pending,
                    timeout=remaining,
                    return_when=FIRST_COMPLETED,
                )
                if not done:
                    timed_out = True
                    break
                for future in done:
                    record(future.result())
                best = min(
                    best_by_string.values(),
                    key=lambda item: item.rank,
                    default=None,
                )
                if _candidate_beats_bounds(best, bounds):
                    stop = True
                    break

            for future in pending:
                future.cancel()
            if timed_out or stop:
                break
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    return _search_result(best_by_string, timed_out, variants_tested)
