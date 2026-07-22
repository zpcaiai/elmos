---
name: b37-extension-sandbox-test-harness
description: "Implement a hardened extension sandbox and conformance test harness for filesystem network process secret model repository resource and tenant boundaries."
---

# Skill 1317: b37-extension-sandbox-test-harness

## Use this skill when

- Untrusted extensions must be executed before publication or installation.
- Existing tests run extensions with host privileges.

## Domain-specific risks and invariants

- Sandbox escape or excessive permissions can compromise customer code and platform infrastructure.
- A permissive test harness can certify behavior that production blocks.

## Workflow

1. Define sandbox policy with deny-by-default permissions and exact capability grants.
2. Implement isolated filesystem, process, network, resource, time, secret, model, repository, and tenant controls.
3. Build conformance and adversarial harnesses for each SDK kind.
4. Record syscall/network/resource and policy-decision evidence.
5. Test escape attempts, fork bombs, path traversal, metadata endpoints, credential theft, covert egress, and cross-tenant access.

## Required repository outputs

- sandbox policy and runtime profile
- SDK-specific conformance harnesses
- adversarial corpus and execution evidence

## Verification

- Run tests in the same isolation class used for certification.
- Verify undeclared permissions fail before extension execution.
- Verify cleanup removes processes, files, mounts, and credentials.

## Stop and escalate when

- Required isolation primitive is unavailable.
- A sandbox escape or hidden network dependency is found.

## Definition of done

- All extension kinds execute with declared least privilege.
- Adversarial tests prove boundaries.
- Cleanup and revocation work.
