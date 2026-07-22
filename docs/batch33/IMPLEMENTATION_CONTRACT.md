
# Batch 33 implementation contract

## Goal

Implement directional, exact, evidence-backed Cloud, IaC, and DevOps modernization packs. A pack is scoped to an exact source tuple and exact target tuple: provider, region set, account hierarchy, IaC tool and version, runtime or orchestrator, CI/CD system, state backend, identity model, network topology, and service set.

## Required implementation chain

1. Capture static source definitions and runtime inventory.
2. Freeze a source fingerprint and source snapshot digest.
3. Emit a typed Runtime Architecture Contract and provider-neutral IaC IR.
4. Select an exact target profile and map each capability with deterministic transformations or explicit adapters.
5. Run real source and target plan or equivalent validation.
6. Apply to an approved ephemeral account, subscription, project, cluster, emulator, or local integration environment when certification requires runtime evidence.
7. Exercise P0 workloads, identity, network, DNS, secrets, rollout, observability, security, cost, drift, rollback, and destroy behavior.
8. Run independent holdout and representative workloads.
9. Emit evidence and let the conservative gate determine the strongest support status.

## Non-negotiable rules

- Do not implement complex IaC migration using regex or string replacement as the semantic core.
- Never broaden IAM, network ingress, egress, encryption, data residency, or secret access to make a deployment work.
- Never store credentials in generated IaC, CI configuration, logs, plans, state, or model context.
- Preserve resource lifecycle, identity, dependencies, availability, health checks, scaling, rollout, backups, retention, observability, and recovery semantics.
- Record every unsupported, conditional, lossy, provider-specific, and unknown behavior.
- Use immutable image and module digests where the target supports them.
- Test cleanup and destroy. Orphaned cloud resources are certification failures.
- Keep development, negative, holdout, and representative workload corpora independent.
