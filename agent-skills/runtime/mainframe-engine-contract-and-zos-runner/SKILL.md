---
name: mainframe-engine-contract-and-zos-runner
description: Govern ELMOS Mainframe Engine capability discovery and leased z/OS dataset, job, build, test, spool, and promotion operations. Use for z/OSMF, JES jobs, PDS or PDSE access, load libraries, mainframe CI, and any request that could execute or change mainframe state.
---

# Mainframe Engine Contract and z/OS Runner

## Execute safely

1. Classify the operation as discovery, build, test, analysis, parallel comparison, cutover, or decommission.
2. Bind it to organization, environment, system, SAF identity, job-name policy, dataset allowlist, allowed programs, resource limits, expiry, and idempotency key.
3. Keep discovery read-only: allow approved source, copylib, catalog metadata, job status, and spool reads only.
4. Submit only reviewed JCL through an approved adapter. Never run TSO or z/OS commands in the control-plane process.
5. Correlate the ELMOS job ID with JES job name, JES job ID, system, submitter, spool hash, return code, and abend.
6. Require independent approval for production loadlib, dataset, scheduler, subsystem, transaction-route, or data-authority changes.

## Fail closed

- Return `NOT_CONFIGURED` or `NOT_RUN` when an adapter, lease, allowlist, identity, or evidence source is absent.
- Reject arbitrary JCL, shared privileged identities, unbounded CPU or elapsed time, and direct production writes.
- Preserve sanitized spool and immutable audit references; never fabricate a successful job result.
