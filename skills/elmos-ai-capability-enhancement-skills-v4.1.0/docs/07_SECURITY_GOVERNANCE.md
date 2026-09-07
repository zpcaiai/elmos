# Security and Governance Architecture

## Threat model

The factory assumes all of the following can be adversarial or wrong:

- user prompts and uploaded files;
- retrieved documents and web content;
- target DSLs, plugins, skills and generated code;
- model outputs and tool arguments;
- package registries and upstream dependencies;
- external tools, agents and protocol peers;
- stale workers and resumed sessions;
- cross-tenant identifiers and cache keys;
- operator actions and approval expiry;
- incomplete or misleading evidence.

The design therefore separates suggestion from authority and execution from certification.

## Identity and tenancy

Required identities:

- human caller;
- service/control-plane workload;
- agent role;
- environment/workspace;
- tool request;
- external peer (MCP/A2A);
- certifier/signer.

Every persistent row and artifact is tenant-bound. PostgreSQL RLS is the default relational control; object-store prefixes, vector namespaces, cache keys, event topics and traces carry equivalent tenant/project scope.

Cross-tenant tests include:

- guessed IDs and direct object references;
- shared cache/vector results;
- resumed run under a different session;
- tool result attached to the wrong Goal;
- evidence/certificate retrieval;
- admin and support break-glass paths.

## Environment-owned authority

Authority is captured at environment/attachment/tool-request boundaries and contains:

- exact tenant/project/Goal/RevisionSet;
- execution epoch, lease generation and fencing;
- allowed tools and operations;
- path and parameter scopes;
- egress destinations and purposes;
- secret references;
- approvals and expiry;
- data classes/provider eligibility;
- resource and cost bounds.

A thread-wide or agent-wide allow list is insufficient because different attached workspaces, servers and tools can have different owners and risk.

## Secretless two-phase execution

### Setup phase

May use separately authorized network and registry credentials to resolve dependencies or build images. Outputs are content-addressed and scanned.

### Execution phase

- no plaintext production secret in workspace;
- brokered short-lived tokens only when required;
- deny-network by default;
- non-root/read-only root where possible;
- no Docker socket;
- resource quotas and kill switch;
- sanitized logs/evidence;
- ephemeral workspace and cleanup attestation.

## Tool security

Each tool contract declares effect and risk. High-risk classes include:

- external communications;
- payments/purchases;
- source/deployment writes;
- database/schema mutations;
- identity/permission changes;
- browser/computer-use actions;
- code execution;
- device/industrial control.

Controls:

1. typed inputs and output validation;
2. request-scoped authority;
3. idempotency key;
4. approval for policy-selected effects;
5. allowlisted destination/path/parameter;
6. timeout/resource limit;
7. isolated execution;
8. result/postcondition verification;
9. side-effect ledger and reconciliation;
10. immutable audit/evidence.

## Prompt and indirect injection

A model cannot convert untrusted text into authority. Generated systems must:

- label source trust;
- separate content from instructions;
- avoid exposing secrets or broad tool capabilities to retrieved text;
- validate tool intent against Goal and policy;
- require current approval for sensitive actions;
- sanitize/encode tool output before reinjection;
- detect cross-domain and instruction-override patterns;
- preserve attack traces and regression cases.

Security is enforced outside the model even when model-based classifiers add defense in depth.

## Plugins, skills and extensions

Pi packages, Harness plugins, OpenClaw plugins/skills, Dify plugins and coding-agent rules can execute code or influence tool use. Treat them as supply-chain components:

- source and publisher provenance;
- review and signature;
- SBOM/license/vulnerability scan;
- exact digest;
- declared permissions and egress;
- isolated conformance;
- update policy;
- kill switch and rollback;
- tenant placement policy.

An imported `SKILL.md` or visual component is never trusted merely because it parses.

## Provider and data governance

The routing decision evaluates:

- data classification;
- customer/tenant policy;
- geographic processing/storage;
- retention and training use;
- encryption and key requirements;
- private endpoint/VPC options;
- provider availability and fallback;
- model capability;
- cost/latency;
- audit and contractual status.

Fallback cannot silently route confidential content to an ineligible provider.

## Evidence security

Evidence storage should be WORM/append-only or equivalently tamper-evident. It records hashes and controlled redacted views. Redaction does not change the canonical evidence hash; access control decides which view is exposed.

Certificates are signed and revocable. Drift, vulnerability, policy change, compromised signer or evidence inconsistency can revoke them.

## Required security campaigns

- direct and indirect prompt injection;
- tool-name/description confusion;
- parameter smuggling;
- authority and approval replay;
- stale fencing and duplicate side effects;
- path traversal and symlink;
- network/SSRF and DNS rebinding;
- secret/log leakage;
- cross-tenant data, memory, cache and vector leakage;
- malicious plugin/skill/package;
- model/provider fallback policy bypass;
- poisoned memory and RAG corpus;
- unsafe browser/computer-use;
- denial of service and budget exhaustion;
- evidence/certificate tampering.

A production certificate names the campaign corpus version and residual risk.
