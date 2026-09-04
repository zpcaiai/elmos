# Spring launch evidence intake

This workflow authenticates evidence produced by real staging, security,
operations, legal and design-partner work. It does not produce those outcomes,
sign for another party, deploy, approve a release, or certify the business line.

The exact receipt schema and verification rules are implemented by
`scripts/batch30/spring_launch_evidence.py`. A valid receipt binds all of the
following to the exact checked-out revision and launch profile:

- migrated artifact bytes and a canonical environment manifest;
- the launch profile bytes as committed at the exact deployed Git revision;
- nine content-distinct gate evidence objects below an explicitly approved root;
- separate execution, independent-verifier and independent-reviewer identities;
- an execution signature and independent verification signature for every gate;
- separate release and risk approvals, plus at least two distinct design partners;
- an independent review signed after every gate, approval and partner endorsement;
- non-revoked Ed25519 keys, role-specific key ownership, expiry and freshness.

`NOT_RUN`, `UNKNOWN`, `INCONCLUSIVE`, placeholders, synthetic evidence, stale
signatures, path escapes, mutable URL-only claims, duplicate evidence, shared
actors/organizations/keys, and self-certification all fail closed.

The environment manifest must validate against
`schemas/batch30/spring-launch-environment-manifest.schema.json`. Its
`configuration_digest` is the exact `SPRING_CONFIGURATION_DIGEST` printed by
the launch validator when it reads the same `/controlled/spring.env` used for
Compose interpolation. The trust store, controlled index and final receipt use
the other three `schemas/batch30/spring-launch-*.schema.json` contracts.

## Operator flow

Keep the trust store, private signing keys, evidence roots, environment file and
final receipt outside the repository. Public keys may be distributed to the
gate host; private keys never belong on that host.

```bash
# Validate the exact inert-data environment file used by the Spring Compose
# overlay and retain the printed SPRING_CONFIGURATION_DIGEST for the manifest.
python3 scripts/batch30/validate_spring_launch_readiness.py \
  --environment-file /controlled/spring.env

# Hash bytes that already exist. This command does not create a pass claim.
python3 scripts/batch30/spring_launch_evidence.py reference \
  /controlled/evidence/staging-deployment.json \
  --evidence-root /controlled/evidence \
  --media-type application/json \
  --gate-reference

# External systems/people create the required Ed25519 envelopes. The repository
# verifier only adds the canonical receipt digest to an otherwise complete draft.
python3 scripts/batch30/spring_launch_evidence.py assemble \
  /controlled/drafts/spring-launch-draft.json \
  --output /controlled/evidence/spring-launch-receipt.json \
  --trust-store /controlled/trust/spring-trust-store.json \
  --evidence-root /controlled/evidence \
  --expected-revision "$(git rev-parse HEAD)" \
  --expected-trust-store-digest "$APPROVED_SPRING_TRUST_STORE_DIGEST" \
  --expected-environment-id spring-staging-cn-1 \
  --expected-deployment-id "$SPRING_DEPLOYMENT_ID" \
  --expected-provider private-linux \
  --expected-region cn-north-1 \
  --expected-environment-class STAGING \
  --expected-configuration-digest "$SPRING_CONFIGURATION_DIGEST"

# The launch gate re-verifies every byte, signature, role and revision binding.
make spring-launch-gate \
  SPRING_ENV_FILE=/controlled/spring.env \
  SPRING_EXTERNAL_EVIDENCE=/controlled/evidence/spring-launch-receipt.json \
  SPRING_TRUST_STORE=/controlled/trust/spring-trust-store.json \
  SPRING_TRUST_STORE_DIGEST="$APPROVED_SPRING_TRUST_STORE_DIGEST" \
  SPRING_EVIDENCE_ROOT=/controlled/evidence \
  SPRING_ENVIRONMENT_ID=spring-staging-cn-1 \
  SPRING_DEPLOYMENT_ID="$SPRING_DEPLOYMENT_ID" \
  SPRING_PROVIDER=private-linux \
  SPRING_REGION=cn-north-1 \
  SPRING_ENVIRONMENT_CLASS=STAGING
```

`APPROVED_SPRING_TRUST_STORE_DIGEST` is a composite digest of the strict trust
store bytes and every referenced public-key byte sequence. Pin it through an
independent deployment approval/configuration channel before receipt intake;
computing it from the same mutable file inline with the gate would not be a
trust anchor. Private signing keys are never inputs to these commands.

The maximum successful repository result remains
`EXTERNAL_EVIDENCE_INTAKE=VALIDATED_NOT_CERTIFIED` and
`CERTIFICATION=NOT_CERTIFIED`. A separate authorized release process owns any
production or certification decision.
