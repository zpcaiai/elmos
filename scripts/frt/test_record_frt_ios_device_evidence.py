from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("record_frt_ios_device_evidence.mjs")


class IosDeviceEvidenceTests(unittest.TestCase):
    def fixture(self, root: Path, *, reality: str = "physical") -> dict[str, Path]:
        app = root / "build/ios/Profile-iphoneos/Runner.app"
        (app / "_CodeSignature").mkdir(parents=True)
        (app / "_CodeSignature/CodeResources").write_text("signed", encoding="utf-8")
        (app / "Runner").write_text("binary", encoding="utf-8")
        device_id = "00008120-PRIVATE-DEVICE-ID"
        values = {
            "install": {
                "info": {"outcome": "success"},
                "result": {"bundleIdentifier": "io.elmos.frtFlutterRoute"},
            },
            "launch": {
                "info": {"outcome": "success"},
                "result": {"process": {"processIdentifier": 731}},
            },
            "processes": {
                "result": {"runningProcesses": [{
                    "processIdentifier": 731,
                    "executable": "file:///private/app/Runner",
                }]},
            },
            "devices": {
                "result": {"devices": [{
                    "identifier": "core-device-id",
                    "hardwareProperties": {
                        "udid": device_id,
                        "reality": reality,
                        "platform": "iOS",
                        "deviceType": "iPhone",
                        "marketingName": "Test iPhone",
                        "productType": "iPhone-test",
                        "cpuType": {"name": "arm64e"},
                    },
                    "deviceProperties": {
                        "name": "PRIVATE PERSON NAME",
                        "osVersionNumber": "27.0",
                        "osBuildUpdate": "test-build",
                        "developerModeStatus": "enabled",
                    },
                    "connectionProperties": {
                        "pairingState": "paired",
                        "tunnelState": "available",
                    },
                }]},
            },
        }
        paths: dict[str, Path] = {}
        for name, value in values.items():
            destination = root / f"{name}.json"
            destination.write_text(json.dumps(value), encoding="utf-8")
            paths[name] = destination
        device_path = root / "device-id.txt"
        device_path.write_text(device_id, encoding="utf-8")
        paths["device_id"] = device_path
        return paths

    def run_recorder(self, root: Path, paths: dict[str, Path]) -> subprocess.CompletedProcess[str]:
        output = root / "evidence.json"
        environment = dict(os.environ)
        environment["ELMOS_FRT_DEVICE_ID_HMAC_KEY"] = "test-only-key-with-at-least-32-bytes"
        return subprocess.run(
            [
                "node", str(SCRIPT),
                "--project", str(root),
                "--install-json", str(paths["install"]),
                "--launch-json", str(paths["launch"]),
                "--processes-json", str(paths["processes"]),
                "--devices-json", str(paths["devices"]),
                "--device-id-file", str(paths["device_id"]),
                "--output", str(output),
            ],
            capture_output=True,
            check=False,
            text=True,
            env=environment,
        )

    def test_records_minimized_physical_device_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-frt-ios-evidence-") as directory:
            root = Path(directory).resolve()
            completed = self.run_recorder(root, self.fixture(root))
            self.assertEqual(completed.returncode, 0, completed.stderr)
            raw = (root / "evidence.json").read_text(encoding="utf-8")
            value = json.loads(raw)
            self.assertEqual(value["status"], "PASSED_LOCAL_EVIDENCE_ONLY")
            self.assertEqual(value["device"]["reality"], "physical")
            self.assertTrue(value["device"]["devicePseudonym"].startswith("hmac-sha256:"))
            self.assertNotIn("PRIVATE PERSON NAME", raw)
            self.assertNotIn("00008120-PRIVATE-DEVICE-ID", raw)
            self.assertNotIn("processIdentifier", value["execution"])
            self.assertIs(value["privacy"]["rawDeviceIdentifierPersisted"], False)
            self.assertIs(value["privacy"]["deviceNameOrAliasPersisted"], False)
            self.assertIs(value["privacy"]["rawProcessIdentifierPersisted"], False)
            self.assertIs(value["privacy"]["rawCommandOutputPersisted"], False)

    def test_rejects_simulator_as_physical_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-frt-ios-evidence-") as directory:
            root = Path(directory).resolve()
            completed = self.run_recorder(root, self.fixture(root, reality="virtual"))
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("FRT_IOS_PHYSICAL_DEVICE_NOT_CONFIRMED", completed.stderr)


if __name__ == "__main__":
    unittest.main()
