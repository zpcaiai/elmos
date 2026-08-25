# Project Intelligence Skills Integration

This directory records the safe repository integration of `elmos-project-intelligence-skills` version `1.1.0`.

- Pinned source ZIP: `skills/subskills/elmos-project-intelligence-skills-v1.1.0.zip` (`sha256:e137d87f87a2ea3e2790bee508e882795f9496fa3d9625648428ca80a5a3923c`)
- Immutable extracted source: `skills/elmos-project-intelligence-skills-v1.1.0/`
- Installed Skill interfaces: `50` exact names under both `agent-skills/runtime/` and `.agents/skills/`
- Package identity: `PINNED_VALIDATED`
- Skill interface state: `INSTALLED`
- Exact runtime bindings: `50` repository-owned allowlisted handlers
- Capability states: `21 LOCAL`, `24 PARTIAL`, `5 PLAN`
- Local qualification: `LOCAL_EXECUTED_SELF_ATTESTED` (`engines/project-intelligence-engine/qualification/local-qualification.json`, `sha256:8896378afd7f04895d6525a58b2349dbf2341bccf56d88beadffaebb19427991`)
- Qualification dispatch guard: `PYTHON_AUDIT_DENY_FILESYSTEM_PROCESS_NETWORK_DURING_DISPATCH`
- External / independent evidence: `NOT_RUN` / `NOT_RUN`
- Certification: `NOT_CERTIFIED`

The importer treats every archive document and script as untrusted input. It does not execute the package installer, validator, tests, shell scripts, PowerShell, packager, `AGENTS.md`, or `CLAUDE.md`. It independently verifies the ZIP and all 335 internal checksums, extracts the source byte-for-byte, validates the 50-Skill DAG, resolves every profile transitively, validates all 500 tasks, 248 acceptance scenarios, traceability, Schemas, examples, and contracts, and generates repository-compatible Skill interfaces.

The source is a detailed implementation contract and backlog, not a hidden production runtime. The repository-owned dependency-free engine under `engines/project-intelligence-engine/` adds 50 unique exact handlers, strict typed requests, tenant/project/run-scoped SQLite state, a private immutable local artifact store, deterministic results, checkpoint/evidence persistence, and a no-fallback dispatcher. Local qualification executes one bounded fixture per handler and binds the result, engine tree, fixture, and qualifier digests in the receipt above.

Those local handlers do not complete the source product backlog: all 500 source tasks remain `todo`, and all 248 product acceptance scenarios, provider/runtime integrations, UI/device journeys, customer workloads, independent verification, production use, and certification remain `NOT_RUN` or `NOT_CERTIFIED`. `PARTIAL` records an honest local subset; `PLAN` validates or emits a plan without performing the named external effect.

Source discrepancies are preserved rather than silently repaired: only the `full` source profile is dependency-closed; generated profile resolution adds missing prerequisites for the other seven profiles. The source installation-profile document has stale counts, its debug-profile closure claim is incomplete, three OpenAPI job-control operations omit their required `jobId` path-parameter declaration, and two canonical names also occur in a different uninstalled source package. The installed owner is this pinned v1.1.0 package; any future differing installed destination fails closed.

Run the repository-owned validation with:

```sh
make project-intelligence-skills
```
