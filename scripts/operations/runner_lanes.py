#!/usr/bin/env python3
"""Bounded host discovery and content-addressed LOCAL evidence. No deployment authority."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
TOPOLOGY = ROOT / "deploy/production/runner/lane-topology.json"
EXPECTED = {
    "linux-rootless-x64": ("Linux", "x86_64", "linux-rootless-docker"),
    "windows-native-x64": ("Windows", "x86_64", "windows-native"),
    "linux-database-x64": ("Linux", "x86_64", "linux-database-native"),
    "macos-arm64": ("Darwin", "arm64", "macos-native"),
}
ROUTES = {
    "linux-rootless-x64": {"spring-rootless", "project-synthesis-production", "qa-foundry-isolation", "b38-b45-dr-slo"},
    "windows-native-x64": {"spring-windows-compat", "sqlserver-windows-auth", "chinadb-windows-drivers", "frontend-windows", "miniapp-windows", "qa-foundry-windows", "dotnet-framework"},
    "linux-database-x64": {"dm8-chinadb-performance", "database-cdc-rollback"},
    "macos-arm64": {"apple-native", "arm64-compat", "miniapp-apple", "frontend-macos"},
}


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate(topology):
    if topology.get("schema") != "elmos.runner-lanes.v1" or topology.get("certification") != "NOT_CERTIFIED":
        raise ValueError("invalid schema or certification claim")
    lanes = topology["lanes"]
    if set(lanes) != set(EXPECTED) or topology["rollout_order"] != list(EXPECTED):
        raise ValueError("lane set or rollout order drift")
    bindings = []
    for name, expected in EXPECTED.items():
        lane = lanes[name]
        if tuple(lane[k] for k in ("os", "arch", "execution")) != expected:
            raise ValueError("platform/execution drift: " + name)
        if set(lane["workloads"]) != ROUTES[name] or len(lane["workloads"]) != len(ROUTES[name]):
            raise ValueError("workload routing drift: " + name)
        if lane["external_evidence"] != "NOT_RUN" or not lane["requirements"]:
            raise ValueError("templates cannot attest external evidence")
        if name != "macos-arm64" and lane["dedicated"] is not True:
            raise ValueError("dedicated host required")
        if lane["host_binding"]:
            bindings.append(lane["host_binding"])
    if len(bindings) != len(set(bindings)):
        raise ValueError("separate lanes require separate host bindings")
    if topology["evidence_authority"]["external_verification"] != "NOT_RUN":
        raise ValueError("template cannot supply verifier evidence")


def command(argv, timeout=20):
    """Only internal fixed read-only commands; output is retained locally for replay."""
    executable = shutil.which(argv[0])
    if not executable:
        return {"argv": argv, "status": "NOT_RUN", "reason": "tool-unavailable"}
    try:
        result = subprocess.run([executable, *argv[1:]], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout, shell=False)
        return {"argv": argv, "status": "PASS" if result.returncode == 0 else "FAIL",
                "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except (subprocess.TimeoutExpired, OSError) as error:
        return {"argv": argv, "status": "UNKNOWN", "reason": type(error).__name__}


def filesystem_probe(workspace):
    results = {}
    # TemporaryDirectory is always a newly created child of the selected workspace.
    with tempfile.TemporaryDirectory(prefix=".elmos-lane-probe-", dir=workspace) as directory:
        base = Path(directory)
        (base / "Case.txt").write_bytes(b"line1\r\nline2\r\n")
        results["case_sensitive"] = not (base / "case.txt").exists()
        results["crlf_byte_roundtrip"] = (base / "Case.txt").read_bytes() == b"line1\r\nline2\r\n"
        for codec in ("gbk", "gb18030"):
            sample = "中文驱动兼容"
            target = base / (codec + ".txt")
            target.write_bytes(sample.encode(codec))
            results[codec + "_roundtrip"] = target.read_bytes().decode(codec) == sample
        target = base
        try:
            for _ in range(8):
                target = target / ("segment-" + "x" * 30)
            target.mkdir(parents=True)
            (target / "中文.txt").write_text("probe", encoding="utf-8")
            results["long_path_roundtrip"] = (target / "中文.txt").read_text(encoding="utf-8") == "probe"
            results["long_path_characters"] = len(str(target / "中文.txt"))
        except OSError as error:
            results["long_path_roundtrip"] = False
            results["long_path_error"] = type(error).__name__
    results["temporary_workspace_cleaned"] = not base.exists()
    return results


def inventory(workspace):
    system = platform.system()
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    facts = {"os": system, "arch": arch, "release": platform.release(),
             "version": platform.version(), "python": platform.python_version(),
             "workspace": str(workspace), "filesystem": filesystem_probe(workspace)}
    raw = {"git": command(["git", "rev-parse", "HEAD"]),
           "docker_version": command(["docker", "version", "--format", "{{json .}}"]),
           "docker_info": command(["docker", "info", "--format", "{{json .}}"]),
           "docker_context": command(["docker", "context", "inspect"]),
           "node": command(["node", "--version"])}
    if system == "Linux":
        facts["uid"] = os.geteuid()
        facts["wsl"] = "microsoft" in platform.release().lower() or bool(os.environ.get("WSL_DISTRO_NAME"))
        facts["container_marker"] = Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()
        raw["virtualization"] = command(["systemd-detect-virt"])
    if system == "Darwin":
        raw["rosetta"] = command(["sysctl", "-in", "sysctl.proc_translated"])
        raw["xcode"] = command(["xcodebuild", "-version"])
    if system == "Windows":
        native_shell = "pwsh" if shutil.which("pwsh") else "powershell.exe"
        raw["windows"] = command([native_shell, "-NoProfile", "-NonInteractive", "-File",
                                  str(ROOT / "scripts/operations/probe_windows_runner.ps1")], timeout=45)
    facts["docker"] = {}
    if raw["docker_info"]["status"] == "PASS":
        try:
            info = json.loads(raw["docker_info"]["stdout"])
            facts["docker"] = {k: info.get(k) for k in ("OSType", "Architecture", "OperatingSystem", "KernelVersion", "ServerVersion", "SecurityOptions")}
        except (ValueError, TypeError):
            raw["docker_info"]["status"] = "UNKNOWN"
    return facts, raw


def eligibility(lane_name, facts, raw):
    os_name, arch, _ = EXPECTED[lane_name]
    gaps = []
    if facts["os"] != os_name or facts["arch"] != arch:
        gaps.append("native-platform-mismatch")
    if os_name == "Linux":
        if facts.get("wsl") or facts.get("container_marker"):
            gaps.append("wsl-or-container-cannot-establish-independent-linux-host")
        if "docker desktop" in str(facts.get("docker", {}).get("OperatingSystem", "")).lower():
            gaps.append("docker-desktop-is-not-independent-linux")
    if lane_name == "linux-rootless-x64":
        docker = facts.get("docker", {})
        if facts.get("uid", 0) == 0:
            gaps.append("non-root-identity-required")
        if docker.get("OSType") != "linux" or "name=rootless" not in (docker.get("SecurityOptions") or []):
            gaps.append("rootless-linux-docker-required")
        try:
            context = json.loads(raw["docker_context"]["stdout"])
            endpoint = context[0]["Endpoints"]["docker"]["Host"]
            if not endpoint.startswith("unix://"):
                gaps.append("local-unix-docker-endpoint-required")
        except (KeyError, ValueError, TypeError, IndexError):
            gaps.append("docker-endpoint-unknown")
    if lane_name == "macos-arm64" and raw.get("rosetta", {}).get("stdout", "").strip() == "1":
        gaps.append("rosetta-cannot-supply-native-arm64-evidence")
    if lane_name == "windows-native-x64":
        try:
            native = raw["windows"]
            if native["status"] != "PASS":
                raise ValueError("native-probe-not-successful")
            observed = json.loads(native["stdout"])
            if observed.get("nativeFileLock") != "PASS" or observed.get("lockProbeCleaned") is not True:
                gaps.append("native-file-lock-or-cleanup-failed")
        except (KeyError, ValueError, TypeError):
            gaps.append("windows-native-probe-unknown")
        for check in ("crlf_byte_roundtrip", "gbk_roundtrip", "gb18030_roundtrip", "long_path_roundtrip"):
            if facts["filesystem"].get(check) is not True:
                gaps.append("windows-filesystem-probe-failed:" + check)
    if not facts["filesystem"].get("temporary_workspace_cleaned"):
        gaps.append("probe-cleanup-failed")
    return gaps


def write_object(destination, value):
    data = canonical(value)
    identity = digest(data)
    path = destination / (identity + ".json")
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError("content-address collision or tampering")
    return identity


def collect(lane_name, destination, workspace):
    inputs = {
        "topology_sha256": TOPOLOGY,
        "collector_sha256": Path(__file__),
        "windows_probe_sha256": ROOT / "scripts/operations/probe_windows_runner.ps1",
    }
    bindings = {name: digest(path.read_bytes()) for name, path in inputs.items()}
    topology = json.loads(TOPOLOGY.read_text(encoding="utf-8"))
    validate(topology)
    facts, raw = inventory(workspace)
    if bindings != {name: digest(path.read_bytes()) for name, path in inputs.items()}:
        raise ValueError("collector inputs changed during observation; rerun required")
    gaps = eligibility(lane_name, facts, raw)
    destination.mkdir(parents=True, exist_ok=True)
    raw_id = write_object(destination, raw)
    report = {
        "schema": "elmos.runner-lane-observation.v1", "lane": lane_name,
        "timestamp": datetime.now(timezone.utc).isoformat(), "facts": facts,
        "raw_sha256": raw_id, **bindings,
        "platform_eligibility": "BLOCKED" if gaps else "LOCAL_MATCH_ONLY",
        "platform_gaps": gaps,
        "evidence_level": "LOCAL_EXECUTED_SELF_ATTESTED",
        "external_evidence": "NOT_RUN", "certification": "NOT_CERTIFIED",
        "requirements": {item: "NOT_RUN" for item in topology["lanes"][lane_name]["requirements"]},
        "deployment_ready": False, "trusted_host_binding": None,
        "limitations": ["Host observations are not attestation or authorization.",
                        "Filesystem probes cover this directory and Python process only.",
                        "No workload, provider, GUI, database, container launch or independent verification was executed."]}
    report_id = write_object(destination, report)
    return destination / (report_id + ".json"), report


def verify(path):
    data = path.read_bytes()
    if path.name != digest(data) + ".json":
        raise ValueError("report digest mismatch")
    report = json.loads(data)
    if report["schema"] != "elmos.runner-lane-observation.v1" or report["lane"] not in EXPECTED:
        raise ValueError("unknown report")
    identity = report["raw_sha256"]
    if not isinstance(identity, str) or not re.fullmatch("[0-9a-f]{64}", identity):
        raise ValueError("invalid object identity")
    raw_path = path.parent / (identity + ".json")
    if raw_path.is_symlink() or digest(raw_path.read_bytes()) != identity:
        raise ValueError("raw evidence mismatch")
    if (report["certification"] != "NOT_CERTIFIED" or report["external_evidence"] != "NOT_RUN"
            or report["deployment_ready"] is not False or report["trusted_host_binding"] is not None):
        raise ValueError("local collector cannot grant external authority")
    # Digest verification deliberately does not authenticate a producer.
    return {"integrity": "PASS", "authenticity": "NOT_VERIFIED", "certification": "NOT_CERTIFIED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("validate")
    route = sub.add_parser("route")
    route.add_argument("workload", choices=sorted(set.union(*ROUTES.values())))
    probe = sub.add_parser("collect")
    probe.add_argument("--lane", choices=EXPECTED, required=True)
    probe.add_argument("--output", type=Path, required=True)
    probe.add_argument("--workspace", type=Path, default=ROOT)
    check = sub.add_parser("verify")
    check.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "verify":
            print(json.dumps(verify(args.report)))
            return 0
        topology = json.loads(TOPOLOGY.read_text(encoding="utf-8"))
        validate(topology)
        if args.action == "validate":
            print("Topology structure PASS; runtime NOT_RUN; NOT_CERTIFIED")
        elif args.action == "route":
            print(next(name for name, workloads in ROUTES.items() if args.workload in workloads))
        else:
            path, report = collect(args.lane, args.output.resolve(), args.workspace.resolve())
            print(json.dumps({"report": str(path), "platform_eligibility": report["platform_eligibility"],
                              "gaps": report["platform_gaps"], "deployment_ready": False}))
            return 3 if report["platform_gaps"] else 0
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print("BLOCKED: " + str(error), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
