"""Regression evidence for reproducible source-distribution metadata."""

from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

from build_backend import _normalize_sdist


def _write_sdist(path: Path, timestamp: int) -> None:
    payload = b"reproducible source\n"
    member = tarfile.TarInfo("codex32/example.txt")
    member.size = len(payload)
    member.mtime = timestamp
    member.uid = member.gid = timestamp
    member.uname = member.gname = str(timestamp)
    member.pax_headers = {"atime": str(timestamp), "purpose": "test"}

    with (
        path.open("wb") as raw,
        gzip.GzipFile(filename="variable.tar", mode="wb", fileobj=raw, mtime=timestamp) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        archive.addfile(member, io.BytesIO(payload))


def test_sdist_normalization_removes_variable_archive_metadata(tmp_path: Path) -> None:
    epoch = 1_763_060_600
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    _write_sdist(first, epoch + 1)
    _write_sdist(second, epoch + 2)

    _normalize_sdist(first, epoch)
    _normalize_sdist(second, epoch)

    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first, "r:gz") as archive:
        member = archive.getmembers()[0]
        assert member.mtime == epoch
        assert (member.uid, member.gid, member.uname, member.gname) == (0, 0, "", "")
        assert member.pax_headers == {"purpose": "test"}
        assert archive.extractfile(member).read() == b"reproducible source\n"
