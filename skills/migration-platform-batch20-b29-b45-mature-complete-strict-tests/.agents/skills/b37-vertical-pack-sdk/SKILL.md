---
name: b37-vertical-pack-sdk
description: Implement a Vertical Pack SDK combining domain ontology mappings policies scenarios invariants dashboards and deployment profiles without leaking customer-specific assets.
---

# Skill 1314: b37-vertical-pack-sdk

## Use this skill when

- Industry-specific migration capabilities need packaging.
- Partners need to distribute finance healthcare manufacturing energy or government packs.

## Domain-specific risks and invariants

- Domain packs may encode regulated data policy, critical invariants, or customer-specific knowledge.
- Generic reuse can leak private schemas or weaken controls.

## Workflow

1. Define vertical-pack metadata, domain capabilities, prerequisites, policies, scenarios, invariants, templates, dashboards, data classifications, deployment constraints, and evidence.
2. Separate public, certified shared, and customer-private assets.
3. Generate SDK, sample pack, and validation harness.
4. Test applicability, policy conflicts, missing prerequisites, and regulated-data boundaries.
5. Publish only after domain and security review.

## Required repository outputs

- vertical pack SDK and manifest
- domain scenario invariant and policy bundles
- privacy and applicability evidence

## Verification

- Validate no customer identifier or proprietary asset enters public release.
- Run representative domain scenarios and negative policy tests.
- Verify pack composition with base product versions.

## Stop and escalate when

- Regulatory or domain owner approval is missing.
- Pack depends on customer-private data or rules not safely separable.

## Definition of done

- One vertical pack can be installed and validated independently.
- Domain claims are evidence-backed and scoped.
