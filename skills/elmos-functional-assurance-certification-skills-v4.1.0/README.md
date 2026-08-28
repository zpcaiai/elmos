# Elmos Functional Assurance & Certification Skills v4.1.0

This package is one half of the split of `elmos-ai-native-project-factory-total-skills-v4.0.0`.

## Boundary

- **Package role:** `certification`
- **Skills:** 178
- **Adapters:** 112
- **Companion relationship:** `elmos-ai-capability-enhancement-skills` is the required base package supplying systems, adapters and evidence producers.
- **Standalone completion boundary:** not standalone; certifies exact outputs of the capability package.
- **Canonical ownership:** the existing Elmos K1–K8 authority model and 16 routable v3 entry points remain unchanged.

## What belongs here

This package contains independent functional assurance, TEVV, laboratory/metrology, conformance decision rules, certification authority, accreditation readiness, audit/CAPA/surveillance, certificate lifecycle, recognition and regulated-sector profiles. It consumes immutable evidence from the capability package and never modifies the candidate under certification.

## Installation order

1. Install `elmos-ai-capability-enhancement-skills`.
2. Install `elmos-functional-assurance-certification-skills` only when independent functional certification is required.

```bash
./validate.sh --strict
./install.sh --repo /path/to/elmos --host both --profile p0
```

The certification installer blocks by default if the capability-package receipt is absent. Use `--allow-missing-base` only for package inspection or an intentionally remote evidence-producer deployment.

## Cross-package dependencies

This package has **123** declared cross-package Skill dependency edges. They are machine-readable in `catalog/external-dependencies.yaml`. Local dependency graphs remain acyclic.

## Completion claims

Package validation proves package structure, dependency boundaries, schemas, policies, reference logic, installer safety and reproducible archives. It does **not** prove native framework/database/cloud execution, customer acceptance, accreditation, E5 or P05.
