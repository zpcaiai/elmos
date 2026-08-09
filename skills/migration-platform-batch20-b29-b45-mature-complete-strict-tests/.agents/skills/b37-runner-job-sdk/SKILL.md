---
name: b37-runner-job-sdk
description: Implement a Runner Job SDK for declared inputs outputs resources permissions leases cancellation checkpoints telemetry and isolated extension execution.
---

# Skill 1313: b37-runner-job-sdk

## Use this skill when

- Extensions need to execute tasks on private or managed runners.
- Custom jobs currently bypass the standard runner contract.

## Domain-specific risks and invariants

- Unbounded jobs can escape sandboxes consume fleet capacity or retain credentials.
- Retries can duplicate external side effects.

## Workflow

1. Define typed job manifest, input/output artifacts, image digest, resource limits, network/filesystem/secret permissions, lease, idempotency key, checkpoints, cancellation, and evidence.
2. Generate SDK client and reference job.
3. Integrate attestation, short-lived credentials, sandbox, quota, and egress controls.
4. Test retries, worker loss, cancellation, timeout, checkpoint resume, and duplicate delivery.
5. Publish only signed jobs with approved runtime dependencies.

## Required repository outputs

- runner job SDK and job schema
- reference job and local harness
- resource permission and recovery evidence

## Verification

- Execute in an approved sandbox or runner.
- Verify duplicate delivery does not duplicate side effects.
- Verify revoked jobs cannot acquire leases.

## Stop and escalate when

- The job requires privileged host access or undeclared egress.
- Idempotency or cleanup cannot be proven.

## Definition of done

- External jobs use the standard lease and evidence protocol.
- Resource and permission limits are enforced.
- Failure recovery is deterministic.
