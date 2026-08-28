# Target Adapter SDK

## Adapter responsibilities

A target adapter is a replaceable compiler/runtime boundary. It does not own the Goal, AI-SIR, execution authority or completion state.

```python
class TargetAdapter:
    def detect(source) -> DetectionResult: ...
    def profile(exact_version, environment) -> TargetCapabilityProfile: ...
    def import_source(source, evidence) -> AISIRFragment: ...
    def lower(ai_sir, target_profile, decisions) -> LoweringPlan: ...
    def emit(plan, workspace, authority) -> GeneratedRevision: ...
    def native_validate(revision, environment) -> ConformanceEvidence: ...
    def upgrade(old_revision, new_profile) -> UpgradePlan: ...
    def evidence(run) -> EvidenceBundleFragment: ...
```

## Mandatory manifest

```yaml
apiVersion: elmos.ai/v3alpha1
kind: TargetAdapter
metadata:
  name: langgraph-python
spec:
  adapterKind: graph-runtime
  languages: [python]
  modes: [import, generate, upgrade, conformance]
  versionPolicy:
    exactVersionRequired: true
    adapterDigestRequired: true
  authority:
    ambientFilesystem: false
    ambientNetwork: false
    ambientSecrets: false
    failureMode: fail-closed
```

## Capability statuses

| Status | Meaning | Certification behavior |
|---|---|---|
| `supported` | Native target construct with executed conformance evidence | Eligible |
| `conditional` | Supported only under declared configuration/version | Bounded until conditions tested |
| `emulated` | Preserved by generated runtime/adapter layer | Requires equivalence and performance evidence |
| `external-runtime` | Supplied by Elmos durable runtime/control plane | Requires integration/recovery evidence |
| `external-policy` | Supplied by Elmos authority/policy plane | Requires positive and negative policy tests |
| `unsupported` | No approved preservation | Critical requirement blocks |
| `blocked` | Policy, version, license, security or evidence prevents use | Blocks |

## Lowering rule contract

```yaml
ruleId: workflow.interrupt.to.langgraph
source:
  nodeKind: HumanApproval
preconditions:
  - target.feature.interrupt == supported
  - checkpoint.store != null
target:
  construct: interrupt-before
preserves:
  - approval-before-side-effect
  - exact-resume-state
obligations:
  - native-interrupt-test
  - checkpoint-crash-recovery
  - authority-expiry-test
rollback:
  removeGeneratedRegion: true
```

Rules are deterministic when possible. Generative completion may choose among approved rules or fill bounded code regions, but it cannot change preconditions, preservation claims or evidence requirements.

## Generated-region ownership

Adapters emit ownership markers through language-appropriate mechanisms:

- generated file manifest and path rules;
- syntax comments or annotations;
- AST/source-range lineage;
- user extension points;
- protected manual regions;
- three-way semantic merge base.

Regeneration must never overwrite a user-owned region merely because a template changed.

## Native conformance

Every P0 adapter executes at least:

1. manifest/capability profile validation;
2. minimal native import/build/load;
3. representative production fixture;
4. negative unsupported-feature case;
5. authority-deny case;
6. exact version/digest/evidence binding;
7. upstream drift/upgrade case.

Target-native means the real platform CLI/API/runtime or official SDK executes. Parsing generated files with Elmos alone is not native conformance.

## Importers

Importers must capture:

- exact source export/repository and lockfiles;
- target/platform version;
- plugins, extensions, custom components and external resources;
- generated and opaque regions;
- runtime-discovered behavior;
- confidence and counterevidence;
- unsupported round-trip elements.

Visual coordinates and cosmetic metadata may be marked non-semantic only when they do not affect runtime behavior or customer acceptance.

## Security

Adapters run in two phases:

1. **Setup:** dependency download/build with separately approved network/secret authority.
2. **Execution:** secretless and deny-network by default; only declared endpoints/tools are allowed.

An adapter cannot request broad network or filesystem rights as a convenience. Every capability is path/parameter/domain scoped.

## Release process

Before an adapter is marked release-conformant:

- pin exact upstream version, package/image and adapter digest;
- generate SBOM and provenance;
- run vulnerability/license policy;
- execute native conformance;
- execute negative authority/security fixtures;
- publish supported feature envelope;
- sign evidence and compatibility metadata;
- register drift watchers and recertification triggers.

The package deliberately contains no invented release digest.
