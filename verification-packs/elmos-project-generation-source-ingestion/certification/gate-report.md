# Batch 35 gate: elmos-project-generation-source-ingestion

- Pack status: `limited`
- Structural gate status: `passed`
- Certification decision: `NOT_CERTIFIED`
- Certification readiness: `BLOCKED`
- Evaluated pack digest: `sha256:c5bf32aa4e3e732941f46dab35bd13745f6d5884df0d52bb99556195bd9f3107`

## Certification blockers
- pack and certification status must both request certified
- representative_workload_pass_rate below 1.0
- assurance_claim_support_rate below 1.0
- critical_unknown_obligations must be explicitly zero
- unsupported_p0_claims must be explicitly zero
- holdout corpus is not independently verified
- holdout corpus independent verifier missing
- representative workload corpus is not production-derived
- representative workload authorization record is missing, invalid, or not content-bound locally
- assurance claim claim.source-boundaries is not fully supported
- assurance case approvals empty
- validation profile approvals empty
- oracle registry approvals empty
- certification approval timestamp missing
- P0 claim claim.source-boundaries has no independent external oracle evidence
- scope controlled_public_dns_rebinding_campaign must be passed (found 'NOT_RUN')
- scope independent_holdout must be passed (found 'LOCAL_EXECUTED_NOT_INDEPENDENTLY_VERIFIED')
- scope representative_production_workload must be passed (found 'NOT_RUN')
