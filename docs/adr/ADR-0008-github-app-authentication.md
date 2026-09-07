# ADR-0008: GitHub App authentication

Status: Accepted

## Decision

ELMOS uses GitHub App installation tokens for GitHub repository access. The broker verifies installation-to-repository authorization, requests only explicit repository ids and operation-specific permissions, caps expiry at one hour, keeps values only in closeable memory, and persists metadata/audit records without token values.

## Consequences

Personal access tokens are not the production integration path. Live private-repository acceptance requires an installed App and cannot be replaced by a simulated token test.
