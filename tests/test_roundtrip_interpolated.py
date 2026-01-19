"""Test for round-trip encoding/decoding and recovery via interpolation."""

from codex32 import Codex32String, decode


def test_round_trip_recovery():
    """Test round-trip encoding/decoding and recovery via interpolation."""
    # secret share from seed
    s = Codex32String.from_seed(
        bytes.fromhex("68f14219957131d21b615271058437e8"), "ms13k00ls"
    )
    assert s.s == "ms13k00lsdrc5yxv4wycayxmp2fcstpphaq55a60p9hfds9t"
    a = Codex32String.from_seed(
        bytes.fromhex("641be1cb12c97ede1c6bad8edf067760"), "ms13k00la"
    )
    assert a.s == "ms13k00lavsd7rjcje9ldu8rt4k8d7pnhvppyrt5gpff9wwl"
    c = Codex32String.from_seed(
        bytes.fromhex("61b3c4052f7a31dc2b425c843a13c9b4"), "ms13k00lc"
    )
    assert c.s == "ms13k00lcvxeugpf00gcac26ztjzr5y7fknx9cw72l8md0xn"
    # derive next share via interpolation
    d = Codex32String.interpolate_at([s, a, c], "d")
    assert d.s == "ms13k00ldp4v5nw8lph96x47mjxzgwjexehw766s4dmj6qx8"

    # now round-trip d share ('d' is derived via interpolation, NOT via 'from_seed')
    dd = Codex32String.from_seed(d.data, "ms13k00ld", d.pad_val)
    assert dd.s == d.s

    e = Codex32String.interpolate_at([s, a, c], "e")
    f = Codex32String.interpolate_at([s, a, c], "f")
    assert e.s == "ms13k00lezuknydaaygk5u20zs4fm736vj6zlcrjhtduanyk"
    assert f.s == "ms13k00lf0ehe53zsu6vrxcjjh9v7wzsa8vd9pjk28l8zavw"

    # recover from shares, use 'd' without round-trip
    rec_s = Codex32String.interpolate_at([a, c, d], "s")
    # recover from shares, use 'd' after round-trip
    rec_ss = Codex32String.interpolate_at([a, c, dd], "s")
    # confirm recovered secrets and padding match original
    assert decode(s.hrp, rec_s.s, "CRC") == ("3k00ls", s.data, "CRC")
    assert decode(s.hrp, rec_ss.s, "CRC") == ("3k00ls", s.data, "CRC")
