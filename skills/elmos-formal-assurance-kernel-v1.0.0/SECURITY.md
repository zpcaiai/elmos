# Security Policy

## Reporting

Report suspected vulnerabilities through the owning organization's private security channel. Do not attach customer source, formulas, counterexamples, database snapshots, secrets or signing material to public issues.

## Security invariants

- external proof engines run no-network, no-secret and non-root;
- tenant/account identity is enforced at API, database RLS, object storage and cache;
- stale fencing tokens cannot commit results;
- proof artifacts are immutable and content-addressed;
- unknown/bounded/unsupported states cannot be inflated;
- critical waivers require separation of duties and expiry;
- source/formula content is excluded from metric labels;
- release images and tools are pinned by digest, scanned and signed.

## Supported versions

Only the latest organization-approved package release and exact pinned verifier adapters are supported. Evidence created by revoked/vulnerable TCB components is marked stale.

## Incident response

1. isolate affected adapter/service;
2. preserve raw evidence and audit events;
3. revoke compromised tokens, images, signatures or TCB components;
4. mark affected proofs stale and freeze relevant releases;
5. determine tenant scope;
6. re-run proofs with a trusted environment;
7. issue a signed incident/evidence correction report.

## Supply chain

Third-party tools are not included. Each production adapter requires license review, SBOM, vulnerability scan, provenance and signature verification.
