# Package Relationship

| Property | Capability package | Certification package |
|---|---|---|
| Package | `elmos-ai-capability-enhancement-skills` | `elmos-functional-assurance-certification-skills` |
| Role | Generate, transform, execute, strengthen, produce evidence | Independently evaluate, decide, certify, surveil, revoke |
| Skills | 296 | 178 |
| Adapters | 264 | 112 |
| Standalone ceiling | E3; E4 evidence may be produced, no E5/P05 certificate | Requires capability evidence; K8 bounded decision |
| Candidate mutation | Allowed under K5 with ChangeGraph | Forbidden after certification intake |
| Completion authority | None | K8 only |

## Dependency rule

`elmos-functional-assurance-certification-skills` has a required-base dependency on `elmos-ai-capability-enhancement-skills`. The capability package may name certification Skills only as optional companion integrations required for higher assurance; those edges do not enter its local dependency DAG.

## Shared contract plane

Both packages carry identical copies of `contracts/` and the reference kernel. These files are interface definitions and checker logic, not duplicated Skill ownership. Their hashes can be compared during integration.
