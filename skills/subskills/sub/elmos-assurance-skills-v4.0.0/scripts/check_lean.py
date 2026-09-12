#!/usr/bin/env python3
"""Check an already-provisioned candidate Lean; never installs or downloads it."""
from __future__ import annotations
import json, os, shutil, subprocess, sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
lean=shutil.which("lean")
if not lean:
    print(json.dumps({"status":"NOT_RUN","reason":"lean executable is not installed","independent_checker":"NOT_RUN","production_claim":False}))
    raise SystemExit(2)
# Explicit opt-in: an elan shim could otherwise download a toolchain automatically.
if os.environ.get("ELMOS_APPROVED_LOCAL_LEAN") != "1":
    print(json.dumps({"status":"NOT_RUN","reason":"operator must provision/pin Lean and explicitly set ELMOS_APPROVED_LOCAL_LEAN=1; no auto-download","production_claim":False}))
    raise SystemExit(2)
try:
    ver=subprocess.run([lean,"--version"],capture_output=True,text=True,timeout=20,cwd=R/"formal/lean")
    expected=(R/"formal/lean/lean-toolchain").read_text().strip().split(":v")[-1]
    import re
    found=re.search(r"version\s+(\d+\.\d+\.\d+)(?:[\s,)]|$)",ver.stdout)
    if ver.returncode or not found or found.group(1)!=expected:
        print(json.dumps({"status":"BLOCKED_TOOLCHAIN_MISMATCH","expected":expected,"observed":ver.stdout,"stderr":ver.stderr,"production_claim":False}))
        raise SystemExit(2)
    run=subprocess.run([lean,"ElmosProofs.lean"],capture_output=True,text=True,timeout=60,cwd=R/"formal/lean")
    print(json.dumps({"status":"KERNEL_DEMO_CHECKED_NOT_PROJECT_PROVED" if run.returncode==0 else "KERNEL_CHECK_FAILED","exit_code":run.returncode,"stdout":run.stdout,"stderr":run.stderr,"independent_checker":"NOT_RUN","production_artifact_binding":"NOT_RUN","production_claim":False},ensure_ascii=False,indent=2))
    raise SystemExit(0 if run.returncode==0 else 1)
except (OSError,subprocess.TimeoutExpired) as exc:
    print(json.dumps({"status":"UNKNOWN","reason":str(exc),"production_claim":False}))
    raise SystemExit(2)
