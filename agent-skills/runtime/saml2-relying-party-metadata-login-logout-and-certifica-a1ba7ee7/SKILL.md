---
name: saml2-relying-party-metadata-login-logout-and-certifica-a1ba7ee7
description: "Implement database-backed multi-tenant SAML 2 relying-party registrations, metadata refresh and verification, SSO, replay protection, login exchange, logout, and certificate rotation."
---

# Objective

Implement enterprise SAML login without exposing SAML assertions or
provider credentials to browser JavaScript.

Target flow:

Browser
→ Next.js SAML start route
→ control-api SAML AuthnRequest endpoint
→ enterprise IdP
→ control-api ACS endpoint
→ validated SAML authentication
→ one-time federation login exchange code
→ Next.js server callback
→ normal Batch 34A server-side session
→ tenant membership and resource authorization

# Framework requirement

Use the repository-managed Spring Security version and:

- spring-security-saml2-service-provider;
- Spring Security RelyingPartyRegistration;
- supported OpenSAML integration;
- Spring Security metadata and logout facilities.

Do not parse, decrypt, or verify SAML XML manually.

# Persistent SAML connection model

Create:

```text
iam.saml_connections
iam.saml_connection_versions
iam.saml_metadata_snapshots
iam.saml_attribute_mappings
iam.saml_certificates
iam.saml_replay_records
iam.saml_login_exchanges
iam.saml_authentication_events
