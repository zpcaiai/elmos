# Elmos Knowledge-Skill-Model Foundry Engine v3

Repository-owned, fail-closed runtime for the pinned
`elmos-knowledge-skill-model-foundry-v3.0.0` specification package.

The source ZIP is data, not execution authority. The importer never runs its
Python, Rego, SQL, pipeline, test, CI, or Markdown content. It compiles the
manifest-designated YAML registry into an exact repository-owned catalog and
binds every canonical Skill name to an allowlisted handler. The stale v2 JSON
catalog in the same archive is retained only as a diagnosed source defect.

## Runtime guarantees

- unknown Skills and unregistered adapters fail closed;
- all 1,310 Skills have exact compiled contracts and runtime bindings; 66
  provider-free Skills have exact local semantic handlers and 1,244 have exact
  repository-owned native programs with digest-bound host Broker routes;
- external-effect mutations bind authenticated tenant, project, actor, purpose,
  environment, workspace, revision, capability lease, exact payload, expiry,
  one-time permit, policy decision, and durable idempotency key;
- external execution accepts only a host-owned Broker route, never a direct
  Python callback; route operation/effect, permit, request, provider receipt and
  declared outputs must match exactly;
- production hosts can bind those routes to exact digest-pinned executables via
  `build_subprocess_broker`; command execution is shell-free, environment/time/
  output bounded, drift checked, and provider receipts require an injected
  trusted signature verifier;
- `ExternalRunRequest`, `IndependentAcceptanceRequest`, and
  `CertificationRequest` bind training, deployment, independent holdout and
  authority decisions to exact artifacts, roles and external signatures;
- SQLite state transitions, checkpoints, evidence, audit events, and outbox
  records are durable and tenant/project scoped;
- artifacts are immutable, content addressed, private, and verified on read;
- model training, provider calls, repository writes, database operations,
  deployment, signing, customer acceptance, and certification require exact
  external adapters and receipts;
- local execution never manufactures E3-E5 evidence or production status.

The knowledge, experience, dataset, model and serving helper classes are
bounded local planning surfaces with optional shared SQLite persistence. Inject
a file-backed `FoundryStore` through `FoundryService` to recover metadata after
restart. Asset changes use versioned compare-and-swap and atomic audit events;
idempotent creation cannot clear quarantine or revert model promotion. Serving
availability expires and cannot survive a gateway restart as trusted health.
Consent and evidence still require trusted authorization verifiers. Without a
store, or with `:memory:`, state is process-local. Local SQLite recovery does not
qualify a production deployment.

## Capability truth

The package contains 41 Meta-Skills and 1,310 atomic specifications. Every
atomic identity has an exact runtime binding. Exactly 66 provider-free Skills are `LOCAL`; the remaining 1,244 are `NATIVE` and
each has an exact source-digest-bound semantic program, adapter identity,
privileged operation and non-executable Broker route. No atomic Skill is
`PREPARE_ONLY` or integration-unbound. The host must
still supply and attest the concrete provider implementation, environment,
durable store, permit and result verifier. The native programs close the repository code gap; they do not prove that a
provider business effect occurred.

Local qualification may report only `LOCAL_EXECUTED_SELF_ATTESTED` and
`READY_FOR_EXTERNAL_GATE`. External evidence remains `NOT_RUN`; certification
remains `NOT_CERTIFIED`.

The external assurance API validates evidence supplied by real providers,
independent verifiers and certification authorities. It intentionally contains
no local issuer, signing key, synthetic success path or default trust decision.
`ExternalTrustStore` and `verify_external_qualification_chain` add role-scoped
Ed25519 verification, key validity/revocation, authority separation, exact
scope/executor bindings, ordered training/deployment checks, and complete
receipt-chain validation. The repository command is documented in
`docs/knowledge-skill-model-foundry/EXTERNAL_QUALIFICATION.md`.

Run the repository integration target:

```bash
make knowledge-skill-model-foundry-skills
```

That target performs no provider, training, deployment, production, or
certification action.

The wheel/sdist include the digest-pinned compiled catalog. Offline installation
also requires the runtime dependencies in `requirements-runtime.lock` to be
present in the local package cache or approved mirror. The JavaScript AST parser
is the pure Python Esprima 4.0.1 package (BSD license); its source archive digest
is pinned in that lock. It parses ECMAScript 2017 without running input programs
and does not provide TypeScript or modern JavaScript runtime support.

After installation, the four read-only/preparation CLI forms are:

```bash
elmos-foundry validate
elmos-foundry route elmos-00-foundation-contracts --query "typed contract"
elmos-foundry pipeline --help
elmos-foundry skill --help
```

The pipeline and Skill forms require explicit tenant, project, actor,
environment, workspace, revision, invocation and lease scope flags shown by
their help commands. The CLI does not configure external Brokers or grant
effect authority.
