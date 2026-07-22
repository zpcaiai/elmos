# Product B40-B55 complete Skill pack

This directory records the integration contract for the submitted Product
B40-B55 enterprise-domain Skill pack. It contains 768 Skills across 16 numbered
batches and 48 subbatches: every numbered batch has 48 Skills and every A/B/C
subbatch has 16.

The normalized distributable remains under
`elmos-codex-skills-batch40-55-complete`; the installed contracts live under
`agent-skills/runtime`. The pack adds 768 non-overlapping names, taking the
canonical Product inventory through B55 to 1,107 and the complete Runtime Skill
catalog to 1,647.

Product B40-B55 is a separate namespace from Migration Packs M40-M45. Product
Skills live under `agent-skills/runtime`; Migration Pack Skills retain their
independent `.agents/skills/b40-*` through `.agents/skills/b45-*` contracts and
conservative certification gates.

## Provenance

- B40A: 16 Skills with `approved-conversation-design` provenance.
- B40B-B55C: 752 Skills with `generated-planning-edition` provenance.

The latter are installable planning contracts, not independently reviewed
domain implementations. A generated Skill, a passing structural check, or the
word “complete” must not be interpreted as regulatory, provider, production or
customer certification.

## Name normalization and interfaces

The submitted pack contained 456 names longer than Codex's 64-character Skill
limit. They use the deterministic alias:

```text
source_name[:55].rstrip("-") + "-" + sha256(source_name)[:8]
```

The package and ELMOS manifests preserve every original `source_name`, original
manifest digest and original copied-package tree digest. All 768 package Skills
and installed Skills include an `agents/openai.yaml` generated with the
official `skill-creator` tooling and explicitly invoke the normalized name.

## Commands

```text
/opt/homebrew/bin/uv run --quiet --with pyyaml python tooling/integrate_product_batch40_55_complete_skill_pack.py
./elmos-codex-skills-batch40-55-complete/validate.sh
make product-batch40-55-skills
make backend
```

The integrator is idempotent and refuses to overwrite a pre-existing Runtime
Skill not owned by this pack. The central gate checks exact batch/subbatch and
provenance counts, deterministic aliases, package/runtime hashes, official
Skill validity, interface invocation, namespace separation and `NOT_RUN`.

The earlier B34-B38 source-package directories are not present in this current
workspace. Their 339 canonical installed Product contracts through B39 are
revalidated from the retained manifests and Runtime hashes, while the missing
source archives are explicitly reported as `NOT_REVALIDATED`.

## Evidence boundary

Static Skill validation and local Maven tests do not establish real CRM,
marketing, procurement, HR/payroll, data/AI, integration, SRE/security, cloud,
industrial, logistics, healthcare, energy, legal/content or product-maturity
outcomes. External standards, provider capabilities, tenant deployments,
regulated decisions, safety controls, customer acceptance and production use
remain `NOT_RUN` until independently executed against an exact, authorized
environment with immutable evidence.
