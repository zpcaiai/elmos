# ELMOS strict and supplemental test-suite validation report

Date: 2026-07-22

## Current engineering qualification

Latest complete report: `artifacts/test-suite/local-qualification-20260722-r17-final-stable/qualification-report.json`

- Scope: `local-engineering-evidence-only`
- Command execution: 10/10 passed, all five recorded cleanups passed, zero timeouts
- Overall report status: `FAILED` because a separate task added 660 Batch 81–95 files and changed 10 source/control files during execution; no files were removed
- Report digest: `sha256:68dea0058e05081f11fb4adcc2d1eddb101fc42e40f4dddc187a19b1fa53d952`
- Qualification-report file SHA-256: `0829905b07eee143f6983e70c3396417524167103d9da47b6b419e3197d6046f`
- Pre-run artifact-manifest SHA-256: `b822a837c172ffc0790a4f8cb336d19354fbe45d800c71e433b534564b6012ae`
- Post-run artifact-manifest SHA-256: `36511965cf39d6ef5ef4517139e1701fafb197939e6d9148891795343a57a8da`
- Environment-manifest SHA-256: `ec1fdf372c5d285520164a66682546c15e09e5797ef75ae3320246f057d07780`
- Certification case updates: none
- Certification decision: `BLOCKED`
- Field evidence: `NOT_RUN`

### Executed results

| Stage | Result |
|---|---:|
| Strict-suite structural and anti-forgery toolkit | 36/36 Batch 1–37 tests and 10/10 Batch 38–45 tests passed; 408 + 400 exact cases remain not run |
| Supplemental catalogs | Batch 1–55: 660; Batch 1–65: 750; Batch 66–80: 450; Batch 81–95: 120; all structure checks passed and results remain `NOT_RUN` / `not-run` |
| Batch 1–55 Skill integration | Structural validation passed; external evidence remains `NOT_RUN` |
| Product Batch 33–55 Skill integration | 1,107 canonical Product Skills passed exact validation; additive runtime namespaces are counted separately |
| Migration Pack M29–M45 toolkits | Full `mature-product-skills` target passed |
| Java Reactor | Full reactor `BUILD SUCCESS`; recorded cleanup passed |
| .NET engine | 12/12 tests passed |
| Python engine | 31/31 tests passed; Ruff and mypy passed |
| Project Synthesis engine | 417 global and 180 package-local Language Pack Skills plus 42 Schemas validated; 5/5 tests, Ruff, mypy, seven build/analysis checks and three startup probes passed |
| Frontend client | 34/34 tests passed |
| Web console | TypeScript and Next.js production build passed |

## Conservative gate results

Every authoritative or supplemental gate returned exit code 2 and failed closed. This is expected because local engineering execution does not manufacture external evidence.

| Suite | Decision | Unexecuted results | Additional blocker |
|---|---|---:|---|
| Batch 1–37 exact | `BLOCKED` | 408 | Signed request, separate trust store and independent evidence absent |
| Batch 1–55 supplemental | `BLOCKED` | 660 | P0 0/152, P1 0/453; source package has no exact Migration Pack M34–M45 cases |
| Batch 1–65 supplemental | `BLOCKED` | 750 | Critical 0/176; 0/65 Batch test Skills externally executed |
| Batch 38–45 exact | `BLOCKED` | 400 | Design partners 0/2, independent reviews 0/1, domain gates absent |
| Batch 66–80 supplemental | `BLOCKED / NOT_RUN` | 450 | P0/P1/P2 and 103 zero-tolerance cases have no authorized native evidence |
| Batch 81–95 supplemental | `BLOCKED` | 120 | Native/vendor execution, independent verification and authorization absent |

## Repaired validation failure

The first immutable run is retained at `artifacts/test-suite/local-qualification-20260722/`. It failed because the pre-existing architecture assertion expected exactly 372 `.agents/skills`, while importing 52 strict-suite Skills correctly raised the total to 424. The assertion now verifies the two namespaces independently: 372 Migration Pack Skills plus 52 strict-suite Skills. A targeted 20-test architecture run and the complete Reactor both passed after the repair.

The second passing run is retained at `artifacts/test-suite/local-qualification-20260722-r2/`. Review found its artifact manifest also enumerated prior generated `artifacts/` evidence. The qualification runner now excludes generated evidence from the source snapshot and has a regression assertion for that boundary. The clean `r3-clean` run proved that correction.

The immutable `r4-final` run is also retained. During that run, a separate workspace process additively generated 768 new `agent-skills/runtime` Skills. The architecture test's exact total observed the directory midway through generation and failed at 1,286 versus the former 879. No generated Skill was deleted or overwritten. The assertion now enforces the stabilized 1,647-Skill minimum cardinality while allowing additive generated Skills; a targeted 20-test architecture run passed, and the full `r5-final` qualification passed against that final state.

Review of `r5-final` found that its runner only captured a pre-run source manifest, so it could not prove that the source remained unchanged throughout execution. The runner now emits both pre-run and post-run manifests, compares every included path, digest, and byte count, and fails the qualification on any added, removed, or changed source. A dedicated source-drift negative test was added. The stable `r6-final-stable` run proved that correction.

The historical `r8-final-authoritative` run included the repaired Batch 38–45 gate protocol and passed all seven then-current stages against identical pre-run and post-run source snapshots. Later repository additions mean it is no longer a current whole-repository authority. The current `r14` run executed all 10 present stages successfully, but correctly failed the global no-drift condition because separate work added Batch 61–65 and UI/test assets during the run. Batch 38–45 itself had zero relevant drift.

## Batch 38–45 attachment integration

The attachment contains 172 Skills with the same exact IDs already represented by the repository's M38–M45 namespace. They were reconciled by ID rather than copied into a duplicate namespace. Its 486-entry file manifest is internally complete, but its 95 auxiliary Schemas permit unrestricted extra properties and its positive gate fixtures use synthetic digest strings, self-authored evidence, no independently verified raw artifacts, and no signed certification request or separate trust store. Its 32 tests therefore remain source-package structural evidence only.

The integrated gate now validates exact files, SHA-256 digests and byte counts; separates executor, verifier and certification authority; requires independent holdout and representative corpora; verifies a detached RSA-SHA256 request against a separate non-revoked trust store; and requires exact M38–M44 domain-gate evidence before M45 can pass. Seven positive and adversarial tests cover the signed path, missing signature, self-verification, raw-evidence tampering, missing domain gates, role collision, and malformed documents. See `docs/mature-product/BATCH38_45_SOURCE_AUDIT.md` and `docs/mature-product/EVIDENCE_PROTOCOL.md`.

## Strict certification gate

Current gate: `test-suites/batch1-37-strict/release-gate.json`

- Gate version: 2
- Gate status: `blocked`
- Decision: `BLOCKED`
- Certification requested: false
- Results: 0 passed, 0 failed, 408 `not-run`, 0 missing, 0 invalid
- Field evidence status: `NOT_RUN`
- Blockers: 408 exact P0/P1 cases
- Gate evidence digest: `sha256:3e6274b07dc004c404921b9f04a7f9185af9e600e2343004eb9c81da12c55852`
- Gate-code digest: `sha256:4a347057a9bcd14dc010fcbff7abf5834477317a7abacf39333cb07fdd276110`

This is the correct boundary. The engineering implementation and local tests are complete; customer, field, production-equivalent, independent holdout, representative workload, security authorization, DR and external certification evidence has not been executed merely by importing this package.
