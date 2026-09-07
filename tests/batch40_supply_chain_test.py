"""Tests for the Batch 40 dependency inventory and credential scan.

Both tools produce numbers that feed a certification gate, so the tests here
care most about the ways a scanner can lie: guessing a version it cannot know,
reporting a clean tree because it silently skipped everything, or letting a
suppression hide a finding forever.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "scripts" / "batch40_dependency_inventory.py"
SCAN = ROOT / "scripts" / "batch40_secret_scan.py"

POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <properties><guava.version>33.0.0-jre</guava.version><chain.version>${missing.version}</chain.version></properties>
  <dependencies>
    <dependency><groupId>com.google.guava</groupId><artifactId>guava</artifactId><version>${guava.version}</version></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency>
    <dependency><groupId>io.elmos</groupId><artifactId>elmos-core</artifactId><version>${project.version}</version></dependency>
    <dependency><groupId>junit</groupId><artifactId>junit</artifactId><version>4.13.2</version><scope>test</scope></dependency>
    <dependency><groupId>bad</groupId><artifactId>chained</artifactId><version>${chain.version}</version></dependency>
  </dependencies>
</project>
"""
LOCK = json.dumps({
    "name": "x", "lockfileVersion": 3,
    "packages": {
        "": {"name": "x"},
        "node_modules/left-pad": {"version": "1.3.0", "license": "WTFPL"},
        "node_modules/typescript": {"version": "5.4.0", "dev": True},
    },
})


def run(script: Path, *args: str) -> tuple[int, dict]:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        output = Path(handle.name)
    result = subprocess.run([sys.executable, str(script), *args, "--output", str(output)],
                            capture_output=True, text=True, check=False)
    return result.returncode, json.loads(output.read_text())


