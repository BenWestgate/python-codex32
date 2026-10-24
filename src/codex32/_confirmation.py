"""Shared alignment of independently transcribed recovery cards."""

_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def _compact(text: str) -> str:
    """Ignore whitespace and ASCII case without interpreting other characters."""
    return "".join(text.split()).translate(_ASCII_LOWER)


def _entered_groups(observed: str, expected: str) -> tuple[list[str], set[int]]:
    """Align entered groups without supplying any expected characters."""
    positions = [i for i, char in enumerate(observed) if not char.isspace()]
    compact = _compact(observed)
    expected = _compact(expected)
    tokens = observed.split()
    grouped = len(tokens) > 1 and compact != expected
    boundaries = {0}
    splits: set[tuple[int, int]] = set()
    position = 0
    for token in tokens:
        for offset in range(0, len(expected), 4):
            if expected[offset : offset + len(token)] == _compact(token) and (
                len(token) % 4 == 0 or offset + len(token) == len(expected)
            ):
                splits.update((position + i, offset + i) for i in range(4, len(token), 4))
        position += len(token)
        boundaries.add(position)
    scores = {0: (0, 0, b"", ())}  # type: dict[int, tuple[int, int, bytes, tuple[int, ...]]]
    for offset in range(0, len(expected), 4):
        canonical = expected[offset : offset + 4]
        following: dict[int, tuple[int, int, bytes, tuple[int, ...]]] = {}
        for start, (edits, disturbed, trace, ends) in scores.items():
            row = [(j, b"\x03" * j) for j in range(len(canonical) + 1)]
            for end in range(start, len(compact) + 1):
                if end > start:
                    current = [(end - start, b"\x02" * (end - start))]
                    for j, char in enumerate(canonical, 1):
                        edit = compact[end - 1] != char
                        current.append(
                            min(
                                (row[j - 1][0] + edit, row[j - 1][1] + bytes([edit])),
                                (row[j][0] + 1, row[j][1] + b"\x02"),
                                (current[j - 1][0] + 1, current[j - 1][1] + b"\x03"),
                            )
                        )
                    row = current
                if grouped and end not in boundaries and (end, offset + len(canonical)) not in splits:
                    continue
                score = (
                    edits + row[-1][0],
                    disturbed + (not grouped and compact[start:end] != canonical),
                    trace + row[-1][1],
                    (*ends, end),
                )
                if end not in following or score < following[end]:
                    following[end] = score
        scores = following
    groups = []
    start = 0
    for end in scores[len(compact)][3]:
        stop = positions[end] if end < len(positions) else len(observed)
        groups.append(observed[start:stop])
        start = stop
    changed = {i for i, value in enumerate(groups) if _compact(value) != expected[i * 4 : i * 4 + 4]}
    return groups, changed
