# Elmos AI Capability Enhancement Skills v4.1.0

This package is one half of the split of `elmos-ai-native-project-factory-total-skills-v4.0.0`.

## Boundary

- **Package role:** `capability`
- **Skills:** 296
- **Adapters:** 264
- **Companion relationship:** `elmos-functional-assurance-certification-skills` is the optional companion for E4/E5/P05 and external certification.
- **Standalone completion boundary:** E3 native implementation/readiness; no production certificate.
- **Canonical ownership:** the existing Elmos K1–K8 authority model and 16 routable v3 entry points remain unchanged.

## What belongs here

This package contains AI-SIR, agent/RAG/project generators, portable Skills and Plugins, MCP/A2A/ACP, polyglot and database semantic routes, model serving, knowledge/memory, platform/runtime, embedded QA, security and formal evidence producers. It can generate and validate native candidates but cannot issue E5/P05 production certificates by itself.

## Installation order

1. Install `elmos-ai-capability-enhancement-skills`.
2. Install `elmos-functional-assurance-certification-skills` only when independent functional certification is required.

```bash
./validate.sh --strict
./install.sh --repo /path/to/elmos --host both --profile p0
```

The certification installer blocks by default if the capability-package receipt is absent. Use `--allow-missing-base` only for package inspection or an intentionally remote evidence-producer deployment.

## Cross-package dependencies

This package has **61** declared cross-package Skill dependency edges. They are machine-readable in `catalog/external-dependencies.yaml`. Local dependency graphs remain acyclic.

## Completion claims

Package validation proves package structure, dependency boundaries, schemas, policies, reference logic, installer safety and reproducible archives. It does **not** prove native framework/database/cloud execution, customer acceptance, accreditation, E5 or P05.
