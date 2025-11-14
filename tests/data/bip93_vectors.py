# tests/data/bip93_vectors.py
# pylint: disable=line-too-long
"""BIP-93 / codex32 canonical test vectors."""
VECTOR_1 = {
    "secret_s": "ms10testsxxxxxxxxxxxxxxxxxxxxxxxxxx4nzvca9cmczlw",
    "secret_hex": "318c6318c6318c6318c6318c6318c631",
    "hrp": "ms",
    "k": "0",
    "identifier": "test",
    "share_index": "s",
    "payload": "xxxxxxxxxxxxxxxxxxxxxxxxxx",
    "checksum": "4nzvca9cmczlw",
}

VECTOR_2 = {
    "share_A": "MS12NAMEA320ZYXWVUTSRQPNMLKJHGFEDCAXRPP870HKKQRM",
    "share_C": "MS12NAMECACDEFGHJKLMNPQRSTUVWXYZ023FTR2GDZMPY6PN",
    "derived_D": "MS12NAMEDLL4F8JLH4E5VDVULDLFXU2JHDNLSM97XVENRXEG",
    "secret_S": "MS12NAMES6XQGUZTTXKEQNJSJZV4JV3NZ5K3KWGSPHUH6EVW",
    "secret_hex": "d1808e096b35b209ca12132b264662a5",
}

VECTOR_3 = {
    "secret_hex": "ffeeddccbbaa99887766554433221100",
    "secret_s": "ms13cashsllhdmn9m42vcsamx24zrxgs3qqjzqud4m0d6nln",
    "share_a": "ms13casha320zyxwvutsrqpnmlkjhgfedca2a8d0zehn8a0t",
    "share_c": "ms13cashcacdefghjklmnpqrstuvwxyz023949xq35my48dr",
    "derived_d": "ms13cashd0wsedstcdcts64cd7wvy4m90lm28w4ffupqs7rm",
    "derived_e": "ms13casheekgpemxzshcrmqhaydlp6yhms3ws7320xyxsar9",
    "derived_f": "ms13cashf8jh6sdrkpyrsp5ut94pj8ktehhw2hfvyrj48704",
    "secret_s_alternates": [
        "ms13cashsllhdmn9m42vcsamx24zrxgs3qqjzqud4m0d6nln",
        "ms13cashsllhdmn9m42vcsamx24zrxgs3qpte35dvzkjpt0r",
        "ms13cashsllhdmn9m42vcsamx24zrxgs3qzfatvdwq5692k6",
        "ms13cashsllhdmn9m42vcsamx24zrxgs3qrsx6ydhed97jx2",
    ],
}

VECTOR_4 = {
    "secret_hex": "ffeeddccbbaa99887766554433221100ffeeddccbbaa99887766554433221100",
    "secret_s_alternates": [
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyqqtum9pgv99ycma",
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyqpj82dp34u6lqtd",
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyqzsrs4pnh7jmpj5",
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyqrfcpap2w8dqezy",
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyqy5tdvphn6znrf0",
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyq9dsuypw2ragmel",
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyqx05xupvgp4v6qx",
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyq8k0h5p43c2hzsk",
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyqgum7hplmjtr8ks",
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyqf9q0lpxzt5clxq",
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyq28y48pyqfuu7le",
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyqt7ly0paesr8x0f",
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyqvrvg7pqydv5uyz",
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyqd6hekpea5n0y5j",
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyqwcnrwpmlkmt9dt",
        "ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyq0pgjxpzx0ysaam",
    ],
}

VECTOR_5 = {
    "secret_s": "MS100C8VSM32ZXFGUHPCHTLUPZRY9X8GF2TVDW0S3JN54KHCE6MUA7LQPZYGSFJD6AN074RXVCEMLH8WU3TK925ACDEFGHJKLMNPQRSTUVWXY06FHPV80UNDVARHRAK",
    "secret_hex": "dc5423251cb87175ff8110c8531d0952d8d73e1194e95b5f19d6f9df7c01111104c9baecdfea8cccc677fb9ddc8aec5553b86e528bcadfdcc201c17c638c47e9",
}

