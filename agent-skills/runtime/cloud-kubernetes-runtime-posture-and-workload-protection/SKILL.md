---
name: cloud-kubernetes-runtime-posture-and-workload-protection
description: Assess cloud accounts, IAM, network, storage, databases, Kubernetes, container runtime, hosts, serverless, registries, and CI runners. Use for posture and workload-protection modernization.
---

# Cloud and Runtime Protection

1. Separate organization/account posture from network, platform, host, and workload findings.
2. Discover root/owner use, MFA gaps, long-lived keys, wildcard grants, cross-account trust, public resources, anonymous access, and metadata exposure.
3. Validate Kubernetes admission enforcement, RBAC, service accounts, privilege, host access, seccomp, network policy, image policy, resources, API exposure, and audit in the target environment.
4. Version process, file, network, user, syscall, port, DNS, and dependency runtime baselines by image and deployment.
5. Include serverless roles, secrets, triggers, layers, network, logging, concurrency, dependencies, and poison-event behavior.
6. Send remediation back to IaC, policy, identity, network, or image sources; avoid untracked production fixes.

## Acceptance

A policy file without observed enforcement is `NOT_IMPLEMENTED`; an unexpected shell or credential-access event retains workload, identity, image, and trace evidence.
