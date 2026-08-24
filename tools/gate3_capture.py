"""Reproduce Gate 3 decoder-capture bounds with exact integer arithmetic."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from math import comb

FALSE_BOUND_DENOMINATOR = 10_000


@dataclass(frozen=True, slots=True)
class Shape:
    """One complete structural alignment generator."""

    name: str
    inserted: int = 0
    omitted: int = 0
    grouped: bool = False
    burst: bool = False

    @property
    def delta(self) -> int:
        return self.inserted - self.omitted


@dataclass(frozen=True, slots=True)
class CaptureClass:
    """One structural shape and exact fixed-decoder outcome class."""

    shape: str
    delta: int
    substitutions: int
    explicit_erasures: int
    alignments: int
    volume: int
    cumulative_volume: int
    safe: bool


def checksum_bits(hrp: str, target_length: int) -> int:
    """Return the registered checksum size for a complete canonical string."""
    expanded_length = target_length + len(hrp)
    if expanded_length <= 93:
        return 65
    if expanded_length >= 96 and expanded_length <= 1023:
        return 75
    raise ValueError("target falls in the invalid checksum-length gap")


def _mutable_groups(hrp: str, target_length: int) -> int:
    prefix_length = len(hrp) + 1
    return sum(start >= prefix_length for start in range(0, target_length - 3, 4))


def alignment_count(shape: Shape, hrp: str, target_length: int) -> int:
    """Count every alignment generated for one observed/target length pair."""
    if shape.name == "fixed":
        return 1
    if shape.grouped:
        target_groups = _mutable_groups(hrp, target_length)
        observed_groups = target_groups + (shape.inserted - shape.omitted) // 4
        inserted_groups = shape.inserted // 4
        omitted_groups = shape.omitted // 4
        if observed_groups < inserted_groups or target_groups < omitted_groups:
            return 0
        if shape.burst:
            deletion_starts = observed_groups - inserted_groups + 1 if inserted_groups else 1
            omission_starts = target_groups - omitted_groups + 1 if omitted_groups else 1
            return deletion_starts * omission_starts
        return comb(observed_groups, inserted_groups) * comb(target_groups, omitted_groups)

    target_body = target_length - len(hrp) - 1
    observed_body = target_body + shape.delta
    if observed_body < shape.inserted or target_body < shape.omitted:
        return 0
    if shape.burst:
        deletion_starts = observed_body - shape.inserted + 1 if shape.inserted else 1
        omission_starts = target_body - shape.omitted + 1 if shape.omitted else 1
        return deletion_starts * omission_starts
    return comb(observed_body, shape.inserted) * comb(target_body, shape.omitted)


def capture_volume(
    shape: Shape,
    hrp: str,
    target_length: int,
    substitutions: int,
    explicit_erasures: int = 0,
) -> int:
    """Return a conservative volume for one exact decoder result class."""
    target_body = target_length - len(hrp) - 1
    unknown = shape.omitted + explicit_erasures
    known = target_body - unknown
    if known < substitutions:
        return 0
    return (
        alignment_count(shape, hrp, target_length)
        * 32**unknown
        * comb(known, substitutions)
        * 31**substitutions
    )


def decoder_capacity(shape: Shape, bits: int, explicit_erasures: int = 0) -> range:
    """Return exact substitution counts guaranteed by the fixed core."""
    erasures = shape.omitted + explicit_erasures
    if shape.burst and not shape.inserted and erasures <= (13 if bits == 65 else 15):
        return range(1)
    if erasures > 8:
        return range(0)
    return range((8 - erasures) // 2 + 1)


def supported_shapes() -> tuple[Shape, ...]:
    """Return the deliberately small candidate envelope evaluated for v1."""
    result = [Shape("fixed")]
    result.extend(
        Shape(f"arbitrary-{inserted}i-{omitted}o", inserted, omitted)
        for inserted in range(3)
        for omitted in range(3)
        if inserted or omitted
    )
    result.extend(Shape(f"burst-{count}i", inserted=count, burst=True) for count in range(3, 10))
    result.extend(Shape(f"burst-{count}o", omitted=count, burst=True) for count in range(3, 14))
    result.extend(Shape(f"groups-{count}i", inserted=4 * count, grouped=True) for count in range(1, 5))
    result.extend(Shape(f"groups-{count}o", omitted=4 * count, grouped=True) for count in range(1, 4))
    result.append(Shape("groups-1i-1o", inserted=4, omitted=4, grouped=True))
    return tuple(result)


def classes(
    hrp: str,
    target_length: int,
    *,
    grouped: bool,
    explicit_erasures: int = 0,
) -> tuple[CaptureClass, ...]:
    """Rank all classes and apply the cumulative conservative union bound."""
    bits = checksum_bits(hrp, target_length)
    space = 1 << bits
    raw: list[tuple[int, Shape, int, int]] = []
    for shape in supported_shapes():
        if shape.grouped and not grouped:
            continue
        alignments = alignment_count(shape, hrp, target_length)
        for substitutions in decoder_capacity(shape, bits, explicit_erasures):
            volume = capture_volume(
                shape,
                hrp,
                target_length,
                substitutions,
                explicit_erasures,
            )
            if alignments and volume:
                raw.append((volume, shape, substitutions, alignments))

    result: list[CaptureClass] = []
    for delta in sorted({shape.delta for _volume, shape, _substitutions, _alignments in raw}):
        ranked = sorted(
            (item for item in raw if item[1].delta == delta),
            key=lambda item: (item[0], item[1].name, item[2]),
        )
        cumulative = 0
        for volume, shape, substitutions, alignments in ranked:
            cumulative += volume
            result.append(
                CaptureClass(
                    shape.name,
                    delta,
                    substitutions,
                    explicit_erasures,
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
    parser.add_argument("--grouped", action="store_true")
    parser.add_argument("--erasures", type=int, default=0)
    arguments = parser.parse_args()
    result = classes(
        arguments.hrp,
        arguments.length,
        grouped=arguments.grouped,
        explicit_erasures=arguments.erasures,
    )
    print(json.dumps([asdict(item) for item in result], indent=2))


if __name__ == "__main__":
    main()
