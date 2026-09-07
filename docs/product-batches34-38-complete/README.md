# Product B34-B38 complete Skill packs

This directory records the integration contract for the five submitted
standalone Codex Skill packs:

- B34 enterprise identity, tenant and access governance: 18 Skills;
- B35 SCM connectors and repository workspaces: 33 Skills;
- B36 private runners, sandboxes and execution operations: 41 Skills;
- B37 artifact, external evidence and assurance analytics: 48 Skills;
- B38 policy, continuous authorization and regulatory operations: 48 Skills.

The source packages remain under `elmos-codex-skills-batch34-complete` through
`elmos-codex-skills-batch38-complete`. Their 188 Skills are installed into
`agent-skills/runtime`. Combined with the prior B33-B38 source family, 105 names
are superseded and 291 canonical Product Skills remain. Product Skills are not
Migration Pack M35-M45 Skills; the latter remain under `.agents/skills`.

## Name normalization

The submitted packs contained 88 names longer than Codex's 64-character Skill
limit. Those names use the deterministic alias:

```text
source_name[:55].rstrip("-") + "-" + sha256(source_name)[:8]
```

Every package manifest preserves `source_name`, the normalized Skill directory,
and package version. Every source and installed Skill has a generated
`agents/openai.yaml` whose default prompt invokes the normalized `$skill-name`.

## Commands

```text
python3 tooling/integrate_product_batch34_38_complete_skill_packs.py
python3 tooling/ensure_runtime_skill_interfaces.py --check
python3 tooling/validate_product_batch33_38_integration.py
make product-batch35-38
make backend
```

The integrator is idempotent. The validator checks official Skill validity,
package and Skill digests, supersession, interface metadata, persistence
invariants, module wiring and the `NOT_RUN` external-evidence boundary.

## Evidence boundary

Passing static package, Skill, architecture and local module tests does not
prove provider connectivity, tenant isolation on a real PostgreSQL instance,
runner or sandbox isolation, third-party evidence ingestion, policy-engine
enforcement, regulatory submission, customer acceptance or production use.
Those outcomes remain `NOT_RUN` until executed by an authorized independent
gate with immutable evidence.
