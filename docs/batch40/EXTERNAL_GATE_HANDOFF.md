# Batch 40 external gate handoff

This handoff starts only after repository-owned remediation is complete. It is
not a certification request, approval, signature, or evidence manifest.

## Current bounded result

- Certification: `NOT_RUN`; production certification: `NOT_CERTIFIED`.
- Local assurance: 13/13 exact CI, threat-model, and evidence-graph controls passed with
  self-attested evidence.
- Repository controls: 11 formerly experimental capability rows now have 11
  executable, fail-closed local controls and bounded `limited` evidence. This
  includes review ownership, PSIRT policy, model-artifact registration, safe
  VEX mapping, provenance tamper rejection, external-adapter denial, active-test
  authorization, independent-identity separation, and trusted-builder policy.
  Provider scanners, active tests, signing, and isolated builders remain
  `NOT_RUN`.
- GitHub Dependabot snapshot: 290 historical alerts, 0 open. Of 185 fixed
  alerts with complete timestamps, 167 met the declared severity SLA and 18
  breached it (`0.9027`). The 105 dismissed alerts are excluded from SLA success
  and still require an explicit risk-acceptance/VEX review.
- Direct dependency inventory: 427 external components have versions, but none
  has a repository-approved license decision. They remain 427 unresolved
  license blocks rather than being silently treated as acceptable. Every
  component is now retained in `license-decision-register.json`; the associated
  policy is explicitly `DRAFT_NOT_APPROVED` with automatic approval disabled.
- Gap inventory: 14 blocking / 2 open, split into 1 repository blocking, 1
  repository open, 13 external-gate blocking, and 1 external-gate open.

The authoritative, refreshable list is
`mature-product-packs/batch40/elmos-platform-supply-chain/gap-inventory.json`.

## Repository-owned closure before external assessment

1. A qualified legal owner must approve an exact license policy and decide all
   427 queued external direct components. Unknown, conflicting, prohibited, or
   context-dependent licenses remain blocking; the repository cannot self-approve
   them.
2. Review the 18 recorded patch-SLA breaches and all 105 dismissed Dependabot
   alerts. Bind every accepted exception to an owner, reason, expiry, and VEX or
   risk-decision record; do not rewrite the observed historical result. The 105
   dismissed alerts are already represented as `UNDER_INVESTIGATION`, never
   inferred as `NOT_AFFECTED`.

## Inputs that must come from accountable external actors

1. A holdout corpus and a representative workload whose authorship is
   independent from implementation and whose exact bytes may be disclosed to
   the gate only after implementation is frozen.
2. An independently controlled execution environment and verifier identity,
   distinct from the executor, that reproduce the complete evidence set.
3. Production artifact/container signature, trusted-builder provenance, hosted
   runner attestation, tamper-rejection result, and tenant-isolation evidence.
4. An independent security assessment and closure record for every finding.
5. An accountable approver that includes the `program.json` owner.
6. A certification key held outside the repository and a separate, non-revoked
   trust store authorizing that key for Batch 40.

## Fail-closed gate sequence

After those facts exist, refresh local evidence and gaps, then run:

```bash
make batch40-evidence PACK=elmos-platform-supply-chain
make batch40-gaps PACK=elmos-platform-supply-chain

make batch40-manifest \
  PACK=elmos-platform-supply-chain \
  ARTIFACT=artifact/schema-surface.json \
  ENVIRONMENT=environment/toolchain.json \
  EXECUTOR=<exact-executor-id> \
  VERIFIER=<independent-verifier-id> \
  AUTHORIZATION=<approved-authorization-ref> \
  REPLAY='<exact replay command>' \
  STARTED_AT=<ISO-8601> \
  FINISHED_AT=<ISO-8601>

make batch40-request \
  PACK=elmos-platform-supply-chain \
  KEY_ID=<offline-certification-key-id>

openssl dgst -sha256 -sign <offline-private-key.pem> \
  -out mature-product-packs/batch40/elmos-platform-supply-chain/certification-request.sig \
  mature-product-packs/batch40/elmos-platform-supply-chain/certification-request.json

make batch40-gate \
  PACK=elmos-platform-supply-chain \
  TRUST_STORE=<independently-controlled-trust-store.json>
```

Do not run the manifest command unless verifier and corpus independence are
facts rather than labels. Do not commit private keys or replace the external
trust store with a repository-generated key. The only authority allowed to
change the final status is the conservative Batch 40 gate.
