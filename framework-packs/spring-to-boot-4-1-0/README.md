# Spring / Spring MVC / Spring Boot to Spring Boot 4.1.0

This is a directional Batch 30 modernization pack for the direct user-facing
edge from a fingerprinted Spring Boot 1.5 through 4.0.x application, a
non-Boot Spring MVC application, or a non-web Spring Framework Core/Context
application using Spring Framework 3.2 through 7.0.8, to the exact Spring Boot
4.1.0 / Java 21 target.

"Direct" describes the requested source-to-target edge. The Boot recipes still
apply the required intermediate OpenRewrite migrations in order before the
final 4.1.0 pin. A source version is never guessed: the engine must resolve an
exact dependency/BOM/plugin version and an exact source JDK before selecting a
route.

The pack remains `experimental`. Two exact Maven tuples have now passed local
engineering execution: Boot 2.7.18 / Java 17 and Boot 3.5.3 / Java 21 to Boot
4.1.0 / Java 21. Two non-customer public repositories have also completed a
local Boot 2.7.18 / Java 17 to Boot 4.1.0 / Java 21 Rewrite, build and test
run; the recorded result is in
`certification/public-reference-route-evidence.json`. Every other route and
every unexecuted source version remains `NOT_RUN`. These public runs are local
engineering references, not an independent holdout, representative customer
repository, organizationally independent verification, or certification claim.
It supplies a real execution recipe and fail-closed obligations, not a certification claim. The
target requires Spring Framework 7.0.8, Spring Security 7.1.0, Hibernate ORM
7.4.1.Final, Tomcat 11.0.22, Java 21 and a compatible Maven or Gradle build.
Security, data, transactions, messaging, cache, scheduler, XML/web.xml,
JSP/view and custom auto-configuration behavior remain source-specific FCM
obligations until a real target build, startup and independent holdout are
recorded.

To inspect the next external-gate prerequisites without changing certification
state, run:

```text
python3 scripts/operations/assess_spring_boot_4_1_external_readiness.py \
  --engine /absolute/path/to/rootless/docker-or-podman
```

This read-only audit reports `NOT_READY_FOR_EXTERNAL_GATE` until a protected
rootless runner preflight, physically separate holdout and representative
repository evidence, and a separate verifier receipt are available. A
preflight observation never becomes external execution evidence, and the
audit never writes certification evidence. The checked-in local execution
receipt may change the protected-runner diagnostic to
`PREFLIGHT_AND_LOCAL_ROOTLESS_EXECUTION_RECORDED_EXTERNAL_NOT_RUN`; it is a
development reference fixture result only and does not change any external
`NOT_RUN` boundary or certification state.

The current local receipt records a real Boot 3.5.3 / Java 21 source build,
OpenRewrite transformation, Boot 4.1.0 / Java 21 target build, source and
target startup probes, and a rootless Podman target startup with cleanup. Its
raw route and runner receipts are content-addressed beside the summary under
`certification/local-execution/2026-08-27/`. This is local engineering
evidence for the reference fixture, not a customer repository, independent
holdout, representative corpus, independent verification, or certification.

The worker routes also reference the repository-owned recipe artifact
`io.elmos:elmos-java-recipes:0.1.0-SNAPSHOT`. A local worker must point
`ELMOS_MAVEN_DEPENDENCY_SEED` at an immutable Maven repository containing that
artifact, its POM, and the `io.elmos:elmos-parent:0.1.0-SNAPSHOT` POM. The
worker fails closed with `ELMOS_RECIPE_ARTIFACT_NOT_SEEDED` when this exact
recipe closure is absent; a successful public-repository run with a manually
seeded artifact is not worker or external certification evidence.
