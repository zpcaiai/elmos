import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import runner_lanes as lanes


class RunnerLaneTests(unittest.TestCase):
    def setUp(self):
        self.topology = json.loads(lanes.TOPOLOGY.read_text(encoding="utf-8"))

    def test_declared_routes(self):
        lanes.validate(self.topology)
        self.assertIn("dotnet-framework", lanes.ROUTES["windows-native-x64"])
        self.assertIn("dm8-chinadb-performance", lanes.ROUTES["linux-database-x64"])

    def test_linux_workload_cannot_move_to_windows(self):
        self.topology["lanes"]["windows-native-x64"]["workloads"].append("spring-rootless")
        with self.assertRaises(ValueError):
            lanes.validate(self.topology)

    def test_performance_host_cannot_share_ci_host(self):
        for name in ("linux-rootless-x64", "linux-database-x64"):
            self.topology["lanes"][name]["host_binding"] = "same-host"
        with self.assertRaises(ValueError):
            lanes.validate(self.topology)

    def test_template_cannot_certify(self):
        self.topology["certification"] = "CERTIFIED"
        with self.assertRaises(ValueError):
            lanes.validate(self.topology)

    def linux_facts(self):
        return {"os": "Linux", "arch": "x86_64", "uid": 1001,
                "wsl": False, "container_marker": False,
                "filesystem": {"temporary_workspace_cleaned": True},
                "docker": {"OSType": "linux", "OperatingSystem": "Ubuntu",
                           "SecurityOptions": ["name=rootless"]}}

    def context(self, endpoint="unix:///run/user/1001/docker.sock"):
        return {"docker_context": {"stdout": json.dumps([{"Endpoints": {"docker": {"Host": endpoint}}}])}}

    def test_local_linux_match_is_only_platform_check(self):
        self.assertEqual(lanes.eligibility("linux-rootless-x64", self.linux_facts(), self.context()), [])

    def test_desktop_wsl_root_remote_and_rootful_rejected(self):
        variants = []
        for key, value in (("wsl", True), ("container_marker", True), ("uid", 0), ("os", "Windows")):
            facts = self.linux_facts()
            facts[key] = value
            variants.append(facts)
        facts = self.linux_facts()
        facts["docker"]["OperatingSystem"] = "Docker Desktop"
        variants.append(facts)
        facts = self.linux_facts()
        facts["docker"]["SecurityOptions"] = []
        variants.append(facts)
        for facts in variants:
            with self.subTest(facts=facts):
                self.assertTrue(lanes.eligibility("linux-rootless-x64", facts, self.context()))
        self.assertTrue(lanes.eligibility("linux-rootless-x64", self.linux_facts(), self.context("ssh://remote")))

    def test_missing_context_rejected(self):
        self.assertIn("docker-endpoint-unknown", lanes.eligibility("linux-rootless-x64", self.linux_facts(), {}))

    def test_native_platform_required(self):
        self.assertIn("native-platform-mismatch", lanes.eligibility("windows-native-x64", self.linux_facts(), {}))

    def test_windows_timeout_cannot_pass_local_preflight(self):
        facts = self.linux_facts()
        facts["os"] = "Windows"
        self.assertIn("windows-native-probe-unknown", lanes.eligibility(
            "windows-native-x64", facts, {"windows": {"status": "UNKNOWN"}}))

    def test_rosetta_rejected(self):
        facts = self.linux_facts()
        facts.update(os="Darwin", arch="arm64")
        self.assertTrue(lanes.eligibility("macos-arm64", facts, {"rosetta": {"stdout": "1"}}))

    def test_probe_cleanup_and_byte_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            result = lanes.filesystem_probe(Path(directory))
            self.assertTrue(result["crlf_byte_roundtrip"])
            self.assertTrue(result["gb18030_roundtrip"])
            self.assertTrue(result["temporary_workspace_cleaned"])
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_report_integrity_and_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(lanes, "inventory", return_value=(self.linux_facts(), self.context())):
                path, report = lanes.collect("linux-rootless-x64", Path(directory), Path(directory))
            self.assertFalse(report["deployment_ready"])
            self.assertEqual(set(report["requirements"].values()), {"NOT_RUN"})
            self.assertEqual(lanes.verify(path)["authenticity"], "NOT_VERIFIED")
            raw_path = path.parent / (report["raw_sha256"] + ".json")
            raw_path.write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                lanes.verify(path)

    def test_changed_inputs_cannot_produce_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            topology_path = Path(directory) / "topology.json"
            topology_path.write_bytes(lanes.canonical(self.topology))
            def drift(_workspace):
                topology_path.write_bytes(topology_path.read_bytes() + b"\n")
                return self.linux_facts(), self.context()
            with patch.object(lanes, "TOPOLOGY", topology_path), patch.object(lanes, "inventory", side_effect=drift):
                with self.assertRaisesRegex(ValueError, "changed during observation"):
                    lanes.collect("linux-rootless-x64", Path(directory), Path(directory))

    def test_path_traversal_and_forged_authority_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            with patch.object(lanes, "inventory", return_value=(self.linux_facts(), self.context())):
                _, report = lanes.collect("linux-rootless-x64", destination, destination)
            for field, value in (("raw_sha256", "../outside"), ("deployment_ready", True),
                                 ("external_evidence", "PASS"), ("trusted_host_binding", "forged")):
                altered = copy.deepcopy(report)
                altered[field] = value
                identity = lanes.write_object(destination, altered)
                with self.subTest(field=field), self.assertRaises(ValueError):
                    lanes.verify(destination / (identity + ".json"))


if __name__ == "__main__":
    unittest.main()
