# Policy as Code, SBOM, SLSA Provenance, and Artifact Signing

- Skill: `elmos-policy-supply-chain-signing`
- Priority: `P1`
- Phase: `G7`
- Dependencies: `elmos-identity-tenant-security`, `elmos-reproducible-toolchain`, `elmos-secure-sandbox-runtime`

## Objective

Make security, compliance, license, model, tool, network, and release decisions explicit, versioned, testable, and auditable.

## Task groups

### Policy engine and contract

- [ ] `ELMOS-POL-001` Integrate OPA/Rego or equivalent with versioned signed policy bundles.
- [ ] `ELMOS-POL-002` Define decision input/output with subject, tenant, resource, action, context, policy digest, allow/deny, rules, reasons, obligations, and expiry.
- [ ] `ELMOS-POL-003` Evaluate user/resource authorization, runner/action, sandbox, egress, secrets, model/provider, cache sharing, artifact export, license, vulnerability, budget override, approval, and production promotion.
- [ ] `ELMOS-POL-004` Cache only safe policy decisions with exact identity/context and short TTL.
- [ ] `ELMOS-POL-005` Fail closed for high-risk operations when policy is unavailable.

### Exception governance

- [ ] `ELMOS-POL-006` Require owner, scope, justification, compensating controls, approver, creation, expiry, and ticket for exceptions.
- [ ] `ELMOS-POL-007` Prevent permanent wildcard exceptions.
- [ ] `ELMOS-POL-008` Warn before expiry and automatically stop applying expired exceptions.
- [ ] `ELMOS-POL-009` Include exceptions in risk/evidence/certification decisions.
- [ ] `ELMOS-POL-010` Audit creation, use, renewal, and revocation.

### SBOM and dependency assurance

- [ ] `ELMOS-POL-011` Generate SBOM for toolchain images, adapters, skills/rules where applicable, and generated/converted projects.
- [ ] `ELMOS-POL-012` Scan vulnerabilities, licenses, secrets, containers, lockfiles, unpinned dependencies, typosquatting, dependency confusion, malicious packages, and provenance gaps.
- [ ] `ELMOS-POL-013` Distinguish source, build, test, runtime, optional, and transitive dependencies.
- [ ] `ELMOS-POL-014` Define severity/age/exploitability/usage-aware blocking policy.
- [ ] `ELMOS-POL-015` Rescan retained deliverables as intelligence changes and issue updated evidence without mutating old packs.

### Build provenance

- [ ] `ELMOS-POL-016` Generate provenance recording builder identity/version, source snapshot, action, toolchain, dependencies, parameters, policy, environment, outputs, and timestamps.
- [ ] `ELMOS-POL-017` Bind provenance to immutable digests and authenticated isolated builders.
- [ ] `ELMOS-POL-018` Prevent unsigned/untrusted builders from publishing production cache/results.
- [ ] `ELMOS-POL-019` Store provenance in CAS/evidence and make it independently verifiable.

### Signing and verification

- [ ] `ELMOS-POL-020` Sign OCI images, toolchains, Skill packages, Rule packs, plugins, generated artifacts, release archives, and Evidence Packs according to policy.
- [ ] `ELMOS-POL-021` Verify signatures/trust before runner execution, package installation, cache promotion, and release.
- [ ] `ELMOS-POL-022` Support keyless/managed and enterprise offline roots with rotation and revocation.
- [ ] `ELMOS-POL-023` Quarantine unsigned, invalid, revoked, or provenance-mismatched objects.
- [ ] `ELMOS-POL-024` Publish checksums and verification commands.

### Release gates

- [ ] `ELMOS-POL-025` Combine authorization, sandbox, tests, behavior, security, SBOM, license, provenance, signature, evidence, cost, and approval decisions.
- [ ] `ELMOS-POL-026` Return exact blocking reasons and remediation rather than a generic failure.
- [ ] `ELMOS-POL-027` Prevent an agent or project configuration from weakening organization policy.
- [ ] `ELMOS-POL-028` Record every gate input digest and decision for deterministic replay.

## Validation

- [ ] Attempt prohibited model/tool/egress/export operations and enforce denial.
- [ ] Use expired/wildcard exceptions and reject them.
- [ ] Inject critical vulnerable, unpinned, typosquatted, and forbidden-license dependencies.
- [ ] Tamper with signed artifacts/provenance and reject execution/promotion.
- [ ] Take policy service offline during a high-risk operation and fail closed.

## Exit gate

- [ ] Policy is versioned, tested, signed, enforced, and evidenced.
- [ ] Production execution and promotion reject untrusted supply-chain inputs.
- [ ] Every exception is bounded and certification-visible.
- [ ] Artifacts are traceable to authenticated inputs and builders.