class DependencyInventoryTest(unittest.TestCase):
    def build(self, tmp: Path) -> Path:
        repo = tmp / "repo"
        (repo / "mod").mkdir(parents=True)
        (repo / "pom.xml").write_text(POM)
        (repo / "package-lock.json").write_text(LOCK)
        return repo

    def inventory(self, repo: Path) -> dict:
        code, report = run(INVENTORY, "--repo", str(repo))
        self.assertEqual(0, code)
        return report

    def resolution(self, report: dict, purl_prefix: str) -> str:
        entry = next(item for item in report["components"] if item["purl"].startswith(purl_prefix))
        return entry["versionResolution"]

    def test_it_resolves_a_property_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.inventory(self.build(Path(tmp)))
            entry = next(item for item in report["components"] if item["name"] == "guava")
            self.assertEqual("33.0.0-jre", entry["version"])
            self.assertEqual("property", entry["versionResolution"])

    def test_it_refuses_to_guess_a_bom_managed_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.inventory(self.build(Path(tmp)))
            entry = next(item for item in report["components"] if item["name"] == "spring-boot-starter-web")
            self.assertIsNone(entry["version"])
            self.assertEqual("managed-by-bom", entry["versionResolution"])

    def test_it_refuses_to_guess_an_unresolvable_property(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.inventory(self.build(Path(tmp)))
            entry = next(item for item in report["components"] if item["name"] == "chained")
            self.assertIsNone(entry["version"])
            self.assertEqual("unresolved-property", entry["versionResolution"])

    def test_a_property_redefined_with_conflicting_values_is_not_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.build(Path(tmp))
            (repo / "mod" / "pom.xml").write_text(
                '<project xmlns="http://maven.apache.org/POM/4.0.0">'
                "<properties><guava.version>1.0-DIFFERENT</guava.version></properties></project>"
            )
            report = self.inventory(repo)
            entry = next(item for item in report["components"] if item["name"] == "guava")
            self.assertIsNone(entry["version"], "a conflicting property must not silently pick one value")
            self.assertEqual("unresolved-property", entry["versionResolution"])

    def test_internal_modules_are_excluded_from_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.inventory(self.build(Path(tmp)))
            self.assertEqual(1, report["totals"]["internalComponentCount"])
            # external = guava, spring-boot-starter-web, junit, chained, left-pad, typescript
            self.assertEqual(6, report["totals"]["externalComponentCount"])
            self.assertEqual(4, report["totals"]["versionedExternalCount"])
            self.assertAlmostEqual(4 / 6, report["metrics"]["sbomCoverage"], places=3)

    def test_npm_lock_entries_carry_their_version_and_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.inventory(self.build(Path(tmp)))
            typescript = next(item for item in report["components"] if item["name"] == "typescript")
            self.assertEqual("5.4.0", typescript["version"])
            self.assertEqual(["dev"], typescript["scopes"])

    def test_node_modules_are_not_walked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.build(Path(tmp))
            vendored = repo / "node_modules" / "vendored"
            vendored.mkdir(parents=True)
            (vendored / "pom.xml").write_text(POM.replace("guava", "vendored-artifact"))
            report = self.inventory(repo)
            self.assertEqual(1, report["sources"]["mavenPomCount"])

    def test_the_report_states_its_limitations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.inventory(self.build(Path(tmp)))
            self.assertTrue(report["limitations"])
            self.assertTrue(any("transitive" in item for item in report["limitations"]))


class SecretScanTest(unittest.TestCase):
    def scan(self, contents: dict[str, str], allowlist: dict | None = None) -> tuple[int, dict, Path]:
        tmp = Path(tempfile.mkdtemp())
        repo = tmp / "repo"
        repo.mkdir()
        for name, body in contents.items():
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
        args = ["--repo", str(repo)]
        if allowlist is not None:
            allow_path = tmp / "allow.json"
            allow_path.write_text(json.dumps(allowlist))
            args += ["--allowlist", str(allow_path)]
        code, report = run(SCAN, *args)
        return code, report, repo

    def rules(self, report: dict) -> set[str]:
        return {finding["rule"] for finding in report["findings"]}

    def test_it_detects_the_credential_shapes_it_claims_to(self) -> None:
        code, report, _ = self.scan({
            "a.py": 'AWS = "AKIA2QWERTYUIOPASDFG"\n',
            "b.py": 'password = "hunter2placeholder"\n',
            "c.py": 'db = "postgres://user:s3cretPassw0rd@host/db"\n',
            "d.py": 'token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"\n',
        })
        self.assertEqual(3, code)
        self.assertEqual(
            {"aws-access-key-id", "assigned-credential", "connection-string-password",
             "github-token"},
            self.rules(report),
        )

    def test_a_clean_tree_exits_zero(self) -> None:
        code, report, _ = self.scan({"a.py": "value = 1\n"})
        self.assertEqual(0, code)
        self.assertEqual(0, report["totals"]["findingCount"])
        self.assertEqual(0.0, report["metrics"]["secretLeakCount"])

    def test_placeholders_and_digests_are_not_reported(self) -> None:
        code, report, _ = self.scan({"a.py": "\n".join([
            'digest = "sha256:' + "a" * 64 + '"',
            'prop = "${spring-boot.version}"',
            'owner = "REPLACE_ME"',
            'template = "{{ vault_token }}"',
            'shell = "$(aws-secret)"',
            'env = "process.env.API_KEY"',
            'placeholder = "<your-token-here>"',
        ]) + "\n"})
        self.assertEqual(0, code, f"false positives: {report['findings']}")

    def test_one_value_is_claimed_by_the_most_specific_rule_only(self) -> None:
        code, report, _ = self.scan({"a.py": 'token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"\n'})
        self.assertEqual(1, report["totals"]["findingCount"],
                         "a token assigned to a variable named token must report once")
        self.assertEqual({"github-token"}, self.rules(report))

    def test_high_entropy_strings_are_advisory_and_do_not_gate(self) -> None:
        code, report, _ = self.scan({"a.py": 'v = "Zx9Kq2Lm8Pw4Rt6Yv1Nc3Bd7Fg5Hj0As"\n'})
        self.assertEqual({"high-entropy-string"}, self.rules(report))
        self.assertEqual("advisory", report["findings"][0]["severity"])
        self.assertEqual(0, code, "an advisory-only result must not fail the run")
        self.assertEqual(0.0, report["metrics"]["secretLeakCount"])
        self.assertEqual(1.0, report["metrics"]["advisoryEntropyHits"])

    def test_a_pem_header_without_key_material_is_not_a_leak(self) -> None:
        code, report, _ = self.scan({
            "loader.java": 'static final String HEADER = "-----BEGIN RSA PRIVATE KEY-----";\n',
        })
        self.assertEqual(0, code, "code that merely names the PEM header is not a leaked key")
        self.assertNotIn("private-key-block", self.rules(report))

    def test_a_pem_header_followed_by_key_material_is_a_leak(self) -> None:
        body = "MIIEowIBAAKCAQEAvSbyGmYhAcRZkFhCTBv7l2Hs0UjKHfNwQpLmXeRtYuIoPaSdFgHjKlZxCvBnM"
        code, report, _ = self.scan({
            "key.pem": f"-----BEGIN RSA PRIVATE KEY-----\n{body}\n{body}\n-----END RSA PRIVATE KEY-----\n",
        })
        self.assertEqual(3, code)
        self.assertIn("private-key-block", self.rules(report))

    def test_vendor_documentation_example_keys_are_not_reported(self) -> None:
        code, report, _ = self.scan({"a.py": 'AWS = "AKIAIOSFODNN7EXAMPLE"\n'})
        self.assertEqual(0, code, "AWS publishes this key id as a documentation example")

    def test_findings_are_redacted(self) -> None:
        code, report, _ = self.scan({"a.py": 'AWS = "AKIA2QWERTYUIOPASDFG"\n'})
        rendered = json.dumps(report)
        self.assertNotIn("AKIA2QWERTYUIOPASDFG", rendered, "the raw credential must never be echoed")
        self.assertIn("len=20", rendered)

    def test_an_allowlist_entry_suppresses_its_own_finding_only(self) -> None:
        code, report, _ = self.scan({"a.py": 'AWS = "AKIA2QWERTYUIOPASDFG"\nB = "AKIA3ZXCVBNMLKJHGFDS"\n'})
        target = report["findings"][0]["fingerprint"]
        code, report, _ = self.scan(
            {"a.py": 'AWS = "AKIA2QWERTYUIOPASDFG"\nB = "AKIA3ZXCVBNMLKJHGFDS"\n'},
            allowlist={"allowed": [{"fingerprint": target, "reason": "fixture", "owner": "sec", "expiresOn": "2099-01-01"}]},
        )
        self.assertEqual(1, report["allowlist"]["suppressedFindings"])
        self.assertEqual(1, report["totals"]["findingCount"], "the other finding must survive")
        self.assertEqual(3, code)

    def test_an_expired_allowlist_entry_stops_suppressing(self) -> None:
        contents = {"a.py": 'AWS = "AKIA2QWERTYUIOPASDFG"\n'}
        _, baseline, _ = self.scan(contents)
        target = baseline["findings"][0]["fingerprint"]
        code, report, _ = self.scan(contents, allowlist={"allowed": [
            {"fingerprint": target, "reason": "fixture", "owner": "sec", "expiresOn": "2020-01-01"}]})
        self.assertEqual(3, code)
        self.assertEqual(1, report["totals"]["findingCount"])
        self.assertTrue(any("expired" in problem for problem in report["allowlist"]["problems"]))

    def test_an_allowlist_entry_without_a_reason_or_owner_is_ignored(self) -> None:
        contents = {"a.py": 'AWS = "AKIA2QWERTYUIOPASDFG"\n'}
        _, baseline, _ = self.scan(contents)
        target = baseline["findings"][0]["fingerprint"]
        code, report, _ = self.scan(contents, allowlist={"allowed": [
            {"fingerprint": target, "expiresOn": "2099-01-01"}]})
        self.assertEqual(3, code)
        self.assertTrue(any("reason or owner" in problem for problem in report["allowlist"]["problems"]))

    def test_coverage_counts_are_reported_so_skips_are_visible(self) -> None:
        code, report, _ = self.scan({"a.py": "value = 1\n", "image.png": "not really a png"})
        self.assertEqual(1, report["coverage"]["filesScanned"])
        self.assertEqual(1, report["coverage"]["filesSkippedBinaryOrUndecodable"])

    def test_it_states_that_a_clean_result_is_not_proof(self) -> None:
        code, report, _ = self.scan({"a.py": "value = 1\n"})
        self.assertTrue(any("does not eliminate" in item for item in report["limitations"]))
        self.assertTrue(any("git history" in item for item in report["limitations"]))

    def test_the_scanned_roots_are_recorded_in_the_report(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        repo = tmp / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "vendor").mkdir(parents=True)
        (repo / "src" / "a.py").write_text('AWS = "AKIA2QWERTYUIOPASDFG"\n')
        (repo / "vendor" / "b.py").write_text('AWS = "AKIA3ZXCVBNMLKJHGFDS"\n')
        code, report = run(SCAN, "--repo", str(repo), "--root", "src")
        self.assertEqual(["src"], report["coverage"]["roots"])
        self.assertEqual(1, report["totals"]["findingCount"],
                         "a root that was not scanned must not contribute findings")
        self.assertEqual(1, report["coverage"]["filesScanned"])

    def test_a_missing_root_is_reported_rather_than_ignored(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        repo = tmp / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "a.py").write_text("value = 1\n")
        code, report = run(SCAN, "--repo", str(repo), "--root", "src", "--root", "does-not-exist")
        self.assertEqual(["does-not-exist"], report["coverage"]["rootsNotFound"],
                         "a typo in a root must be visible, not silently reduce coverage")

    def test_merging_partials_unions_roots_and_deduplicates_findings(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        repo = tmp / "repo"
        for name in ("src", "lib"):
            (repo / name).mkdir(parents=True)
        (repo / "src" / "a.py").write_text('AWS = "AKIA2QWERTYUIOPASDFG"\n')
        (repo / "lib" / "b.py").write_text('AWS = "AKIA3ZXCVBNMLKJHGFDS"\n')
        partials = tmp / "partial"
        partials.mkdir()
        for name in ("src", "lib"):
            subprocess.run([sys.executable, str(SCAN), "--repo", str(repo), "--root", name,
                            "--output", str(partials / f"{name}.json")], capture_output=True, check=False)
        # The same partial listed twice must not double-count its finding.
        (partials / "src-again.json").write_text((partials / "src.json").read_text())
        merged = tmp / "merged.json"
        result = subprocess.run([sys.executable, str(SCAN), "--merge", str(partials),
                                 "--output", str(merged)], capture_output=True, text=True, check=False)
        self.assertEqual(3, result.returncode)
        report = json.loads(merged.read_text())
        self.assertEqual(["lib", "src"], report["coverage"]["roots"])
        self.assertEqual(2, report["totals"]["findingCount"])
        self.assertEqual(2.0, report["metrics"]["secretLeakCount"])
        self.assertTrue(any("only the roots listed" in item for item in report["limitations"]))

    def test_merging_an_empty_directory_is_an_error_not_a_clean_result(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        empty = tmp / "partial"
        empty.mkdir()
        result = subprocess.run([sys.executable, str(SCAN), "--merge", str(empty),
                                 "--output", str(tmp / "out.json")], capture_output=True, text=True, check=False)
        self.assertEqual(2, result.returncode, "an empty merge must not look like a clean scan")


if __name__ == "__main__":
    unittest.main()
