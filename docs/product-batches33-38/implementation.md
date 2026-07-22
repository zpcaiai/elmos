# Product Batch B33-B38 implementation

## Namespace

- Product commercialization roadmap: `Product Batch B33-B38`
- Existing certification toolkits: `Migration Pack M35-M45`
- Product Runtime Skills: `agent-skills/runtime/`
- Migration Pack Skills: `.agents/skills/b35-*` through `.agents/skills/b45-*`

The original source manifest records 208 Product Skill definitions. The
complete B34-B38 packages add 188 authoritative definitions, supersede 105
same-name legacy definitions and produce 291 canonical Product Skills after
deduplication. Source names longer than the Skill name limit use a stable
SHA-256 suffix; `source_name` remains recorded in the complete-pack manifest.

This is a Skill-contract overlay, not evidence that every capability described
by the 188 contracts has been implemented or externally exercised.

## Implemented control domains

| Product batch | Module | Local decision ceiling |
|---|---|---|
| B35 | `source-control-workspace-governance` | `READY_FOR_EXTERNAL_GATE` |
| B36 | `secure-execution-plane` | `READY_FOR_EXTERNAL_GATE` |
| B37 | `evidence-assurance-fabric` | `READY_FOR_HUMAN_DECISION` |
| B38A | `continuous-authorization` | `READY_FOR_ENFORCEMENT_GATE` |

The API namespace is `/api/v1/product-commercialization`. The capability
response explicitly names the separate Migration Pack namespace and reports
external execution evidence as `NOT_RUN`.

## Persistence

Migrations V42-V47 materialize every qualified table family listed in the
Product B35-B38 database sections: 279 B35, 419 B36, 174 B37A, 146 B37B, 214 B37C
and 185 B38A table declarations (1,417 total; 1,416 unique qualified tables).
Records are tenant scoped, RLS-forced,
append-only and evidence-bound. External-operation fields are constrained to
false because these migrations do not perform provider, runner or production
actions.

## Evidence boundary

Local unit and contract tests prove deterministic fail-closed model behavior.
They do not prove GitHub/GitLab/Azure/Bitbucket/Gitee connectivity, real runner
attestation, rootless sandbox isolation, third-party CI import, object-lock
enforcement, OPA/Cedar/CEL production behavior, Kubernetes admission, customer
outcome or production deployment. Those claims remain `NOT_RUN` and block any
certification or go-live claim.
