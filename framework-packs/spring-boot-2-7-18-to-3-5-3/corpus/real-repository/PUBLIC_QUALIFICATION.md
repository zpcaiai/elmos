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

An explicit `--local-engineering-non-certifying` path is implemented in the
separate `replay_spring_public_repository_local.py` module. It is an operator
opt-in to execute the fixed public source on the current host after exact
archive, source-file, toolchain, service-image RepoDigest, and platform checks.
Its receipt is always `LOCAL_NON_CERTIFYING`, records whether the daemon is
actually Rootless, and fixes customer, independent, external, and certification
claims to false/`NOT_RUN`/`NOT_CERTIFIED`. It cannot update this protected gate.

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
  is recorded by an explicit local engineering replay. The default protected
  qualification path never runs a CMake project command.
- There are 22 declared tests: two JUnit Jupiter tests and twenty JUnit4
  integration tests. The POM does not declare `junit-vintage-engine`, so Maven's
  default JUnit Platform run discovers only the two Jupiter tests. The harness
  creates a separate, digest-recorded `qualification-pom.xml` adding only the
  Boot-managed Vintage 5.8.2 test engine; no test source is edited.
- The integration base names Testcontainers PostgreSQL `13-alpine` and Redis
  `6-alpine`. Those mutable tags are retained only as source provenance. They
  are never accepted as identity evidence. The protected audit recognizes only
  each content-addressed `execution_reference`; actual Rootless execution still
  requires digest-only injection and runtime receipt verification. The local
  non-certifying path may temporarily bind those unavoidable source names to the
  exact audited local image ID, verifies the binding before and after the tests,
  and never promotes that alias into protected evidence.
- Testcontainers 1.21.3 also names its Ryuk 0.12.0 resource reaper. Its tag is
  provenance only; the audit recognizes the exact linux/arm64 digest reference.
  No container is started by the default protected path. The explicit local
  path supplies Ryuk by digest and re-audits all service bindings after use.
- The JUnit Jupiter `@SpringBootTest` classes also require a PostgreSQL
  datasource. Their Testcontainers JDBC source and repository-owned
  `sql/schema.sql` are audited but not executed. A future protected runner must
  inject the resolved digest without replacing persistence with an in-memory
  database.
- The retained protected-runner Maven design uses `--strict-checksums`, an empty
  run-owned user home, and a run-owned `maven.repo.local` below the disposable
  workspace. The default protected path runs only the exact Maven executable's
  version identity audit outside the untrusted source tree. The explicit local
  mode uses the same isolation for its non-certifying lifecycle replay.

An earlier exploratory native build resolved JNI through Homebrew's default
OpenJDK rather than the declared JDK 17 and is therefore superseded and
ineligible as exact-tuple evidence. Under the protected execution boundary, all
22 source tests, native build, transformation, and target runtime remain
`NOT_RUN_ROOTLESS_ATTESTED_RUNNER_REQUIRED`, independently of capacity or
locally cached prerequisites. Any explicit local replay result is reported in a
separate `LOCAL_NON_CERTIFYING` receipt.

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

Without the explicit local flag, the command does not run Maven/CMake project
work, tests, transformation, or containers. Exit code `2` with
`NOT_RUN_ROOTLESS_ATTESTED_RUNNER_REQUIRED` means the static/prerequisite audit
completed and protected execution remains unavailable. It is not a tooling
crash and must not be converted to success.

## Explicit local engineering replay

After all three exact `linux/arm64` service images have been pulled separately,
the same command may add:

```bash
  --local-engineering-non-certifying
```

This mode enforces a 12 GiB start threshold and an 8 GiB hard stop, builds the
JNI library against the declared JDK, and runs the Vintage overlay only if test
source hashes remain unchanged. PostgreSQL and Redis source-tag aliases are
created only when they bind the already-audited exact image identity and only
aliases created by this replay are removed afterward. Target transformation and
tests start only after the source reports exactly 22 tests with zero failures,
errors, or skips. Even when source and target both pass the same complete test
oracle, the protected Rootless, customer, independent, external, global
success-rate, and certification states remain unchanged.

## Fixed Linux source-baseline replay

