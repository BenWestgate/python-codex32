# codex32 user guide

`codex32` checks, corrects, recovers, and derives shares across application
prefixes. `ms32` provides Bitcoin master-seed workflows, including secure
creation. Use `ms32 create` for new Bitcoin backups.
BIP39 worksheet profiles are
[not recommended for creation](https://secretcodex32.com/docs/index.html),
but existing backups can be recovered and corrected.

When correction has little checksum evidence left, either executable warns:

```text
Warning: If you are generating new data and attempting to fill in the missing
squares to complete a checksum, ensure that you have transcribed the data
exactly as it will be used. There is no way to detect or correct transcription
errors, so any errors you have made up to this point will be "locked in" by
completing the checksum.

If you are recovering data with this many missing characters, understand that
the completion may be incorrect and you may need to resort to other methods
(e.g. grinding through possible typos) to recover your data.

If you understand this, type YES to attempt to correct the data:
```

Only literal uppercase `YES` reveals the suggestion. Other case variants, blank
input, or EOF end the command without showing it. This also applies to
worksheet-residue repairs and `--plain`. Redirected damaged input can be read,
and redirected `correct` output is plain by default, but protected disclosure
still requires an interactive terminal. After
disclosure, workflows that consume the repaired artifact ask the usual `[y/N]`
whole-card confirmation. `correct` only reports a suggestion, so it does not ask
that second question. A checksum cannot make weak input secure.

Choose the setup that fits you:

- **Recommended: dedicated online spending wallet — easiest.** A normally
  networked Bitcoin Core node stores encrypted signing keys, synchronizes the
  wallet, and handles ordinary receiving and spending.
- **More protection: Bitcoin Core's offline-signing workflow — more steps.**
  Restore the signing wallet offline with `ms32 wallet`, then follow Bitcoin
  Core v32's maintained watch-only/PSBT procedure.

Recovery, inheritance, multisig, and damaged-card help follow those two setup
choices.

A **master seed** is the complete private-key recovery secret. A **share** is
one part of a split master seed. A **wallet record** describes the expected
wallet without containing recovery secrets; store it separately from every
recovery card.

The same Bitcoin master-seed jobs are available in a window. If you would rather
not use a terminal, see [the codex32 window](gui.md); it covers creation,
restoration, checking, repair, and replacing a card, and it asks for the Bitcoin
Core wallet passphrase that this command deliberately does not.

## Recommended: dedicated Bitcoin Core spending wallet

### 1. Prepare

You will need:

- Bitcoin Core 32 or newer, with its local RPC server enabled and
  `bitcoin-cli` available on `PATH`;
- codex32 installed using the [README instructions](../../README.md#install);
- one blank [codex32 recovery card](recovery-card.html) per secret or share; and
- a separately stored [wallet-verification record](wallet-verification-record.html).

Before running `create` for a real wallet, have your blank cards, a pen, and
wallet record ready, and choose separate trusted places for shared cards.
If you want to try the process first, use the signet practice setup below.

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
then enter a master seed or shares on the separate `>` line when prompted.
This keeps a 48-character string grouped in fours within an 80-column terminal.
Later share prompts may show a fixed common header after `>`. Never photograph
recovery text or put it in a website, chat, cloud clipboard, or online QR
service.

### 2. Choose a backup

Choose one command:

- **2-of-3 shares (recommended):** `ms32 create 2` produces three shares;
  any two recover the seed and one can be lost.
- **3-of-5 shares:** `ms32 create 3` produces five shares; any three recover
  the seed and any two can be lost.
- **Unshared:** `ms32 create` produces one secret. You may make redundant
  copies, but any copy can recover the seed.
- **Custom:** thresholds 4 through 9 require `--shares` or `--indices`. For
  example, `ms32 create 4cash --shares 7` produces seven `cash` shares; any
  four recover the seed.

More required shares make theft harder; fewer required shares make recovery
easier.

Already have a complete codex32 `ms` secret? Run `ms32 create --existing` to
write and confirm its recovery card and initialize a Bitcoin Core wallet.
The existing secret is preserved unchanged. To split it into three cards
requiring any two, use `ms32 create 2 --existing` instead. Enter the secret
only when prompted. Bitcoin Core also scans for prior transactions.

### 3. Make a Bitcoin Core wallet

Run the command you chose. codex32 finds the local Bitcoin Core network before
generating anything. If more than one network is running, choose it by number.

1. Write each result on a new recovery card and press Enter. Where supported,
   codex32 clears the terminal and its saved scrollback, then asks you to
   re-enter the result from the card. Type the recovery text on the next line,
   after `>`.
2. If the text differs, check the red groups against your recovery card and
   correct the highlighted section. Correct groups stay confirmed. You can also
   enter the entire card again. Spaces and letter case do not affect
   confirmation, and you can retry as often as needed.
3. After every card is confirmed, approve the eligible blank Bitcoin Core
   wallet shown. If there is more than one, choose by number and confirm its
   exact name.

Confirmation shows that the operator can produce the correct recovery
string during setup. It cannot prove that the physical backup was
corrected rather than reconstructed using confirmation feedback.

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

Before the wallet is filled, write the displayed master fingerprint on the
wallet record and type it back from what you wrote. Then copy the displayed
backup identifier, wallet name, Bitcoin Core version, derivation standards, and
account number to the wallet record. Add the approximate
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

On the offline signer, create an empty encrypted descriptor wallet with private
keys enabled and run `ms32 wallet`. Keep that computer disconnected from every
network while recovery text or signing keys are present.

After the signer is restored, follow Bitcoin Core v32's maintained
[offline-signing tutorial](https://github.com/bitcoin/bitcoin/blob/v32.0rc1/doc/offline-signing-tutorial.md).
That workflow owns the watch-only export/import and PSBT transport steps. In
Bitcoin Core v32, `exportwatchonlywallet` creates the watch-only wallet file and
`restorewallet` loads it on the online node. Do not improvise a codex32-specific
descriptor-transfer procedure in place of that maintained workflow.

## Recover an existing or inherited wallet

An existing wallet has records and history that can identify a wrong recovery.
Restore it on the intended offline or otherwise trusted signer before comparing
its public wallet data with the separate wallet record.

1. Collect the required cards with matching identifiers and text lengths.
2. Find the separately stored wallet record and the original wallet
   instructions.
3. On Tails or another reviewed offline computer, check each card with
   `ms32 check`. If validation fails, recheck what you typed before assuming
   the paper is wrong.
4. Disable Ethernet, internet, Tor, Wi-Fi, Bluetooth, cellular, and every other
   network path. Load a blank encrypted descriptor wallet with private keys
   enabled in Bitcoin Core, and run:

   ```bash
   ms32 wallet --timestamp 0
   ```

5. Type the master fingerprint from the wallet record. A mismatch stops before
   Bitcoin Core is changed. Press Enter with nothing typed only if there is no
   record; then only a seed-derived backup identifier is accepted.
6. Select and confirm that wallet. If it is locked, follow the displayed
   Bitcoin-Qt Console instructions; codex32 waits and continues automatically.
   It imports the private descriptors, verifies the public set, and relocks an
   encrypted wallet.
7. If you need an online watch-only counterpart, keep the restored signer
   offline and follow Bitcoin Core v32's
   [offline-signing tutorial](https://github.com/bitcoin/bitcoin/blob/v32.0rc1/doc/offline-signing-tutorial.md)
   to export and restore the watch-only wallet. Let the online node synchronize,
   then compare the account, policy, addresses, balance, and transaction
   history with the wallet record.

A timestamp of zero safely scans all history and may take time; it belongs in
the recovery command, not on a paper card. During an emergency recovery, move
the funds to a newly established wallet after a small test payment when
circumstances permit.

Stop and get knowledgeable help instead of guessing when records are missing,
results disagree, or the wallet is multisig or nonstandard.

## Special cases

### Multisig cosigner recovery

Restore the cosigner's private Bitcoin Core wallet with `ms32 wallet`, then
follow Bitcoin Core v32's maintained
[multisig tutorial](https://github.com/bitcoin/bitcoin/blob/v32.0rc1/doc/multisig-tutorial.md).

### Card maintenance and damaged writing

- `ms32 check` validates a card's format and checksum. A valid result does
  not prove that it belongs to this wallet.
- `ms32 correct` suggests a repair. Compare any suggestion character by
  character with the physical backup before confirming it.
- `ms32 share d` derives a replacement at unused index `d`. Confirm and
  store the new card before retiring an old one. Interactive use displays the
  share, then asks you to write and re-enter it. Matching groups stay confirmed
  while you recheck highlighted regions. Success prints “Recovery card
  confirmed.” `--plain` skips card confirmation. Redirected damaged input can
  still require an interactive correction confirmation.

### Advanced: completing missing trailing characters

The correction command can fill trailing erasures when the final characters
are actually unknown. For a normal codex32 string, replace the final 13 missing
characters with `?`; a long-checksum string uses 15. Thirteen genuinely
unreadable characters at the end of an existing backup are therefore a valid
recovery case. The same mechanism can complete newly generated worksheet data
whose final 13 squares have not yet been filled.

Never intentionally delete or replace the existing final characters from a
backup that merely fails validation. Doing so can hide a transcription or
corruption error by locking it into a newly valid result. Preserve the observed
text and use normal correction instead.

Enter sensitive material only through the prompt. Run `ms32 correct` and then
enter the damaged string with trailing `?` characters when asked; do not place a
secret or share in the command arguments. The strong warning and literal `YES`
gate apply before the completed suggestion is shown.

The generic `codex32` façade can check, correct, recover, and derive shares for
compatible Core Lightning, BIP39 worksheet, and opaque-HRP artifacts. It does
not generate BIP39 words or Core Lightning secrets. Registered profiles retain
their application validation; unknown HRPs remain opaque codex32 symbols.
Keep the matching application worksheet and original wallet instructions with
the inheritance plan. Published BIP-93 still defines the `ms` application; the
arbitrary-HRP format direction is not yet merged into that specification.

### QR troubleshooting

Maximize the terminal and reduce its font size if a QR does not fit. Keep `qr`
connected to the terminal; redirecting its output creates an image file. Only
public descriptors, xpubs, and PSBTs may cross the offline boundary by QR.

## Technical references

Automation, low-level private exports, parser behavior, correction mathematics,
and exact limits are documented in the [API and architecture guide](../developer/api.md).
Auditors should also read the [security model](../security/model.md).

Interactive `create --existing` offers bounded correction for a mistyped codex32
secret of the selected profile. Compare the entire proposed string with the
original recovery card before answering yes. Bitcoin candidates show their master
fingerprint above the text. Declining or finding no usable correction returns to
source entry; hexadecimal seeds are never corrected. Confirmation of newly
created cards is a separate step after accepting the source.

A correction suggestion may be labelled **best effort / search incomplete**.
This means the search found that candidate but did not establish uniqueness.
Compare and confirm the entire string against the original backup before use.
Correction separates missing, extra or swapped characters from BCH repair of
wrong or unreadable characters. Four-character display groups have a separate
alignment search. Both searches stop within a ten-second computation budget;
deeper character searches are best effort.