VECTOR_6 = {
    "codex32_luea": "cl10lueasd35kw6r5de5kueedxyesqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqanvrktzhlhusz",
    "ident_cln2": "cln2",
    "codex32_cln2": "cl10cln2sd35kw6r5de5kueedxyesqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqn9lcvcu7cez4s",
    "codex32_peev": "cl10peevst6cqh0wu7p5ssjyf4z4ez42ks9jlt3zneju9uuypr2hddak6tlqsjhsks4laxts8q",
}

BAD_CHECKSUMS = [
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxve740yyge2ghq",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxve740yyge2ghp",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxlk3yepcstwr",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxx6pgnv7jnpcsp",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxx0cpvr7n4geq",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxm5252y7d3lr",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxrd9sukzl05ej",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxc55srw5jrm0",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxgc7rwhtudwc",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxx4gy22afwghvs",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxme084q0vpht7pe0",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxme084q0vpht7pew",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxqyadsp3nywm8a",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxzvg7ar4hgaejk",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxcznau0advgxqe",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxch3jrc6j5040j",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx52gxl6ppv40mcv",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx7g4g2nhhle8fk",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx63m45uj8ss4x8",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxy4r708q7kg65x",
]

WRONG_CHECKSUMS = [
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxurfvwmdcmymdufv",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxcsyppjkd8lz4hx3",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxu6hwvl5p0l9xf3c",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxwqey9rfs6smenxa",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxv70wkzrjr4ntqet",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx3hmlrmpa4zl0v",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxrfggf88znkaup",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxpt7l4aycv9qzj",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxus27z9xtyxyw3",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxcwm4re8fs78vn",
]

INVALID_LENGTHS = [
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxw0a4c70rfefn4",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxk4pavy5n46nea",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxx9lrwar5zwng4w",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxr335l5tv88js3",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxvu7q9nz8p7dj68v",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxpq6k542scdxndq3",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxkmfw6jm270mz6ej",
    "ms12fauxxxxxxxxxxxxxxxxxxxxxxxxxxzhddxw99w7xws",
    "ms12fauxxxxxxxxxxxxxxxxxxxxxxxxxxxx42cux6um92rz",
    "ms12fauxxxxxxxxxxxxxxxxxxxxxxxxxxxxxarja5kqukdhy9",
    "ms12fauxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxky0ua3ha84qk8",
    "ms12fauxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx9eheesxadh2n2n9",
    "ms12fauxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx9llwmgesfulcj2z",
    "ms12fauxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx02ev7caq6n9fgkf",
]

INVALID_SHARE_INDEX = [
    "ms10fauxxxxxxxxxxxxxxxxxxxxxxxxxxxx0z26tfn0ulw3p",
]

INVALID_THRESHOLD = [
    "ms1fauxxxxxxxxxxxxxxxxxxxxxxxxxxxxxda3kr3s0s2swg",
]

INVALID_PREFIX_OR_SEPARATOR = [
    "0fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
    "10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
    "ms0fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
    "m10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
    "s10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
    "0fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxhkd4f70m8lgws",
    "10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxhkd4f70m8lgws",
    "m10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxx8t28z74x8hs4l",
    "s10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxh9d0fhnvfyx3x",
]

BAD_CASES = [
    "Ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
    "mS10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
    "MS10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
    "ms10FAUXsxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
    "ms10fauxSxxxxxxxxxxxxxxxxxxxxxxxxxxuqxkk05lyf3x2",
    "ms10fauxsXXXXXXXXXXXXXXXXXXXXXXXXXXuqxkk05lyf3x2",
    "ms10fauxsxxxxxxxxxxxxxxxxxxxxxxxxxxUQXKK05LYF3X2",
]
