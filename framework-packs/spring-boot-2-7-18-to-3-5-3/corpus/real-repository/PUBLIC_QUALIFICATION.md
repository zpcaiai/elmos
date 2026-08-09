# Replayable public-repository qualification

This corpus is local public engineering evidence. It is neither customer
evidence nor organizationally independent verification.

## Fail-closed rule

`scripts/operations/qualify_spring_public_repository.py` verifies a fixed
archive, exact source tuple, required-file digests, the complete test inventory,
toolchains, native artifact, and digest-pinned service images. It may execute a
target only after every declared source test is discovered and passes without
failures, errors, or skips. The target executor applies the pack's exact
OpenRewrite recipe with Java 21 and Maven 3.9.11, rebuilds the native library,
and requires the same complete test-case oracle before it may report a local
target pass.

The runner refuses unsafe tar members, floating commits, archive drift, an
occupied or overly broad workspace, and execution below the 10 GiB free-space
stop line. Network fetches use bounded connection and total timeouts. It never
pulls service images implicitly.

## `retro-game` prerequisite audit

The fixed source is
[`retro-game@3d08c4b`](https://github.com/retro-game/retro-game/tree/3d08c4b2ca814acfd873fc7874f724089e5b1d85),
whose root POM is exactly Spring Boot 2.7.18 and Java 17.

- Its repository CI runs `mvn -DskipTests package`; that is not a source test
  baseline.
- The native differential test constructs `NativeBattleEngineStrategy`, which
  loads `BattleEngine`. The repository's CMake project is the authoritative
  build path. The harness passes the declared JDK's `JAVA_HOME`, JNI headers,
  JVM library, and AWT library explicitly to CMake, then rejects the build
  unless every corresponding `CMakeCache.txt` entry resolves inside that exact
  JDK home.
- There are 22 declared tests: two JUnit Jupiter tests and twenty JUnit4
  integration tests. The POM does not declare `junit-vintage-engine`, so Maven's
  default JUnit Platform run discovers only the two Jupiter tests. The harness
  creates a separate, digest-recorded `qualification-pom.xml` adding only the
  Boot-managed Vintage 5.8.2 test engine; no test source is edited.
- The integration base uses Testcontainers PostgreSQL `13-alpine` and Redis
  `6-alpine`. Those source references are mutable. The manifest records the
  exact linux/arm64 digests resolved on 2026-08-09. The content-addressed pull
  references use `mirror.gcr.io/library`; their platform digests are identical
  to the Docker Hub index entries. The harness proceeds only when each source
  tag is locally bound to that exact image. It does not substitute the
  already-installed PostgreSQL 17 or Redis 7 images.
- Testcontainers 1.21.3 also starts its Ryuk 0.12.0 resource reaper. The
  harness binds that exact linux/arm64 image as a prerequisite so container
  cleanup is not disabled or silently replaced to make the test baseline run.
- The JUnit Jupiter `@SpringBootTest` classes also require a PostgreSQL
  datasource. The replay command binds them to the same Testcontainers JDBC
  source and repository-owned `sql/schema.sql`; it does not replace persistence
  with an in-memory database.

An earlier exploratory native build resolved JNI through Homebrew's default
OpenJDK rather than the declared JDK 17 and is therefore superseded and
ineligible as exact-tuple evidence. The corrected exact-JDK native step has not
been rerun because the two pinned service images remain absent and the 10 GiB
capacity stop line is not met. Therefore all 22 source tests remain
`NOT_RUN_PREREQUISITES`, and target transformation/runtime correctly remains
`NOT_RUN_SOURCE_NOT_GREEN`.

## Separate public candidate

[`scc-digitalhub/AAC@f946102`](https://github.com/scc-digitalhub/AAC/tree/f946102986af5e6324b881b68486648563e89e99)
is recorded as a separate exact-tuple candidate: Spring Boot 2.7.18, Java 17,
1,244 main Java files, and 39 test Java files, with security, OAuth2/OIDC,
SAML, JPA, mail, validation, and Actuator scope. Only its fixed Git tree and POM
were audited in this run. Source and target execution remain `NOT_RUN`; it is
not counted as a migration success.

## Replay

Use an empty disposable workspace and the fixed archive recorded in
`public-qualification-manifest.json`:

```bash
python3 scripts/operations/qualify_spring_public_repository.py \
  --repository-id retro-game \
  --archive /path/to/verified-retro-game.tar.gz \
  --workspace /tmp/empty-retro-qualification \
  --output /tmp/retro-game-qualification.json \
  --java-home /Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home \
  --target-java-home /opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home \
  --maven-executable /path/to/apache-maven-3.9.11/bin/mvn
```

An exit code of `2` means the audit completed but source prerequisites or tests
did not pass. It is not a tooling crash and must not be converted to success.
