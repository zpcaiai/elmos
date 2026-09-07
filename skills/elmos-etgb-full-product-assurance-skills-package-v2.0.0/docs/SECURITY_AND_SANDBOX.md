# Security and sandbox

Untrusted source, generated code, dependencies and tests run in isolated, non-root, resource-limited Environments. Network is denied by default; package registries and services require explicit allowlists/proxies. Secrets are named references scoped to the owning Environment.

Authority is Environment/Attachment-owned, bound to tenant/owner/fencing/expiry and checked at the tool boundary. Transformation workers cannot read/write hidden tests. Validation workers cannot mutate source/target. Release workers cannot alter results or gate policy.

Scan archives, symlinks, submodules, binaries, build scripts, dependency confusion, Prompt injection, secrets and PII. Produce SBOM/provenance and quarantine suspicious artifacts. Preserve raw restricted evidence and separately publish redacted derivatives.

Cross-tenant database/object/cache/trace access, stale fencing side effects, hidden-test leakage, secret exposure or sandbox escape are P0.
