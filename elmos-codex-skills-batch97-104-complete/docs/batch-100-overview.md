# Batch 100 — Hardened Runner Fabric Pack

## Purpose

Hardens the private execution plane so untrusted repositories and generated code cannot escape declared boundaries.

System objective: secure runner enrollment, workload identity, mTLS, attestation, task signatures, sandboxing, isolation, egress, secrets, quotas, signed artifacts, fleet routing, revocation and certification.

## Inventory

- Skills: **16**
- Stable local IDs: **B100-S01–B100-S16**
- Global IDs: intentionally unassigned to avoid collision with the user's existing Batch 81–96 package.

| ID | Skill | Title | Purpose |
|---|---|---|---|
| B100-S01 | `b100-runner-enrollment-workload-identity` | Runner Enrollment and Workload Identity | Enroll runners with unique short-lived workload identities and explicit tenant or fleet ownership. |
| B100-S02 | `b100-runner-mtls-channel` | Runner mTLS Channel | Establish mutually authenticated, rotated and policy-bound runner control channels. |
| B100-S03 | `b100-runner-attestation-posture` | Runner Attestation and Posture | Attest runner software, image, kernel, configuration and policy posture before sensitive tasks. |
| B100-S04 | `b100-signed-task-envelope-verifier` | Signed Task Envelope Verifier | Verify task signature, nonce, audience, scope, expiry and capability manifest before claim. |
| B100-S05 | `b100-sandbox-profile-selector` | Sandbox Profile Selector | Select container, microVM, VM, device or isolated-host profiles based on risk and tool requirements. |
| B100-S06 | `b100-workspace-filesystem-isolation` | Workspace and Filesystem Isolation | Create per-task isolated workspaces with safe mounts, path controls, cleanup and residue detection. |
| B100-S07 | `b100-process-execution-allowlist` | Process Execution Allowlist | Execute only inspected, declared and policy-authorized commands without arbitrary shell escape. |
| B100-S08 | `b100-network-egress-control` | Network Egress Control | Apply default-deny DNS, IP, port, protocol and identity-aware egress controls per task. |
| B100-S09 | `b100-secret-broker-redaction` | Secret Broker and Redaction | Inject task-scoped secrets by reference, redact all surfaces and revoke immediately after use. |
| B100-S10 | `b100-resource-quota-enforcer` | Resource Quota Enforcer | Enforce CPU, memory, disk, inode, process, network and wall-clock budgets against hostile workloads. |
| B100-S11 | `b100-artifact-signing-upload` | Artifact Signing and Upload | Hash, sign, scan and upload artifacts through content-addressed, tenant-isolated channels. |
| B100-S12 | `b100-runner-lease-cancel-protocol` | Runner Lease and Cancel Protocol | Coordinate task leases, heartbeat, cancellation, result fencing and stale runner behavior. |
| B100-S13 | `b100-fleet-routing-capability-match` | Fleet Routing and Capability Match | Route tasks to compatible, healthy and authorized runners by platform, toolchain, trust and locality. |
| B100-S14 | `b100-runner-upgrade-drain` | Runner Upgrade and Drain | Patch runners safely through staged rollout, drain, rollback and version compatibility checks. |
| B100-S15 | `b100-runner-quarantine-revocation` | Runner Quarantine and Revocation | Quarantine compromised or unhealthy runners, revoke credentials and preserve forensic evidence. |
| B100-S16 | `b100-runner-fabric-certification-gate` | Runner Fabric Certification Gate | Certify runner profiles only after identity, attestation, isolation, malicious workload, cancellation and recovery tests pass. |

## Batch completion gate

The Batch is not complete merely because these Markdown files validate. Completion requires implementation in the target ELMOS repository, real integration tests, failure-path evidence, exact scope binding and the final Batch certification Skill result.
