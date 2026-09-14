# Batch 40 Docker local evidence

The Docker harness closes only repository-owned execution gaps. It packages a
repository-owned Go probe in a `scratch` image and runs the image by its exact
content digest with no network, a read-only root filesystem, a non-root user,
all capabilities dropped, `no-new-privileges`, bounded CPU/memory/PIDs, no host
mounts, and an ephemeral `tmpfs`.

Run it explicitly:

```bash
make batch40-docker-evidence PACK=elmos-platform-supply-chain
```

The probe exercises local negative controls for signature verification,
unsigned and tampered artifact rejection, provenance subject binding, runner
downgrade rejection, tenant binding, and corpus separation. The output is
content-addressed by `scripts/batch40_record_results.py` and recorded as
`LOCAL_EXECUTED_SELF_ATTESTED`.

The target deliberately preserves the previously captured dependency artifact
and environment digests. Refresh those only through `batch40-evidence` in a
complete checkout; a Docker fixture run is not a dependency-inventory refresh.

This target intentionally does not run as part of `batch40-check`: CI hosts are
not assumed to expose a Docker daemon. It also does not create an evidence
manifest, certification request, signature, approval, trust store, production
attestation, or independent assessment. A local Docker daemon, Docker Desktop,
OrbStack, or a second container on the same host is not an independent verifier.
The report must therefore preserve:

- `productionEvidence = NOT_RUN`
- `independentVerification = NOT_RUN`
- `certificationStatus = NOT_CERTIFIED`

The conservative Batch 40 gate remains the only authority for final status.
