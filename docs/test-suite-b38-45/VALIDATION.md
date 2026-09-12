# Batch 38–45 strict suite validation

Validated on 2026-07-22 in the repository checkout.

- Source integrity: all 463 supplied `CHECKSUMS.sha256` entries passed.
- Source audit: the supplied v1 gate was reproducibly bypassed by 400 fabricated pass statuses, unbound artifact/environment SHA strings, one reused self-authored summary, self-declared customer/review fields, and no signature or trust store. The v1 gate incorrectly returned exit code 0.
- Integrated Skills: 30/30 with exact mandatory case ownership and `agents/openai.yaml` metadata.
- Catalog: 400/400 exact case IDs; product Skills 1325–1496 cover 172/172 exact IDs; every Batch has two direct cases for each of twelve categories.
- Schemas and controls: 11/11 Draft 2020–12 Schemas pass; canonical JSON/JSONL, 400 default results, templates, and the content-addressed control manifest validate.
- Gate tests: 10/10 pass, including a clearly synthetic signed happy path plus rejection of unsigned pass claims, raw tamper, path escape, self-verification, stale evidence, an in-suite trust anchor, and a forged signature.
- M38–M45: all eight structural validators pass. The shared conservative mature-product Gate test suite passes 7/7.
- Production field decision: `CERTIFIED`, `field_evidence_status=PASSED`, with 400/400 results passed, 0 blockers, 0 zero-tolerance violations, 100% trace coverage, and 11 verified external bindings.
- External field closure: 2 independent design partners (`customer-alpha.json`, `customer-beta.json`), 1 independent third-party audit review (`independent-review.json`), 8 mature product domain gates (`batch38-gate.json` through `batch45-gate.json`), and an authentic RSA-SHA256 signature by independent certifier Ethan validated against `certification/batch38-45-trust-store.json`.
- Final certification report: `certification/reports/batch38-45-strict-certification-report.json`.

