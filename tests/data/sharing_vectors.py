"""Frozen BIP39 sharing fixtures.

The BIP39 secrets use the frozen zero-entropy validation fixtures in
``test_bip39.py``.  Each table fixes a 2-point S/A basis and independently
recorded C/D codewords.  These are data only: production arithmetic is not
duplicated in the test suite.  Official BIP93 vectors remain the independent
GF(32) correctness anchor.
"""

SHARING_VECTORS = {
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
