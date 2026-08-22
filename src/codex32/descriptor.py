# Portions of this file are derived from:
#   BIP-0380 (descriptor checksum) — https://github.com/bitcoin/bips/blob/master/bip-0380.mediawiki
# Copyright (c) 2018-present The Bitcoin Core developers
# Copyright (c) 2026 Ben Westgate <benwestgate@protonmail.com>
# Distributed under the MIT software license, see the accompanying
# file LICENSE or https://opensource.org/licenses/MIT

"""Descriptor checksum implementation."""

from bip32 import BIP32

from codex32.bech32 import _chars_to_u5, _u5_to_chars
from codex32.checksums import DESCSUM
from codex32.errors import (
    CodexError,
    InvalidChar,
    InvalidChecksum,
    InvalidLength,
    SeparatorNotFound,
)
from codex32.wallet_policies import WalletPolicy

# pylint: disable=line-too-long
INPUT_CHARSET = "0123456789()[],'/*abcdefgh@:$%{}IJKLMNOPQRSTUVWXYZ&+-.;<=>?!^_|~ijklmnopqrstuvwxyzABCDEFGH`#\"\\ "
GENERATOR = [0xF5DEE51989, 0xA9FDCA3312, 0x1BAB10E32D, 0x3706B1677A, 0x644D626FFD]


def descsum_expand(s):
    """Internal function that does the character to symbol expansion"""
    groups = []
    symbols = []
    for i, c in enumerate(s):
        if c not in INPUT_CHARSET:
            raise InvalidChar(f"'{c!r}' at pos={i} must be in \"{INPUT_CHARSET!r}\"")
        v = INPUT_CHARSET.find(c)
        symbols.append(v & 31)
        groups.append(v >> 5)
        if len(groups) == 3:
            symbols.append(groups[0] * 9 + groups[1] * 3 + groups[2])
            groups = []
    if len(groups) == 1:
        symbols.append(groups[0])
    elif len(groups) == 2:
        symbols.append(groups[0] * 3 + groups[1])
    return symbols


def descsum_check(s):
    """Verify that the checksum is correct in a descriptor"""
    try:
        if s[-9] != "#":
            raise SeparatorNotFound(
                f"'#' not found at 9th from last character, pos={len(s)-9}"
            )
    except IndexError as exc:
        raise InvalidLength(f"String too short to be valid {len(s)}") from exc
    if not DESCSUM.verify(descsum_expand(s[:-9]) + _chars_to_u5(s[-8:])):
        raise InvalidChecksum("descriptor checksum does not validate")
    return True


def descsum_create(s):
    """Add a checksum to a descriptor without"""
    return s + "#" + _u5_to_chars(DESCSUM.create(descsum_expand(s)))


DESCRIPTOR_TEMPLATES = {
    "Legacy": ("pkh(@0/**)", "m/44h/{coin_type}h/{account}h"),
    "Nested P2SH-SegWit": ("sh(wpkh(@0/**))", "m/49h/{coin_type}h/{account}h"),
    "Native SegWit": ("wpkh(@0/**)", "m/84h/{coin_type}h/{account}h"),
    "Taproot": ("tr(@0/**)", "m/86h/{coin_type}h/{account}h"),
}


def get_key_origin_xkey_from_path(node: BIP32, path: str, private: bool = False):
    """Get key origin and encoded extended key from derivation path."""
    if private:
        return node.get_xpriv() + path.removeprefix("m")
    return f"[{node.get_fingerprint().hex()}{path[1:]}]{node.get_xpub_from_path(path)}"


def descriptors_from_node(
    node: BIP32,
    templates: dict[str, tuple[str, str]],
    account: int = 0,
    private: bool = False,
    timestamp: str | int = "now",
) -> list[dict]:
    """Build a list of descriptor dicts (ready for importdescriptors) from a root node."""
    descriptors = []
    for tmpl in templates.values():
        path = tmpl[1].format(coin_type=int(node.network == "test"), account=account)
        key = get_key_origin_xkey_from_path(node, path, private)
        raw_desc = WalletPolicy(tmpl[0], [key]).to_descriptor()
        checksumed = descsum_create(raw_desc)
        descriptors.append({"desc": checksumed, "active": True, "timestamp": timestamp})
    return descriptors


