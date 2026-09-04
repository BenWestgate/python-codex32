"""Reproduce structural-correction capture bounds with independent integer arithmetic."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from itertools import combinations, groupby
from math import comb

FALSE_BOUND_DENOMINATOR = 100_000


@dataclass(frozen=True, slots=True)
class Shape:
    """One character- or group-only structural class."""

    name: str
    inserted: int = 0
    omitted: int = 0
    unit: int = 1

    @property
    def delta(self) -> int:
        return self.unit * (self.inserted - self.omitted)

    @property
    def erasures(self) -> int:
        return self.unit * self.omitted


@dataclass(frozen=True, slots=True)
class CaptureClass:
    shape: str
    delta: int
    substitutions: int
    alignments: int
    volume: int
    cumulative_volume: int
    safe: bool


@dataclass(frozen=True, slots=True)
class CrossLengthClass:
    target_length: int
    shape: str
    remaining_explicit: int
    substitutions: int
    alignments: int
    volume: int
    checksum_bits: int
    scaled_volume: int
    primary: bool
    admitted: bool


def checksum_bits(hrp: str, target_length: int) -> int:
    expanded_length = target_length + len(hrp)
    if expanded_length <= 93:
        return 65
    if 96 <= expanded_length <= 1023:
        return 75
    raise ValueError("target falls in the invalid checksum-length gap")


def supported_shapes() -> tuple[Shape, ...]:
    characters = tuple(
        Shape(f"characters-{inserted}i-{total - inserted}o", inserted, total - inserted)
        for total in range(1, 5)
        for inserted in range(total + 1)
    )
    groups = tuple(
        Shape(f"groups-{inserted}gi-{total - inserted}go", inserted, total - inserted, 4)
        for total in range(1, 3)
        for inserted in range(total + 1)
    )
    return (Shape("fixed"), *characters, *groups)


def group_boundary(immutable_length: int) -> int:
    return 4 * ((immutable_length + 3) // 4)


def alignment_count(
    shape: Shape,
    target_length: int,
    immutable_length: int,
) -> int:
    if shape.name == "fixed":
        return 1
    if shape.unit == 1:
        mutable = target_length - immutable_length
        observed = mutable + shape.delta
        return comb(observed, shape.inserted) * comb(mutable, shape.omitted)
    target_groups = (target_length - group_boundary(immutable_length)) // 4
    observed_groups = target_groups + shape.inserted - shape.omitted
    return comb(observed_groups, shape.inserted) * comb(target_groups, shape.omitted)


def fixed_volume(
    mutable_symbols: int,
    erasures: int,
    substitutions: int,
) -> int:
    return 32**erasures * comb(mutable_symbols - erasures, substitutions) * 31**substitutions


def capture_volume(
    shape: Shape,
    target_length: int,
    immutable_length: int,
    substitutions: int,
    explicit_erasures: int = 0,
) -> int:
    mutable = target_length - immutable_length
    return alignment_count(shape, target_length, immutable_length) * fixed_volume(
        mutable,
        shape.erasures + explicit_erasures,
        substitutions,
    )


def decoder_capacity(shape: Shape, explicit_erasures: int = 0) -> range:
    erasures = shape.erasures + explicit_erasures
    if erasures > 8:
        return range(0)
    return range((8 - erasures) // 2 + 1)


def alignment_distribution(
    shape: Shape,
    observed_length: int,
    target_length: int,
    immutable_length: int,
    explicit_positions: tuple[int, ...] = (),
) -> dict[int, int]:
    """Count alignments by explicit erasures retained after deleting extras."""
    explicit = frozenset(
        position for position in explicit_positions if immutable_length <= position < observed_length
    )
    if shape.name == "fixed":
        return {len(explicit): 1}
    if shape.unit == 1:
        observed = observed_length - immutable_length
        target = target_length - immutable_length
        known = observed - len(explicit)
        omitted = comb(target, shape.omitted)
        return {
            len(explicit) - deleted: comb(len(explicit), deleted)
            * comb(known, shape.inserted - deleted)
            * omitted
            for deleted in range(max(0, shape.inserted - known), min(shape.inserted, len(explicit)) + 1)
        }
    boundary = group_boundary(immutable_length)
    target_groups = (target_length - boundary) // 4
    observed_groups = target_groups + shape.inserted - shape.omitted
    end = boundary + 4 * observed_groups
    per_group = tuple(
        sum(position in explicit for position in range(start, start + 4)) for start in range(boundary, end, 4)
    )
    outside = len(explicit) - sum(per_group)
    counts: dict[int, int] = {}
    omitted = comb(target_groups, shape.omitted)
    for deleted in combinations(range(observed_groups), shape.inserted):
        remaining = outside + sum(count for index, count in enumerate(per_group) if index not in deleted)
        counts[remaining] = counts.get(remaining, 0) + omitted
    return counts


def cross_length_classes(
    observed_length: int,
    targets: tuple[int, ...] = (48, 54, 61, 67, 74, 127),
    primary_targets: tuple[int, ...] = (48, 74, 127),
    reduced_targets: tuple[int, ...] = (54, 61, 67),
    immutable_prefix: str = "ms1",
    explicit_positions: tuple[int, ...] = (),
) -> tuple[CrossLengthClass, ...]:
    """Reproduce the production cross-target frontier without importing it."""
    raw: list[tuple[int, int, tuple[int, Shape, int, int], int]] = []
    for target in targets:
        shapes = supported_shapes()
        if target in reduced_targets:
            shapes = tuple(
                shape
                for shape in shapes
                if shape.name == "fixed"
                or shape.unit == 1
                and shape.inserted + shape.omitted <= 3
                or shape.unit == 4
                and shape.inserted + shape.omitted <= 2
            )
        for shape in shapes:
            if shape.delta != observed_length - target:
                continue
            for remaining, alignments in alignment_distribution(
                shape, observed_length, target, len(immutable_prefix), explicit_positions
            ).items():
                for substitutions in decoder_capacity(shape, remaining):
                    volume = alignments * fixed_volume(
                        target - len(immutable_prefix), shape.erasures + remaining, substitutions
                    )
                    raw.append(
                        (
                            volume,
                            checksum_bits("ms", target),
                            (target, shape, remaining, substitutions),
                            alignments,
                        )
                    )
    maximum = max((bits for _volume, bits, _key, _alignments in raw), default=0)
    cumulative = 0
    admitted: set[tuple[int, str, int, int]] = set()
    for selected_primary in (True, False):
        pool = (item for item in raw if (item[2][0] in primary_targets) is selected_primary)
        for _rank, grouped in groupby(sorted(pool, key=lambda item: item[0]), key=lambda item: item[0]):
            batch = tuple(grouped)
            increment = sum(volume << (maximum - bits) for volume, bits, _key, _count in batch)
            if FALSE_BOUND_DENOMINATOR * (cumulative + increment) >= 1 << maximum:
                break
            cumulative += increment
            admitted.update(
                (target, shape.name, remaining, substitutions)
                for _volume, _bits, (target, shape, remaining, substitutions), _count in batch
            )
    return tuple(
        CrossLengthClass(
            target,
            shape.name,
            remaining,
            substitutions,
            alignments,
            volume,
            bits,
            volume << (maximum - bits),
            target in primary_targets,
            (target, shape.name, remaining, substitutions) in admitted,
        )
        for volume, bits, (target, shape, remaining, substitutions), alignments in raw
    )


def classes(
    hrp: str,
    target_length: int,
    immutable_prefix: str | None = None,
    explicit_erasures: int = 0,
) -> tuple[CaptureClass, ...]:
    immutable_length = len(immutable_prefix or f"{hrp}1")
    space = 1 << checksum_bits(hrp, target_length)
    raw = [
        (
            capture_volume(
                shape,
                target_length,
                immutable_length,
                substitutions,
                explicit_erasures,
            ),
            shape,
            substitutions,
            alignment_count(shape, target_length, immutable_length),
        )
        for shape in supported_shapes()
        for substitutions in decoder_capacity(shape, explicit_erasures)
    ]
    result: list[CaptureClass] = []
    for delta in sorted({shape.delta for _volume, shape, _substitutions, _count in raw}):
        cumulative = 0
        for volume, shape, substitutions, alignments in sorted(
            (item for item in raw if item[1].delta == delta),
            key=lambda item: (item[0], item[1].name, item[2]),
        ):
            cumulative += volume
            result.append(
                CaptureClass(
                    shape.name,
                    delta,
                    substitutions,
                    alignments,
                    volume,
                    cumulative,
                    FALSE_BOUND_DENOMINATOR * cumulative < space,
                )
            )
    return tuple(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hrp", default="ms")
    parser.add_argument("--length", type=int, default=48)
    parser.add_argument("--observed-length", type=int)
    parser.add_argument("--immutable-prefix")
    parser.add_argument("--erasures", type=int, default=0)
    arguments = parser.parse_args()
    if arguments.observed_length is not None and arguments.erasures:
        parser.error("--erasures cannot be combined with --observed-length")
    result = (
        cross_length_classes(
            arguments.observed_length,
            immutable_prefix=arguments.immutable_prefix or "ms1",
        )
        if arguments.observed_length is not None
        else classes(arguments.hrp, arguments.length, arguments.immutable_prefix, arguments.erasures)
    )
    print(json.dumps([asdict(item) for item in result], indent=2))


if __name__ == "__main__":
    main()
