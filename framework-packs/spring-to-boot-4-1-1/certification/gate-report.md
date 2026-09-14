# Spring Boot 4.1.1 gate boundary

This report records the verification boundary for the experimental
`spring-to-boot-4-1-1` Pack. Static source fingerprinting, conversion planning,
and typed feature/type mapping are implemented as local engineering behavior.

The declarative `verification/track-contract.json` is checked together with
the plan. It binds source/target build and startup, component contracts,
security/database/transaction/messaging/provider behavior, holdout,
representative-repository and independent verification to exact inputs and
evidence roles. It is not an executable runner and cannot promote evidence.

All twelve exact routes have bounded local synthetic source/target build,
startup and HTTP behavior receipts. The following formal evidence tracks are
still intentionally `NOT_RUN`: pack-level source and target execution,
component contracts, provider behavior for security/database/transactions/
messaging/cache/scheduler, independent holdout, authorized representative
repository execution, and independent verification. The Boot 1.5 Gradle route
now records a governed dual-toolchain local stage, and both non-Boot Spring
routes record typed FCM generation plus source container/context startup; none
of those local receipts substitutes for a formal track result.

The Pack remains `NOT_CERTIFIED` until those tracks produce content-addressed
evidence with authorization and an independent verifier. This file is a gate
boundary record, not runtime or certification evidence.
