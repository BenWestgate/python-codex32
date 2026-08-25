"""Setuptools backend with opt-in reproducible sdist archive metadata."""

from __future__ import annotations

import gzip
import io
import os
import tarfile
from pathlib import Path
from typing import Any

from setuptools import build_meta as _backend

_VARIABLE_PAX_FIELDS = {
    "atime",
    "ctime",
    "gid",
    "gname",
    "mtime",
    "uid",
    "uname",
}

build_editable = _backend.build_editable
build_wheel = _backend.build_wheel
get_requires_for_build_editable = _backend.get_requires_for_build_editable
get_requires_for_build_sdist = _backend.get_requires_for_build_sdist
get_requires_for_build_wheel = _backend.get_requires_for_build_wheel
prepare_metadata_for_build_editable = _backend.prepare_metadata_for_build_editable
prepare_metadata_for_build_wheel = _backend.prepare_metadata_for_build_wheel


def _stable_pax_headers(headers: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key not in _VARIABLE_PAX_FIELDS}


def _normalize_sdist(path: Path, epoch: int) -> None:
    with tarfile.open(path, "r:gz") as source:
        members = [
            (member, source.extractfile(member).read() if member.isfile() else None)
            for member in source.getmembers()
        ]

    temporary = path.with_suffix(".tmp")
    with (
        temporary.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as output,
    ):
        for member, data in members:
            member.mtime = epoch
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            member.pax_headers = _stable_pax_headers(member.pax_headers)
            output.addfile(member, io.BytesIO(data) if data is not None else None)
    os.replace(temporary, path)


def build_sdist(
    sdist_directory: str,
    config_settings: dict[str, Any] | None = None,
) -> str:
    filename = _backend.build_sdist(sdist_directory, config_settings)
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is not None:
        _normalize_sdist(Path(sdist_directory, filename), int(epoch))
    return filename
