"""
Docstring for tests.test_descriptor
"""

import pytest
from codex32.descriptor import descsum_check, descsum_create
from codex32.errors import InvalidChecksum, SeparatorNotFound, InvalidChar

# pylint: disable=line-too-long
VALID_DESCSUM = [
    "raw(deadbeef)#89f8spxm",
    "wsh(sortedmulti(2,[6f53d49c/44h/1h/0h]tpubDDjsCRDQ9YzyaAq9rspCfq8RZFrWoBpYnLxK6sS2hS2yukqSczgcYiur8Scx4Hd5AZatxTuzMtJQJhchufv1FRFanLqUP7JHwusSSpfcEp2/0/*,[e6807791/44h/1h/0h]tpubDDAfvogaaAxaFJ6c15ht7Tq6ZmiqFYfrSmZsHu7tHXBgnjMZSHAeHSwhvjARNA6Qybon4ksPksjRbPDVp7yXA1KjTjSd5x18KHqbppnXP1s/0/*,[367c9cfa/44h/1h/0h]tpubDDtPnSgWYk8dDnaDwnof4ehcnjuL5VoUt1eW2MoAed1grPHuXPDnkX1fWMvXfcz3NqFxPbhqNZ3QBdYjLz2hABeM9Z2oqMR1Gt2HHYDoCgh/0/*))#av0kxgw0",
    "wsh(thresh(4,pk([7258e4f9/44h/1h/0h]tpubDCZrkQoEU3845aFKUu9VQBYWZtrTwxMzcxnBwKFCYXHD6gEXvtFcxddCCLFsEwmxQaG15izcHxj48SXg1QS5FQGMBx5Ak6deXKPAL7wauBU/0/*),s:pk([c80b1469/44h/1h/0h]tpubDD3UwwHoNUF4F3Vi5PiUVTc3ji1uThuRfFyBexTSHoAcHuWW2z8qEE2YujegcLtgthr3wMp3ZauvNG9eT9xfJyxXCfNty8h6rDBYU8UU1qq/0/*),s:pk([4e5024fe/44h/1h/0h]tpubDDLrpPymPLSCJyCMLQdmcWxrAWwsqqssm5NdxT2WSdEBPSXNXxwbeKtsHAyXPpLkhUyKovtZgCi47QxVpw9iVkg95UUgeevyAqtJ9dqBqa1/0/*),s:pk([3b1d1ee9/44h/1h/0h]tpubDCmDTANBWPzf6d8Ap1J5Ku7J1Ay92MpHMrEV7M5muWxCrTBN1g5f1NPcjMEL6dJHxbvEKNZtYCdowaSTN81DAyLsmv6w6xjJHCQNkxrsrfu/0/*),sln:after(840000),sln:after(1050000),sln:after(1260000)))#k28080kv",
]
INVALID_DESCSUM = [
    "raw(deadbeef)",  # No checksum
    "raw(deadbeef)#",  # Missing checksum
    "raw(deadbeef)#89f8spxmx",  # Too long checksum (9 chars)
    "raw(deadbeef)#89f8spx",  # Too short checksum (7 chars)
    "raw(deedbeef)#89f8spxm",  # Error in payload
    "raw(deadbeef)#89f8spxn",  # Error in checksum
    "raw(Ü)#00000000",  # Invalid characters in payload
]


def test_valid_checksum():
    """Test checksum creation and validation."""
    for test in VALID_DESCSUM:
        assert descsum_check(test)
        pos = test.rfind("#")
        assert descsum_create(test[:pos]) == test
        test = test[: pos + 1] + chr(ord(test[pos + 1]) ^ 1) + test[pos + 2 :]
        with pytest.raises((InvalidChecksum, InvalidChar)):
            descsum_check(test)


def test_invalid_checksum():
    """Test validation of invalid checksums."""
    for test in INVALID_DESCSUM:
        with pytest.raises((InvalidChecksum, SeparatorNotFound, InvalidChar)):
            descsum_check(test)
