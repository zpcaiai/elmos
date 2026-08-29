# Policy Model

Use a two-layer design:

- **Decision policy** (OPA-style): model/tool/network/build/deploy/security/compliance decisions.
- **Application authorization** (Cedar/relationship-style): who may perform which action on which tenant/repository/branch/environment/resource.

Minimum context:
`principal, tenant, role, agent, skill, tool, model, repository, revision, environment, resource, action, riskTier, requestedNetwork, requestedSecrets, costBudget`.

Default posture: deny privileged operations unless explicitly allowed. Approval is a policy outcome, not a UI-only convention.
