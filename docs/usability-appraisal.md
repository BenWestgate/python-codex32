# Gate 5 usability appraisal

Status: **human validation incomplete** as of 2026-08-25.

The locally producible recovery materials are complete:

- [one-page share recovery card](recovery-card.html);
- [separate wallet-verification record](wallet-verification-record.html);
- [inheritance workflow](inheritance.md), with watch-only verification before
  private restoration; and
- a versioned manual fallback with a frozen filename and SHA-256 digest.

Automated checks verify the required fields, 32 four-character protected-text
groups, separation of fingerprint/address metadata, offline warnings, and the
watch-only-first sequence. These checks establish document structure, not human
comprehension.

## Moderated protocol still required

Use dummy, unfunded secrets only. Recruit at least ten participants, including
at least five unfamiliar with this repository and at least three heir scenarios
where the participant did not create the backup. For each participant, record:

1. whether they selected the correct recovery path from the card without a
   critical intervention;
2. whether protected text was ever offered to an online service or disclosed
   outside the test harness;
3. setup time excluding Bitcoin Core synchronization and recovery rescans;
4. whether watch-only verification preceded private restoration; and
5. every confusing instruction, intervention, and resulting document or CLI
   change.

Report the observed successful-recovery rate and setup-time distribution. Do
not convert a small moderated sample into a universal safety claim. Any critical
intervention or wrong recovery path requires a revised artifact and another
iteration.

## Prior reported evidence

The project plan records earlier Bails beta testing: 24 unfamiliar participants,
including at least three who did not create the backup, reportedly installed,
created, wrote down, and recovered in under 30 minutes. That report was supplied
as planning context and has not been independently reproduced or audited in this
repository. It may inform the protocol but does not close Gate 5's card-specific
moderated validation.
