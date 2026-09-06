---
name: elmos-live-workbench
description: Implement and operate the ELMOS lw.v1 Live Workbench through immutable source, evidence-bound teaching, fixed 600-second previews, and fenced debugging.
---

# ELMOS Live Workbench

Use this skill for repository-owned integration of the Live Workbench source pack.

Read `docs/live-workbench/IMPLEMENTATION.md` and validate the pinned source package with
`python3 scripts/live_workbench/validate_archive.py` before changing the runtime.

- Use `modules/live-workbench` for lw.v1 contracts, lifecycle, source anchors, evidence, missions, and debug fencing.
- Reuse `modules/developer-workflow` for the Batch 36 IDE/preview/ownership policy boundary; do not create a privileged parallel bridge.
- Bind every read, preview, debug, replay, evidence, and export action to host-minted authority, tenant, repository, snapshot, generation, and expiry.
- The preview deadline is exactly 600 seconds after independently committed readiness. No refresh, reconnect, debug pause, or repeated ready signal can extend it.
- Never execute uploaded or repository code in the control-plane process. Actual sandbox, DAP/CDP, browser, device, provider, and independent certification evidence must remain `NOT_RUN` until an approved host supplies and qualifies them.
- Do not use a generic dispatcher to imply unsupported capabilities. P2 distributed/device routes remain blocked unless an exact qualified host profile exists.

Run `make live-workbench` for repository-owned source integrity and local module tests. This is engineering qualification only, not deployment or E5 certification.
