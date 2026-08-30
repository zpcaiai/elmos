# Spring Framework 5.3 MVC / Java 11 to Spring Boot 3.5.3 / Java 21

Directional Batch 30 experimental modernization pack for a traditional, non-Boot
Spring MVC WAR application. The only admitted source tuple is Spring Framework
`5.3.39`, Java `11`, Maven `3.9.11`, Servlet API `4.0.1`, and WAR packaging. The
target tuple is Spring Boot `3.5.3`, Spring Framework `6.2.8`, Java `21`, Maven
`3.9.11`, Jakarta Servlet `6.1`, and embedded Tomcat `10.1.42`.

The pack contains a typed Framework Contract Model, deterministic OpenRewrite
recipe composition, an executable-shaped legacy MVC development fixture, and a
controlled target emitter for the admitted XML/Servlet/JSP construct set. The
production execution port now calls a trusted, typed Java materializer after the
pinned rewrite step and before target verification; it never executes repository
Python. The materializer is deliberately limited to the complete 13-file exact
fixture, bound by path, byte count and SHA-256. It creates a Boot main plus
`SpringBootServletInitializer`, explicit Java
configuration, a Tomcat Jasper executable WAR, health-only Actuator exposure,
repackage configuration, and content-addressed XML/`web.xml` retirement receipts.
It rejects unknown files, changed bytes, tuple drift and constructs instead of
inferring their behavior. The exact checked-in fixture has now completed one
fresh local engineering replay: Java 11/Maven 3.9.11 source `clean verify`
(`6/6` tests), external Tomcat `9.0.120` startup, pinned OpenRewrite, the trusted
Java materializer, Java 21/Maven 3.9.11 target `clean verify`/package (`9/9`
tests), executable-WAR `WarLauncher`, exact Actuator health, two GET/JSP
source-to-target comparisons and bounded shutdown. The JSP comparison produced
the same 142 UTF-8 bytes; only the exact 32-hex-character `JSESSIONID` value is
treated as governed nondeterminism while cookie attributes remain exact.

The content-addressed evidence index is
`certification/local-execution/2026-08-30/evidence-index.json`. It separately
binds the 17,347-byte migrated-repository ZIP and the 28,990,394-byte executable
WAR (`7a326b69fc5651fe4986d00742dbae7a4f8b6e81aacdecc361a0d9cf30ec1d97`),
whose manifest names Boot `3.5.3`, `WarLauncher` and
`io.elmos.legacy.LegacyMvcApplication`. It also preserves the Java materializer
receipt and source map, including exact byte/SHA-256 bindings for the controlled
target profile and scaffold manifest. The Python scaffold remains static and was
not the runtime materializer used by this replay. A separate supplemental local
receipt records a 200-request loopback benchmark, local operability probes, an
isolated source rollback rehearsal and an artifact-bound CycloneDX component
inventory; it explicitly leaves vulnerability scanning and external qualification
`NOT_RUN`.

The result is therefore `PASSED_LOCAL` for this one exact fixture while the pack
remains `experimental` and `NOT_CERTIFIED`. Negative and holdout corpora,
representative/customer repositories, security/data/transaction/messaging
profiles, Rootless execution and independent review remain `NOT_RUN`. This run
must not be presented as an overall Spring migration success rate.

Validation commands:

```bash
python3 scripts/batch30/validate_legacy_spring_mvc_pack.py
python3 scripts/batch30/validate_framework_pack.py \
  framework-packs/spring-framework-5-3-mvc-to-spring-boot-3-5-3
python3 scripts/batch30/run_framework_gate.py \
  framework-packs/spring-framework-5-3-mvc-to-spring-boot-3-5-3
```
