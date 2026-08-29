# Security

## Reporting

Report suspected vulnerabilities privately to the owner of the ELMOS deployment. Do not include credentials, proprietary source, or customer data in public issues.

## Package security properties

- deny-by-default sample runner policy
- bounded agent patch policy
- immutable snapshot and evidence freshness model
- no embedded credentials
- static secret and private-key scan in validation
- readiness cannot pass from static file presence

## Deployment responsibility

This package is not a sandbox by itself. An implementation must enforce isolation, command/path/network policy, short-lived secrets, resource limits, approvals, audit, tenant separation, and idempotent external side effects in the control plane and Runner.
