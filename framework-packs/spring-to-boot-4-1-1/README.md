# Spring / Spring MVC / Spring Boot → Spring Boot 4.1.1

This is the exact Spring Boot 4.1.1 / Java 21 target profile. It covers
Spring Framework and Spring MVC source applications as well as Spring Boot
1.5 through 4.0 applications using Maven or Gradle.

The feature matrix is a typed inventory, not a promise that static syntax can
prove runtime equivalence. Core deterministic work is delegated to the pinned
OpenRewrite Spring recipes. Bean graphs, security, persistence, transactions,
messaging, cache, scheduler, views, reactive backpressure, and provider
behavior are emitted as FCM obligations and remain conditional until a real
source/target build, startup, contract, holdout, and independent verification
exists.

The fingerprint also emits an explicit `unmapped-spring-construct` observation
for Spring-looking source that does not match a known feature. Such source is
preserved and blocked for human or provider-specific mapping; it is never
silently treated as converted.

The verification plan is paired with `verification/track-contract.json`. This
declarative, non-executable contract binds all nine tracks to the exact route,
target profile, provider lock, corpus, evidence roles and fail-closed policy.
Security, database, transaction, messaging and other provider behavior are
separate domains; unresolved provider profiles remain explicit and all runtime
execution, authorization and independent-verifier states remain `NOT_RUN`.

Spring Boot 4.1.1 is the latest stable target represented by this pack. One
exact local reference route, Spring Boot 3.5.3 / Java 21 / Maven 3.9.11 to
Spring Boot 4.1.1 / Java 21, has passed source and target builds, startup, HTTP,
validation, security, JPA, and transaction rollback parity. This is bounded
`PASSED_LOCAL` engineering evidence only. The other exact routes, the full
provider matrix, holdout and representative repositories, external execution,
independent verification, and certification remain `NOT_RUN` /
`NOT_CERTIFIED`; the pack therefore remains experimental.

Validate the structure with:

    python3 scripts/batch30/validate_framework_pack.py framework-packs/spring-to-boot-4-1-1
    python3 scripts/operations/validate_spring_verification_plan.py framework-packs/spring-to-boot-4-1-1

The pack does not authorize customer repository access, provider operations,
deployment, signing, or certification.
