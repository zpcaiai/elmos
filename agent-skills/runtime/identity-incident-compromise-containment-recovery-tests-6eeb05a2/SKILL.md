---
name: identity-incident-compromise-containment-recovery-tests-6eeb05a2
description: "Implement identity-security incident response for compromised human and machine credentials, workload identities, IdPs, SCIM clients, OAuth clients, JIT and break-glass misuse, with containment, blast-radius analysis, recovery drills, security tests, and mandatory release evidence."
---

# Objective

Ensure ELMOS can contain and recover from identity and credential compromise
without relying on service restarts or manual database edits.

# Incident types

```text
HUMAN_ACCOUNT_COMPROMISE
SESSION_THEFT
API_TOKEN_LEAK
OAUTH_CLIENT_COMPROMISE
PRIVATE_KEY_COMPROMISE
WORKLOAD_IDENTITY_THEFT
RUNNER_IDENTITY_THEFT
AGENT_IDENTITY_THEFT
SCIM_CLIENT_COMPROMISE
SAML_IDP_COMPROMISE
SAML_CERTIFICATE_COMPROMISE
SECRET_PROVIDER_COMPROMISE
MALICIOUS_PRIVILEGED_ADMIN
JIT_GRANT_MISUSE
BREAK_GLASS_MISUSE
CROSS_TENANT_ACCESS_ATTEMPT
REVOCATION_FAILURE
