# Elmos Commercial Capability Expansion Skills v2.0.0

Generated: 2026-08-29

This package is an **additive capability expansion** for Elmos. It consolidates the discussed GitHub/Gitee/AI-agent-company technologies into implementation-oriented Skills rather than copying upstream projects.

## Package goals

1. Upgrade Skills from prompt fragments to executable, versioned, policy-controlled production assets.
2. Turn Elmos into a repository semantic compiler backed by syntax/symbol/build/runtime/data/evidence graphs.
3. Prefer deterministic rewrite engines and compiler APIs before free-form LLM editing.
4. Make untrusted execution, hermetic builds, reproducibility and multi-tenant isolation first-class.
5. Treat E0-E5 certification as evidence aggregation, not a single test command.
6. Produce proof-carrying build/transformation bundles with provenance, SBOM, attestations and signatures.
7. Let production trajectories improve Rules/Skills/corpora only through offline evaluation + canary promotion.

## Contents

- `SKILL.md` – master orchestration skill.
- `manifest.json` – machine-readable inventory.
- `skills/<kernel>/<skill>/SKILL.md` – 85 implementation-oriented skills.
- `architecture/` – target architecture, kernel mapping, lifecycle, evidence contracts.
- `schemas/` – JSON Schemas for Skill Manifest, Evidence Bundle and Certification Result.
- `policies/` – reference policy model and examples.
- `evals/` – E0-E5 gate matrix and promotion criteria.
- `references/` – upstream inspiration/source map.
- `scripts/validate_package.py` – offline structural validator.
- `MERGE_GUIDE.md` – how to merge into an existing Elmos skills repository.

## Design rule

**Do not wrap upstream tools 1:1.** Normalize them behind Elmos IR, Policy, Evidence and Runtime contracts so any upstream component remains replaceable.
