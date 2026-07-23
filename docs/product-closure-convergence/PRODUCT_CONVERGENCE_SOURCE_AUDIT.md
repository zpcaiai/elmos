# Product Convergence source audit

The supplied package at
`/Users/stephen/Downloads/elmos-product-convergence-reference-skills/` contains
32 `CONV-001`–`CONV-032` Skills, 12 Draft 2020-12 Schemas, templates, reference
plans, validators and eight source-toolkit tests. All 100 supplied checksum
entries passed before integration.

The immutable repository copy preserves the original checksum and file manifests
as `SOURCE_CHECKSUMS.sha256` and `SOURCE_FILE_MANIFEST.txt`. Its normalized
checksum inventory excludes generated `__pycache__`/`.pyc` files so validation
does not depend on a local Python runtime cache.

## Source limitations

The source toolkit is structurally useful but is not a reference product
implementation or readiness authority:

- the Capability Registry, Dependency Graph, Evidence Graph and Benchmark Corpus
  are empty;
- the convergence plan is a draft with no owners or milestones;
- the Reference Route uses fuzzy `3.x` and `current LTS` versions, is only
  `planned`, and has no evidence;
- the customer-handoff exercises and readiness criteria are all `not-run`;
- the source gate accepts digest-shaped strings without binding the referenced
  files, their byte counts or contents;
- the source positive test does not establish customer, runtime or production
  evidence.

These limitations are preserved as explicit blockers rather than silently
converted to success.

## Repository hardening

- All 32 Skills are installed under `.agents/skills/conv-*` with official Codex
  validation and generated `agents/openai.yaml` interfaces.
- `tooling/import_product_closure_convergence.py` verifies exact source hashes,
  installed hashes, provenance and the 32-Skill registry.
- `validate_repository_convergence_bundle.py` validates all 12 Schemas, 11 bound
  instances, exact Skill IDs and paths, the 32-P0 plan and eight readiness
  criteria.
- `run_repository_convergence_gate.py` additionally requires an approved owned
  plan, evidence-bearing capability/dependency/evidence graphs, exact Route
  versions, real Route evidence, independent corpora, customer handoff, content-
  addressed repository and criterion evidence, two design partners and one
  independent review.
- The repository gate can only return `READY_FOR_EXTERNAL_GATE`. It always keeps
  certification, deployment and customer-acceptance authority false.

The checked-in default remains `BLOCKED` with external evidence `NOT_RUN`.
