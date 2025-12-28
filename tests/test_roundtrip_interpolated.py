from itertools import product
from src.codex32.codex32 import Codex32String, IDX_ORDER


def recover_with_bytes(hrp, header_str, share_idx_list, share_bytes_list, target="s"):
    """Recover codex32 secret from share bytes assuming default padding."""
    pad_len = (5 - (len(share_bytes_list[0]) * 8) % 5) % 5
    default_padded_shares = IDX_ORDER[1 : 1 + len(share_idx_list)]
    pad_candidates = product(range(1 << pad_len), repeat=len(share_idx_list))
    for pad_vals in pad_candidates:
        given_shares = []
        for idx, data, pad_val in zip(share_idx_list, share_bytes_list, pad_vals):
            given_shares.append(Codex32String.from_seed(data, hrp + '1' + header_str + idx, pad_val))
        for share_idx in default_padded_shares:
            initial_share = Codex32String.interpolate_at(given_shares, share_idx)
            round_tripped_initial_share = Codex32String.from_seed(initial_share.data, hrp + "1" + header_str + share_idx)
            if str(round_tripped_initial_share) != str(initial_share):
                break
        return Codex32String.interpolate_at(given_shares, target)

def test_round_trip_recovery():
    # secret share from seed
    s = Codex32String.from_seed(bytes.fromhex("68f14219957131d21b615271058437e8"), "ms13k00ls")
    assert s.s == "ms13k00lsdrc5yxv4wycayxmp2fcstppharks8z0r84pf3uj"

    # derive 'a' via proposed BIP-85
    a = Codex32String.from_seed(bytes.fromhex("641be1cb12c97ede1c6bad8edf067760"), "ms13k00la")
    assert a.s == "ms13k00lavsd7rjcje9ldu8rt4k8d7pnhvppyrt5gpff9wwl"

    # derive 'c' via proposed BIP-85
    c = Codex32String.from_seed(bytes.fromhex("61b3c4052f7a31dc2b425c843a13c9b4"), "ms13k00lc")
    assert c.s == "ms13k00lcvxeugpf00gcac26ztjzr5y7fkjl7fx7nx7ykhkr"

    # derive next share via interpolation
    d = Codex32String.interpolate_at([s, a, c], "d")
    assert d.s == "ms13k00ldp4v5nw8lph96x47mjxzgwjexe44p32swkq99e0w"

    # now round-trip d share ('d' is derived via interpolation, NOT via 'from_seed')
    dd = Codex32String.from_seed(d.data, "ms13k00ld")
    # they are NOT equal after round-trip - seem we miss padding at interpolation level
    # assert dd.s == d.s  # FAIL (should equal)

    # irrelevant
    # e = Codex32String.interpolate_at([s, a, c], "e")
    # assert e.s == "ms13k00lezuknydaaygk5u20zs4fm736vj909mdj6xqp8pc2"
    #
    # f = Codex32String.interpolate_at([s, a, c], "f")
    # assert f.s == "ms13k00lf0ehe53zsu6vrxcjjh9v7wzsa83mqfvku3fd8kem"

    # recover from shares, use 'd' without round-trip
    rec_s = Codex32String.interpolate_at([a, d, c], "s")
    # recover from shares, use 'd' after round-trip
    rec_ss = Codex32String.interpolate_at([a, dd, c], "s")


    xx = recover_with_bytes("ms", "3k00l", ["a", "d", "c"], [a.data, d.data, c.data])
    # recover with round-trip D share
    yy = recover_with_bytes("ms", "3k00l", ["a", "d", "c"], [a.data, dd.data, c.data])

    print("     s:", s.data.hex())
    print(" rec_s:", rec_s.data.hex())
    print("rec_ss:", rec_ss.data.hex())
    print("rec_xx:", xx.data.hex())
    print("rec_yy:", yy.data.hex())
    assert s.data == rec_s.data
    assert s.data == yy.data      # FAIL
    assert s.data == xx.data      # FAIL
    assert s.data == rec_ss.data  # FAIL

