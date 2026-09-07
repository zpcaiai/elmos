# Production Exit Gate

A generated project may be labeled production-deliverable only when:

1. The signed Generation Manifest and SBOM are complete.
2. Clean isolated Build Green evidence is current.
3. Required test suites and mandatory environment matrix cells pass.
4. Critical security, license, provenance, secret, container, and IaC gates pass.
5. The release manifest resolves immutable source, package, image, contract, migration, and evidence versions.
6. Production configuration uses external secret references.
7. Telemetry, health, readiness, SLI, SLO, alerts, and runbooks are defined.
8. Deployment rollout, promotion, and automatic abort rules are defined.
9. Database compatibility supports mixed versions or deployment ordering prevents incompatibility.
10. Rollback or forward recovery is explicitly selected for every release change.
11. Backup restore and disaster-recovery exercises are scheduled and evidenced.
12. Remaining risks and exceptions have owners, expiry, and approval.
