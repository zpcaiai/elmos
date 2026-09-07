---
name: break-glass-emergency-access-dual-control-and-post-review
description: "Implement tightly constrained emergency access for identity-provider outages, critical incidents, and recovery, with dual control, sealed credentials, minimal scope, alerts, action evidence, automatic revocation, and mandatory post-use review."
---

# Objective

Provide a recoverable emergency path without creating a hidden permanent
super-admin path.

Break-glass is used only when the normal identity or authorization path
cannot safely perform an urgent recovery action.

# Emergency use cases

```text
IDENTITY_PROVIDER_OUTAGE
ELMOS_CONTROL_PLANE_RECOVERY
TENANT_LOCKOUT_RECOVERY
CRITICAL_SECURITY_INCIDENT
RUNNER_FLEET_RECOVERY
DATABASE_RECOVERY_COORDINATION
AUDIT_RECOVERY
