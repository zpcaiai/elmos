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
- all 1,310 Skills have exact compiled contracts; 26 provider-free Skills have
  exact local semantic handlers and 1,284 remain prepare-only;
- external-effect mutations bind authenticated tenant, project, actor, purpose,
  environment, workspace, revision, capability lease, exact payload, expiry,
  one-time permit, policy decision, and durable idempotency key;
- external execution accepts only a host-owned Broker route, never a direct
  Python callback; route operation/effect, permit, request, provider receipt and
  declared outputs must match exactly;
- SQLite state transitions, checkpoints, evidence, audit events, and outbox
  records are durable and tenant/project scoped;
- artifacts are immutable, content addressed, private, and verified on read;
- model training, provider calls, repository writes, database operations,
  deployment, signing, customer acceptance, and certification require exact
  external adapters and receipts;
- local execution never manufactures E3-E5 evidence or production status.

The knowledge, experience, dataset, model and serving helper classes are
bounded process-local planning surfaces. They deliberately fail without trusted
authorization verifiers where consent or evidence is required, but they are not
durable production asset stores. Durable execution and evidence require the
injected SQLite and private CAS implementations.

## Capability truth

The package contains 41 Meta-Skills and 1,310 atomic specifications. Every
atomic identity has an exact runtime binding. Exactly 26 provider-free Skills
are `LOCAL`; the remaining 1,284 are `PREPARE_ONLY` until the required language,
database, framework, cloud, model, customer, or independent-verifier adapter is
configured and evidenced. A prepared plan is not the business effect it
describes.

Local qualification may report only `LOCAL_EXECUTED_SELF_ATTESTED` and
`READY_FOR_EXTERNAL_GATE`. External evidence remains `NOT_RUN`; certification
remains `NOT_CERTIFIED`.

Run the repository integration target:

```bash
make knowledge-skill-model-foundry-skills
```

That target performs no provider, training, deployment, production, or
certification action.

The wheel/sdist are offline-installable and include the digest-pinned compiled
catalog. After installation, the four read-only/preparation CLI forms are:

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
