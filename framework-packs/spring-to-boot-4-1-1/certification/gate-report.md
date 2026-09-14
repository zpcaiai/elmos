# Spring Boot 4.1.1 gate boundary

This report records the verification boundary for the experimental
`spring-to-boot-4-1-1` Pack. Static source fingerprinting, conversion planning,
and typed feature/type mapping are implemented as local engineering behavior.

The declarative `verification/track-contract.json` is checked together with
the plan. It binds source/target build and startup, component contracts,
security/database/transaction/messaging/provider behavior, holdout,
representative-repository and independent verification to exact inputs and
evidence roles. It is not an executable runner and cannot promote evidence.

The exact `boot-3.5-maven-to-boot-4.1.1-java-21` local reference route has
bounded `PASSED_LOCAL` evidence from Maven 3.9.11 and Java 21. Its source and
target builds and startup passed, as did HTTP response, validation, HTTP Basic
security, JPA/H2 count, and transaction rollback parity. The version matrix
binds `certification/local-reference-evidence.json`, which records the exact
recipe and built artifact content hashes.

That local fixture does not advance the pack-level certification campaign.
The remaining exact routes and provider surfaces, real security/database/
transaction/messaging/cache/scheduler providers, independent holdout,
authorized representative repository execution, external execution, and
independent verification are intentionally `NOT_RUN`.

The Pack remains `NOT_CERTIFIED` until those tracks produce content-addressed
evidence with authorization and an independent verifier. This file is a gate
boundary record, not runtime or certification evidence.
