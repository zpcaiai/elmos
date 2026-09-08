# VB6 SP6 cross-host route campaign

VB6 routes use a three-phase campaign because the repository's exact non-VB6
toolchains and the proprietary Windows/x86 VB6 compiler do not share one host.
Every transferred file is bound by byte count and SHA-256.

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
