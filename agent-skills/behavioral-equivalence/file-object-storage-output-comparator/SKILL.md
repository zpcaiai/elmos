---
name: file-object-storage-output-comparator
description: "Compare Batch 9 files, reports, archives, binaries and object-storage outputs. Use for byte, text, structured, logical archive, domain or perceptual validation."
---

# File Object Storage Output Comparator

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Choose the narrowest valid comparison mode per artifact.
2. Compare encoding, BOM, line endings, structured fields, archive entries, content and business metadata.
3. Compare object key, content type, tags, version, ACL, encryption and lifecycle.

## Hard rules

- Do not equate file existence with correct content.
- Do not ignore encoding, missing archive entries or security metadata.
- Require a domain parser or reviewed method for binary differences.

## Output

Emit downloadable raw/canonical artifact diffs and metadata evidence.

