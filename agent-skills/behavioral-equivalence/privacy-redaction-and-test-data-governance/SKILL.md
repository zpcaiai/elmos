---
name: privacy-redaction-and-test-data-governance
description: "Govern Batch 9 sensitive traffic, database, message, file, log, Golden and evidence data. Use when ingesting, tokenizing, retaining, sharing or deleting behavioral test data."
---

# Privacy Redaction and Test Data Governance

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Classify data and choose mask, hash, tokenize, pseudonymize, synthesize, drop or encrypt treatment.
2. Preserve referential relationships across every observation channel.
3. Replace credentials with reissued test identities and scan all exports.

## Hard rules

- Delete credentials rather than merely masking them.
- Keep Golden and evidence free of real secrets.
- Define access, retention, legal requirements and deletion evidence.

## Output

Emit redaction/token maps, lineage, scan results and retention decisions.

