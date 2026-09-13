# Four Business-Line Verification Adapters

Adapters define how to execute, observe, and parse facts. They never decide final PASS.

## 1. Spring Legacy Modernization → Spring Boot 4

Verify behavioral equivalence for:

- routes and HTTP methods/status/headers;
- request binding and validation;
- session/cookie behavior;
- filters/interceptors;
- exception mapping;
- transaction boundaries/rollback;
- authentication/authorization;
- JSP/view/template semantics;
- i18n;
- upload/download;
- pagination;
- Tiles/FreeMarker/JSTL/Sitemesh compatibility where applicable;
- Quartz;
- Shiro/Spring Security;
- `web.xml` migration behavior.

Prefer differential source-vs-target scenario replay and hidden compatibility cases.

## 2. Repository-Level Language Conversion

Verify source runtime vs target runtime:

- API/contract equivalence;
- serialization/deserialization;
- state transitions;
- error/exception behavior;
- concurrency/order/idempotency;
- database/storage behavior;
- network protocol behavior;
- representative end-to-end scenarios;
- performance envelope where required.

## 3. Multi-Language Project Generation

Verify:

- deterministic buildability;
- dependency integrity;
- startup/health checks;
- configuration correctness;
- API/schema behavior;
- database migration;
- smoke/functional/E2E tests;
- security baseline;
- generated test usefulness via mutation testing.

## 4. SQL Dialect / Routine Conversion

Verify source DB vs target DB with controlled datasets:

- syntax/parse validity;
- schema equivalence;
- procedures/functions/triggers;
- transaction behavior;
- query-result equivalence;
- NULL semantics;
- date/time/timezone behavior;
- collation/string behavior;
- numeric precision;
- locking/concurrency where relevant;
- performance envelope.

Do not accept successful parsing alone as semantic SQL equivalence.
