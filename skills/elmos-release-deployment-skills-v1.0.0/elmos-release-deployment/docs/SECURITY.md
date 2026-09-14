# Security model

## Authority chain

`User/Automation -> DeploymentTicket -> Policy decision -> CapabilityLease -> CredentialBroker -> Provider Adapter`

The cloud provider credential alone is not authorization. The adapter must verify ticket and lease scope on every mutating call.

## CapabilityLease

Must bind:

- tenant/project/environment
- deployment_id/ticket_id
- allowed provider
- allowed account/role
- allowed region
- exact instance IDs or selector digest
- allowed operations
- expiry
- nonce/lease ID

## Remote execution

- default to a dedicated `elmos-deploy` OS user when practical
- deny arbitrary user-selected root scripts in production
- command templates are versioned and checksummed
- redact environment variables and command outputs
- enforce execution timeout/resource limits
- do not expose secrets in process arguments

## Supply chain

P0:
- digest pinning
- SBOM
- vulnerability gate
- provenance/evidence digest

P1:
- image signing and verification
- KMS-backed signing / Sigstore/in-toto bridge
- policy requires valid attestation before production

## Audit

Every provider call and remote command must be attributable to deployment/ticket/actor and correlated to immutable evidence.
