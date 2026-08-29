# Security Model

## Threats

- malicious or compromised repository code
- prompt injection in source, comments, issues, or documentation
- generated command privilege expansion
- credential exfiltration
- dependency and build-script execution
- sandbox escape
- supply-chain substitution
- cross-tenant artifact leakage
- duplicate side effects after retry
- false readiness claims

## Controls

- immutable source snapshot and provenance
- deny-by-default scope and tool policy
- minimal context and model-routing policy
- isolated sandbox or private runner
- network allowlists and package mirrors
- short-lived secret handles
- command, argument, path, resource, and diff limits
- human approval for privileged or irreversible actions
- SBOM, signatures, checksums, provenance, vulnerability and license checks
- durable checkpoints, fencing tokens, idempotency, and compensation
- evidence freshness and bounded readiness certificates

Prompt instructions are not an enforcement boundary. Controls must exist in the Runner and control plane.
