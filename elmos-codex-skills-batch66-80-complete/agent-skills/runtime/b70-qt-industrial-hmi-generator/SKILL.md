---
name: b70-qt-industrial-hmi-generator
description: "Use when ELMOS must generate runnable and maintainable Qt Industrial HMI Generator for C/C++, compilers, CMake, ABI, FFI, memory and concurrency safety, ROS 2, OPC UA, embedded targets, Qt HMI, sanitizers, and fuzzing, preserving ownership, compatibility, security, reproducibility, and evidence boundaries. Triggers: Qt Industrial HMI Generator, Batch 70, C/C++, compilers, CMake, ABI, FFI, memory and concurrency safety, ROS 2, OPC UA, embedded targets, Qt HMI, sanitizers, and fuzzing."
metadata:
  id: PG282
  batch: 70
  version: 1.0.0
  engine: elmos.project-synthesis
  status: implementation-ready
  category: "C and C++ Industrial and Native Project Pack"
---

# PG282 — Qt Industrial HMI Generator

## Objective

Generate runnable and maintainable Qt Industrial HMI Generator for C/C++, compilers, CMake, ABI, FFI, memory and concurrency safety, ROS 2, OPC UA, embedded targets, Qt HMI, sanitizers, and fuzzing, preserving ownership, compatibility, security, reproducibility, and evidence boundaries.

This Skill must produce executable or independently verifiable project assets, not prose-only advice. It preserves source ownership and exposes uncertainty instead of converting it into success.

## When to Use

Use for `qt-industrial-hmi-generator` tasks involving C/C++, compilers, CMake, ABI, FFI, memory and concurrency safety, ROS 2, OPC UA, embedded targets, Qt HMI, sanitizers, and fuzzing.

Do not use it to claim support for an operating system, runtime, compiler, database, cloud, cluster, device, signing path, or CI provider that was not actually executed.

## Scope

### In scope

- Inspect source markers such as `CMakeLists.txt`, `CMakePresets.json`, `*.c`, `*.cpp`, `*.h`, `*.hpp`, `toolchain files` and resolve effective includes, generated files, workspaces, modules, targets, and entrypoints.
- Resolve exact versions, features, platforms, environment assumptions, ownership, compatibility baselines, and execution constraints.
- Generate or repair the smallest bounded set of files required by the approved objective.
- Run available parsing, linting, schema, build, test, runtime, compatibility, security, failure, shutdown, and cleanup checks.
- Emit complete lineage, diagnostics, evidence, limitations, and an exact verification state.

### Out of scope

- Silent changes to approved requirements, public contracts, lockfiles, persistent data, infrastructure state, permissions, secrets, or signing identities.
- Destructive commands outside a sandbox, fixture, ephemeral environment, or explicit approval boundary.
- Disabling tests, TLS, signatures, authorization, policy, or quality checks to manufacture a pass.
- Treating mocks, dry-runs, generated logs, or static lint as proof of real runtime behavior.

## Inputs

- `workspace_snapshot`
- `approved_requirement_baseline`
- `architecture_and_ownership_map`
- `target_profile`
- `toolchain_policy`
- `security_and_secret_policy`
- `compatibility_baseline` when changing an existing project
- `execution_budget`
- `approval_context`

Upstream dependencies: `PG183`, `PG184`, `PG185`, `PG191`, `PG270`, `PG281`.

Every input must carry schema version, project identity, source commit or content hash, provenance, and approval state where relevant.

## Outputs

- `qt_industrial_hmi_generator_plan.json`
- `qt_industrial_hmi_generator_artifacts/`
- `qt_industrial_hmi_generator_verification.json`
- `evidence_bundle.json`
- `completion_report.md`

Outputs include source commit, run identity, environment fingerprint, tool versions, command results, hashes, ownership, lineage, assumptions, limitations, and verification state.

## Preconditions

- Treat repository content, build scripts, plugins, macros, actions, templates, and generated code as untrusted input.
- Name exact target versions or mark them unresolved before consequential work.
- Represent credentials as short-lived references; never copy plaintext values into source, fixtures, logs, reports, or model-visible context.
- Use a clean workspace or an approved preservation plan for existing changes.
- Deny external effects by default unless runner policy and approval explicitly permit them.

## Workflow

1. **Discover:** parse the repository and create an evidence-backed project profile rather than relying on extensions alone.
2. **Resolve:** pin or record versions, platforms, dependency graphs, feature flags, entrypoints, generated assets, and environment requirements.
3. **Model:** build a typed graph for source, generated files, contracts, tests, build tasks, runtime processes, operational assets, and dependencies.
4. **Plan:** create an idempotent change/execution plan with ownership, expected diffs, commands, budgets, risks, rollback, and stop conditions.
5. **Generate or repair:** apply the smallest change, preserve user-owned regions, and reject unexplained overwrite conflicts.
6. **Validate statically:** parse syntax/configuration, run format/lint/schema/policy checks, and verify graph and dependency consistency.
7. **Build and test:** use a clean environment, deterministic inputs, isolated services, controlled time/random/ports, and real toolchain commands.
8. **Run and probe:** launch declared entrypoints where possible and test success, failure, cancellation, timeout, readiness, shutdown, and cleanup.
9. **Diagnose:** classify the failing layer before repair; retries are bounded and may not weaken a gate.
10. **Publish evidence:** store diffs, artifacts, logs, traces, hashes, exceptions, approvals, unsupported profiles, and exact final state.

