# python-codex32

python-codex32
===============

Reference implementation of BIP-0093: codex32: Checksummed SSSS-aware BIP32 seeds


Abstract
--------

This document describes a standard for backing up and restoring the master seed of a
[https://github.com/bitcoin/bips/blob/master/bip-0032.mediawiki BIP-0032] hierarchical deterministic wallet, using Shamir's secret sharing.
It includes an encoding format, a BCH error-correcting checksum, and algorithms for share generation and secret recovery.
Secret data can be split into up to 31 shares.
A minimum threshold of shares, which can be between 1 and 9, is needed to recover the secret, whereas without sufficient shares, no information about the secret is recoverable.

BIP Paper
---------

See https://github.com/bitcoin/bips/blob/master/bip-0093.mediawiki
for full specification

Installation
------------

To install this library and its dependencies use:

 ``pip install codex32``

Usage examples
--------------

Import library into python project via:

.. code-block:: python

   from codex32.codex32 import Codex32String as c32

Initialize class instance, picking from available:

hrp:
- "ms"
- "cl"

threshold:
- 0
- 2 through 9

num_shares:

- 1 through 31 (must be greater than or equal to threshold)

identifier:
- four bech32 characters to disambiguate backups (optional)

.. code-block:: python

   codex32 = Codex32(hrp, threshold, num_shares, identifier)
   codex32 = Codex32("ms", 2, 3, "test")

Generate string list given the strength (128 - 512):

.. code-block:: python

   strings = codex32.generate(strength=128)

Given the string list and custom passphrase (empty in example), generate seed:

.. code-block:: python

   seed = codex32.to_seed(strings, passphrase="")

Given the parameters, calculate original entropy:

.. code-block:: python

   entropy = codex32.to_entropy(strings)
   