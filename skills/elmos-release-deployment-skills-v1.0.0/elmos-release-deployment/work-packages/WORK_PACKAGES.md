# Work packages

## RD-00 Domain contracts
Create IDs/value objects, state machine, schemas and persistence mappings.
Exit: serialization + invariant tests pass.

## RD-01 CertifiedRelease bridge
Consume existing Elmos Assurance outputs and create immutable release manifest.
Exit: uncertified/mismatched digest release creation is rejected.

## RD-02 DeploymentTicket + OPA Gate
Implement ticket issue/validate/expire/revoke and production policy checks.
Exit: scope/expiry/digest/environment negative tests pass.

## RD-03 Target Registry + Alibaba read-only probe
Register existing ECS targets and perform capability discovery.
Exit: wrong account/region/resource/tag targets are rejected.

## RD-04 STS CredentialBroker + CapabilityLease
Implement short-lived session acquisition and scope fencing.
Exit: expired/overbroad lease calls are denied.

## RD-05 ACR artifact resolver
Resolve by digest, never deploy mutable tag without resolving/persisting digest.
Exit: tag mutation cannot change a prepared deployment.

## RD-06 CloudAssistantExecutor
Implement submit/poll/cancel/result capture, deterministic templates, output redaction, retries and external invocation ID persistence.
Exit: crash/retry does not duplicate unsafe mutations.

## RD-07 DockerHostRuntime
Implement runtime preflight, image pull by digest, versioned container/Compose activation and previous-state snapshot.
Exit: single Spring/Vue/Python/.NET smoke deployments pass.

## RD-08 Config + SecretResolver
Implement config schema validation and secret-reference-only injection.
Exit: secret scanner confirms no secret values in persisted logs/evidence.

## RD-09 MigrationController
Detect/classify Flyway/Liquibase/Alembic/Django/EF Core migration plans.
Exit: destructive production migration denied without dedicated authorization.

## RD-10 Health + Smoke verification
Implement layered probes and configurable retry/backoff/deadline.
Exit: delayed-start, bad-port, bad-health and functional failure cases behave deterministically.

## RD-11 RollbackManager
Restore prior image/config/traffic and verify rollback.
Exit: post-mutation health failure automatically restores prior stable release.

## RD-12 DeploymentEvidence
Create immutable evidence bundle and commit only after step results are collected.
Exit: evidence contains all required digests/provider IDs and passes schema validation.

## RD-13 Temporal workflow
Compose RD-00..12 into resumable workflow with per-environment mutex and concurrency quota.
Exit: worker kill/restart at every major step resumes safely.

## RD-14 Full-stack bundle
Support backend + Vue/Nginx Compose bundle on one ECS; external DB/Redis bindings for production.
Exit: generated full-stack sample deploys and rolls back.

## RD-15 Product API/UI contract
Expose plan/preview/apply/status/log/evidence/rollback APIs.
Exit: one-click UX can be implemented without privileged direct cloud access from frontend.

## P1
RD-20 multi-ECS rolling batches
RD-21 canary + ALB/SLB traffic control
RD-22 DNS/TLS automation
RD-23 IaC environment provisioning
RD-24 ACR scan/signing gate
RD-25 preview environments + TTL cleanup
RD-26 SLS/CloudMonitor/OTel deployment annotations

## P2
RD-30 ACK/Kubernetes provider
RD-31 Helm/GitOps bridge
RD-32 progressive delivery/SLO rollback
RD-33 multi-cloud providers
