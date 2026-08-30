# Experimental gate report

- Pack: `spring-framework-5-3-mvc-to-spring-boot-3-5-3`
- Pack status: `experimental`
- Certification decision: `NOT_CERTIFIED`
- Pack-specific static validation: `PASSED_LOCAL_STATIC`
- Batch 30 structural validation: `PASSED_LOCAL`
- Batch 30 gate: `PASSED_EXPERIMENTAL_NOT_CERTIFIED`
- Batch 30 Skill interfaces: `20/20 PASSED_LOCAL_STATIC`
- Batch 30 full Python regression: `222/222 PASSED_LOCAL`
- P0-P11 focused Python regression: `103/103 PASSED_LOCAL`; `3/3` subtests passed
- Worker route/fingerprint regression tests: `30/30 PASSED_LOCAL`
- Exact source-to-target qualification integration test: `1/1 PASSED_LOCAL`
- Controlled executable-WAR scaffold: `MATERIALIZED_STATIC_NOT_RUNTIME_VERIFIED`
- XML well-formedness: `PASSED_LOCAL_STATIC`
- Exact source build: `6/6 PASSED_LOCAL` with Java `11.0.26` / Maven `3.9.11`
- Exact source startup: `PASSED_LOCAL` on external Tomcat `9.0.120`
- OpenRewrite `6.44.0` / rewrite-spring `6.35.0`: `PASSED_LOCAL`
- Trusted Java target materializer: `PASSED_LOCAL`; Python scaffold was not used
- Controlled target profile/scaffold resources: byte-bound at `3,731` / `1,773`
  bytes and preserved in the materializer receipt
- Exact target build: `9/9 PASSED_LOCAL` with Java `21.0.11` / Maven `3.9.11`
- Exact target startup: `PASSED_LOCAL` through Boot `3.5.3` `WarLauncher`
- Actuator health and two GET/JSP comparisons: `PASSED_LOCAL`
- Source commit: `7e1c098541143c96cce7d9a637fffe57d0e2baae`
- Source snapshot SHA-256: `68fed1342ec39a2b5fb101f021a8632e3c78ea094318ded003855d0bf8c4e581`
- Exact tuple SHA-256: `f487c24648b0c0480653b41f6fb9f2c5fb701c1774c1859353e4e400130c0103`
- Target profile SHA-256: `8042f1bed7cde57d13e9794b7a694437d5b12d40f0eb4948c656d942a9297ee1`
- Qualification policy SHA-256: `e7e1e19b10a2e7545f859204542c9a1afbe3aeaa49478415c4050340bac7e88c`
- Download ZIP: `17,347` bytes / `f85763c1d86a6af8e39cbdcb0d98571595e58e9ecf8a047b1df6e0ebf1fcd298`
- Executed source WAR: `9,873,951` bytes / `ad40f44d02fbebe7300f2c1aefa4ba27fcae3dd180d2ae839e0e3685e3aba42d`
- Executed target WAR: `28,990,394` bytes / `7a326b69fc5651fe4986d00742dbae7a4f8b6e81aacdecc361a0d9cf30ec1d97`
- Evidence index: `certification/local-execution/2026-08-30/evidence-index.json`
- Supplemental local target benchmark: `200/200`, `0` failed requests, concurrency `8`
- Supplemental local operability and isolated rollback rehearsal: `PASSED_LOCAL`
- Supplemental artifact-bound CycloneDX inventory: `PARTIAL_LOCAL_INVENTORY_ONLY`
- Negative, holdout and representative corpora: `NOT_RUN`
- Vulnerability scanners, customer, Rootless and independent review: `NOT_RUN`

This is local engineering evidence for one exact fixture. It is not customer,
representative, independent or certification evidence, and it cannot establish
an overall behavior-equivalence percentage for old Spring projects.
