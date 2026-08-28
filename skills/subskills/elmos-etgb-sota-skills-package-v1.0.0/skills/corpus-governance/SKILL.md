---
name: corpus-governance
description: Select, pin, license-review, sandbox, time-split, fetch, and maintain public/private ETGB corpora reproducibly.
---

# Corpus Governance

## Goals

Reproducibility, legal safety, supply-chain isolation, representative coverage and benchmark contamination control.

## Intake workflow

1. Map candidate to an uncovered capability/scale/technology cell.
2. Record repository, exact commit/tag, retrieval date, upstream metadata and purpose.
3. Review license, patent, trademark, data, secret, binary and redistribution risks.
4. Scan history/worktree for secrets, PII, malware indicators, symlinks, submodules and dangerous build steps.
5. Build only in isolated no-secret sandbox with network allowlist.
6. Establish deterministic build/test commands and known flakes.
7. Create time split and hidden variants.
8. Approve or block; metadata-only distribution is default.

## Lock policy

Release/golden cannot follow branch names. Every corpus reference is a 40-character commit plus artifact digest where a dataset/release archive is used. Update is a reviewed benchmark version change, not routine background drift.

## License policy

`license_review=required` blocks release profile. Do not infer permission from popularity or public visibility. Retain review evidence and attribution obligations.

## Contamination policy

- public tests are visible baseline only;
- private hidden tests reside in a separate permission domain;
- time-split tasks prevent using future fixes;
- paraphrase/parameter/metamorphic variants prevent literal memorization;
- disclose known overlap with training or public leaderboards when identifiable.

## Fetch policy

`scripts/fetch_corpora.py` refuses network unless explicitly enabled and skips all unapproved entries. Production fetcher must verify commit/digest and use an allowlisted mirror where possible.

## Retirement

Retire corpora that become unavailable, legally blocked, irreproducible or no longer representative. Preserve historical metadata so old evidence remains interpretable.