def make_private_descriptor(desc: str, xprv: str) -> str:
    """Convert a public descriptor to a private one by replacing the xpub with the xprv."""
    node = BIP32.from_xpriv(xprv)
    fingerprint = node.get_fingerprint().hex()
    descsum_check(desc)  # validate input descriptor
    wp = WalletPolicy.from_descriptor(desc[:-9])  # remove checksum for parsing
    new_keys_info = []
    for key in wp.keys_info:
        if key[0] != "[" or "]" not in key:
            raise CodexError("descriptor keys must have an origin to be converted")
        key_fingerprint = key[1:9]  # fingerprint is 8 chars after the opening bracket
        # path is between the fingerprint and closing bracket
        path = key[9 : key.find("]")]
        derived_xpub = node.get_xpub_from_path("m" + path)
        desc_xpub = key[key.find("]") + 1 :]
        # if the fingerprint matches, verify that the xprv derives the same key as the xpub in the descriptor
        if key_fingerprint == fingerprint and derived_xpub == desc_xpub:
            new_keys_info.append(f"{xprv}{path}")
        else:
            new_keys_info.append(key)
    new_wp = WalletPolicy(wp.descriptor_template, new_keys_info)
    new_desc = new_wp.to_descriptor()
    ret = descsum_create(new_desc)
    descsum_check(ret)  # validate output descriptor
    return str(ret)


