# Spring Corpus Equivalence Evaluation

`scripts/batch30/evaluate_spring_corpus_equivalence.py` computes a project-grain
equivalence rate only for a declared, exact Spring migration tuple and only from
eligible signed external corpus evidence. It is a local evaluator, not the Batch 30
certification gate. It never derives a percentage for arbitrary legacy Spring projects.

## Typed contracts

The evaluator uses three Draft 2020-12 contracts:

- `schemas/batch30/spring-corpus-equivalence-manifest.schema.json`
- `schemas/batch30/spring-project-equivalence-evidence.schema.json`
- `schemas/batch30/spring-corpus-equivalence-result.schema.json`

The manifest pins one directional tuple containing:

- route ID, pack ID/version and the SHA-256 of the actual `pack.json` bytes;
- recipe ID, owning pack-bundle version, and the SHA-256 of the actual
  `recipes/manifest.json` bytes;
- exact source and target framework versions;
- exact source and target runtime versions;
- exact source and target build-tool versions; and
- exact source and target provider versions.

Floating versions, ranges, mutable labels such as `latest` or `SNAPSHOT`, duplicate
provider names, a source/target identity tuple, and a mismatched canonical tuple digest
fail closed. Each project repeats the canonical tuple digest, so evidence from another
version edge cannot be pooled silently.

For a submitted external intake, `--pack-dir` is mandatory. The existing Batch 30
external-intake verifier reads and hashes the real pack manifest, version matrix, target
profile, and recipe manifest. The corpus evaluator then checks that its tuple matches
those verified bytes and that its recipe ID occurs in the real recipe manifest. A digest
string copied into the corpus manifest without the corresponding pack bytes is
ineligible.

The current `recipes/manifest.json` contract has no independent recipe-version field.
Accordingly, `tuple.recipe.version` means the exact immutable version of the pack bundle
that owns that manifest, and the evaluator requires it to equal the externally verified
`pack_version`. It must not be interpreted or reported as a separately observed recipe
semantic version.

## Content and trust binding

Every project contains content references for its source snapshot, target snapshot, and
outcome record. Each reference includes a relative path, media type, byte count, and
SHA-256. The evaluator reads each bounded regular file once below the explicit evidence
root, rejects symlinks and path escapes, and verifies the declared byte count and digest.
The signed outcome record repeats both snapshot identities as well as the project ID,
corpus role, exact tuple, and evaluation scope.

Local actor names or a manifest field saying `AUTHORIZED` are not trust evidence. An
aggregate project is considered only when the manifest supplies a content-addressed
Batch 30 external-certification intake and the caller supplies its separate Ed25519 trust
store. `scripts/batch30/validate_external_certification_intake.py` must verify all nine
roles, including:

- an unexpired, non-revoked customer authorization whose signed scope covers every
  evidence content digest;
- authorized customer repository, customer holdout, and customer acceptance evidence;
- Rootless runner, transformer, and verifier evidence;
- independent review; and
- external certification evidence.

The intake must also preserve signer/executor subject and organization separation and
the stricter global organization separation enforced by the external-intake verifier.
Expired or revoked keys or records, unknown organizations, self-verification, a stale
authorization scope, a modified content byte, or a modified signature makes the intake
`INVALID` and the rate `NOT_EVALUATED`.

The current conservative project-to-signed-content mapping is:

| Corpus role | Signed content role | Additional binding |
| --- | --- | --- |
| `development` | none | local engineering evidence only |
| `holdout` | `customer_holdout` | artifact, execution profile, and all three Rootless evidence digests |
| `representative` | `independent_review` | artifact, execution profile, and all three Rootless evidence digests |
| `customer` | `authorized_customer_repository` | the same runnable digests plus signed `customer_acceptance` |

The external-intake format has one content object for each signed role. Therefore this
evaluator conservatively supports exactly one project for each aggregate corpus role.
Two projects claiming the same signed role are both excluded with
`MULTIPLE_PROJECTS_PER_SIGNED_ROLE_UNSUPPORTED`; their outcomes are not pooled.

## Corpus separation and project eligibility

The manifest declares four physically separate roots:

- `development`
- `holdout`
- `representative`
- `customer`

Roots and per-project directories may not be equal or nested across corpus boundaries.
This prevents a development fixture from being relabelled as holdout, representative, or
customer evidence.

A development result may be locally evidence-eligible after its three content references
and typed outcome agree. It never enters the overall denominator and has no signed-role
claim.

An aggregate project is eligible only when all of these conditions hold:

