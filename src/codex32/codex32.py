#!/bin/python3
# Author: Leon Olsson Curr and Pearlwort Sneed <pearlwort@wpsoftware.net>
# License: BSD-3-Clause
"""Complete BIP-93 Codex32 implementation"""

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
MS32_CONST = 0x10CE0795C2FD1E62A
MS32_LONG_CONST = 0x43381E570BF4798AB26
bech32_inv = [
    0, 1, 20, 24, 10, 8, 12, 29, 5, 11, 4, 9, 6, 28, 26, 31,
    22, 18, 17, 23, 2, 25, 16, 19, 3, 21, 14, 30, 13, 7, 27, 15,
]


def ms32_polymod(values):
    """Compute the ms32 polymod."""
    gen = [
        0x19DC500CE73FDE210,
        0x1BFAE00DEF77FE529,
        0x1FBD920FFFE7BEE52,
        0x1739640BDEEE3FDAD,
        0x07729A039CFC75F5A,
    ]
    residue = 0x23181B3
    for v in values:
        b = residue >> 60
        residue = (residue & 0x0FFFFFFFFFFFFFFF) << 5 ^ v
        for i in range(5):
            residue ^= gen[i] if ((b >> i) & 1) else 0
    return residue


def ms32_verify_checksum(data):
    """Determine long or short checksum and verify it."""
    if len(data) >= 96:  # See Long codex32 Strings
        return ms32_verify_long_checksum(data)
    if len(data) <= 93:
        return ms32_polymod(data) == MS32_CONST
    raise InvalidLength(f"{len(data)} data characters must be 26-93 or 96-103 in length")


def ms32_create_checksum(data):
    """Determine long or short checksum, create and return it."""
    if len(data) > 80:  # See Long codex32 Strings
        return ms32_create_long_checksum(data)
    values = data
    polymod = ms32_polymod(values + [0] * 13) ^ MS32_CONST
    return [(polymod >> 5 * (12 - i)) & 31 for i in range(13)]


def ms32_long_polymod(values):
    """Compute the ms32 long polymod."""
    gen = [
        0x3D59D273535EA62D897,
        0x7A9BECB6361C6C51507,
        0x543F9B7E6C38D8A2A0E,
        0x0C577EAECCF1990D13C,
        0x1887F74F8DC71B10651,
    ]
    residue = 0x23181B3
    for v in values:
        b = residue >> 70
        residue = (residue & 0x3FFFFFFFFFFFFFFFFF) << 5 ^ v
        for i in range(5):
            residue ^= gen[i] if ((b >> i) & 1) else 0
    return residue


def ms32_verify_long_checksum(data):
    """Verify the long codex32 checksum."""
    return ms32_long_polymod(data) == MS32_LONG_CONST


def ms32_create_long_checksum(data):
    """Create the long codex32 checksum."""
    values = data
    polymod = ms32_long_polymod(values + [0] * 15) ^ MS32_LONG_CONST
    return [(polymod >> 5 * (14 - i)) & 31 for i in range(15)]


def bech32_mul(a, b):
    """Multiply two bech32 values."""
    res = 0
    for i in range(5):
        res ^= a if ((b >> i) & 1) else 0
        a *= 2
        a ^= 41 if (32 <= a) else 0
    return res


# noinspection PyPep8
def bech32_lagrange(l, x):  # noqa: E741
    """Compute bech32 lagrange."""
    n = 1
    c = []
    for i in l:
        n = bech32_mul(n, i ^ x)
        m = 1
        for j in l:
            m = bech32_mul(m, (x if i == j else i) ^ j)
        c.append(m)
    return [bech32_mul(n, bech32_inv[i]) for i in c]


def ms32_interpolate(l, x):  # noqa: E741
    """Interpolate codex32."""
    w = bech32_lagrange([s[5] for s in l], x)
    res = []
    for i in range(len(l[0])):
        n = 0
        for j, val in enumerate(l):
            n ^= bech32_mul(w[j], val[i])
        res.append(n)
    return res


def ms32_recover(l):  # noqa: E741
    """Recover the codex32 secret."""
    return ms32_interpolate(l, 16)


# Copyright (c) 2025 Ben Westgate
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

# pylint: disable=missing-class-docstring

class Codex32Error(Exception):
    msg = "Base Codex32 error class"
    def __init__(self, extra: str | None = None):
        self.extra = extra
        super().__init__(extra)

    def __str__(self):
        return f"{self.__class__.msg}" + (f" {self.extra}" if self.extra else "")


class IdNotLength4(Codex32Error):
    msg = "Identifier had wrong length"

class IncompleteGroup(Codex32Error):
    msg = "Incomplete group (extraneous bits)"

class InvalidDataValue(Codex32Error):
    msg = "Data must be list of integers"

class SeparatorNotFound(Codex32Error):
    msg = "No separator character '1' found"

