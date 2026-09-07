---
name: infrastructure-as-code-import-state-drift-and-policy
description: Import existing infrastructure into governed IaC, establish no-change baselines, secure state, pin providers, classify drift, analyze plans, and gate apply operations. Use for OpenTofu, Terraform-compatible, CloudFormation, Bicep, Pulumi, Ansible, Helm, or Kustomize.
---

# Infrastructure as Code Governance

## Import workflow

1. Discover and match each remote resource to an organization-scoped canonical identity.
2. Generate reviewed import candidates and configuration.
3. Import into an encrypted, versioned, locked, backed-up, audited remote state with tenant-isolated keys.
4. Refresh and achieve an explained no-change baseline before refactoring.
5. Pin provider source and version, preserve lockfile hashes/signatures, licenses, regions, credentials, and compatibility results.
6. Generate a Plan that itemizes create, update, replace, delete, exposure, IAM, encryption, region, cost, data, downtime, state moves, and provider upgrades.
7. Run policy, cost, security, residency, and approval gates before apply.
8. Classify drift as expected operational, emergency, unauthorized, provider-default change, recreated, incomplete import, or unknown.

Allow automatic apply only where an explicit policy permits development scope. Require named manual production approval; require stronger approval for replace, destroy, IAM, public access, state move, or provider upgrade.

Agents may generate candidates, import blocks, modules, policy fixes, and documentation. Never let an Agent apply production, delete/unlock state, cross tenant boundaries, or auto-accept replace/destroy.

