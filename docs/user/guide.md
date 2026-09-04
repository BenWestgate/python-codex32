# codex32 user guide

Choose the setup that fits you:

- **Recommended: dedicated online spending wallet — easiest.** A normally
  networked Bitcoin Core node stores encrypted signing keys, synchronizes the
  wallet, and handles ordinary receiving and spending.
- **More protection: online watch-only wallet plus offline signer — more
  steps.** The computer with signing keys stays disconnected from every
  network and signs PSBT files.

Recovery, inheritance, multisig, and damaged-card help follow those two setup
choices.

A **master seed** is the complete private-key recovery secret. A **share** is
one part of a split master seed. A **wallet record** describes the expected
wallet without containing recovery secrets; store it separately from every
recovery card.

## Recommended: dedicated Bitcoin Core spending wallet

### 1. Prepare

You will need:

- Bitcoin Core 30 or newer, with its local RPC server enabled and
  `bitcoin-cli` available on `PATH`;
- codex32 installed using the [README instructions](../../README.md#install);
- one blank [codex32 recovery card](recovery-card.html) per secret or share; and
- a separately stored [wallet-verification record](wallet-verification-record.html).

Run Bitcoin Core before starting. If practical, disconnect the computer from
external networks while recovery text is on screen. codex32 talks only to the
local Core instance at `127.0.0.1` during setup.

For graphical practice on signet, start Bitcoin-Qt with:

```bash
bitcoin-qt -signet -server
```

codex32 detects and reports the local Bitcoin Core network. You do not need to
change `bitcoin.conf` when using the standard local data directory and RPC
port.

Use a computer you believe is malware-free and whose other software you trust.
Only codex32 and Bitcoin Core should perform recovery, derivation, wallet
initialization, or signing. The QR tools below transport only public
descriptors or PSBTs.

Bitcoin Core wallet encryption is strongly recommended. Bitcoin Core owns the
passphrase and its prompts; codex32 never asks for, reads, or forwards it.

Do not type recovery text on the same line as a command. Run the command first,
then enter a master seed or shares only when prompted. Never photograph
recovery text or put it in a website, chat, cloud clipboard, or online QR
service.

### 2. Choose a backup

Choose one command:

- **2-of-3 shares (recommended):** `codex32 create 2` produces three shares;
  any two recover the seed and one can be lost.
- **3-of-5 shares:** `codex32 create 3` produces five shares; any three recover
  the seed and any two can be lost.
- **Unshared:** `codex32 create` produces one secret. You may make redundant
  copies, but any copy can recover the seed.
- **Custom:** thresholds 4 through 9 require `--shares` or `--indices`. For
  example, `codex32 create 4cash --shares 7` produces seven `cash` shares; any
  four recover the seed.

More required shares make theft harder; fewer required shares make recovery
easier.

### 3. Make a Bitcoin Core wallet

Run the command you chose. codex32 finds the local Bitcoin Core network before
generating anything. If more than one network is running, choose it by number.

1. Write each result on a new recovery card and press Enter. Where supported,
   codex32 clears the terminal and its saved scrollback, then asks you to
   re-enter the result from the card.
2. If the re-entry differs, codex32 displays only what you entered and marks
   the groups to check in red. A completely omitted group appears as `____`.
   Check the card and edit your entry; codex32 does not reveal or apply the
   expected text. Spaces and letter case do not affect confirmation.
3. After every card is confirmed, approve the eligible blank Bitcoin Core
   wallet shown. If there is more than one, choose by number and confirm its
   exact name.

If no eligible wallet is listed, choose **Create another wallet**. In
Bitcoin-Qt, choose **File > Create Wallet...** and create a blank descriptor
wallet with private keys enabled. Select encryption if this will be the online
spending wallet. codex32 detects the new wallet automatically.

After each shared card, codex32 reports how many cards you have confirmed. If
the selected encrypted wallet is locked, open **Window > Console** in
Bitcoin-Qt, select the named wallet, and enter
`walletpassphrase "YOUR PASSPHRASE" 5`. codex32 waits and continues
automatically. It imports account 0, verifies the public descriptors Core
accepted, and relocks the wallet. It does not create wallets or choose
encryption.

You are done with this step when the terminal says:

```text
Bitcoin Core spending wallet initialized.
```

If you interrupt before every card is confirmed, mark the incomplete cards
void. If setup stops afterward, the confirmed cards remain valid, but no Core
wallet should be trusted until initialization completes.

### 4. Complete the record and store the cards

Copy the displayed backup identifier, wallet name, Bitcoin Core version,
master fingerprint, derivation standards, and account number to the wallet
record. Add the approximate
creation / earliest-use date. Do not put a descriptor timestamp on a recovery
card; Core's public descriptor export preserves its stored timestamps.

Store each card securely. For a shared backup, use different trusted places.
Keep the wallet record separately from all cards.

### 5. Receive and spend normally

Reconnect if needed and let the normally networked Bitcoin Core node finish
blockchain and wallet synchronization. Trust balances and history only after
that finishes. In Bitcoin-Qt:

1. Use **Receive** and send a small test amount to the new wallet.
2. Confirm that the payment appears before receiving a larger amount.
3. Use **Send** for payments and check the destination, amount, and fee.

Let Bitcoin Core choose the ordinary receiving address type. Bitcoin-Qt asks
for the wallet passphrase when an operation needs it and relocks a wallet that
it temporarily unlocked.

This is the easiest setup, but its signing wallet lives on a networked
computer. Use the next setup when keeping signing keys permanently offline is
worth the extra steps.

## More protection: watch-only wallet and offline signer

Prepare a dedicated signing computer with Bitcoin Core, codex32, `jq`, `qr`,
and a local ZBar reader before disconnecting it permanently. Tails includes
`qr`; this guide uses it for local public-data and PSBT transfers. Disable
Ethernet, internet, Tor, Wi-Fi, Bluetooth, cellular, and every other network
path on this computer.

### 1. Initialize the offline signer

With every network path disabled, follow the Recommended steps through **Make
a Bitcoin Core wallet** on the offline computer. Name the blank encrypted
wallet clearly, such as `offline-signer`. This computer and its Core wallet
must remain offline.

### 2. Transfer only Core's accepted public descriptors

For a wallet named `offline-signer`, export Core's accepted public descriptors
with:

```bash
bitcoin-cli -rpcconnect=127.0.0.1 -rpcwallet=offline-signer listdescriptors | jq -c '[.descriptors[] | {desc,timestamp,active,internal,range,next_index}]' | qr
```

Public descriptors cannot spend, but they reveal wallet activity. Do not use a
website, cloud scanner, chat service, or synced clipboard.

On the online computer, create a blank descriptor wallet named
`codex32-watch-only` with private keys disabled. Scan one local QR directly
into it:

```bash
zbarcam --raw --oneshot |
  bitcoin-cli -rpcwallet=codex32-watch-only -stdin importdescriptors
```

Every result must say `"success": true`. Generate one fresh receiving address
in each Bitcoin-Qt wallet and compare them on the two screens. Do not receive
funds if they differ.

### 3. Spend with a PSBT

1. In the online Bitcoin-Qt watch-only wallet, fill in **Send**, check the
   destination, amount, and fee, and choose **Create Unsigned**.
2. Copy the base64 PSBT. Run `qr`, paste the text, and press Ctrl-D to display
   it as a local QR.
3. On the offline computer, receive it into a file:

   ```bash
   zbarcam --raw --oneshot > unsigned.psbt
   ```

4. Load `unsigned.psbt` in Bitcoin-Qt. On the offline screen, verify every
   destination, amount, and fee before signing.
5. Copy the signed base64 PSBT, run `qr`, paste it, and press Ctrl-D.
6. On the online computer, scan it into `signed.psbt`, load that file in the
   watch-only Bitcoin-Qt wallet, check it again, and broadcast:

   ```bash
   zbarcam --raw --oneshot > signed.psbt
   ```

If a PSBT is too large for a reliable QR, use a dedicated removable drive. The
drive crosses the security boundary: keep it for this purpose, treat every file
on it as untrusted, and still verify the transaction on the offline screen.

Bitcoin Core maintains an
[offline-signing tutorial](https://github.com/bitcoin/bitcoin/blob/master/doc/offline-signing-tutorial.md)
for this watch-only/PSBT split.

## Recover an existing or inherited wallet

An existing wallet has records and history that can identify a wrong recovery.
Verify it watch-only before exposing private keys.

1. Collect the required cards with matching identifiers and text lengths.
2. Find the separately stored wallet record and the original wallet
   instructions.
3. On Tails or another reviewed offline computer, check each card with
   `codex32 check`. If validation fails, recheck what you typed before assuming
   the paper is wrong.
4. Disable Ethernet, internet, Tor, Wi-Fi, Bluetooth, cellular, and every other
   network path. Load a blank descriptor wallet with private keys disabled in
   Bitcoin Core, and run:

   ```bash
   codex32 wallet bitcoin-core watch-only --timestamp 0
   ```

5. Select and confirm the blank watch-only wallet. codex32 imports and verifies
   its public descriptors. Reconnect the normally networked Bitcoin Core node
   and let blockchain and wallet synchronization finish.
6. Only then compare the recovered fingerprint, account, complete policy,
   balance, and transaction history with the wallet record.

Proceed to private restoration only when everything matches. Disconnect the
intended computer, create a blank encrypted descriptor wallet with private
keys enabled, and run:

```bash
codex32 wallet bitcoin-core restore --timestamp 0
```

Select and confirm that wallet. If it is locked, follow the displayed
Bitcoin-Qt Console instructions; codex32 waits and continues automatically. It
imports the private descriptors, verifies the public set, and relocks an
encrypted wallet. A timestamp of zero
safely scans all history and may take time; it belongs in this recovery command,
not on a paper card. During an emergency recovery, move the funds to a newly
established wallet after a small test payment when circumstances permit.

Stop and get knowledgeable help instead of guessing when records are missing,
results disagree, or the wallet is multisig or nonstandard.

## Special cases

### Multisig cosigner recovery

codex32 can export this seed's public cosigner key. It cannot reconstruct the
complete multisig policy or sign a transaction.

```bash
codex32 wallet multisig-xpub | qr
```

Import the xpub into the selected reviewed coordinator. Use the coordinator only
to assemble the policy and PSBT; use a Bitcoin Core descriptor wallet as the
signer. Follow a reviewed Bitcoin Core multisig workflow; codex32 does not build
the signing wallet.

Before receiving or signing, verify the xpub's exact fingerprint, derivation
path, and xpub in the complete policy. Check every PSBT destination, amount,
fee, policy, and cosigner. Never give a coordinator a codex32 share, master
seed, or root xprv.

### Card maintenance and damaged writing

- `codex32 check` validates a card's format and checksum. A valid result does
  not prove that it belongs to this wallet.
- `codex32 correct` suggests a repair. Compare any suggestion character by
  character with the physical backup before confirming it.
- `codex32 share d` derives a replacement at unused index `d`. Confirm and
  store the new card before retiring an old one.

### Worksheets and migration formats

`codex32 checksum` completes the non-pink bold squares from a Codex32 Book
checksum worksheet. It does not turn arbitrary dice rolls, words, passwords,
or hexadecimal text into a safe wallet.

codex32 can check and recover its fixed Core Lightning and BIP39 worksheet
profiles, but it does not generate BIP39 words. Keep the matching worksheet and
original wallet instructions with the inheritance plan.

### QR troubleshooting

Maximize the terminal and reduce its font size if a QR does not fit. Keep `qr`
connected to the terminal; redirecting its output creates an image file. Only
public descriptors, xpubs, and PSBTs may cross the offline boundary by QR.

## Technical references

Automation, low-level private exports, parser behavior, correction mathematics,
and exact limits are documented in the [API and architecture guide](../developer/api.md).
Auditors should also read the [security model](../security/model.md).
