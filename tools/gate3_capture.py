"""Reproduce Gate 3 structural capture bounds with independent integer arithmetic."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
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
    parser.add_argument("--immutable-prefix")
    parser.add_argument("--erasures", type=int, default=0)
    arguments = parser.parse_args()
    result = classes(
        arguments.hrp,
        arguments.length,
        arguments.immutable_prefix,
        arguments.erasures,
    )
    print(json.dumps([asdict(item) for item in result], indent=2))


if __name__ == "__main__":
    main()
