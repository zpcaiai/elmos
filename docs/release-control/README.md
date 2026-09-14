# Release Control A

Group A owns the only integration path to `main`. Other groups deliver small,
independently testable work units; Group A resolves their exact commit SHAs into
one candidate and reruns every required gate on that candidate.

## Current candidate procedure

1. Reconcile `release-control/ci-failures-2026-09-13.json` against the latest CI
   run. Do not close an item from a different SHA.
2. Integrate task-owned commits only. Do not copy unrelated dirty-worktree state.
3. Run `python3 scripts/release_control/run_release_gate.py --candidate-sha
   "$(git rev-parse HEAD)" --output-dir .release-control-artifacts`.
4. Run the full CI workflow. Its daily schedule is 18:17 UTC / 02:17
   Asia/Shanghai and covers every job in `.github/workflows/ci.yml`.
5. Require the protected-branch `release-control` check and CODEOWNERS approval.
   Repository policy declares the owner, but GitHub branch-protection enforcement
   remains `NOT_VERIFIED` until checked in provider settings.
6. Treat the generated dependency inventory and CycloneDX document as bounded
   local engineering evidence. Vulnerability, provider, customer, independent,
   deployment, and certification evidence remain `NOT_RUN` / `NOT_CERTIFIED`.

## Revocation boundary

Incident `ELMOS-CERT-KEY-2026-09-13-01` revokes the repository-held Ethan key and
all verifier/approver private keys committed under framework campaign runs. Git
history still contains the compromised material, so deletion from the current
tree is not secret rotation. A replacement key must be generated and retained
outside the repository (HSM/KMS or equivalent), then its public trust anchor must
be authenticated separately.
