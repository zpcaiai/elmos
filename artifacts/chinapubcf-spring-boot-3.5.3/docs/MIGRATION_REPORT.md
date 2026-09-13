# Migration report

## Outcome

The target compiles, starts and passes its local integration suite as a Spring
Boot 3.5.3 application. The delivery is a one-repository implementation, not a
claim that ELMOS now supports every Servlet/JSP-to-Spring-Boot route.

## Source fingerprint

The source revision contains 145 files and 42 Java source files. It has Eclipse
WTP metadata, compiled `.class` files, JSP/static assets, Servlet 2.5
configuration and vendored JARs, but no Maven, Gradle or Ant build definition.
Runtime assumptions are Java 6, Tomcat 7 and JNDI `jdbc/chinapubcf`; the code
also contains a hard-coded MySQL root/no-password fallback. `web.xml` maps Axis
to `*.jws`, but no JWS implementation exists.

No license is present in the source repository. This delivery is an engineering
artifact; redistribution and production use require separate rights review.

The checked-in SQL snapshot is a MySQL 5.1-era export with 23 books, 9 users and
36 ratings. It contains plaintext and MD5 credentials, floating-point money,
nullable relationships and duplicate user/book ratings.

## Target architecture

- `LegacyApiController` preserves the active servlet URL surface.
- `AccountService`, `RatingService` and `RecommendationService` own business
  behavior and transactions.
- JDBC repositories replace static table gateways and global connection state.
- `schema.sql` and `data.sql` provide a disposable H2/MySQL-mode local runtime.
- `db/mysql/schema.sql` and `db/mysql/seed.sql` provide explicit MySQL 8 setup.
- Static HTML/CSS/JavaScript replaces JSP and Prototype.js.

## Intentional safety corrections

- SQL concatenation became bound parameters.
- Authentication no longer returns or stores password material in the HTTP
  session or JSON payloads.
- New credentials use BCrypt cost 12. Historical MD5 values are only accepted
  for a one-time compatibility login and are upgraded immediately.
- Rating writes require an authenticated matching session user, validate the
  entire batch first and commit atomically.
- Money uses exact decimal columns and ratings are range constrained.
- Duplicate historical ratings use deterministic latest-`ratingId` wins.
- Errors return bounded problem details instead of being swallowed.

## Compatibility decisions

| Source surface | Target decision |
|---|---|
| Servlet endpoints | Preserved through GET/POST aliases |
| JSP entry pages | Redirected to static HTML |
| JNDI DataSource | Replaced by Spring Boot datasource configuration |
| MySQL root fallback | Removed; external credentials required |
| Mahout 0.8 | Replaced by repository-owned typed algorithms |
| Axis `*.jws` mapping | Retired because no service implementation exists |
| Compiled classes and vendored JARs | Retired; sources and Maven coordinates are authoritative |
| Historical data | Catalog/users retained; duplicate ratings reconciled |

## Evidence classification

`LOCAL_EXECUTED_SELF_ATTESTED`: Java 21/Maven build, eleven integration tests,
executable JAR startup, health/API calls and an in-app browser journey.

`NOT_RUN`: reproducible Java 6/Tomcat 7 source baseline, real MySQL 8 execution,
independent holdout corpus, performance/load, DAST, external verifier,
deployment and rollback.

`NOT_CERTIFIED`: the exact source family is outside the current reusable ELMOS
Spring source-route catalog, and the required independent/native evidence is
absent. Local green checks do not override that boundary.
