# Runbook: Adoption Change Management

## Entry conditions

- An existing canonical route owner has selected `adoption-change-management`.
- The TaskContract, RevisionSet, policy profile, required evidence obligations, and capability lease are valid.
- The workspace and execution environment are owned by the current Turn/Invocation, not by thread-global mutable state.
- Required local dependencies have completed on compatible revisions.

## Procedure

1. Map changed workflows and affected user groups.
2. Identify adoption barriers and required training assets.
3. Define cohort rollout, support, and feedback collection.
4. Instrument adoption and quality metrics.
5. Run training, office hours, and feedback review.
6. Complete handoff only when support ownership and runbooks are accepted.

## Operational checks

- Emit start, checkpoint, tool-result, policy-decision, artifact, failure, completion, and cancellation telemetry.
- Record model, tool, compiler, database, environment, policy, Skill, Adapter, and artifact versions.
- Keep model/compute/storage/network/license cost separate from human review.
- Report machine wall-clock and queue time; never disguise human elapsed time as machine execution.

## Failure handling

1. Stop new side effects and capture the exact failure boundary.
2. Append the tool result, error, environment state, and affected artifacts to the Evidence/Effect Ledgers.
3. Classify failure as source, environment, dependency, authority, policy, unsupported, unknown, verifier, or external service.
4. Resume only from a valid checkpoint with lossless authority replay and unchanged input identities.
5. Roll back code through atomic revert/workspace discard; compensate data or external effects through the approved route-specific procedure.
6. Escalate material security, data-integrity, irreversible, or customer-impacting failures to human authority.

## Completion handoff

Submit typed outputs, claims, evidence, counterexamples, unknowns, residual risks, and rollback records to an independent verifier. K8 alone records completion/readiness. This runbook does not authorize E4/E5 or production release.
