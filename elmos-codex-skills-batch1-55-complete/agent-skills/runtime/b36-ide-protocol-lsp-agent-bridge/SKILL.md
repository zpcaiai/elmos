---
name: b36-ide-protocol-lsp-agent-bridge
description: "Implement a versioned secure IDE protocol language-server and local-agent bridge for navigation diagnostics previews repairs tests approvals and evidence without granting unrestricted repository access."
---

# Skill 1288: b36-ide-protocol-lsp-agent-bridge

## Use this skill when

- An IDE extension needs a stable protocol to communicate with local or remote migration services.
- Language Server Protocol concepts must be extended with migration-specific artifacts and policy decisions.

## Domain-specific risks and invariants

- A local agent bridge can become an unrestricted shell or source-code exfiltration path.
- Protocol retries, stale documents, and mismatched artifact versions can apply actions to the wrong code.

## Workflow

1. Inventory existing LSP, JSON-RPC, local daemon, control-plane, and runner contracts.
2. Define protocol versioning, capability negotiation, request IDs, cancellation, deadlines, authentication, tenant/project scope, document versions, artifact digests, and error envelopes.
3. Define typed methods for preview, source-target navigation, explanation, diagnostics, quick fixes, local eval, review, and evidence retrieval.
4. Implement a least-privilege local bridge with explicit tool and path allowlists.
5. Add compatibility tests for N-1/N/N+1 clients and servers plus replay, cancellation, timeout, and malformed-message tests.

## Required repository outputs

- `protocol/ide-protocol.json` and generated client/server bindings
- Protocol conformance tests, compatibility matrix, threat model, and bridge sandbox configuration
- Request/response traces linked to artifact and document versions

## Verification

- Validate the protocol schema and generated bindings.
- Run real client/server handshake and capability negotiation.
- Test stale document rejection, cancellation, replay, cross-tenant requests, path traversal, and unknown methods.
- Verify local bridge commands are allowlisted and arguments are structured rather than shell-concatenated.

## Stop and escalate when

- A method cannot bind to an immutable document version or artifact digest.
- The bridge requires arbitrary shell, filesystem, network, or secret access.
- Protocol compatibility cannot be maintained for a supported client version.
- Cancellation or retry can produce duplicate repository changes.

## Definition of done

- Every supported method is versioned, typed, cancellable, traceable, and policy-enforced.
- Real IDE clients communicate through the protocol without privileged backdoors.
- Negative security and compatibility tests pass.
- Protocol evidence is included in the Batch 36 certification pack.