1. source snapshot, target snapshot, and outcome bytes match their references;
2. the typed outcome matches the project, snapshots, exact tuple, role, and scope;
3. the scope is `WHOLE_REPOSITORY`;
4. the outcome is conclusive (`EQUIVALENT` or `NOT_EQUIVALENT`) and is internally
   consistent with build, startup, behavior-oracle, and test-integrity checks;
5. the complete external intake and trust store pass cryptographic verification;
6. the role-specific signature covers the exact project outcome bytes;
7. the outcome binds the verified artifact, execution profile, and Rootless runner,
   transformer, and verifier content digests;
8. a customer outcome additionally binds the verified customer-acceptance content; and
9. the signed verifier and recorded executor are separate subjects and organizations.

`EQUIVALENT` requires every check to pass, at least one observation, zero regressions, and
no unknowns. `NOT_EQUIVALENT` requires a failed check and at least one recorded
regression. `INCONCLUSIVE`, `NOT_RUN`, invalid evidence, and excluded projects remain
visible but never enter a denominator.

## Honest denominator

The evaluator answers two separate questions:

1. `overall_equivalence` is the observed project rate for the exact tuple and the exact
   signed corpus supplied to this run.
2. `universal_legacy_spring_equivalence` asks whether the evidence establishes a rate for
   arbitrary legacy Spring projects. Its status is always `NOT_EVALUATED`.

The observed rate becomes `EVALUATED` only when exactly one eligible, conclusive,
whole-repository project exists in each of holdout, representative, and customer corpus.
The project-grain formula is:

```text
numerator   = eligible projects with outcome EQUIVALENT
denominator = eligible projects with outcome EQUIVALENT or NOT_EQUIVALENT
percentage  = 100 * numerator / denominator
```

A failing eligible project remains in the denominator. Tests, requests, observations,
source files, and generated classes are not alternate denominator grains. If any required
role is absent or no evidence is eligible, numerator, denominator, and percentage are all
`null` and the status is `NOT_EVALUATED`.

Consequently, the local Spring MVC Maven/Tomcat exact fixture can report its own exact
result but cannot create or change an overall rate:

```json
{
  "overall_equivalence": {
    "status": "NOT_EVALUATED",
    "numerator_equivalent_projects": null,
    "denominator_eligible_projects": null,
    "percentage": null
  },
  "universal_legacy_spring_equivalence": {
    "status": "NOT_EVALUATED",
    "percentage": null
  }
}
```

The unit test containing a complete nine-role signed bundle is test-only cryptographic
wiring. It is not customer acceptance, independent field evidence, or a certified Spring
corpus result.

## CLI

With no external evidence, declare `external_intake.status` as `NOT_RUN` and
`external_intake.content` as `null`. The command still emits a typed fail-closed result:

```bash
python3 scripts/batch30/evaluate_spring_corpus_equivalence.py \
  /path/to/spring-corpus-manifest.json \
  --evidence-root /path/to/evidence-root \
  --output /path/to/spring-corpus-result.json
```

To evaluate a submitted signed intake, also supply the exact pack and separate trust
store:

```bash
python3 scripts/batch30/evaluate_spring_corpus_equivalence.py \
  /path/to/spring-corpus-manifest.json \
  --evidence-root /path/to/evidence-root \
  --pack-dir /path/to/exact-framework-pack \
  --trust-store /path/to/external-evidence-trust-store.json \
  --output /path/to/spring-corpus-result.json
```

The manifest's `tuple_sha256` is SHA-256 over canonical compact UTF-8 JSON with sorted
object keys:

```python
from scripts.precision_migration.trust import canonical_digest

manifest["tuple_sha256"] = canonical_digest(manifest["tuple"])
```

Exit code `0` means a structurally safe manifest was evaluated. This includes typed
`NOT_RUN`, `INVALID`, and `NOT_EVALUATED` evidence outcomes. Exit code `2` means the
manifest, exact tuple, corpus layout, content path, or output target itself was unsafe or
structurally invalid. Evidence failures remain explicit in project and external-intake
exclusion reasons rather than being omitted.

## Evidence boundary

This evaluator does not launch or authorize a privileged nested daemon, manufacture a
customer identity, sign evidence, accept a customer outcome, or certify a framework
route. It only consumes evidence already produced by authorized real actors. Protected
Rootless execution, customer acceptance, independent review, and external certification
therefore remain `NOT_RUN` until those events actually occur.

Even a cryptographically verified intake yields only an observed exact-corpus percentage
and `NOT_CERTIFYING` here. It cannot promote Spring MVC beyond experimental or Spring Boot
beyond limited status. Only `scripts/batch30/run_framework_gate.py` may determine Batch 30
readiness, and that gate cannot convert a single exact fixture or a declared corpus into a
universal legacy-Spring equivalence claim.