The repository workflow uses `ubuntu-latest`, declares no Arm runner, and its
Docker build has no platform override. The separate engineering baseline
therefore selects `linux/amd64`; it does not inherit the Apple Silicon host
architecture merely because that is convenient. The upstream Maven job runs
with `-DskipTests`, while its native matrix only configures and builds the JNI
library, so an upstream green run is build context rather than evidence that the
22-test oracle passed.

`scripts/operations/replay_retro_game_linux_baseline.py` re-extracts the exact
archive, applies only the Vintage discovery overlay, copies and hashes a
run-owned offline Maven repository, and rebuilds `libBattleEngine.so` inside a
`linux/amd64` runner. Its Maven 3.9.11/JDK 17 base is selected by platform
manifest digest. The derived image is then executed only by its image ID. Since
the Dockerfile installs `build-essential` and CMake from apt without snapshot
version pins, the receipt does not call the Dockerfile inputs fully locked. It
instead records the derived image ID plus the resolved path, byte count,
SHA-256, and version output of Java, `javac`, Maven, CMake, C++, and Make, and
the installed dpkg versions and architectures.

Before untrusted Maven execution, the replay pulls the three exact
`linux/arm64` service images into a temporary nested daemon, moves that daemon
from a staging network to a Docker `Internal=true` network, removes the staging
network, and verifies an external-egress negative probe. The amd64 test runner
is emulated on an arm64 Docker host and talks only to that disposable daemon.
This nested setup is an engineering containment boundary, not the repository's
missing protected Runner: the receipt always keeps `rootless=false`,
`rootless_attested=false`, `independent_verification=false`, and
`certification_status=NOT_CERTIFIED`, even if the nested daemon reports a
rootless security option.

On Docker Desktop, starting that nested daemon requires a privileged outer
container. The ordinary local-engineering opt-in is not authorization for that
operation. Unless the user separately and explicitly authorizes privileged
runtime, the replay stops before the first Docker operation with
`BLOCKED_PRIVILEGED_RUNNER_AUTHORIZATION_REQUIRED`. Only an explicitly
authorized invocation may add `--authorize-privileged-nested-daemon`; the flag
must never be inferred or added merely to make the replay pass.

Use an empty workspace and a Maven repository populated by the preceding exact
local replay:

```bash
python3 scripts/operations/replay_retro_game_linux_baseline.py \
  --repository-id retro-game \
  --archive /path/to/verified-retro-game.tar.gz \
  --workspace /tmp/empty-retro-linux-baseline \
  --output /tmp/retro-game-linux-baseline.json \
  --maven-repository /path/to/run-owned-maven-repository \
  --local-engineering-non-certifying
```

The example intentionally omits privileged authorization and therefore records
the fail-closed blocked state after binding the source and offline dependency
inputs, without pulling, building, or starting Docker resources.

The Linux source gate requires exactly 22 discovered tests, zero failures,
zero errors, zero skips, unchanged test and source-owned files, the exact JNI
cache binding, unchanged offline dependencies, and digest-matched PostgreSQL,
Redis, and Ryuk images. Target work remains blocked unless this gate is green.

### 2026-08-11 observed boundary

The local Docker Desktop daemon retained and re-inspected the exact
`linux/arm64` PostgreSQL, Redis, and Ryuk images. Its context was
`desktop-linux`, endpoint `unix:///Users/stephen/.docker/run/docker.sock`, and
security options were only the built-in seccomp profile and cgroup namespace;
no rootless security option, Podman, RootlessKit, or rootless dockerd command
was available. It is therefore an ordinary local daemon, not the protected
Rootless Runner.

The first Linux runner build attempt failed before runtime because the Ubuntu
HTTP `noble/universe` index could not be downloaded. The Dockerfile was changed
to HTTPS with bounded retries, and the second build passed the failed index
download, but was deliberately canceled before it could reach the unauthorized
privileged nested-daemon operation. The final fail-closed replay performed no
Docker operation and records
`BLOCKED_PRIVILEGED_RUNNER_AUTHORIZATION_REQUIRED` in
`retro-game-linux-amd64-local-non-certifying-20260811.json`. The two historical
attempt receipts remain separate as
`retro-game-linux-amd64-local-non-certifying-build-attempt1-20260811.json` and
`retro-game-linux-amd64-local-non-certifying-security-stop-attempt2-20260811.json`.
No Linux test result was produced, so source remains not green and target
remains `NOT_RUN_SOURCE_ALL_22_TESTS_GREEN_REQUIRED`.
