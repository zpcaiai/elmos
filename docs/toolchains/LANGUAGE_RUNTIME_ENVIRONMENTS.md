# ELMOS language runtime environments

ELMOS uses task-scoped runtime profiles. There is intentionally no single
global language version: the repository needs Python 3.12.12 and 3.14.6,
Node 22/24/26 in different execution surfaces, Maven 3.9.10 and 3.9.11, and
JDK 8/11/17/21 for different routes. A command must select the profile it is
about to execute.

The typed catalog is `toolchains/runtime-manifest.json`; its schema is
`schemas/toolchains/runtime-manifest.schema.json`. The only executable probe
allowlist lives in `scripts/toolchains/runtime_environment.py`, so manifest
content cannot turn the doctor into a generic shell runner.

## Commands

```bash
# Validate manifest structure, exact language coverage, and Batch 66-95 bindings.
make toolchains-validate

# Read-only status for one profile; output is also written atomically below .elmos/.
make toolchains-doctor PROFILE=synthesis
make toolchains-doctor PROFILE=all

# Strict local gates for core, all eight synthesis targets, and the macOS route profile.
make toolchains-check

# Idempotently provision the safe automated subset, then rerun the profile doctor.
make toolchains-install PROFILE=synthesis

# Activate exact managed paths without changing global shell configuration.
source <(make -s toolchains-env PROFILE=synthesis)
```

`toolchains-install` is deliberately limited to `core`, `synthesis`,
`routes-macos`, and `all`. Broad profiles such as `language-packs` require an
exact selected language, vendor/platform version, license, authorization, and
target; the installer returns `NOT_RUN` instead of guessing. A new toolchain
root also requires at least 4 GiB free before provisioning begins.

## Profiles

| Profile | Scope | Gate behavior |
| --- | --- | --- |
| `core` | Java 21/Maven, Python 3.14/uv, .NET 10, Node 26/pnpm | Required runtimes must match; container tooling is reported but remains profile-selected |
| `synthesis` | Java, Python, C#, TypeScript, Go, Kotlin, PHP, Rust, PostgreSQL | All eight exact emitter runtimes are required |
| `routes-macos` | Java, Python, C#, TypeScript, Go, Rust, C++, Objective-C, Swift | Darwin arm64 only; Xcode, SDK, Clang, and Swift are exact host requirements |
| `b66-80` | Mainstream language and engineering-asset Skills | Catalog/observation profile; target-specific tools remain `NOT_RUN` until selected |
| `spring-legacy` | JDK 8/11/17/21 plus Maven 3.9.11 | Approved container/profile evidence is required; host PATH is not flattened |
| `frontend-native` | Flutter/Dart, Apple, Android, HarmonyOS | Device, simulator, signing, and vendor evidence remains separate |
| `language-packs` | COBOL through Lua/OpenResty, Batches 81-95 | Licensed/vendor/physical/remote runtimes are never auto-promoted |
| `all` | All active local runtimes plus every optional/external boundary | Active local requirements gate; optional gaps stay visible |

## Exact active versions

| Runtime | Exact profile version |
| --- | --- |
| Java / Maven | JDK 21.0.11; Maven 3.9.10 |
| Python | 3.14.6 for the Python engine; 3.12.12 for route/synthesis execution; uv 0.11.16 |
| C# | .NET SDK 10.0.301 |
| TypeScript | Node 26.0.0; pnpm 10.12.4; TypeScript 5.9.2 for routes |
| Go | 1.25.0 |
| Kotlin | plugin/compiler 2.2.20 on Java 21 and Gradle 8.14.3 |
| PHP | 8.4.12 with `pdo_pgsql`, `openssl`, `hash`, and `json` |
| Rust | rustc/Cargo 1.89.0 with Clippy and rustfmt |
| PostgreSQL | server/client 17.5 |
| Apple native | Xcode 26.6 build 17F113, macOS SDK 26.5, Apple Clang 21.0.0, Swift 6.3.3 |
| Flutter | Flutter 3.44.1 with its bundled Dart 3.12.1 |

The generated environment fragment puts managed Go, Gradle, PHP, Rust,
Maven, PostgreSQL, Node, and the selected JDK ahead of ambient PATH entries.
It never chooses one Python when a profile needs both 3.12 and 3.14; those
commands must use `uv --python` explicitly.

## Status and evidence boundary

- `READY` means every allowlisted version probe for that local runtime matched.
- `VERSION_MISMATCH` and `NOT_INSTALLED` block a required profile.
- `NOT_APPLICABLE` identifies a platform mismatch without pretending a pass.
- `NOT_RUN` is mandatory for profile-selected, container, provider, vendor,
  licensed, remote-system, or physical-device execution that has not occurred.
- `observed_available=true` is discovery only. For example, a Docker client,
  Erlang VM, Lua executable, or GnuCOBOL compiler does not prove the selected
  container daemon, BEAM cluster, OpenResty gateway, or mainframe semantics.

The maximum result of this tool is `TOOLCHAIN_READY`. It does not change
external evidence, customer acceptance, deployment, safety, independent
verification, or certification, which remain `NOT_RUN` / `NOT_CERTIFIED` until
their own exact gates execute.