class InvalidLength(Codex32Error):
    msg = "Illegal codex32 length"

class InvalidChar(Codex32Error):
    msg = "Invalid character"

class InvalidCase(Codex32Error):
    msg = "Mixed case"

class InvalidChecksum(Codex32Error):
    msg = "Invalid checksum"

class InvalidThreshold(Codex32Error):
    msg = "Invalid threshold"

class InvalidThresholdN(Codex32Error):
    msg = "Invalid numeric threshold"

class InvalidShareIndex(Codex32Error):
    msg = "Invalid share index"

class MismatchedLength(Codex32Error):
    msg = "Mismatched share lengths"

class MismatchedHrp(Codex32Error):
    msg = "Mismatched human-readable part"

class MismatchedThreshold(Codex32Error):
    msg = "Mismatched threshold"

class MismatchedId(Codex32Error):
    msg = "Mismatched identifier"

class RepeatedIndex(Codex32Error):
    msg = "Repeated index"

class ThresholdNotPassed(Codex32Error):
    msg = "Threshold not passed"


def bech32_encode(data, hrp=''):
    """Compute a Bech32 string given HRP and data values."""
    for i, x in enumerate(data):
        if not 0 <= x < 32:
            raise InvalidDataValue(f"from 0 to 31 index={i} value={x}")
    ret = (hrp + '1' if hrp else '') + ''.join(CHARSET[d] for d in data)
    if hrp.lower() == hrp:
        return ret.lower()
    if hrp.upper() == hrp:
        return ret.upper()
    raise InvalidCase("in hrp")


def bech32_to_u5(bech=''):
    """Map bech32 data-part string -> list of 5-bit integers (0-31)."""
    bech = bech.lower()
    for i, ch in enumerate(bech):
        if ch not in CHARSET:
            raise InvalidChar(f"{ch!r} at pos={i} in data part")
    return [CHARSET.find(x) for x in bech]


def bech32_decode(bech='', hrp='ms'):
    """Validate a Bech32/Codex32 string, and determine HRP and data."""
    for i, ch in enumerate(bech):
        if ord(ch) < 33 or ord(ch) > 126:
            raise InvalidChar(f"non-printable U+{ord(ch):04X} at pos={i}")
    if bech.upper() == bech:
        hrp = hrp.upper()
    elif bech.lower() != bech:
        raise InvalidCase
    pos = bech.rfind('1')
    if pos < 0:
        raise SeparatorNotFound
    hrpgot = bech[:pos]
    if hrpgot != hrp:
        raise MismatchedHrp(f"{hrpgot} expected {hrp}")
    data = bech32_to_u5(bech[pos + 1:])
    return hrp, data


def compute_crc(crc_len, values):
    """Internal function that computes a CRC checksum for padding."""
    if not 0 <= crc_len < 5: # Codex32 string CRC padding
        raise InvalidLength(f"{crc_len!r} (expected int in 0..4)")
    # Define the CRC polynomial (x^crc_len + x + 1) optimal for 1-4
    polynomial = (1 << crc_len) | 3
    crc = 0
    for i, bit in enumerate(values):
        if bit not in (0, 1):
            raise InvalidDataValue(f" 0 or 1 index={i} value={bit}")
        crc = (crc << 1) | int(bit)
        if crc & (1 << crc_len):
            crc ^= polynomial
    return crc & (2 ** crc_len - 1) # Return last crc_len bits as CRC


def convertbits(data, frombits, tobits, pad=True, pad_val=-1):
    """General power-of-2 base conversion with CRC padding."""
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for i, value in enumerate(data):
        if value < 0 or (value >> frombits):
            raise InvalidDataValue(f" 0 though {frombits} index={i} value={value}")
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
            acc = acc & ((1 << bits) - 1)
    if pad and bits:
        if pad_val == -1:  # Use CRC padding
            data_bits = convertbits(ret, tobits, 1) + convertbits([acc], bits, 1)
            pad_val = compute_crc(tobits - bits, convertbits(data_bits, tobits, 1))
        ret.append(((acc << (tobits - bits)) + pad_val) & maxv)
    elif bits >= frombits:
        raise IncompleteGroup(f"{bits} bits left over")
    return ret

def verify_crc(data, pad_val):
    """Verify the codex32 padding matches the specified type."""
    unpadded = convertbits(data, 5, 8, False)
    if data != convertbits(unpadded, 8, 5, pad_val=pad_val):
        pad_str = "CRC" if pad_val < 0 else bin(pad_val)
        raise InvalidChecksum(f"Padding bits do not match expected {pad_str} padding.")


