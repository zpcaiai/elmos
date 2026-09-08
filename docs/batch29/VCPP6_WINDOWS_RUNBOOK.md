# Microsoft Visual C++ 6.0 SP6 cross-host route campaign

VC++6 routes use a three-phase campaign because the repository's exact
non-VC++6 toolchains and the proprietary Windows/x86 VC++6 compiler do not
normally share one host. Every transferred file is bound by byte count and
SHA-256. The two VC++6/VB6 directions additionally require the non-VC++6 phase
to run on a governed VB6 SP6 host; those routes never inherit evidence from
either vendor campaign.

## 1. Prepare the non-VC++6 sides

```bash
python3 scripts/batch29/run_vcpp6_cross_host_campaign.py prepare-set \
  --repo-root . \
  --output-root verification-packs/vcpp6-cross-host-prepared-v1
```

This executes the non-VC++6 source or target side for development, holdout and
representative corpora. It leaves the VC++6 side `NOT_RUN`. For
`vb6-to-vcpp6` and `vcpp6-to-vb6`, configure the governed VB6 binding described
in `VB6_WINDOWS_RUNBOOK.md` before preparation.

## 2. Bind the governed Windows toolchain

Create a JSON document outside the repository conforming to
`schemas/batch29/vcpp6-toolchain-binding.schema.json`. The paths must identify
the licensed `CL.EXE`, `LINK.EXE`, and `MSVCP60.DLL`; the resolver verifies all
three SHA-256 values and requires all three PE files to be x86.

Set these variables in the authorized Windows runner:

```powershell
$env:ELMOS_VCPP6_TOOLCHAIN_MANIFEST = "C:\elmos-governed\vcpp6-binding.json"
$env:ELMOS_VCPP6_TOOLCHAIN_MANIFEST_SHA256 = "<lowercase sha256 of manifest>"
```

The binding is `GOVERNED_EXTERNAL_SELF_ATTESTED`; it is not independent
verification and cannot certify a route.

## 3. Execute and verify each route

On Windows:

```powershell
python scripts\batch29\run_vcpp6_cross_host_campaign.py execute-windows `
  --request verification-packs\vcpp6-cross-host-prepared-v1\java-to-vcpp6 `
  --output C:\elmos-evidence\java-to-vcpp6
```

Back on a verification host:

```bash
python3 scripts/batch29/run_vcpp6_cross_host_campaign.py verify \
  --request verification-packs/vcpp6-cross-host-prepared-v1/java-to-vcpp6 \
  --windows-output /path/to/windows/java-to-vcpp6 \
  --output /path/to/verified/java-to-vcpp6.json
```

A successful comparison is `PASSED_LOCAL_CROSS_HOST`. Independent verification,
customer execution, production certification, and unsupported VC++6 semantics
remain `NOT_RUN` / `NOT_CERTIFIED` until separately evidenced.
