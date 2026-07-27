# Spring Boot reference gate

- Spring Boot 2.7.18 / Java 17 build and startup: `PASSED_LOCAL`
- Spring Boot 3.5.3 / Java 21 build and startup: `PASSED_LOCAL`
- Development, synthetic holdout and representative API parity: `PASSED_LOCAL`
- Public representative repository (88 source/88 target tests): `PASSED_LOCAL_ENGINEERING`
- Independent public holdout (1 source/1 target test): `PASSED_LOCAL_ENGINEERING`
- Separate local Verifier with fresh extraction and offline Maven: `PASSED_LOCAL_ENGINEERING`
- Product one-click start without an attested Rootless Runner: `BLOCKED_EXPECTED` (`HTTP 409`)
- GitHub App private-repository execution: `NOT_RUN`
- Authorized customer repository: `NOT_RUN`
- Customer holdout workload: `NOT_RUN`
- Rootless Transformer, Verifier and Runner: `NOT_RUN`
- External independent review: `NOT_RUN`
