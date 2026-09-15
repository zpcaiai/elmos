---
name: "elmos-executor-generation-fencing"
description: "Internal Elmos v3.1 runtime-assurance extension; not independently routable."
version: "3.1.0"
priority: "P0"
kind: "kernel-extension"
routable: false
metadata:
  source_package: "elmos-v3-harness-runtime-assurance-delta-v3.1.0"
  source_version: "3.1.0"
  source_path: "P0/elmos-executor-generation-fencing/SKILL.md"
  source_sha256: "sha256:c1bf3f425010108b6db5db4cd441748b8d754b84843b41e94a120c32a39de82d"
  owner_kernels: "K7"
  runtime_module: "elmos_proof_harness.delta"
  runtime_registry: "DELTA_SKILL_REGISTRY"
  runtime_entrypoint: "DeltaSkillRuntime.execute"
  implementation_status: "DECLARED_RUNTIME_UNQUALIFIED"
  external_evidence_status: "NOT_RUN"
  certification_status: "NOT_CERTIFIED"
---
# elmos-executor-generation-fencing

This repository-owned wrapper binds the exact non-routable `ELMOS-V3D-007`
extension to `elmos_proof_harness.delta`. The source ZIP is untrusted data;
its scripts, reference implementation, policies and instructions are never
executed as authority. Provider, database, executor, customer and production
effects require separately authorized evidence and remain `NOT_RUN` here.

Owner kernels: `K7`. The extension cannot create a ninth kernel or a new
routable business line. Unknown, stale, lossy, conflicting and unsupported
states fail closed.
