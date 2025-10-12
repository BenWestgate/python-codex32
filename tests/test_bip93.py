# test_codex32.py
"""Tests for BIP-93 Codex32 implementation."""
import pytest # pylint: disable=import-error

from data.bip93_vectors import (
    VECTOR_1,
    VECTOR_2,
    VECTOR_3,
    VECTOR_4,
    VECTOR_5,
    BAD_CHECKSUMS,
    WRONG_CHECKSUMS,
    INVALID_LENGTHS,
    INVALID_SHARE_INDEX,
    INVALID_THRESHOLD,
    INVALID_PREFIX_OR_SEPARATOR,
    BAD_CASES,
)

from codex32.codex32 import (
    Codex32String,
    InvalidChecksum,
    InvalidLength,
    SeparatorNotFound,
    MismatchedHrp,
    IncompleteGroup,
    InvalidShareIndex,
    InvalidThreshold,
    InvalidCase,
)

def test_parts():
    """Test Vector 1: parse a codex32 string into parts"""
    c32 = Codex32String.from_string(VECTOR_1["secret_s"])
    parts = c32.parts()
    assert parts.hrp == VECTOR_1["hrp"]
    assert parts.k == VECTOR_1["k"]
    assert parts.share_index == VECTOR_1["share_index"]
    assert parts.ident == VECTOR_1["identifier"]
    assert parts.payload == VECTOR_1["payload"]
    assert parts.checksum == VECTOR_1["checksum"]
    assert parts.data().hex() == VECTOR_1["secret_hex"]

def test_derive_and_recover():
    """Test Vector 2: derive new share and recover the secret"""
    a = Codex32String.from_string(VECTOR_2["share_A"])
    c = Codex32String.from_string(VECTOR_2["share_C"])
    # interpolation target is 'D' (uppercase as inputs are uppercase)
    d = Codex32String.interpolate_at([a, c], 'D')
    assert str(d) == VECTOR_2["derived_D"]
    s = Codex32String.interpolate_at([a, c], 'S')
    assert str(s) == VECTOR_2["secret_S"]
    assert s.parts().data().hex() == VECTOR_2["secret_hex"]

def test_from_seed_and_interpolate_3_of_5():
    """Test Vector 3: encode secret share from seed and split 3-of-5"""
    seed = bytes.fromhex(VECTOR_3["secret_hex"])
    a = Codex32String.from_string(VECTOR_3["share_a"])
    c = Codex32String.from_string(VECTOR_3["share_c"])
    parts = a.parts()
    s = Codex32String.from_seed(seed, parts.ident, parts.hrp, parts.k,  pad_val=0)
    assert str(s) == VECTOR_3["secret_s"]
    d = Codex32String.interpolate_at([s, a, c], 'd')
    e = Codex32String.interpolate_at([s, a, c], 'e')
    f = Codex32String.interpolate_at([s, a, c], 'f')
    assert str(d) == VECTOR_3["derived_d"]
    assert str(e) == VECTOR_3["derived_e"]
    assert str(f) == VECTOR_3["derived_f"]
    for pad_val in range(4):
        s = Codex32String.from_seed(seed, parts.ident, parts.hrp, parts.k,  pad_val=pad_val)
        assert str(s) == VECTOR_3["secret_s_alternates"][pad_val]

def test_from_seed_and_alternates():
    """Test Vector 4: encode secret share from seed"""
    seed = bytes.fromhex(VECTOR_4["secret_hex"])
    for pad_v in range(0b1111):
        s = Codex32String.from_seed(seed, hrp='ms', k=0, ident='leet', share_idx='s', pad_val=pad_v)
        assert str(s) == VECTOR_4["secret_s_alternates"][pad_v]
        assert s.parts().data() == list(seed) or s.parts().data() == seed
        # confirm all 16 encodings decode to same master data

def test_long_string():
    """Test Vector 5: decode long codex32 secret and confirm secret bytes."""
    long_str = VECTOR_5["secret_s"]
    long_seed = Codex32String.from_string(long_str)
    assert long_seed.parts().data().hex() == VECTOR_5["secret_hex"]

# pylint: disable=missing-function-docstring
def test_invalid_bad_checksums():
    for chk in BAD_CHECKSUMS:
        with pytest.raises(InvalidChecksum):
            Codex32String.from_string(chk)

def test_wrong_checksums_or_length():
    for chk in WRONG_CHECKSUMS:
        with pytest.raises((InvalidChecksum, InvalidLength)):
            Codex32String.from_string(chk)

def test_invalid_improper_length():
    for chk in INVALID_LENGTHS:
        with pytest.raises((InvalidLength, IncompleteGroup)):
            Codex32String.from_string(chk)

def test_invalid_index():
    for chk in INVALID_SHARE_INDEX:
        with pytest.raises(InvalidShareIndex):
            Codex32String.from_string(chk)

def test_invalid_threshold():
    for chk in INVALID_THRESHOLD:
        with pytest.raises(InvalidThreshold):
            Codex32String.from_string(chk)

def test_invalid_prefix_or_separator():
    for chk in INVALID_PREFIX_OR_SEPARATOR:
        try:
            Codex32String.from_string(chk)
            assert False, f"Accepted invalid HRP/separator in: {chk}"
        except (MismatchedHrp, SeparatorNotFound):
            pass

def test_invalid_case_examples():
    for chk in BAD_CASES:
        with pytest.raises(InvalidCase):
            Codex32String.from_string(chk)