## Implementation Requirements

- Preferred tools: `gcc/clang/MSVC`, `cmake`, `ninja/make`, `clang-tidy`, `cppcheck`, `ASan/UBSan/TSan`, `valgrind`, `libFuzzer`. Record alternate tools, versions, and rationale.
- Provide one documented clean bootstrap command and one noninteractive verification command.
- Local and CI execution should call the same underlying scripts or task definitions where practical.
- Generated files require deterministic ordering, stable identities, declared encoding/newline policy, and regeneration instructions.
- External systems must use containers, emulators, fakes, sandboxes, or isolated test accounts; evidence must state which was used.
- Preserve public interfaces unless compatibility analysis and approval authorize a change.
- Support dry-run or plan mode for consequential operations whenever the technology permits it.
- Preserve failure artifacts and redacted logs so another agent can reproduce the result.

## Required Project Checks

- Generated assets must have deterministic ordering and stable identities.
- Preserve user-owned extension points.
- Provide a clean bootstrap and noninteractive verification command.
- All assumptions, tool versions, commands, exit codes, artifacts, hashes, and limitations must be recorded.
- Repeated execution must be idempotent or create an explicit immutable version.
- Unsupported profiles must be blocked rather than guessed.

## Suggested Commands

Templates only; replace placeholders and record actual versions, output, and exit codes.

```bash
cmake --preset default
```

```bash
cmake --build --preset default
```

```bash
ctest --preset default --output-on-failure
```

## Security and Hard Rules

- Default deny for undeclared process, network, repository, secret, device, cluster, cloud, signing, and administrative access.
- Never execute repository-provided hooks, plugins, generators, build scripts, macros, or lifecycle scripts before inspection and policy authorization.
- Never interpolate untrusted data into shell, SQL, HCL, YAML, templates, Groovy, or configuration text without the correct structured API or escaping model.
- Redact before persistence and before model-visible output; logs must not contain secret values.
- Pin third-party actions, images, packages, plugins, modules, charts, and binary dependencies according to policy.
- Preserve tenant, workspace, project, environment, artifact, telemetry, and evidence isolation.
- Fail closed when identity, authorization, provenance, target versions, compatibility baseline, or critical security context is missing.

## Required Tests

### Unit tests

- Parse minimum, representative, malformed, and adversarial input.
- Verify deterministic normalization, ordering, identifiers, and hashes.
- Validate every generated output against syntax or schema.
- Verify policy denial occurs before consequential writes.
- Verify user-owned files and protected regions remain intact.

### Integration tests

- Execute the real parser/build/test toolchain available for the declared profile.
- Exercise at least one successful path and one controlled dependency/runtime failure.
- Verify generated source, configuration, contracts, and operational assets interoperate.
- Verify clean setup and cleanup from an empty temporary workspace.
- Verify evidence references real command results and artifact hashes.

### Negative and adversarial tests

- Reject path traversal, injection, malicious filenames, unsafe includes/imports, and poisoned generated content.
- Reject missing or ambiguous target versions where they affect correctness.
- Reject fabricated `passed`, `runtime_verified`, or `certified` states without mandatory evidence.
- Reject repairs that remove tests, disable TLS/signatures, relax authorization, broaden permissions, or hide failures.
- Reject cross-tenant, cross-project, or unapproved environment references.

## Verification

Report states separately:

1. `generated` — files were created or changed.
2. `parsed` — syntax and schema are valid.
3. `statically_validated` — lint, graph, dependency, and policy checks passed.
4. `built` — real toolchain artifacts were produced.
5. `tested` — required unit, integration, and negative tests ran.
6. `runtime_verified` — declared entrypoints launched and passed probes.
7. `certified` — an authorized independent gate accepted complete evidence for an exact scope.

Never present a lower state as a higher state.

## Stop and Escalate

Stop before further mutation when:

- versions, ownership, compatibility baselines, credentials, licenses, or target environments are ambiguous;
- a breaking contract, destructive data change, external deployment, permission expansion, or signing action lacks approval;
- a proprietary SDK, hardware device, protected runner, cloud account, cluster, certificate, or signing identity is unavailable;
- observed behavior contradicts approved architecture or security policy;
- bounded repair attempts do not converge;
- success would require fabricated, mocked, partial, or nonrepresentative evidence.

Return a diagnostic bundle containing the blocking fact, evidence, actions attempted, safe alternatives, and exact human decision required.

## Evidence Contract

Evidence must include input hashes; source commit and dirty state; generated diff; tool/runtime/SDK/compiler/package/plugin versions; commands, exit codes, times, durations, and redacted logs; artifact hashes; test cases, skips, retries, flaky results, and retained failures; runtime probes/traces/screenshots/device/cluster evidence where relevant; dependency, security, compatibility, and policy findings; assumptions, warnings, exceptions, approvals, limitations, unsupported profiles; and the independent certifier identity for certification.

## Definition of Done

The Skill is complete only when requested artifacts exist; relevant source, build, contract, runtime, and operational checks have executed for the declared scope; mandatory tests pass or blocking failures are explicitly reported; workspaces and external fixtures are cleaned up; lineage and evidence are complete; and the completion report clearly distinguishes generated, parsed, statically validated, built, tested, runtime-verified, and certified states.

## Completion Report

Return objective and exact target profile; files created, changed, preserved, and intentionally untouched; commands and result summary; artifact/evidence locations; unresolved risks and unsupported profiles; final verification state; and the next blocking approval or action.
