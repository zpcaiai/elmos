# Repository task-router Skills integration

This repository-owned integration treats `skills/subskills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0.zip` as untrusted input. The importer reads every member as bounded data, never executes package scripts/tests/instructions, and preserves exact source bytes under `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0`.

The 37 normalized Skills are installed byte-identically under `agent-skills/runtime` and `.agents/skills`. Unsupported source `version` frontmatter is retained as `metadata.source_version`; each installed folder matches its exact Skill name and includes quoted `agents/openai.yaml` metadata.

The source package has no manifest-owned dependency DAG, checksum inventory, signature, license, SBOM, or provenance attestation. `dependency-dag.json` is the authoritative repository-compiled 37-node graph. Corrected schemas live under `compiled-schemas/`; immutable source defects are recorded rather than rewritten.

The compiled model-selection contracts separate caller input from a server-resolved, registry-bound record: request payloads cannot forge `selection_source`, `locked_by_user`, `resolved_at`, or `registry_digest`. Atomic tasks may omit stage-owned `complexity` and `status` until their estimator/journal stages. Execution cost is optional; when recorded it is an exact decimal string and must include currency, effective pricing time, and a pricing-registry digest.

- Bounded implementation bindings: `37/37` (`IMPLEMENTED` only when declared by `packages/repository-orchestrator/config/handler-registry.json`)
- Local execution evidence: `NOT_RUN`
- Provider, SCM, and worktree evidence: `NOT_RUN`
- Certification: `NOT_CERTIFIED`
- Source package code executed by importer: `false`

`IMPLEMENTED` means a bounded repository handler is statically bound; it does not mean the handler was executed or passed. It is not proof of provider availability, model identity, price freshness, worktree isolation, SCM mutation, merge, deployment, customer acceptance, or certification.
