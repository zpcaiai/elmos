---
name: github-app-integration
description: Build or review ELMOS GitHub App authentication, installation discovery, repository authorization, and short-lived installation-token brokering without persisting credentials. Use for SCM onboarding, private repository access, GitHub API adapters, or credential lease code.
---

# GitHub App Integration

Implement GitHub access as a narrow, audited port. Treat every installation token as an in-memory secret, never as repository metadata.

## Required workflow

1. Resolve the GitHub App installation and confirm the requested repository belongs to it.
2. Mint an installation access token scoped to explicit `repository_ids` and the minimum permissions for the operation.
3. Reject a token whose expiry exceeds one hour or whose permission set is broader than requested.
4. Return the value through an `AutoCloseable` secret wrapper and zero it on close.
5. Persist only lease metadata: provider, installation, repository, permissions, issue/expiry times, status, and audit correlation.

## Non-negotiable boundaries

- Never store or log the raw installation token, App private key, JWT, or authorization header.
- Never accept a personal access token as the normal production path.
- Never mint an organization-wide token when one repository suffices.
- Use an injectable clock and issuer port so expiry and scope behavior have deterministic tests.
- Fail closed when repository authorization, installation identity, expiry, or permissions cannot be proved.

## Acceptance checks

- Tests prove unauthorized repositories and excessive TTL/permissions are rejected.
- Tests prove closing the credential clears its backing character array.
- A persistence test demonstrates no token-shaped value is written.
- Audit records identify the operation without containing credentials.

