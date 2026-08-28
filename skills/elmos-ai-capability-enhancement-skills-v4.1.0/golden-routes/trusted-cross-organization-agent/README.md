# Elmos Trusted Cross Organization Agent

**Status:** not-certified  
**Owner:** `domain-pack.project-generation`  

## Commercial objective

Enterprise agent requiring cross-organization discovery, delegated execution and auditable revocation is transformed into the declared targets without transferring semantic, execution or completion authority to a provider.

## Mandatory execution

1. compile-agent-card
1. sign-and-verify
1. discover-and-pin
1. attest-workload
1. issue-delegated-credential
1. run-a2a-task
1. revoke-and-audit

## Native evidence

- signed Agent Card verification
- workload attestation
- scope-reducing token exchange
- cross-tenant isolation
- revocation propagation
- task and side-effect audit

## Holdout and negative cases

- expired Agent Card
- untrusted federation
- scope expansion request
- revoked workload identity

## Completion boundary

The route may be reported as structurally available after package validation, but only an independent K8 certificate bound to current native evidence may report E5/P05 completion.
