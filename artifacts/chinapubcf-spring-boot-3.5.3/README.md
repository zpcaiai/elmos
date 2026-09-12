# ChinaPub CF — Spring Boot 3.5.3 modernization

This is a repository-wide, behavior-oriented rewrite of
[`giftfuture/chinapubcf`](https://github.com/giftfuture/chinapubcf) at commit
`df038f57318d2bff1bc2041db718ac91316562ee`.

The source is not a Spring application. It is an Eclipse Dynamic Web Project
targeting Java 6, Tomcat 7, Servlet 2.5 and JSP, with manually vendored Axis 1.4,
Mahout 0.8 and JSON-lib dependencies. The modernization therefore follows the
directional route `Java EE Servlet/JSP -> Spring Boot 3.5.3`; it is not an
in-place Spring Boot upgrade.

## What is included

- Spring Boot 3.5.3 executable JAR on Java 21.
- Embedded Tomcat and Maven-managed dependencies; no checked-in binary JARs.
- JDBC repositories with prepared statements and transactions.
- H2/MySQL-mode local runtime plus an explicit MySQL 8 profile.
- Legacy URL compatibility for login, registration, books, ratings, logout and
  all four recommendation routes.
- User-based, item-based, Slope One and combined recommendation services.
- Session-bound authorization, BCrypt for new passwords, and one-time legacy
  MD5 verification followed by automatic BCrypt upgrade.
- Static browser UI replacing JSP and Prototype.js.
- The original 23-book catalog, 9 historical users and a reconciled 27-rating
  seed set. The source's 36 rating rows contain duplicate user/book records;
  migration uses latest `ratingId` wins.
- Eleven integration tests covering startup, health, UI, paging, authentication,
  injection resistance, authorization, atomic rating writes, algorithms,
  response formats and logout.

## Build and run

Requirements: JDK 21 and Maven 3.9.x.

```bash
export JAVA_HOME=/path/to/jdk-21
mvn -B --no-transfer-progress clean verify
java -jar target/chinapubcf-2.0.0-SNAPSHOT.jar
```

Open <http://localhost:8080/chinapubcf/>. The default runtime uses an ephemeral
H2 database initialized from `schema.sql` and `data.sql`.

## MySQL 8 runtime

Create an empty database, apply the schema and optional legacy seed, then start
with externally supplied credentials:

```bash
mysql --default-character-set=utf8mb4 "$DATABASE_NAME" < src/main/resources/db/mysql/schema.sql
mysql --default-character-set=utf8mb4 "$DATABASE_NAME" < src/main/resources/db/mysql/seed.sql
export CHINAPUBCF_DATABASE_URL='jdbc:mysql://127.0.0.1:3306/chinapubcf?useUnicode=true&characterEncoding=utf8&serverTimezone=UTC'
export CHINAPUBCF_DATABASE_USERNAME='chinapubcf'
export CHINAPUBCF_DATABASE_PASSWORD='replace-me'
java -jar target/chinapubcf-2.0.0-SNAPSHOT.jar --spring.profiles.active=mysql
```

Do not put credentials in source control. The MySQL profile deliberately does
not auto-apply DDL or seed data.

## Evidence and boundaries

- [Migration report](docs/MIGRATION_REPORT.md)
- [Source fingerprint](docs/source-fingerprint.json)
- [Framework contract](docs/framework-contract-model.json)
- [Every-file source map](docs/source-map.json)
- [Local execution evidence](docs/evidence.json)
- [Resolved dependency tree](docs/dependency-tree.txt)
- [Original 2014 SQL snapshot](docs/legacy-chinapubcf.sql)

The local build and browser exercise are self-attested engineering evidence.
The Java 6/Tomcat 7 source baseline, a real MySQL 8 instance, independent
holdout workloads, external verification, deployment and production
certification were not run. The source repository also exposes no license, so
distribution/production use requires separate rights review. Status is
therefore `NOT_CERTIFIED`.