class Codex32String:
    """Class representing a Codex32 string."""
    def __init__(self, s=''):
        self.s = s

    def __str__(self):
        return self.s

    def __eq__(self, other):
        if not isinstance(other, Codex32String):
            return False
        return self.s == other.s

    def __hash__(self):
        return hash(self.s)

    def sanity_check(self):
        """Perform sanity check on the codex32 string."""
        parts = self.parts_inner()
        incomplete_group = (len(parts.payload) * 5) % 8
        if incomplete_group > 4:
            raise IncompleteGroup(str(incomplete_group))

    @classmethod
    def from_unchecksummed_string(cls, s, hrp="ms"):
        """Create Codex32String from unchecksummed string."""
        hrp, data = bech32_decode(s, hrp=hrp)
        ret = cls(bech32_encode(data + ms32_create_checksum(data), hrp))
        ret.sanity_check()
        return ret

    @classmethod
    def from_string(cls, s, hrp="ms"):
        """Create Codex32String from a codex32 string."""
        _, data = bech32_decode(s, hrp=hrp)
        if not ms32_verify_checksum(data):
            raise InvalidChecksum(f"string={s}")
        ret = cls(s)
        ret.sanity_check()
        return ret

    def parts_inner(self):
        """Get inner parts of the codex32 string."""
        hrp, s = self.s.rsplit('1', 1) if '1' in self.s else ("", self.s)
        if len(s) < 94 and len(s) > 44:
            checksum_len = 13
        elif len(s) >= 96 and len(s) < 125:
            checksum_len = 15
        else:
            raise InvalidLength(f"{len(s)} must be 45-93 or 96 to 124")
        threshold_char = s[0]
        if threshold_char.isdigit() and threshold_char != '1':
            k = int(threshold_char)
        else:
            raise InvalidThreshold(threshold_char)
        ret = Parts(
            hrp=hrp,
            k=k,
            ident=s[1:5],
            share_index=s[5],
            payload=s[6:len(s) - checksum_len],
            checksum=s[-checksum_len:],
        )
        if ret.k == 0 and ret.share_index.lower() != 's':
            raise InvalidShareIndex(ret.share_index + "must be 's' when k=0")
        return ret

    def parts(self):
        """Get parts of the codex32 string."""
        return self.parts_inner()

    @classmethod
    def interpolate_at(cls, shares, target):
        """Interpolate to a specific target share index."""
        indices = []
        ms32_shares = []
        s0_parts = shares[0].parts()
        if s0_parts.k > len(shares):
            raise ThresholdNotPassed(f"threshold={s0_parts.k}, n_shares={len(shares)}")
        for share in shares:
            parts = share.parts()
            if len(shares[0].s) != len(share.s):
                raise MismatchedLength(f"{len(shares[0].s)}, {len(share.s)}")
            if s0_parts.hrp != parts.hrp:
                raise MismatchedHrp(f"{s0_parts.hrp}, {parts.hrp}")
            if s0_parts.k != parts.k:
                raise MismatchedThreshold(f"{s0_parts.k}, {parts.k}")
            if s0_parts.ident != parts.ident:
                raise MismatchedId(f"{s0_parts.ident}, {parts.ident}")
            if parts.share_index in indices:
                raise RepeatedIndex(parts.share_index)
            indices.append(parts.share_index)
            ms32_shares.append(bech32_decode(share.s)[1])
        for i, share in enumerate(shares):
            if indices[i] == target:
                return share
        result = ms32_interpolate(ms32_shares, CHARSET.index(target.lower()))
        ret = bech32_encode(result, s0_parts.hrp)
        return cls(ret)

    @classmethod
    # pylint: disable=too-many-positional-arguments,too-many-arguments
    def from_seed(cls, data, ident, hrp='ms', k=0, share_idx='s', pad_val=-1):
        """Create Codex32String from seed bytes."""
        if 16 > len(data) or len(data) > 64:
            raise InvalidLength(f"{len(data)} bytes data MUST be 16 to 64 bytes")
        if len(ident) != 4:
            raise IdNotLength4(f"{len(ident)}")
        if not (1 < k <= 9 or k == 0):
            raise InvalidThresholdN(str(k))
        payload = convertbits(data, 8, 5, pad_val=pad_val)
        header = bech32_to_u5(str(k) + ident + share_idx)
        combined = header + payload
        ret = bech32_encode(combined + ms32_create_checksum(combined), hrp)
        return cls(ret)

class Parts:
    """Class representing parts of a Codex32 string."""
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(self, hrp, k, ident, share_index, payload, checksum):
        self.hrp = hrp
        self.k = k
        self.ident = ident
        self.share_index = share_index
        self.payload = payload
        self.checksum = checksum

    def data(self):
        """Get data from parts."""
        return bytes(convertbits(bech32_to_u5(self.payload), 5, 8, False))

    def __eq__(self, other):
        if not isinstance(other, Parts):
            return False
        return (self.hrp == other.hrp and
                self.k == other.k and
                self.ident == other.ident and
                self.share_index == other.share_index and
                self.payload == other.payload and
                self.checksum == other.checksum)

    def __hash__(self):
        return hash((self.hrp, self.k, self.ident, self.share_index, self.payload, self.checksum))
