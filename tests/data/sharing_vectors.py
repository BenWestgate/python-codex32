"""Frozen non-ms sharing fixtures.

The CL secret payload comes from Core Lightning's published ``peev`` example.
The BIP39 secrets use the frozen zero-entropy validation fixtures in
``test_bip39.py``.  Each table fixes a 2-point S/A basis and independently
recorded C/D codewords.  These are data only: production arithmetic is not
duplicated in the test suite.  Official BIP93 vectors remain the independent
GF(32) correctness anchor.
"""

SHARING_VECTORS = {
    "cl": {
        "S": "cl12testst6cqh0wu7p5ssjyf4z4ez42ks9jlt3zneju9uuypr2hddak6tlqs3zcw0ee6q2xuc",
        "A": "cl12testapppppppppppppppppppppppppppppppppppppppppppppppppppprqasqgqsaeje2",
        "C": "cl12testc6umke5r4jpf88qca737v37dw80q96s3hvq4044cpxdennzwu69k848y5zw6tfcdqu",
        "D": "cl12testd2d8ya7mnepjxxvsqhwhzwh0cx4vu2rwfzvn4nnspt0a55kcd2uyxt2vd60xm05ygz",
    },
    "bip39_12w": {
        "S": "bip39_12w12testsqqqqqqqqqqqqqqqqqqqqqqqqqqc38e6s58qr9lnk",
        "A": "bip39_12w12testapppppppppppppppppppppppppppnz8ygjskeu3nc",
        "C": "bip39_12w12testckkkkkkkkkkkkkkkkkkkkkkkkkkm5mrq9mlwnxynd",
        "D": "bip39_12w12testdyyyyyyyyyyyyyyyyyyyyyyyyyy8en6etvf2s6wn8",
    },
    "bip39_24w": {
        "S": "bip39_24w12testsqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqxvgpyg0tl3zzf80",
        "A": "bip39_24w12testapppppppppppppppppppppppppppppppppppppppppppppppppppppz05449u3dvx9a",
        "C": "bip39_24w12testckkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkklye69plsv30eyzt",
        "D": "bip39_24w12testdyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy63fsk8u6n3hnu04",
    },
}


INVALID_BIP39_IMPLIED_SECRET = {
    "A": "bip39_12w12testapppppppppppppppppppppppppppnz8ygjskeu3nc",
    "C": "bip39_12w12testckkkkkkkkkkkkkkkkkkkkkkkkkkk9spn92wl9dcuz",
}
