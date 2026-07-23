# Product Closure Batch 56A and Convergence Verification

## Scope and namespace

This integration imports two additive, non-interchangeable packages:

- Product Batch 56A: 16 reviewed-design Runtime Skills with source IDs `CLO56A001` through `CLO56A016`.
- Product Convergence: 32 repository Agent Skills with source IDs `CONV-001` through `CONV-032`.

Batch 56A is not Migration Pack M56. Product Convergence is an implementation and reference overlay, not a new feature Batch. Neither package changes the status of Product B34-B55, Migration M29-M45, or any strict/supplemental qualification suite.

## Installation contract

The canonical package trees are immutable inputs. `tooling/import_product_closure_convergence.py`:

1. validates exact package identity, Skill IDs, counts, source paths and source checksums;
2. preserves every source Skill digest in the installed manifest;
3. normalizes only Batch 56A frontmatter fields that the official Codex validator rejects, moving source identity and maturity into supported `metadata`;
4. installs deterministic `agents/openai.yaml` interfaces for all 48 Skills;
5. copies Schemas, templates, documentation, reference data and validation tooling without silently replacing a different existing file; and
6. verifies the installed bytes, interfaces, provenance and integrated assets on every subsequent run.

The authoritative installed inventory is `docs/product-closure-convergence/installed-manifest.json`. The convergence package preserves the supplied checksum and file inventories as `SOURCE_CHECKSUMS.sha256` and `SOURCE_FILE_MANIFEST.txt`; the normalized canonical tree has its own verified `CHECKSUMS.sha256` and `FILE_MANIFEST.txt`.

## Readiness authority

The package-supplied static validators remain useful structural engineering checks. They are not authoritative for product readiness because a syntactically plausible digest alone is not evidence of an executed workload.

The repository authorities are:

- `scripts/product-closure-batch56a/run_product_closure_gate.py`
- `scripts/product-convergence/run_repository_convergence_gate.py`

Both gates bind evidence to an in-root file path, real SHA-256, positive byte count, authorization reference, execution identity and different independent verifier. Product Convergence additionally requires two distinct accepted design-partner organizations and an independent reviewer who did not execute or verify partner evidence. P0 and zero-tolerance findings are non-waivable.

The maximum successful local decision is `READY_FOR_EXTERNAL_GATE`. `gaApproved` and `productionCertified` remain false. Checked-in requests intentionally contain `NOT_RUN`/`not-run` states and therefore return `BLOCKED` with exit code 2.

## Reproducible checks

```bash
make product-closure-convergence-skills
make batch1-55-skills
make product-batch33-55-skills
make product-closure-gate       # expected fail-closed
make product-convergence-gate   # expected fail-closed
```

The positive gate fixtures in `tests/product-closure-convergence/test_repository_integration.py` use real temporary evidence files and prove only that an exact request can be prepared for an external gate. They are deliberately not retained as field evidence and cannot update customer, GA, production or certification state.

## Current result

- Package and installed Skill structure: locally validated.
- Source-to-install provenance and interfaces: locally validated.
- Anti-fabrication, self-verification and default fail-closed behavior: locally validated.
- Real Golden Journeys, providers, Private Runner, design-partner acceptance, independent field review, customer outcomes and unit economics: `NOT_RUN`.
- Product closure/GA/certification: `BLOCKED` pending authorized external evidence.
