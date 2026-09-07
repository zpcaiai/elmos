# Exact local implementation scope

The runtime now binds 45 exact local algorithms. `LOCAL` describes bounded
repository-owned behavior; no whole-Skill completion, independent verification,
provider execution or certification follows from registration or local tests.

## Foundation extension

| Exact Skill | Implemented behavior | Remaining boundary |
| --- | --- | --- |
| `architecture-decision-record` | Validate alternatives, selected decision, ownership, assumptions, consequences, exit conditions and rollback; content-address the ADR | External ADR publication, approval and retrieval service |
| `capability-taxonomy-governance` | Validate exact catalog names, boundaries, owners, risk, bounded maturity, dependency graph and topological order | Organizational governance and approval; proposed taxonomy never replaces source authority |
| `compatibility-matrix-manager` | Exact directional version tuples, duplicate rejection, immutable matrix digest and lookup | Caller compatibility declarations are unverified; native runtime validation remains required |
| `tenancy-scope-contract` | Bind tenant/project/actor/environment/workspace/revision/purpose to authenticated context; validate resource tree | Resource ownership attestation and infrastructure enforcement |
| `evidence-contract` | Compile mandatory typed evidence obligations and independent role requirements | Obligations remain `NOT_RUN`; commands are data and are never executed by this handler |
| `policy-contract` | Compile exact default-deny rules and simulate deny-overrides decisions; reject unsupported obligations | Simulation cannot mint an execution permit; trusted policy deployment/enforcement remains required |
| `data-usage-consent-contract` | Validate purpose, explicit use restrictions, revocation, validity and retention intervals | Caller declarations/time do not establish verified consent or permission to train/export |
| `release-bundle-contract` | Bind model, adapter, knowledge, toolchain, policy, evaluation, rollback and exact Skill pins into a content-addressed unit | Artifact existence, signatures, provider publication and production release approval |

## Dataset extension

| Exact Skill | Implemented behavior | Remaining boundary |
| --- | --- | --- |
| `repo-org-time-split-builder` | Transitive grouping across repository, organization, fork/task family and content digest; strict temporal splits; quarantine groups crossing cutoffs | Trusted complete repository identities and independent holdout qualification |
| `dataset-lineage-and-provenance` | Scoped typed DAG validation, cycle/dangling rejection and transitive sample ancestry | Source discovery and independent provenance attestation |
| `dataset-revocation-unlearning-index` | Descendant impact from revoked objects/samples/datasets to checkpoints and adapters | Deletion, retraining and model unlearning are not executed |
| `preference-pair-builder` | Bind chosen/rejected candidates to explicit review and verification facts | Facts remain caller declarations; consent and independent evidence required before training |
| `active-learning-sample-selection` | Deterministic bounded weighted ranking and annotation-budget selection | Annotation execution and independent metric/label quality |
| `semantic-and-ast-deduplication` | Bounded Python AST structural fingerprints and exact duplicate grouping | Unsupported languages rejected; structural equality is not behavioral equivalence |

All dataset outputs remain quarantined and ineligible for training. Dataset
algorithms run on supplied bounded records, without fetching or executing code.

## Bootstrap runtime extension

| Exact Skill | Implemented behavior | Remaining boundary |
| --- | --- | --- |
| `skill-transaction-and-rollback` | Apply bounded JSON set/delete operations with exact preconditions, replay inverse operations, persist private snapshots and terminal idempotent receipts; interrupted runs require reconciliation | No repository/database/provider mutation or external rollback; only local checkpoint state is covered |
| `tenant-policy-aware-retrieval` | Filter caller documents by host-leased tenant/project, revision, purpose, region, classification, rights and roles; rank lexical matches within a UTF-8 byte budget | Caller metadata is untrusted; vector retrieval, token counting, external source authorization and independent provenance verification remain unimplemented |

## Repository semantic extension

| Exact Skill | Implemented behavior | Remaining boundary |
| --- | --- | --- |
| `build-and-dependency-graph` | Parse supplied Maven POM 4.0.0 and npm package manifests into typed dependency/module/plugin/profile nodes and edges, source locators and declaration-level graph differences | No dependency resolution, effective Maven inheritance, lifecycle execution, Gradle/Cargo/Python build semantics or native build evidence |
| `multi-language-ast-extraction` | Parse bounded Python and ECMAScript 2017 source with real CPython AST and pinned Esprima 4.0.1; emit typed nodes, edges, source maps, diagnostics, immutable checkpoints and replayable results | No source execution, TypeScript/JSX/newer ECMAScript support, cross-file symbol resolution or semantic equivalence; structural source ranges are labeled explicitly |
| `semantic-ir-reconciliation` | Reconcile digest-bound parser projections, explicit type facts, source spans, CFG consistency and supplied trace/test observations; preserve conflicts, missing facts and unknown semantics | Parser coverage/confidence and evidence are caller declarations; no native parsing, runtime replay, subtype inference or cross-language equivalence is established |

These exact handlers consume supplied, scoped content. A local graph or parser
result does not establish that a repository is complete, builds successfully,
behaves equivalently or satisfies an independent acceptance corpus.

## Durable asset metadata

Inject one file-backed `FoundryStore` through `FoundryService`. Knowledge,
sanitized experience, datasets, local model release metadata and serving health
use the same scoped store. Immutable creation identity supports safe retries;
versioned updates and audit events commit atomically. A creation retry cannot
reset quarantine or a model's later gate. Schema v1 upgrades to the exact v2
asset schema after prior-schema attestation. Malformed or tampered stores fail
closed. Serving availability expires and is fenced by gateway instance.
Generic asset updates cannot change consent or promote a model; local E1
promotion uses the private host path only after evidence and authorization
verification. Read-only attestation precedes mutable SQLite connection settings.

Absent a store, or with SQLite `:memory:`, metadata remains process-local.
This does not implement model training/serving, distributed PostgreSQL/RLS,
multi-host concurrency, backups/DR, KMS signing or production deployment.

## Completion denominator

The unchanged source denominator is 1,310 atomic Skills, 41 packs, 9,090
dependency edges and 14 pipelines. The exhaustive implementation matrix keeps
code gaps separate from unexecuted verification and lists the source workflow
for each unimplemented identity. Adding a local handler must also update the
three explicit allowlists, regenerate and re-pin the compiled catalog, add
public service acceptance and negative cases, refresh the matrix, and execute
the qualification writer before the package gate can pass.
