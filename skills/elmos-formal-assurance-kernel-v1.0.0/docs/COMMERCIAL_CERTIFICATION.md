# Commercial Certification Standard

## Product claims

The package supports four product-grade assurance claims:

1. `Assurance Ready`: specifications, obligations and tool adapters are integrated.
2. `Model Assured`: E1/E2 pass for declared profiles.
3. `Conversion Assured`: E1–E4 pass with source/target evidence.
4. `Customer Trusted`: P05 and E1–E5 pass on a named Golden Route with signed evidence.

## Repository scale

For the Spring large-repository Golden Route, commercial certification requires at least three repositories above 500k LOC and at least one above 1M LOC. LOC alone is insufficient; the set must include realistic framework, data, security, asynchronous and operational complexity.

## Repeatability

A route is repeatable when another authorized operator can use the release manifest and runbook to reproduce:

- source/target revisions;
- environment and database state;
- formal models and assumptions;
- exact verifier versions/options/bounds;
- proof results and counterexamples;
- release decision and report.

## Evidence retention

Customer evidence bundles use a documented retention class and redaction policy. Source code need not be exported when customers require in-environment verification; hashes, certificates, summaries and replay metadata can be separated.

## Acceptance thresholds

- 100% classification of P0 entrypoints/features.
- 0 unapproved P0 unknown/unsupported results.
- 0 status-inflation findings.
- 100% proof artifact integrity.
- All critical counterexamples reproduced and closed or explicitly accepted.
- SLO, failure injection, backup/restore and security tests pass.
