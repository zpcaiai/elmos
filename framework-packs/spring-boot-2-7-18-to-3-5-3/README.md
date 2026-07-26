# Spring Boot 2.7.18 / Java 17 → Spring Boot 3.5.3 / Java 21

Directional, exact Batch 30 framework upgrade pack. The implementation accepts only a root
Maven project whose effective source tuple resolves exactly to Spring Boot 2.7.18 and Java 17,
with `spring-boot-starter-parent` as its version authority.
It extracts the FCM before applying pinned OpenRewrite recipes, builds with Java 21, packages a
content-addressed ZIP and requires a separate fresh-artifact verifier before download or startup.

The local development fixture has completed a real OpenRewrite transform, exact target replay,
Java 21 build, tests, startup, health probe and business probe. This is engineering evidence only.
The product API journey has also completed the materialized-Snapshot path through durable Run state,
FCM, conversion, test parity, a physically separate local verifier service, digest-matched download,
verified-JAR startup and graceful stop. The Worker now keeps durable Run state and promoted FCM
outside the Transformer-only `execution/` subtree, rejects escaping output paths, revalidates the
locked Snapshot after the Java 17 baseline, and excludes local secret files from copied output; see
`certification/local-product-journey-evidence.json`. The Rootless deployment path uses a one-shot
offline Transformer, one-shot Verifier and per-Run `network=none` Runtime, but those containers were
not executed on this host because no attested rootless daemon was available.
The pack is `experimental`, not certified. Rootless Runner execution, an authorized customer
repository and external independent review are separate evidence roles and remain `NOT_RUN`.

Runtime API: `/engine/v1/spring-upgrades`.

Reproducible local reference command:

```bash
ELMOS_MAVEN_EXECUTABLE=/path/to/apache-maven-3.9.11/bin/mvn \
  python3 scripts/batch30/run_spring_boot_reference.py --repo-root .
```

The runner rejects every Maven version other than 3.9.11 and never executes a
repository-provided `mvnw`.
