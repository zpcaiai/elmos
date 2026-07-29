# ELMOS project-generation Cloud Run handoff

Exact directional Batch 33 pack from a generated local Python container to
Google Cloud Run v2 in `asia-east1`.

Local Docker 29.4.0 evidence passed: the digest-pinned Python 3.12.12 image
built, ran as `10001:10001` with a read-only root filesystem, all Linux
capabilities dropped and `no-new-privileges`; `/health` returned `UP`; the
container, image, and temporary workspace were then cleaned up.

Google Cloud execution remains `NOT_RUN` because `gcloud`, an approved project,
billing authorization, and short-lived least-privilege credentials are absent.
Replay the conservative structural gate with:

```bash
python scripts/batch33/validate_cloud_pack.py \
  cloud-packs/elmos-project-generation-cloud-run-handoff
python scripts/batch33/run_cloud_gate.py \
  cloud-packs/elmos-project-generation-cloud-run-handoff
```
