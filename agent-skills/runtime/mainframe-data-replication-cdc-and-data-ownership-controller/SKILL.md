---
name: mainframe-data-replication-cdc-and-data-ownership-controller
description: Govern bulk load, CDC, application events, dual writes, file increments, replay, reconciliation, and write-authority transitions for Db2, VSAM, IMS, sequential files, GDGs, MQ, and temporary storage. Use for mainframe data coexistence, writer cutover, reverse sync, or rollback planning.
---

# Mainframe Data Transition

## Establish authority

1. Record one explicit authority state from mainframe-authoritative through controlled dual-write, new-authoritative, mainframe-read-only, and decommissioned.
2. Select bulk export, log CDC, application event, dual write, incremental file, batch reconciliation, or event replay per asset and evidence quality.
3. Decode CCSID, EBCDIC, packed/zoned decimal, binary, variable, and blocked records with versioned layouts.
4. Preserve IMS hierarchy and VSAM access semantics; document loss risk when reliable log CDC is unavailable.
5. Reconcile counts, keys, control totals, amounts, statuses, relationships, duplicates, deletes, and business invariants.

## Switch writes

- Require full load, caught-up increments, encoding validation, reconciliation, new-writer tests, consumer readiness, recovery, and business approval.
- Block when an online, batch, file, message, or unknown legacy writer remains.
- Define downcast/data repair or forward fix when the old system cannot understand new states.
