# ELMOS project-generation Cloud Run handoff

Exact directional Batch 33 pack from a generated local Python container to
Google Cloud Run v2 in `asia-east1`.

Local Docker 29.4.0 evidence passed: the digest-pinned Python 3.12.12 image
built, ran as `10001:10001` with a read-only root filesystem, all Linux
capabilities dropped and `no-new-privileges`; `/health` returned `UP`; the
container, image, and temporary workspace were then cleaned up.

Generated projects now include `deploy/cloud-run-control.py` and an exact
request template. The controller validates a regional Artifact Registry image
digest, dedicated runtime identity, private ingress, immutable Secret versions,
capacity and health contracts. Mutating actions default to refusal and require
an exact, expiring, separate-approver authorization. Deployment creates a
no-traffic candidate, runs the authenticated health contract, and only then
promotes it; rollback and destroy require separate authorizations and receipts.
Thirteen local generation/policy tests pass, including repository-owned negative
and holdout corpora. This is code-level engineering
evidence, not Google Cloud execution evidence.

Google Cloud execution remains `NOT_RUN` because `gcloud`, an approved project,
billing authorization, and short-lived least-privilege credentials are absent.
Replay the conservative structural gate with:

```bash
uv run --project engines/project-synthesis-engine pytest \
  engines/project-synthesis-engine/tests/test_cloud_run_control.py \
  engines/project-synthesis-engine/tests/test_deployment_guidance.py
python scripts/batch33/validate_cloud_pack.py \
  cloud-packs/elmos-project-generation-cloud-run-handoff
python scripts/batch33/run_cloud_gate.py \
  cloud-packs/elmos-project-generation-cloud-run-handoff
```
