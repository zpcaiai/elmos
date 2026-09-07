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
The route installer content-addresses the Darwin arm64 standalone Kotlin
compiler tree at
`${ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT}/kotlin/2.2.20`; locked Node
dependencies are installed with lifecycle scripts disabled. Route PHP 8.5 is
accepted only at `/opt/homebrew/Cellar/php/8.5.9`, and the current exact
Flutter/Dart tuple only at `/opt/homebrew/share/flutter`. Those absolute roots,
Apple SDKs, and other host-bound prerequisites must already be present; PHP and
Flutter environment-variable path overrides are not accepted. The post-install
doctor remains `BLOCKED` when any such prerequisite or engine exact receipt is
unavailable.
If both `ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT` and the compatibility variable
`ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT` are supplied, they must name the same
normalized absolute root or installation and doctoring fail closed.

## Profiles

| Profile | Scope | Gate behavior |
| --- | --- | --- |
| `core` | Java 21/Maven, Python 3.14/uv, .NET 10, Node 26/pnpm | Required runtimes must match; container tooling is reported but remains profile-selected |
| `synthesis` | Java, Python, C#, TypeScript, Go, Kotlin, PHP, Rust, PostgreSQL | All eight exact emitter runtimes are required |
| `routes-macos` | 13 active identities: Java, Python, C#, TypeScript, Go, Rust, C++, Objective-C, Swift, PHP, Kotlin, React, Flutter | Darwin arm64 only; 14 exact runtime entries are required because Node and the TypeScript compiler are checked separately; all central probes and the route engine's 13-language exact receipt must pass; deprecated JavaScript is excluded |
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
| Kotlin | synthesis: plugin 2.2.20 on Java 21 and Gradle 8.14.3; Darwin arm64 routes: standalone compiler 2.2.20 under the governed shared root, with an exact compiler tree, compiler/stdlib JARs, build number, and JDK binding |
| PHP | synthesis: 8.4.12 with `pdo_pgsql`, `openssl`, `hash`, and `json`; Darwin arm64 routes: 8.5.9 NTS at `/opt/homebrew/Cellar/php/8.5.9`, with `tokenizer` and an independently bound install tree |
| Rust | rustc/Cargo 1.89.0 with Clippy and rustfmt |
| PostgreSQL | server/client 17.5 |
| Apple native | Xcode 26.6 build 17F113, macOS SDK 26.5, Apple Clang 21.0.0, Swift 6.3.3 |
| React | React/React DOM 19.2.7, `@types/react` 19.1.10, `@types/react-dom` 19.1.7, TypeScript 5.9.2, Node 26.0.0; exact package trees and real React/ReactDOM runtime imports are verified; the route analyzer accepts only its typed-pure-module subset and rejects JSX, hooks, effects, and lifecycle semantics |
| Flutter | Darwin arm64 exact tuple at `/opt/homebrew/share/flutter`: Flutter 3.44.1 revision 924134a44c with its bundled Dart 3.12.1; ambient or environment-selected Dart is not accepted. The read-only doctor invokes only bundled Dart; the exact receipt binds the Flutter launcher/version metadata and complete bundled Dart SDK tree without calling Flutter's mutable cache updater. The repository gate analyzes, compiles to a linked kernel, and executes dependency-free import-free pure-Dart modules. Flutter framework/UI, plugins, assets, platform builds, emulators and devices remain `UNSUPPORTED` / `NOT_RUN`. |

The generated environment fragment puts managed Go, Gradle, standalone Kotlin,
synthesis PHP 8.4.12, Rust, Maven, PostgreSQL, Node, and the selected JDK ahead
of ambient PATH entries. Route PHP is never injected into PATH because the
route engine consumes its exact absolute executable.
It never chooses one Python when a profile needs both 3.12 and 3.14; those
commands must use `uv --python` explicitly.

## Status and evidence boundary

- `READY` means every allowlisted version probe for that local runtime matched.
- `routes-macos READY` additionally means the route engine independently
  resolved all 13 exact toolchain identities, digests and auxiliaries, ran
  the bounded React/ReactDOM import probe, and verified the full bundled Dart
  SDK tree used by the Flutter pure-Dart repository build. Receipt schema 1.1
  binds the ordered active/deprecated language sets, every exact version and
  every complete serialized toolchain-record SHA-256 into one pinned contract
  digest; a self-consistent but different record is rejected. It does not mean
  any of the 156 directed routes executed.
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
