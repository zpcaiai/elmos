# VB6 SP6 cross-host route campaign

VB6 routes use a three-phase campaign because the repository's exact non-VB6
toolchains and the proprietary Windows/x86 VB6 compiler do not share one host.
Every transferred file is bound by byte count and SHA-256.
The request, Windows receipt, comparison, and set manifests conform to
`schemas/batch29/vb6-cross-host-campaign.schema.json`; runtime validation adds
stricter route, role, ordering, path, file-identity, and digest checks.

## 1. Prepare the non-VB6 sides

```bash
python3 scripts/batch29/run_vb6_cross_host_campaign.py prepare-set \
  --repo-root . \
  --output-root verification-packs/vb6-cross-host-prepared-v1
```

This executes the non-VB6 source or target side for development, holdout and
representative corpora. It leaves the Windows side `NOT_RUN`.

## 2. Bind the governed Windows toolchain

Create a JSON document outside the repository conforming to
`schemas/batch29/vb6-toolchain-binding.schema.json`. The paths must identify
the licensed `VB6.EXE` and `MSVBVM60.DLL`; the resolver verifies both SHA-256
values and requires both PE files to be x86.

Set these variables in the authorized Windows runner:

```powershell
$env:ELMOS_VB6_TOOLCHAIN_MANIFEST = "C:\elmos-governed\vb6-binding.json"
$env:ELMOS_VB6_TOOLCHAIN_MANIFEST_SHA256 = "<lowercase sha256 of manifest>"
```

The binding is `GOVERNED_EXTERNAL_SELF_ATTESTED`; it is not independent
verification and cannot certify a route.

## 3. Execute and verify each route

On Windows:

```powershell
python scripts\batch29\run_vb6_cross_host_campaign.py execute-windows `
  --request verification-packs\vb6-cross-host-prepared-v1\java-to-vb6 `
  --output C:\elmos-evidence\java-to-vb6
```

Back on a verification host:

```bash
python3 scripts/batch29/run_vb6_cross_host_campaign.py verify \
  --request verification-packs/vb6-cross-host-prepared-v1/java-to-vb6 \
  --windows-output /path/to/windows/java-to-vb6 \
  --output /path/to/verified/java-to-vb6.json
```

A successful comparison is `PASSED_LOCAL_CROSS_HOST`. Independent verification,
customer execution, production certification and unsupported VB6 semantics
remain `NOT_RUN` / `NOT_CERTIFIED` until separately evidenced.

## 4. Execute and verify all 26 routes as resumable sets

On the governed Windows runner, use the set command. Every route is published
atomically; a failed route leaves no partial route directory, while previously
completed and digest-validated routes are reused on the next invocation.

```powershell
python scripts\batch29\run_vb6_cross_host_campaign.py execute-windows-set `
  --request-root verification-packs\vb6-cross-host-prepared-v1 `
  --output-root C:\elmos-evidence\vb6-windows-set
```

After transferring the complete Windows output, compare all observations:

```bash
python3 scripts/batch29/run_vb6_cross_host_campaign.py verify-set \
  --request-root verification-packs/vb6-cross-host-prepared-v1 \
  --windows-output-root /path/to/vb6-windows-set \
  --output-root /path/to/vb6-verified-set
```

The set manifests bind exactly 26 ordered request, receipt, and verification
records. Missing, duplicate, cross-corpus, hard-linked, symlinked, changed, or
digest-mismatched artifacts fail closed.

## 5. Governed GitHub execution

`.github/workflows/vb6-cross-host-campaign.yml` exposes a manual-only workflow.
It requires a self-hosted runner with the labels `Windows`, `X86`, `vb6-sp6`,
and `governed`, Python 3.12.12, the repository variable
`ELMOS_VB6_TOOLCHAIN_MANIFEST`, and the secret
`ELMOS_VB6_TOOLCHAIN_MANIFEST_SHA256`. The `vb6-governed-lab` environment is the
approval boundary. Input `all` executes all 26 routes; an exact route key runs
one direction.

The hosted comparison job is a separate execution phase but is not an
independent certification authority. Workflow artifacts therefore retain
`GOVERNED_EXTERNAL_SELF_ATTESTED`, `NOT_RUN`, and `NOT_CERTIFIED` as applicable.
