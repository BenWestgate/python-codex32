# Copyright (c) 2017, 2020 Pieter Wuille
# Copyright (c) 2026 Ben Westgate <benwestgate@protonmail.com>
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

"""Reference implementation for Bech32/Bech32m and segwit addresses."""

from enum import Enum

from codex32.errors import CodexError
from codex32.bech32 import u5_encode, u5_decode, convertbits
from codex32.checksums import BECH32, BECH32M


class Encoding(Enum):
    """Enumeration type to list the various supported encodings."""

    BECH32 = 1
    BECH32M = 2


def bech32_encode(hrp, data, spec):
    """Compute a Bech32 string given HRP and data values."""
    return u5_encode(hrp, data, BECH32 if spec == Encoding.BECH32 else BECH32M)


def bech32_decode(bech: str):
    """Validate a Bech32/Bech32m string, and determine HRP and data."""
    try:
        hrp, data, spec = u5_decode(bech, [BECH32, BECH32M])
        if spec is None:
            return (None, None, None)
        return hrp, data, Encoding.BECH32 if spec == BECH32 else Encoding.BECH32M
    except CodexError:
        return (None, None, None)


def decode(hrp: str, addr):
    """Decode a segwit address."""
    hrpgot, data, spec = bech32_decode(addr)
    if hrpgot != hrp or not data:
        return (None, None)
    try:
        decoded = convertbits(data[1:], 5, 8, False)
    except CodexError:
        decoded = None
    if decoded is None or len(decoded) < 2 or len(decoded) > 40:
        return (None, None)
    if data[0] > 16:
        return (None, None)
    if data[0] == 0 and len(decoded) != 20 and len(decoded) != 32:
        return (None, None)
    if (
        data[0] == 0
        and spec != Encoding.BECH32
        or data[0] != 0
        and spec != Encoding.BECH32M
    ):
        return (None, None)
    return (data[0], decoded)


def encode(hrp, witver, witprog):
    """Encode a segwit address."""
    spec = Encoding.BECH32 if witver == 0 else Encoding.BECH32M
    ret = bech32_encode(hrp, [witver] + convertbits(witprog, 8, 5, True, 0), spec)
    if decode(hrp, ret) == (None, None):
        return None
    return ret
