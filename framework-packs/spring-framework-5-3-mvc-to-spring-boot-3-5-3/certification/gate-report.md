# Experimental gate report

- Pack: `spring-framework-5-3-mvc-to-spring-boot-3-5-3`
- Pack status: `experimental`
- Certification decision: `NOT_CERTIFIED`
- Pack-specific static validation: `PASSED_LOCAL_STATIC`
- Batch 30 structural validation: `PASSED_LOCAL`
- Batch 30 gate: `PASSED_EXPERIMENTAL_NOT_CERTIFIED`
- Pack-specific unit tests: `22/22 PASSED_LOCAL`
- Worker route/materializer/runtime regression tests: `63/63 PASSED_LOCAL`
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
- Source snapshot SHA-256: `68fed1342ec39a2b5fb101f021a8632e3c78ea094318ded003855d0bf8c4e581`
- Download ZIP: `17,347` bytes / `f85763c1d86a6af8e39cbdcb0d98571595e58e9ecf8a047b1df6e0ebf1fcd298`
- Executed WAR: `28,990,394` bytes / `58c46baf60eeec971a95a02d183c8c8e74108699a6194263e2db20f3a28c986f`
- Negative, holdout and representative corpora: `NOT_RUN`
- Customer, Rootless and independent review: `NOT_RUN`

This is local engineering evidence for one exact fixture. It is not customer,
representative, independent or certification evidence, and it cannot establish
an overall behavior-equivalence percentage for old Spring projects.