if __name__ == "__main__":
    descriptorsa = [
        "pkh([d34db33f/44'/0'/0']xpub6ERApfZwUNrhLCkDtcHTcxd75RbzS1ed54G1LkBUHQVHQKqhMkhgbmJbZRkrgZw4koxb5JaHWkY4ALHY2grBGRjaDMzQLcgJvLJuZZvRcEL/**)",
        "wsh(multi(1,xpub661MyMwAqRbcFW31YEwpkMuc5THy2PSt5bDMsktWQcFF8syAmRUapSCGu8ED9W6oDMSgv6Zz8idoc4a6mr8BDzTJY47LJhkJ8UB7WEGuduB/**,xpub69H7F5d8KSRgmmdJg2KhpAK8SR3DjMwAdkxj3ZuxV27CprR9LgpeyGmXUbC6wb7ERfvrnKZjXoUmmDznezpbZb7ap6r1D3tgFxHmwMkQTPH/**))",
        "tr([12345678/44'/0'/0']xpub6BVZ6JrGsWsUbpP74S8rnz13hVFDtYtKyuTTEYPNSF6GFpDFpL1YXWg3BpwpUWAnsZZ7Qe3XKz7GL3BEx3RQVq61cxqSkjceq25S1xFKFVa,{pk(xpub6AGdromjXf5yf3m7ndaCoR9Ac3UjwTvQ7QQkZoyoh2vfGE9i1AwB2vCbvjTpBL1KRERUsGszg63SVNXsHZU3CiykQqtZPrdXKMdaG2vs6uu),pk(xpub6AnhdkteWC4kPQvkY3QQXGmDCMfmFoYzEQ7FwRFa4BQ1a22k4VL4BD3Jdcog2Sf2KzBscXXAdPRMgjCBDeq6bAryqnMaWX2FaVUGPxWMLDh)})",
        "tr(xpub6AEWqA1MNRzBBXenkug4NtNguDKTNcXoKQj8fU9VQyid38yikruFRffjoDm9UEaHGEJ6jQxjYdWWZRxR7Xy5ePrQNjohXJuNzkRNSiiBUcE,sortedmulti_a(2,[11223344/44'/0'/0']xpub6AyJhEKxcPaPnYNuA7VBeUQ24v6mEzzPSX5AJm3TSyg1Zsti7rnGKy1Hg6JAdXKF4QUmFZbby9p97AjBNm2VFCEec2ip5C9JntyxosmCeMW,xpub6AQVHBgieCHpGo4GhpGAo4v9v7hfr2Kr4D8ZQJqJwbEyZwtW3pWYSLRQyrNYbTzpoq6XpFtaKZGnEGUMtiydCgqsJDAZNqs9L5QDNKqUBsV))",
        "tr([11111111/44'/0'/0']xpub6CLZSUDtcUhJVDoPSY8pSRKi4W1RSSLBgwZ2AYmwTH9Yv5tPVFHZxJBUQ27QLLwHej6kfo9DQQbwaHmpXsQq59CjtsE2gNLHmojwgMrsQNe/**,{and_v(v:pk([22222222/44'/0'/0']xpub6CiztfGsUxmpwkWe6gvz8d5VHyFLDoiPpeUfWmQ2vWAhQL3Z1hhEc6PE4irFs4bzjS7dCB4yyinaubrCpFJq4bcKGCD4jjqTxaWiKAJ7mvJ/**),older(52596)),multi_a(2,[33333333/44'/0'/0']xpub6DTZd6od7is2wxXndmE7zaUifzFPwVKshVSGEZedfTJtUjfLyhy4hgCW15hvxRpGaDmtiFoJKaCEaSRfXrQBuYRx18zwquy46dwBsJnsrz2/**,[44444444/44'/0'/0']xpub6BnK4wFbPeLZM4VNjoUA4yLCru6kCT3bhDJNBhbzHLGp1fmgK6muz27h4drixJZeHG8vSS5U5EYyE3gE8ozG94iNg3NDYE8M5YafvhzhMR9/**)})",
        "tr(musig([33333333/44'/0'/0']xpub6DTZd6od7is2wxXndmE7zaUifzFPwVKshVSGEZedfTJtUjfLyhy4hgCW15hvxRpGaDmtiFoJKaCEaSRfXrQBuYRx18zwquy46dwBsJnsrz2,[44444444/44'/0'/0']xpub6BnK4wFbPeLZM4VNjoUA4yLCru6kCT3bhDJNBhbzHLGp1fmgK6muz27h4drixJZeHG8vSS5U5EYyE3gE8ozG94iNg3NDYE8M5YafvhzhMR9)/**,{and_v(v:pk([22222222/44'/0'/0']xpub6CiztfGsUxmpwkWe6gvz8d5VHyFLDoiPpeUfWmQ2vWAhQL3Z1hhEc6PE4irFs4bzjS7dCB4yyinaubrCpFJq4bcKGCD4jjqTxaWiKAJ7mvJ/**),older(52596)),pk([11111111/44'/0'/0']xpub6CLZSUDtcUhJVDoPSY8pSRKi4W1RSSLBgwZ2AYmwTH9Yv5tPVFHZxJBUQ27QLLwHej6kfo9DQQbwaHmpXsQq59CjtsE2gNLHmojwgMrsQNe/**)})",
        "pkh([1a5bcd07/44h/0h/0h]xpub6CiqvEruL32CUGsK2CqbcMJ4XV95y7SeMrGKxq1fb9WPmDryUb9sKnBUxBpSSG1uB9iEsXoueA2KkPLq7S9VwAm7gQYbdEwPNmaxw9HaEMs/0/*)",
        "pkh([1a5bcd07/44h/0h/0h]xpub6CiqvEruL32CUGsK2CqbcMJ4XV95y7SeMrGKxq1fb9WPmDryUb9sKnBUxBpSSG1uB9iEsXoueA2KkPLq7S9VwAm7gQYbdEwPNmaxw9HaEMs/1/*)",
        "pkh(xprv9s21ZrQH143K36XBZLytgQidYwAu6371Q1fSaexsbx6GThYNMSWusNStaohb5GVW71JJX3opJs4E9ADkRnd9hQgP4DYDdR63wtpWNTEXnZZ/44h/0h/0h/<0;1>/*)",
        "sh(wpkh(xprv9s21ZrQH143K36XBZLytgQidYwAu6371Q1fSaexsbx6GThYNMSWusNStaohb5GVW71JJX3opJs4E9ADkRnd9hQgP4DYDdR63wtpWNTEXnZZ/49h/0h/0h/<0;1>/*))",
        "wpkh(xprv9s21ZrQH143K36XBZLytgQidYwAu6371Q1fSaexsbx6GThYNMSWusNStaohb5GVW71JJX3opJs4E9ADkRnd9hQgP4DYDdR63wtpWNTEXnZZ/84h/0h/0h/<0;1>/*)",
        "wpkh([45fc8f4e/84h/0h/0h]xpub6BgDoiyNWC2BYVGc4pPxLcCyAHKLerP7V2kCA3zt7kF6ew6Ddge9ZTEgF1doic1kx5r7ppNsBzZSWPbvkUerVY8vZi9tgK8wGnagUJ8wqn3/<0;1>/*)",
        "tr(xprv9s21ZrQH143K36XBZLytgQidYwAu6371Q1fSaexsbx6GThYNMSWusNStaohb5GVW71JJX3opJs4E9ADkRnd9hQgP4DYDdR63wtpWNTEXnZZ/86h/0h/0h/<0;1>/*)",
    ]
    desc_templates = ["pkh(@0/**)", "sh(wpkh(@0/**))", "wpkh(@0/**)", "tr(@0/**)"]

"wsh(or_d(pk([c6d41d09/48'/0'/0'/2']xpub6ExUjueK6xXK68Hx9sbX197svbussYvFpkMHwJtZt28og6b7yKsP62yXwf52n3gEjBm8DwfqtJzxTXkaosfgRZk5KVUvX2NBU4rGxd9CC25/<0;1>/*),and_v(v:pkh([8c78eedb/48'/0'/0'/2']xpub6DtAe7uNuFuf9VtP1Whk8DyqibY9xagPyPW1Q59DFvm9fD3x9PnyvcJqGis8q1Mo4vxwBmVDEGJMBwXE3enYTADjCT11axaaFurv7B21Lvg/<0;1>/*),older(52596))))#z4redr5s"
