# Replayable public-repository qualification

This corpus is local public engineering evidence. It is neither customer
evidence nor organizationally independent verification.

## Fail-closed rule

`scripts/operations/qualify_spring_public_repository.py` verifies a fixed
archive, exact source tuple, required-file digests, the complete test inventory,
toolchains, and digest-pinned service-image prerequisites. It is currently a
static/prerequisite audit only. Untrusted Maven lifecycles, CMake configure or
build, source tests, OpenRewrite transformation, target builds, and target tests
are hard-disabled on an ordinary host and in non-attested Docker. They return
`NOT_RUN_ROOTLESS_ATTESTED_RUNNER_REQUIRED`.

There is no protected rootless-runner receipt verifier in this repository. The
harness therefore has no receipt or attestation CLI input and never accepts a
caller-supplied JSON claim as authorization. Enabling execution requires a
protected-control-plane verifier binding a content-addressed runner image,
sandbox policy, nonzero effective UID/rootless runtime, digest-only service
images, separate executor/verifier identities, freshness, and revocation. Until
that implementation exists, execution remains unconditionally disabled.

The Darwin/arm64 replay profile pins the executable bytes and exact first
version line for Java, `javac`, Maven, CMake, Apple Clang, and Make. Relocating
an identical executable is allowed; a wrapper, symlink target, upgraded binary,
different vendor build, version substring match, or missing digest is not. The
evidence records each requested path, resolved path, byte count, SHA-256,
version command, and exact-match decision. It resolves and hashes the executable
again after the version command; realpath, digest, or byte-count drift fails the
audit. This is local toolchain engineering evidence, not rootless attestation or
permission to execute repository content.

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
  future build path. The retained protected-runner design passes the declared
  JDK's `JAVA_HOME`, JNI headers,
  platform-specific `jni_md.h` directory, Java and `javac` executables, JVM
  library, and AWT library explicitly to CMake. It also pins the C++ compiler
  and Make executable. The build is rejected unless all required cache entries
  match and every additional absolute Java/JNI/JVM/JDK/AWT cache path resolves
  inside that exact JDK home. The parsed `CMakeCache.txt` byte count and SHA-256
  would be recorded with the decision. No CMake project command runs today.
- There are 22 declared tests: two JUnit Jupiter tests and twenty JUnit4
  integration tests. The POM does not declare `junit-vintage-engine`, so Maven's
  default JUnit Platform run discovers only the two Jupiter tests. The harness
  creates a separate, digest-recorded `qualification-pom.xml` adding only the
  Boot-managed Vintage 5.8.2 test engine; no test source is edited.
- The integration base names Testcontainers PostgreSQL `13-alpine` and Redis
  `6-alpine`. Those mutable tags are retained only as source provenance. They
  are never execution objects and are not inspected for equality. The audit
  recognizes only each content-addressed `execution_reference`. Actual rootless
  execution also requires digest-only injection and runtime receipt verification,
  which is not implemented; tag-bearing Testcontainers properties are not run.
- Testcontainers 1.21.3 also names its Ryuk 0.12.0 resource reaper. Its tag is
  provenance only; the audit recognizes the exact linux/arm64 digest reference.
  No container is started by this harness.
- The JUnit Jupiter `@SpringBootTest` classes also require a PostgreSQL
  datasource. Their Testcontainers JDBC source and repository-owned
  `sql/schema.sql` are audited but not executed. A future protected runner must
  inject the resolved digest without replacing persistence with an in-memory
  database.
- The retained protected-runner Maven design uses `--strict-checksums`, an empty
  run-owned user home, and a run-owned `maven.repo.local` below the disposable
  workspace. No Maven project lifecycle runs today; only the exact Maven
  executable's version identity is audited outside the untrusted source tree.

An earlier exploratory native build resolved JNI through Homebrew's default
OpenJDK rather than the declared JDK 17 and is therefore superseded and
ineligible as exact-tuple evidence. The corrected exact-JDK native step has not
been rerun. Under the current hard execution boundary, all 22 source tests,
native build, transformation, and target runtime remain
`NOT_RUN_ROOTLESS_ATTESTED_RUNNER_REQUIRED`, independently of capacity or
locally cached prerequisites.

## Separate public candidate

[`scc-digitalhub/AAC@f946102`](https://github.com/scc-digitalhub/AAC/tree/f946102986af5e6324b881b68486648563e89e99)
is recorded as a separate exact-tuple candidate: Spring Boot 2.7.18, Java 17,
1,244 main Java files, and 39 test Java files, with security, OAuth2/OIDC,
SAML, JPA, mail, validation, and Actuator scope. Only its fixed Git tree and POM
were audited in this run. Source and target execution remain `NOT_RUN`; it is
not counted as a migration success.

## Static/prerequisite audit

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
  --maven-executable /path/to/apache-maven-3.9.11/bin/mvn \
  --cmake-executable /opt/homebrew/Cellar/cmake/4.4.0/bin/cmake \
  --cxx-executable /usr/bin/c++ \
  --make-executable /usr/bin/make
```

Each supplied executable must match the corresponding
SHA-256 and exact version line in `public-qualification-manifest.json`. The
Maven path must be the Apache 3.9.11 distribution launcher itself, not the
currently installed Homebrew Maven 3.9.10 wrapper.

The command does not run Maven/CMake project work, tests, transformation, or
containers. Exit code `2` with
`NOT_RUN_ROOTLESS_ATTESTED_RUNNER_REQUIRED` means the static/prerequisite audit
completed and protected execution remains unavailable. It is not a tooling
crash and must not be converted to success.
