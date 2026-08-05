#!/usr/bin/env python3
"""Collect a privacy-minimized physical-device inventory candidate.

This probe never treats an emulator as a physical device and never persists a
serial number, UDID, device name or raw command output.  It is engineering
input for an authorized device_matrix run, not manual acceptance evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def pseudonym(value: str, key: bytes) -> str:
    return "hmac-sha256:" + hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def command_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def ios_devices(key: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not shutil.which("xcrun"):
        return [], {"state": "NOT_RUN", "reason": "XCRUN_UNAVAILABLE"}
    with tempfile.TemporaryDirectory(prefix="elmos-frt-devicectl-") as directory:
        output = Path(directory) / "devices.json"
        completed = subprocess.run(
            [
                "xcrun",
                "devicectl",
                "list",
                "devices",
                "--timeout",
                "15",
                "--json-output",
                str(output),
                "--quiet",
            ],
            capture_output=True,
            check=False,
            timeout=20,
        )
        if completed.returncode != 0 or not output.is_file():
            return [], {
                "state": "FAILED",
                "reason": "DEVICECTL_LIST_FAILED",
                "stderr_sha256": command_digest(completed.stderr),
            }
        raw = output.read_bytes()
        value = json.loads(raw)
    devices: list[dict[str, Any]] = []
    for item in value.get("result", {}).get("devices", []):
        hardware = item.get("hardwareProperties", {})
        properties = item.get("deviceProperties", {})
        connection = item.get("connectionProperties", {})
        if hardware.get("reality") != "physical":
            continue
        identifier = str(hardware.get("udid") or item.get("identifier") or "")
        if not identifier:
            continue
        devices.append(
            {
                "platform": hardware.get("platform"),
                "device_type": hardware.get("deviceType"),
                "marketing_model": hardware.get("marketingName"),
                "product_type": hardware.get("productType"),
                "architecture": hardware.get("cpuType", {}).get("name"),
                "os_version": properties.get("osVersionNumber"),
                "os_build": properties.get("osBuildUpdate"),
                "developer_mode": properties.get("developerModeStatus"),
                "pairing_state": connection.get("pairingState"),
                "tunnel_state": connection.get("tunnelState"),
                "device_pseudonym": pseudonym(identifier, key),
                "reality": "physical",
            }
        )
    return devices, {
        "state": "COLLECTED",
        "tool": value.get("info", {}).get("version"),
        "raw_output_sha256": command_digest(raw),
        "raw_output_persisted": False,
    }


def android_devices(key: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    adb = shutil.which("adb")
    if not adb:
        return [], {"state": "NOT_RUN", "reason": "ADB_UNAVAILABLE"}
    completed = subprocess.run(
        [adb, "devices", "-l"],
        capture_output=True,
        check=False,
        timeout=20,
    )
    if completed.returncode != 0:
        return [], {
            "state": "FAILED",
            "reason": "ADB_LIST_FAILED",
            "stderr_sha256": command_digest(completed.stderr),
        }
    devices: list[dict[str, Any]] = []
    for raw_line in completed.stdout.decode("utf-8", errors="replace").splitlines()[1:]:
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split()
        serial = fields[0]
        state = fields[1] if len(fields) > 1 else "unknown"
        properties = {
            key_value.split(":", 1)[0]: key_value.split(":", 1)[1]
            for key_value in fields[2:]
            if ":" in key_value
        }
        is_emulator = serial.startswith("emulator-") or properties.get("device", "").startswith(
            ("generic", "emu")
        )
        if is_emulator:
            continue
        devices.append(
            {
                "platform": "Android",
                "state": state,
                "product": properties.get("product"),
                "model": properties.get("model"),
                "device": properties.get("device"),
                "transport": properties.get("transport_id"),
                "device_pseudonym": pseudonym(serial, key),
                "reality": "physical",
            }
        )
    return devices, {
        "state": "COLLECTED",
        "tool": "adb",
        "raw_output_sha256": command_digest(completed.stdout),
        "raw_output_persisted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw_key = os.environ.get("ELMOS_FRT_DEVICE_ID_HMAC_KEY", "")
    if len(raw_key.encode("utf-8")) < 32:
        raise SystemExit("ELMOS_FRT_DEVICE_ID_HMAC_KEY must contain at least 32 bytes")
    key = raw_key.encode("utf-8")
    ios, ios_probe = ios_devices(key)
    android, android_probe = android_devices(key)
    devices = ios + android
    value = {
        "schema_version": 1,
        "kind": "FRT_PHYSICAL_DEVICE_INVENTORY_CANDIDATE",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "state": "CANDIDATE_NOT_EXTERNALLY_VERIFIED",
        "physical_device_count": len(devices),
        "devices": devices,
        "probes": {"ios": ios_probe, "android": android_probe},
        "privacy": {
            "raw_identifiers_persisted": False,
            "raw_command_output_persisted": False,
            "device_names_persisted": False,
            "pseudonymization": "HMAC-SHA256 with an external non-persisted key",
        },
        "boundaries": {
            "install_launch": "NOT_RUN",
            "p0_journeys": "NOT_RUN",
            "manual_visual_review": "NOT_RUN",
            "assistive_technology": "NOT_RUN",
            "external_device_matrix": "NOT_RUN",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
