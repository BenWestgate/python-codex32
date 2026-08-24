"""Bounded smoke and property campaigns for checked-in fuzz targets."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tools.fuzz_correction_context import LLVMFuzzerTestOneInput as fuzz_context
from tools.fuzz_untrusted_boundaries import MAX_INPUT, LLVMFuzzerTestOneInput


@pytest.mark.parametrize(
    "data",
    (
        b"",
        b"\x00" + b"q" * (MAX_INPUT - 1),
        b"\x01ms1\xff\xfe\x00\n",
        b"\x02bip39_24w1" + b"?" * 128,
        b"\x03" + b"ms10testsxxxxxxxxxxxxxxxxxxxxxxxxxx4nzvca9cmczlw " * 10,
        b"\x04create --bytes 17",
        b"\x00" + b"q" * MAX_INPUT,
    ),
)
def test_fuzz_target_boundary_seeds(data: bytes) -> None:
    assert LLVMFuzzerTestOneInput(data) == 0


@given(st.binary(max_size=MAX_INPUT))
@settings(max_examples=250, deadline=None)
def test_fuzz_target_does_not_crash(data: bytes) -> None:
    assert LLVMFuzzerTestOneInput(data) == 0


@given(st.binary(max_size=MAX_INPUT))
@settings(max_examples=250, deadline=None)
def test_correction_context_fuzz_target_does_not_crash(data: bytes) -> None:
    assert fuzz_context(data) == 0
