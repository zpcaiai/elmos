from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from scripts.batch30.spring_launch_evidence import (
    APPROVER_ROLE,
    BUSINESS_LINE,
    DESIGN_PARTNER_ROLE,
    EXECUTOR_ROLE,
    GATE_IDS,
    INDEX_AUTHORITY_ROLE,
    NAMESPACE,
    PROFILE,
    REVIEWER_ROLE,
    ROUTE_ID,
    SPRING_WORKER_CONFIGURATION_ENV_KEYS,
    VERIFIER_ROLE,
    SpringLaunchEvidenceError,
    VerifiedEnvelope,
    _immutable_uri,
    _load_trust,
    _register_signer,
    _write_new_owner_only,
    application_mount_sources_digest,
    application_environment_commitment_digest,
    assemble_spring_launch_receipt,
    collect_web_console_runtime_attestation,
    content_reference,
    expected_spring_worker_environment,
    expected_web_console_environment,
    expected_web_console_environment_names,
    receipt_digest,
    spring_worker_configuration_digest,
    web_console_configuration_digest,
    web_console_environment_names_digest,
    verify_spring_launch_receipt,
    verify_spring_launch_receipt_file,
)
from scripts.precision_migration.trust import (
    TrustStore,
    canonical_bytes,
    canonical_digest,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/batch30/spring_launch_evidence.py"


class SpringLaunchEvidenceTests(unittest.TestCase):
    def test_reference_binds_existing_bytes_below_an_explicit_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            evidence_root = Path(temporary).resolve()
            evidence = evidence_root / "staging-report.json"
            payload = b'{"outcome":"PASSED_EXTERNAL"}'
            evidence.write_bytes(payload)

            reference = content_reference(
                evidence,
                evidence_roots=[evidence_root],
                media_type="application/json",
            )

        self.assertEqual("file://" + str(evidence), reference["uri"])
        self.assertEqual("sha256:" + hashlib.sha256(payload).hexdigest(), reference["digest"])
        self.assertEqual(len(payload), reference["size_bytes"])

    def test_reference_rejects_paths_outside_the_approved_root(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            evidence = Path(first).resolve() / "evidence.bin"
            evidence.write_bytes(b"external evidence")
            with self.assertRaisesRegex(SpringLaunchEvidenceError, "approved evidence roots"):
                content_reference(evidence, evidence_roots=[Path(second).resolve()])

    def test_receipt_digest_is_canonical_and_excludes_its_own_field(self) -> None:
        left = {"z": 1, "a": {"b": 2}}
        right = {"a": {"b": 2}, "receipt_digest": "ignored", "z": 1}
        self.assertEqual(receipt_digest(left), receipt_digest(right))
        self.assertRegex(receipt_digest(left), r"^sha256:[0-9a-f]{64}$")

    def test_worker_configuration_digest_binds_presence_and_supported_inventory(self) -> None:
        explicit_empty = {
            name: "" for name in SPRING_WORKER_CONFIGURATION_ENV_KEYS
        }
        self.assertNotEqual(
            spring_worker_configuration_digest({}),
            spring_worker_configuration_digest(explicit_empty),
        )
        image_injected = dict(explicit_empty)
        image_injected["ELMOS_ALLOWED_GIT_HOSTS"] = "unreviewed.example"
        self.assertNotEqual(
            spring_worker_configuration_digest(explicit_empty),
            spring_worker_configuration_digest(image_injected),
        )
        expected = expected_spring_worker_environment(
            {
                "ELMOS_SPRING_RUNTIME_RUNNER_BASE_URL": "https://spring-runner.example/runtime",
                "ELMOS_SPRING_RUNTIME_RUNNER_ENABLED": "true",
                "ELMOS_SPRING_TRANSFORMER_BROKER_BASE_URL": "https://spring-runner.example/transform",
                "ELMOS_SPRING_TRANSFORMER_BROKER_ENABLED": "true",
                "ELMOS_SPRING_UPGRADE_NETWORK_POLICY_ATTESTED": "true",
                "ELMOS_SPRING_UPGRADE_ROOTLESS_ATTESTED": "true",
                "ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL": "https://spring-runner.example/verify",
                "ELMOS_SPRING_UPGRADE_VERIFIER_ENABLED": "true",
                "ELMOS_SPRING_UPGRADE_VERIFIER_ID": "independent-verifier-one",
            }
        )
        expected_digest = spring_worker_configuration_digest(expected)
        for name in (
            "SPRING_APPLICATION_JSON",
            "JAVA_TOOL_OPTIONS",
            "_JAVA_OPTIONS",
            "JAVA_OPTS",
            "JDK_JAVA_OPTIONS",
            "SERVER_SERVLET_CONTEXT_PATH",
            "SERVER_SERVLET_PATH",
            "SPRING_MVC_SERVLET_PATH",
        ):
            with self.subTest(missing_explicit_empty=name):
                missing = dict(expected)
                del missing[name]
                self.assertNotEqual(
                    expected_digest,
                    spring_worker_configuration_digest(missing),
                )

        expected_web_names = expected_web_console_environment_names(
            {"DATABASE_PASSWORD": "never-serialize-this"}
        )
        self.assertIn("DATABASE_PASSWORD", expected_web_names)
        self.assertNotIn("never-serialize-this", expected_web_names)
        with self.assertRaisesRegex(
            SpringLaunchEvidenceError, "must not declare Spring or process override"
        ):
            expected_web_console_environment_names(
                {"ELMOS_SPRING_PROXY_ENABLED": "true"}
            )

        application_yaml = (
            ROOT / "apps/java-engine-worker/src/main/resources/application.yml"
        ).read_text(encoding="utf-8")
        configured = set(
            re.findall(r"\$\{(ELMOS_[A-Z0-9_]+)(?::[^}]*)?\}", application_yaml)
        )
        self.assertEqual(set(SPRING_WORKER_CONFIGURATION_ENV_KEYS), configured)
        dockerfile = (ROOT / "apps/java-engine-worker/Dockerfile").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'ENTRYPOINT ["/opt/java/openjdk/bin/java","-XX:MaxRAMPercentage=70","-jar","/app/app.jar"]',
            dockerfile,
        )
        self.assertRegex(dockerfile, r"(?m)^CMD \[\]$")

    def test_application_environment_commitment_never_hashes_secret_values(self) -> None:
        first = {
            "DATABASE_PASSWORD": "correct-horse-battery-staple",
            "OIDC_CLIENT_SECRET": "first-secret-value",
            "EMPTY_OPTION": "",
            "ELMOS_DATABASE_SQL_PREFLIGHT_ENABLED": "true",
        }
        rotated = {
            **first,
            "DATABASE_PASSWORD": "independently-rotated-secret",
            "OIDC_CLIENT_SECRET": "second-secret-value",
        }
        digest = application_environment_commitment_digest(first)
        self.assertEqual(digest, application_environment_commitment_digest(rotated))
        self.assertNotIn("correct-horse", digest)
        self.assertNotEqual(
            digest,
            application_environment_commitment_digest(
                {**first, "EMPTY_OPTION": "now-present-and-nonempty"}
            ),
        )
        self.assertNotEqual(
            digest,
            application_environment_commitment_digest(
                {**first, "ELMOS_DATABASE_SQL_PREFLIGHT_ENABLED": "false"}
            ),
        )

    def test_verify_cli_rejects_unsigned_placeholder_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            receipt = root / "receipt.json"
            trust = root / "trust.json"
            receipt.write_text(json.dumps({"schema_version": 1}) + "\n", encoding="utf-8")
            trust.write_text(json.dumps({"schema_version": 1, "keys": []}) + "\n", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "verify",
                    str(receipt),
                    "--trust-store",
                    str(trust),
                    "--evidence-root",
                    str(root),
                    "--expected-trust-store-digest",
                    "sha256:" + "0" * 64,
                    "--expected-environment-id",
                    "staging-one",
                    "--expected-deployment-id",
                    "deployment-one",
                    "--expected-provider",
                    "private-linux",
                    "--expected-region",
                    "cn-test-one",
                    "--expected-environment-class",
                    "STAGING",
                    "--expected-configuration-digest",
                    "sha256:" + "1" * 64,
                    "--expected-application-environment-commitment-digest",
                    "sha256:" + "2" * 64,
                    "--expected-effective-spring-configuration-digest",
                    "sha256:" + "3" * 64,
                    "--expected-effective-web-console-configuration-digest",
                    "sha256:" + "4" * 64,
                    "--expected-web-console-environment-names-digest",
                    "sha256:" + "5" * 64,
                    "--expected-application-mount-sources-digest",
                    "sha256:" + "6" * 64,
                    "--expected-worker-application-artifact-digest",
                    "sha256:" + "7" * 64,
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(2, completed.returncode)
        self.assertIn("SPRING LAUNCH EVIDENCE FAIL", completed.stderr)
        self.assertIn("receipt fields are invalid", completed.stderr)

    def test_sanitized_web_collector_and_worker_artifact_are_make_wired(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "collect-web-runtime", "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, completed.returncode)
        self.assertIn("--expected-image-digest", completed.stdout)
        self.assertIn("--worker-container", completed.stdout)
        self.assertIn("--expected-worker-image-digest", completed.stdout)
        self.assertNotIn("--raw-inspect-file", completed.stdout)
        makefile = (ROOT / "Makefile.batch30").read_text(encoding="utf-8")
        self.assertIn("spring-web-runtime-attestation:", makefile)
        self.assertIn("collect-web-runtime", makefile)
        self.assertIn('--worker-container "$${SPRING_WORKER_CONTAINER}"', makefile)
        self.assertIn(
            '--expected-worker-image-digest "$${SPRING_WORKER_IMAGE_DIGEST}"',
            makefile,
        )
        self.assertIn('test -n "$${SPRING_EXPECTED_REVISION}"', makefile)
        self.assertIn('--expected-revision "$${SPRING_EXPECTED_REVISION}"', makefile)
        self.assertIn(
            'test -n "$${SPRING_WORKER_APPLICATION_ARTIFACT_DIGEST}"', makefile
        )
        self.assertIn(
            '--expected-worker-application-artifact-digest "$${SPRING_WORKER_APPLICATION_ARTIFACT_DIGEST}"',
            makefile,
        )


class SignedSpringLaunchReceiptTests(unittest.TestCase):
    NOW = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
    REVISION = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    KEY_SPECS = {
        "executor": (EXECUTOR_ROLE, "executor-actor", "executor-org"),
        "verifier": (VERIFIER_ROLE, "verifier-actor", "verifier-org"),
        "reviewer": (REVIEWER_ROLE, "reviewer-actor", "reviewer-org"),
        "release": (APPROVER_ROLE, "release-actor", "release-org"),
        "risk": (APPROVER_ROLE, "risk-actor", "risk-org"),
        "partner-a": (DESIGN_PARTNER_ROLE, "partner-a-actor", "partner-a-org"),
        "partner-b": (DESIGN_PARTNER_ROLE, "partner-b-actor", "partner-b-org"),
        "index": (INDEX_AUTHORITY_ROLE, "index-actor", "index-org"),
    }
    SIGNATURE_CACHE: dict[tuple[str, bytes], str] = {}

    @classmethod
    def setUpClass(cls) -> None:
        cls.key_directory = tempfile.TemporaryDirectory(prefix="spring-launch-keys-")
        cls.key_root = Path(cls.key_directory.name)
        cls.private_keys = {}
        cls.public_keys = {}
        for name in cls.KEY_SPECS:
            private_key = cls.key_root / f"{name}.private.pem"
            public_key = cls.key_root / f"{name}.public.pem"
            subprocess.run(
                ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
                check=True,
                capture_output=True,
            )
            cls.private_keys[name] = private_key
            cls.public_keys[name] = public_key

    @classmethod
    def tearDownClass(cls) -> None:
        cls.key_directory.cleanup()

    def setUp(self) -> None:
        self._ANCESTOR_CACHE.clear()
        self.temporary = tempfile.TemporaryDirectory(prefix="spring-launch-case-")
        self.case = Path(self.temporary.name).resolve()
        self.evidence_root = self.case / "evidence"
        self.evidence_root.mkdir()
        self.trust_root = self.case / "trust"
        (self.trust_root / "keys").mkdir(parents=True)
        for name, public_key in self.public_keys.items():
            (self.trust_root / "keys" / f"{name}.pem").write_bytes(public_key.read_bytes())
        self.trust_path = self.trust_root / "trust.json"
        self.write_json(
            self.trust_path,
            {
                "schema_version": 1,
                "namespace": NAMESPACE,
                "keys": [
                    {
                        "key_id": f"key-{name}",
                        "actor_id": actor,
                        "organization_id": organization,
                        "roles": [role],
                        "public_key_path": f"keys/{name}.pem",
                        "not_before": "2026-01-01T00:00:00Z",
                        "not_after": "2027-01-01T00:00:00Z",
                        "revoked": False,
                    }
                    for name, (role, actor, organization) in self.KEY_SPECS.items()
                ],
                "revoked_record_ids": [],
            },
        )
        os.chmod(self.trust_path, 0o600)
        self.signature_number = 0

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def write_json(path: Path, value: object, *, canonical: bool = False) -> None:
        if canonical:
            path.write_bytes(canonical_bytes(value))
        else:
            path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")

    def ref(self, path: Path, media_type: str = "application/json") -> dict[str, object]:
        return content_reference(
            path,
            evidence_roots=[self.evidence_root],
            media_type=media_type,
        )

    @staticmethod
    def mount_object_identity(source: str) -> dict[str, object]:
        observed = os.stat(source, follow_symlinks=False)
        uid = 0 if observed.st_uid == 0 else 10001
        gid = 0 if observed.st_uid == 0 else 10001
        return {
            "device": observed.st_dev,
            "inode": observed.st_ino,
            "object_type": (
                "DIRECTORY" if stat.S_ISDIR(observed.st_mode) else "REGULAR_FILE"
            ),
            "size_bytes": observed.st_size,
            "mode": stat.S_IMODE(observed.st_mode),
            # Production requires the application container identity.  Tests
            # cannot chown temporary files without privilege, so the injected
            # observer preserves all real inode/change fields and supplies the
            # production ownership contract explicitly.
            "uid": uid,
            "gid": gid,
            "link_count": observed.st_nlink,
            "ctime_ns": observed.st_ctime_ns,
        }

    _ANCESTOR_CACHE: dict[str, list[dict[str, object]]] = {}

    @classmethod
    def mount_source_snapshot(cls, source: str) -> dict[str, object]:
        path = Path(source)
        parent_path_str = str(path.parent)
        cached = cls._ANCESTOR_CACHE.get(parent_path_str)
        if cached is not None:
            ancestors = [dict(item) for item in cached]
        else:
            ancestors = []
            current = Path(path.anchor)
            ancestors.append(cls.mount_object_identity(str(current)))
            for part in path.parts[1:-1]:
                current /= part
                ancestors.append(cls.mount_object_identity(str(current)))
            cls._ANCESTOR_CACHE[parent_path_str] = [dict(item) for item in ancestors]
        return {
            "object_identity": cls.mount_object_identity(source),
            "parent_identity": dict(ancestors[-1]),
            "ancestor_identities": ancestors,
        }

    def live_mount_observer(
        self, source: str, process_id: int, destination: str, label: str
    ) -> tuple[
        dict[str, object],
        dict[str, object],
        dict[str, object],
        list[dict[str, object]],
        str,
    ]:
        snapshot = self.mount_source_snapshot(source)
        identity = dict(snapshot["object_identity"])
        process_digest = "sha256:" + hashlib.sha256(
            f"{process_id}\0{destination}\0{label}".encode("utf-8")
        ).hexdigest()
        return (
            identity,
            dict(identity),
            dict(snapshot["parent_identity"]),
            [dict(item) for item in snapshot["ancestor_identities"]],
            process_digest,
        )

    def collect_web_runtime(
        self,
        web_value: object,
        *,
        worker_bytes: bytes | None = None,
        reinspection_web_value: object | None = None,
        reinspection_worker_bytes: bytes | None = None,
        observer: object | None = None,
    ) -> dict[str, object]:
        raw_web = canonical_bytes(web_value)
        raw_worker = worker_bytes or self.worker_inspect_bytes
        raw_web_after = canonical_bytes(
            web_value if reinspection_web_value is None else reinspection_web_value
        )
        raw_worker_after = reinspection_worker_bytes or raw_worker
        return collect_web_console_runtime_attestation(
            raw_web,
            raw_worker_inspect=raw_worker,
            expected_image_digest="sha256:" + "9" * 64,
            expected_worker_image_digest="sha256:" + "8" * 64,
            collector_identity="staging-runtime-collector",
            captured_at=datetime(2026, 9, 4, 8, 50, tzinfo=timezone.utc),
            stable_reinspect=lambda: (raw_web_after, raw_worker_after),
            _live_mount_observer=observer or self.live_mount_observer,
        )

    def sign(self, key_name: str, payload: dict[str, object]) -> dict[str, object]:
        payload_bytes = canonical_bytes(payload)
        cache_key = (key_name, payload_bytes)
        cached_signature = self.SIGNATURE_CACHE.get(cache_key)
        if cached_signature is not None:
            return {
                "algorithm": "ed25519",
                "key_id": f"key-{key_name}",
                "payload": payload,
                "signature": cached_signature,
            }
        self.signature_number += 1
        payload_path = self.case / f"payload-{self.signature_number}.json"
        signature_path = self.case / f"signature-{self.signature_number}.bin"
        payload_path.write_bytes(payload_bytes)
        subprocess.run(
            [
                "openssl", "pkeyutl", "-sign", "-inkey", str(self.private_keys[key_name]),
                "-rawin", "-in", str(payload_path), "-out", str(signature_path),
            ],
            check=True,
            capture_output=True,
        )
        encoded_signature = base64.b64encode(signature_path.read_bytes()).decode("ascii")
        self.SIGNATURE_CACHE[cache_key] = encoded_signature
        return {
            "algorithm": "ed25519",
            "key_id": f"key-{key_name}",
            "payload": payload,
            "signature": encoded_signature,
        }

    @staticmethod
    def fixture_envelope(
        key_name: str, payload: dict[str, object]
    ) -> dict[str, object]:
        """Build a shape-only envelope for tests that fail before crypto intake."""

        return {
            "algorithm": "ed25519",
            "key_id": f"key-{key_name}",
            "payload": payload,
            "signature": base64.b64encode(b"\0" * 64).decode("ascii"),
        }

    def make_receipt(
        self,
        *,
        controlled_index: bool = False,
        real_signatures: bool = False,
        sampled_signatures: bool = False,
    ) -> dict[str, object]:
        if real_signatures and sampled_signatures:
            raise ValueError("fixture cannot request both real and sampled signatures")
        sampled_keys: set[str] = set()

        def sampled_signer(
            key_name: str, payload: dict[str, object]
        ) -> dict[str, object]:
            if key_name not in sampled_keys:
                sampled_keys.add(key_name)
                return self.sign(key_name, payload)
            return self.fixture_envelope(key_name, payload)

        sign_envelope = (
            self.sign
            if real_signatures
            else sampled_signer
            if sampled_signatures
            else self.fixture_envelope
        )
        profile = self.evidence_root / "profile.json"
        profile.write_bytes(PROFILE.read_bytes())
        artifact = self.evidence_root / "artifact.jar"
        artifact.write_bytes(b"exact deployed artifact bytes")
        profile_ref = self.ref(profile)
        artifact_ref = self.ref(artifact, "application/java-archive")
        worker_environment = expected_spring_worker_environment(
            {
            "ELMOS_SPRING_RUNTIME_RUNNER_BASE_URL": "https://spring-runner.example/runtime",
            "ELMOS_SPRING_RUNTIME_RUNNER_ENABLED": "true",
            "ELMOS_SPRING_TRANSFORMER_BROKER_BASE_URL": "https://spring-runner.example/transform",
            "ELMOS_SPRING_TRANSFORMER_BROKER_ENABLED": "true",
            "ELMOS_SPRING_UPGRADE_NETWORK_POLICY_ATTESTED": "true",
            "ELMOS_SPRING_UPGRADE_ROOTLESS_ATTESTED": "true",
            "ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL": "https://spring-runner.example/verify",
            "ELMOS_SPRING_UPGRADE_VERIFIER_ENABLED": "true",
            "ELMOS_SPRING_UPGRADE_VERIFIER_ID": "independent-verifier-one",
            }
        )
        mount_root = self.case / "runtime-mounts"
        workspace_source = mount_root / "workspace"
        replay_source = mount_root / "engine-replay"
        workspace_source.mkdir(parents=True, exist_ok=True)
        replay_source.mkdir(exist_ok=True)
        os.chmod(mount_root, 0o700)
        os.chmod(workspace_source, 0o700)
        os.chmod(replay_source, 0o700)
        secret_sources: dict[str, Path] = {}
        for name in ("verifier", "transformer", "runtime", "engine", "resend"):
            path = mount_root / f"{name}.secret"
            if not path.exists():
                path.write_bytes((name.encode("ascii") + b"-") * 8)
            os.chmod(path, 0o600)
            secret_sources[name] = path
        worker_mounts = {
            "/workspace/private-runner": (str(workspace_source), True),
            "/run/secrets/elmos-verifier-hmac": (str(secret_sources["verifier"]), False),
            "/run/secrets/elmos-transformer-hmac": (str(secret_sources["transformer"]), False),
            "/run/secrets/elmos-runtime-hmac": (str(secret_sources["runtime"]), False),
            "/run/secrets/elmos-spring-engine-hmac": (str(secret_sources["engine"]), False),
            "/var/lib/elmos/spring-engine-auth-replay": (str(replay_source), True),
        }
        inspect_value = [
            {
                "Id": "a" * 64,
                "Name": "/elmos-staging-java-engine-worker-1",
                "Image": "sha256:" + "8" * 64,
                "Path": "/opt/java/openjdk/bin/java",
                "Args": [
                    "-XX:MaxRAMPercentage=70",
                    "-jar",
                    "/app/app.jar",
                ],
                "State": {
                    "Running": True,
                    "Restarting": False,
                    "Dead": False,
                    "Pid": 41001,
                },
                "Config": {
                    "Image": "elmos-java-engine-worker:staging-one",
                    "Entrypoint": [
                        "/opt/java/openjdk/bin/java",
                        "-XX:MaxRAMPercentage=70",
                        "-jar",
                        "/app/app.jar",
                    ],
                    "Cmd": [],
                    "User": "10001:10001",
                    "WorkingDir": "/app",
                    "ExposedPorts": {"8081/tcp": {}},
                    "Labels": {
                        "com.docker.compose.project": "elmos-staging",
                        "com.docker.compose.service": "java-engine-worker",
                    },
                    "Env": [
                        f"{name}={value}"
                        for name, value in sorted(worker_environment.items())
                    ],
                },
                "HostConfig": {
                    "ReadonlyRootfs": True,
                    "Privileged": False,
                    "PidMode": "",
                    "IpcMode": "private",
                    "UTSMode": "",
                    "UsernsMode": "",
                    "CgroupnsMode": "private",
                    "AutoRemove": False,
                    "PublishAllPorts": False,
                    "Init": True,
                    "PidsLimit": 1024,
                    "Runtime": "runc",
                    "Isolation": "",
                    "OomKillDisable": False,
                    "CapAdd": None,
                    "CapDrop": ["ALL"],
                    "SecurityOpt": ["no-new-privileges:true"],
                    "Devices": [],
                    "DeviceRequests": None,
                    "VolumesFrom": None,
                    "Links": None,
                    "RestartPolicy": {"Name": "unless-stopped"},
                    "Tmpfs": {
                        "/tmp": "rw,noexec,nosuid,size=512m",
                        "/home/elmos/.m2": "rw,noexec,nosuid,size=512m",
                    },
                    "NetworkMode": "elmos-staging_backend",
                    "PortBindings": {},
                    "Binds": [
                        f"{source}:{destination}:{'rw' if writable else 'ro'}"
                        for destination, (source, writable) in worker_mounts.items()
                    ],
                },
                "NetworkSettings": {
                    "Networks": {"elmos-staging_backend": {}},
                    "Ports": {"8081/tcp": None},
                },
                "Mounts": [
                    {
                        "Type": "bind",
                        "Source": source,
                        "Destination": destination,
                        "RW": writable,
                        "Mode": "rw" if writable else "ro",
                        "Propagation": "rprivate",
                    }
                    for destination, (source, writable) in worker_mounts.items()
                ],
            }
        ]
        container_inspect = self.evidence_root / "java-engine-worker.inspect.json"
        self.write_json(container_inspect, inspect_value)
        self.worker_inspect_value = copy.deepcopy(inspect_value)
        self.worker_inspect_bytes = container_inspect.read_bytes()
        container_inspect_ref = self.ref(container_inspect)
        container_inspect_evidence = {
            **container_inspect_ref,
            "verification": {
                "mode": "LOCAL_BYTES",
                "local_uri": container_inspect_ref["uri"],
            },
        }
        web_environment = expected_web_console_environment()
        web_mounts = {
            "/run/secrets/elmos/resend-api-key": (str(secret_sources["resend"]), False),
            "/run/secrets/elmos-spring-engine-hmac": (str(secret_sources["engine"]), False),
        }
        web_inspect_value = [
            {
                "Id": "b" * 64,
                "Name": "/elmos-staging-web-console-1",
                "Image": "sha256:" + "9" * 64,
                "Path": "/usr/local/bin/docker-entrypoint.sh",
                "Args": [
                    "/usr/local/bin/node",
                    "/workspace/apps/web-console/node_modules/next/dist/bin/next",
                    "start",
                    "--hostname",
                    "0.0.0.0",
                    "--port",
                    "3000",
                ],
                "State": {
                    "Running": True,
                    "Restarting": False,
                    "Dead": False,
                    "Pid": 41002,
                },
                "Config": {
                    "Image": "elmos-web-console:staging-one",
                    "Entrypoint": ["/usr/local/bin/docker-entrypoint.sh"],
                    "Cmd": [
                        "/usr/local/bin/node",
                        "/workspace/apps/web-console/node_modules/next/dist/bin/next",
                        "start",
                        "--hostname",
                        "0.0.0.0",
                        "--port",
                        "3000",
                    ],
                    "User": "10001:10001",
                    "WorkingDir": "/workspace/apps/web-console",
                    "ExposedPorts": {"3000/tcp": {}},
                    "Labels": {
                        "com.docker.compose.project": "elmos-staging",
                        "com.docker.compose.service": "web-console",
                    },
                    "Env": [
                        f"{name}={value}"
                        for name, value in sorted(web_environment.items())
                    ],
                },
                "HostConfig": {
                    "ReadonlyRootfs": True,
                    "Privileged": False,
                    "PidMode": "",
                    "IpcMode": "private",
                    "UTSMode": "",
                    "UsernsMode": "",
                    "CgroupnsMode": "private",
                    "AutoRemove": False,
                    "PublishAllPorts": False,
                    "Init": True,
                    "PidsLimit": 512,
                    "Runtime": "runc",
                    "Isolation": "",
                    "OomKillDisable": False,
                    "CapAdd": None,
                    "CapDrop": ["ALL"],
                    "SecurityOpt": ["no-new-privileges:true"],
                    "Devices": [],
                    "DeviceRequests": None,
                    "VolumesFrom": None,
                    "Links": None,
                    "RestartPolicy": {"Name": "unless-stopped"},
                    "Tmpfs": {"/tmp": "rw,noexec,nosuid,size=64m"},
                    "NetworkMode": "elmos-staging_edge",
                    "PortBindings": {},
                    "Binds": [
                        f"{source}:{destination}:{'rw' if writable else 'ro'}"
                        for destination, (source, writable) in web_mounts.items()
                    ],
                },
                "NetworkSettings": {
                    "Networks": {
                        "elmos-staging_edge": {},
                        "elmos-staging_backend": {},
                    },
                    "Ports": {"3000/tcp": None},
                },
                "Mounts": [
                    {
                        "Type": "bind",
                        "Source": source,
                        "Destination": destination,
                        "RW": writable,
                        "Mode": "rw" if writable else "ro",
                        "Propagation": "rprivate",
                    }
                    for destination, (source, writable) in web_mounts.items()
                ],
            }
        ]
        self.web_inspect_value = copy.deepcopy(web_inspect_value)
        self.application_mount_sources = {
            "worker_workspace": worker_mounts["/workspace/private-runner"][0],
            "worker_verifier_hmac": worker_mounts[
                "/run/secrets/elmos-verifier-hmac"
            ][0],
            "worker_transformer_hmac": worker_mounts[
                "/run/secrets/elmos-transformer-hmac"
            ][0],
            "worker_runtime_hmac": worker_mounts[
                "/run/secrets/elmos-runtime-hmac"
            ][0],
            "application_engine_hmac": worker_mounts[
                "/run/secrets/elmos-spring-engine-hmac"
            ][0],
            "worker_engine_replay": worker_mounts[
                "/var/lib/elmos/spring-engine-auth-replay"
            ][0],
            "web_resend_secret": web_mounts[
                "/run/secrets/elmos/resend-api-key"
            ][0],
        }
        web_runtime_value = self.collect_web_runtime(web_inspect_value)
        web_runtime = self.evidence_root / "web-console.runtime-attestation.json"
        self.write_json(web_runtime, web_runtime_value, canonical=True)
        web_runtime_ref = self.ref(web_runtime)
        web_runtime_evidence = {
            **web_runtime_ref,
            "verification": {
                "mode": "LOCAL_BYTES",
                "local_uri": web_runtime_ref["uri"],
            },
        }
        image_attestation = self.evidence_root / "worker-image-artifact-attestation.json"
        self.write_json(
            image_attestation,
            {
                "schema_version": 1,
                "namespace": NAMESPACE,
                "method": "OCI_IMAGE_CONTENT_EXTRACTION_V1",
                "builder_identity": "staging-image-extractor",
                "build_invocation_id": "build-one",
                "deployed_revision": self.REVISION,
                "image_digest": "sha256:" + "8" * 64,
                "image_reference": "elmos-java-engine-worker:staging-one",
                "artifact_path": "/app/app.jar",
                "worker_application_artifact_digest": "sha256:" + "c" * 64,
                "extracted_at": "2026-09-04T08:45:00Z",
                "outcome": "VERIFIED",
                "synthetic": False,
                "unknowns": [],
                "not_run": [],
            },
            canonical=True,
        )
        image_attestation_ref = self.ref(image_attestation)
        image_attestation_evidence = {
            **image_attestation_ref,
            "verification": {
                "mode": "LOCAL_BYTES",
                "local_uri": image_attestation_ref["uri"],
            },
        }
        environment_value = {
            "schema_version": 1,
            "namespace": NAMESPACE,
            "environment_id": "staging-one",
            "deployment_id": "deployment-one",
            "environment_class": "STAGING",
            "provider": "private-linux",
            "region": "cn-test-one",
            "tenant_mode": "MULTI_TENANT",
            "execution_plane": "PRIVATE_ROOTLESS_RUNNER_BROKER",
            "deployed_revision": self.REVISION,
            "launch_profile_digest": profile_ref["digest"],
            "artifact_digest": artifact_ref["digest"],
            "configuration_digest": "sha256:" + "1" * 64,
            "application_environment_commitment_digest": (
                application_environment_commitment_digest({})
            ),
            "container_inspect": container_inspect_evidence,
            "web_console_runtime_attestation": web_runtime_evidence,
            "effective_spring_configuration_digest": spring_worker_configuration_digest(
                worker_environment
            ),
            "effective_web_console_configuration_digest": web_console_configuration_digest(
                web_environment
            ),
            "web_console_environment_names_digest": web_console_environment_names_digest(
                web_environment
            ),
            "application_mount_sources_digest": application_mount_sources_digest(
                self.application_mount_sources,
                _identity_provider=lambda name, source: self.mount_source_snapshot(source),
            ),
            "worker_image_artifact_attestation": image_attestation_evidence,
            "worker_application_artifact_digest": "sha256:" + "c" * 64,
            "network_policy_digest": "sha256:" + "2" * 64,
            "rootless_policy_digest": "sha256:" + "3" * 64,
            "runtime_image_digests": {
                "worker": "sha256:" + "8" * 64,
                "web": "sha256:" + "9" * 64,
                "proxy": "sha256:" + "4" * 64,
                "transformer": "sha256:" + "5" * 64,
                "runner": "sha256:" + "6" * 64,
            },
            "captured_at": "2026-09-04T08:50:00Z",
            "secrets_embedded": False,
        }
        environment = self.evidence_root / "environment.json"
        self.write_json(environment, environment_value, canonical=True)
        binding = {
            "deployed_revision": self.REVISION,
            "launch_profile": profile_ref,
            "artifact": artifact_ref,
            "environment": self.ref(environment),
        }
        binding_digest = canonical_digest(binding)
        receipt_id = "spring-launch-one"
        gate_refs = []
        for index, gate_id in enumerate(GATE_IDS):
            path = self.evidence_root / f"gate-{index}.json"
            path.write_text(json.dumps({"gate": gate_id, "sequence": index}) + "\n")
            reference = self.ref(path)
            gate_refs.append(
                {
                    **reference,
                    "verification": {"mode": "LOCAL_BYTES", "local_uri": reference["uri"]},
                }
            )

        evidence_index = None
        index_envelope = None
        index_digest = None
        if controlled_index:
            first = gate_refs[0]
            remote_uri = "s3://spring-evidence/staging.json?versionId=one"
            entry = {
                "entry_id": "staging-entry",
                "uri": remote_uri,
                "digest": first["digest"],
                "size_bytes": first["size_bytes"],
                "media_type": first["media_type"],
                "recorded_at": "2026-09-04T08:45:00Z",
            }
            index_value = {
                "schema_version": 1,
                "namespace": NAMESPACE,
                "index_id": "index-one",
                "generated_at": "2026-09-04T08:55:00Z",
                "entries": [entry],
            }
            index_file = self.evidence_root / "index.json"
            self.write_json(index_file, index_value, canonical=True)
            index_ref = self.ref(index_file)
            index_envelope = sign_envelope(
                "index",
                {
                    "record_id": "index-record",
                    "issued_at": "2026-09-04T09:01:00Z",
                    "expires_at": "2026-09-05T10:00:00Z",
                    "actor_id": "index-actor",
                    "organization_id": "index-org",
                    "role": INDEX_AUTHORITY_ROLE,
                    "receipt_id": receipt_id,
                    "binding_digest": binding_digest,
                    "index_id": "index-one",
                    "index_content_digest": index_ref["digest"],
                    "index_content_size_bytes": index_ref["size_bytes"],
                    "outcome": "INDEX_AUTHENTICATED",
                    "synthetic": False,
                    "unknowns": [],
                    "not_run": [],
                },
            )
            evidence_index = {"content": index_ref, "attestation": index_envelope}
            gate_refs[0] = {
                "uri": remote_uri,
                "digest": first["digest"],
                "size_bytes": first["size_bytes"],
                "media_type": first["media_type"],
                "verification": {
                    "mode": "CONTROLLED_INDEX",
                    "entry_id": "staging-entry",
                    "entry_digest": canonical_digest(entry),
                },
            }
            index_digest = index_ref["digest"]

        evidence_set_digest = canonical_digest(
            {
                "receipt_id": receipt_id,
                "binding_digest": binding_digest,
                "observed_at": "2026-09-04T09:00:00Z",
                "controlled_index_content_digest": index_digest,
                "gates": [
                    {"id": gate, "status": "PASSED_EXTERNAL", "evidence": gate_refs[index]}
                    for index, gate in enumerate(GATE_IDS)
                ],
            }
        )
        gates = []
        gate_envelope_digests = []
        for index, gate_id in enumerate(GATE_IDS):
            reference = gate_refs[index]
            common = {
                "receipt_id": receipt_id,
                "binding_digest": binding_digest,
                "evidence_set_digest": evidence_set_digest,
                "gate_id": gate_id,
                "evidence_uri": reference["uri"],
                "evidence_digest": reference["digest"],
                "evidence_size_bytes": reference["size_bytes"],
                "outcome": "PASSED_EXTERNAL",
                "evidence_class": "EXTERNAL_NON_SYNTHETIC",
                "synthetic": False,
                "unknowns": [],
                "not_run": [],
            }
            execution_payload = {
                "record_id": f"execution-{index}",
                "issued_at": "2026-09-04T09:05:00Z",
                "expires_at": "2026-09-05T10:00:00Z",
                "actor_id": "executor-actor",
                "organization_id": "executor-org",
                "role": EXECUTOR_ROLE,
                **common,
            }
            execution = sign_envelope("executor", execution_payload)
            verification = sign_envelope(
                "verifier",
                {
                    "record_id": f"verification-{index}",
                    "issued_at": "2026-09-04T09:10:00Z",
                    "expires_at": "2026-09-05T10:00:00Z",
                    "actor_id": "verifier-actor",
                    "organization_id": "verifier-org",
                    "role": VERIFIER_ROLE,
                    **common,
                    "execution_record_id": execution_payload["record_id"],
                    "execution_payload_digest": canonical_digest(execution_payload),
                },
            )
            gates.append(
                {
                    "id": gate_id,
                    "status": "PASSED_EXTERNAL",
                    "evidence": reference,
                    "execution_attestation": execution,
                    "verification_attestation": verification,
                }
            )
            gate_envelope_digests.append(
                {
                    "gate_id": gate_id,
                    "execution_envelope_digest": canonical_digest(execution),
                    "verification_envelope_digest": canonical_digest(verification),
                }
            )

        approvals = []
        for key_name, scope in (("release", "RELEASE_AUTHORIZATION"), ("risk", "RISK_ACCEPTANCE")):
            _, actor, organization = self.KEY_SPECS[key_name]
            approvals.append(
                sign_envelope(
                    key_name,
                    {
                        "record_id": f"approval-{key_name}",
                        "issued_at": "2026-09-04T09:15:00Z",
                        "expires_at": "2026-09-05T10:00:00Z",
                        "actor_id": actor,
                        "organization_id": organization,
                        "role": APPROVER_ROLE,
                        "receipt_id": receipt_id,
                        "binding_digest": binding_digest,
                        "evidence_set_digest": evidence_set_digest,
                        "approval_scope": scope,
                        "outcome": "APPROVED",
                        "synthetic": False,
                        "unknowns": [],
                        "not_run": [],
                    },
                )
            )
        partners = []
        for key_name in ("partner-a", "partner-b"):
            _, actor, organization = self.KEY_SPECS[key_name]
            partners.append(
                sign_envelope(
                    key_name,
                    {
                        "record_id": f"acceptance-{key_name}",
                        "issued_at": "2026-09-04T09:15:00Z",
                        "expires_at": "2026-09-05T10:00:00Z",
                        "actor_id": actor,
                        "organization_id": organization,
                        "role": DESIGN_PARTNER_ROLE,
                        "receipt_id": receipt_id,
                        "binding_digest": binding_digest,
                        "evidence_set_digest": evidence_set_digest,
                        "partner_organization_id": organization,
                        "outcome": "ACCEPTED",
                        "synthetic": False,
                        "unknowns": [],
                        "not_run": [],
                    },
                )
            )
        review_subject_digest = canonical_digest(
            {
                "receipt_id": receipt_id,
                "binding_digest": binding_digest,
                "evidence_set_digest": evidence_set_digest,
                "controlled_index_attestation_digest": (
                    canonical_digest(index_envelope) if index_envelope else None
                ),
                "gate_attestations": gate_envelope_digests,
                "approval_envelope_digests": sorted(canonical_digest(item) for item in approvals),
                "design_partner_envelope_digests": sorted(canonical_digest(item) for item in partners),
            }
        )
        review = sign_envelope(
            "reviewer",
            {
                "record_id": "review-record",
                "issued_at": "2026-09-04T09:20:00Z",
                "expires_at": "2026-09-05T10:00:00Z",
                "actor_id": "reviewer-actor",
                "organization_id": "reviewer-org",
                "role": REVIEWER_ROLE,
                "receipt_id": receipt_id,
                "binding_digest": binding_digest,
                "evidence_set_digest": evidence_set_digest,
                "review_subject_digest": review_subject_digest,
                "outcome": "REVIEWED",
                "synthetic": False,
                "unknowns": [],
                "not_run": [],
            },
        )
        receipt = {
            "schema_version": 1,
            "namespace": NAMESPACE,
            "receipt_id": receipt_id,
            "business_line": BUSINESS_LINE,
            "route_id": ROUTE_ID,
            "observed_at": "2026-09-04T09:00:00Z",
            "binding": binding,
            "binding_digest": binding_digest,
            "principals": {
                "execution": {"actor_id": "executor-actor", "organization_id": "executor-org"},
                "independent_verifier": {"actor_id": "verifier-actor", "organization_id": "verifier-org"},
                "independent_reviewer": {"actor_id": "reviewer-actor", "organization_id": "reviewer-org"},
            },
            "evidence_index": evidence_index,
            "gates": gates,
            "approvals": approvals,
            "design_partner_acceptances": partners,
            "independent_review": review,
        }
        receipt["receipt_digest"] = receipt_digest(receipt)
        return receipt

    def rewrite_container_inspect(
        self,
        receipt: dict[str, object],
        *,
        value: object | None = None,
        raw: bytes | None = None,
    ) -> None:
        if (value is None) == (raw is None):
            raise ValueError("provide exactly one container inspect representation")
        environment_path = Path(
            receipt["binding"]["environment"]["uri"].removeprefix("file://")
        )
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
        inspect_path = Path(
            environment["container_inspect"]["verification"]["local_uri"].removeprefix(
                "file://"
            )
        )
        if raw is not None:
            inspect_path.write_bytes(raw)
        else:
            self.write_json(inspect_path, value)
        inspect_ref = self.ref(inspect_path)
        environment["container_inspect"] = {
            **inspect_ref,
            "verification": {
                "mode": "LOCAL_BYTES",
                "local_uri": inspect_ref["uri"],
            },
        }
        self.write_json(environment_path, environment, canonical=True)
        receipt["binding"]["environment"] = self.ref(environment_path)

    def environment_document(
        self, receipt: dict[str, object]
    ) -> tuple[Path, dict[str, object]]:
        environment_path = Path(
            receipt["binding"]["environment"]["uri"].removeprefix("file://")
        )
        return environment_path, json.loads(
            environment_path.read_text(encoding="utf-8")
        )

    def rewrite_environment_document(
        self, receipt: dict[str, object], environment: dict[str, object]
    ) -> None:
        environment_path = Path(
            receipt["binding"]["environment"]["uri"].removeprefix("file://")
        )
        self.write_json(environment_path, environment, canonical=True)
        receipt["binding"]["environment"] = self.ref(environment_path)

    def rewrite_environment_supporting_document(
        self,
        receipt: dict[str, object],
        field: str,
        value: object,
    ) -> None:
        _, environment = self.environment_document(receipt)
        reference = environment[field]
        path = Path(reference["verification"]["local_uri"].removeprefix("file://"))
        self.write_json(path, value, canonical=True)
        updated = self.ref(path)
        environment[field] = {
            **updated,
            "verification": {"mode": "LOCAL_BYTES", "local_uri": updated["uri"]},
        }
        self.rewrite_environment_document(receipt, environment)

    @staticmethod
    def container_inspect_document(receipt: dict[str, object]) -> list[object]:
        environment_path = Path(
            receipt["binding"]["environment"]["uri"].removeprefix("file://")
        )
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
        inspect_path = Path(
            environment["container_inspect"]["verification"]["local_uri"].removeprefix(
                "file://"
            )
        )
        return json.loads(inspect_path.read_text(encoding="utf-8"))

    def verify(
        self, receipt: dict[str, object], **options: object
    ) -> dict[str, object]:
        return verify_spring_launch_receipt(
            receipt,
            trust_store=self.trust_path,
            evidence_roots=[self.evidence_root],
            expected_revision=self.REVISION,
            now=self.NOW,
            **options,
        )

    @staticmethod
    def _verify_without_process(
            store: TrustStore,
            envelope: dict[str, object],
            *,
            required_role: str,
            bindings: dict[str, object],
            now: datetime | None = None,
        ) -> dict[str, object]:
        payload = envelope["payload"]
        for field, expected in bindings.items():
            if type(payload.get(field)) is not type(expected) or payload.get(field) != expected:
                raise ValueError(f"signed envelope binding mismatch: {field}")
        return {
            "record_id": payload["record_id"],
            "key_id": envelope["key_id"],
            "role": required_role,
            "payload_digest": canonical_digest(payload),
            "trust_store_digest": store.digest,
        }

    @classmethod
    def fast_signature_verification(cls) -> mock._patch:

        return mock.patch.object(
            TrustStore,
            "verify_envelope",
            autospec=True,
            side_effect=cls._verify_without_process,
        )

    @classmethod
    def sampled_signature_verification(cls) -> mock._patch:
        original_verify = TrustStore.verify_envelope
        verified_keys: set[str] = set()

        def verify_sample(
            store: TrustStore,
            envelope: dict[str, object],
            *,
            required_role: str,
            bindings: dict[str, object],
            now: datetime | None = None,
        ) -> dict[str, object]:
            key_id = str(envelope["key_id"])
            if key_id not in verified_keys:
                verified_keys.add(key_id)
                return original_verify(
                    store,
                    envelope,
                    required_role=required_role,
                    bindings=bindings,
                    now=now,
                )
            return cls._verify_without_process(
                store,
                envelope,
                required_role=required_role,
                bindings=bindings,
                now=now,
            )

        return mock.patch.object(
            TrustStore,
            "verify_envelope",
            autospec=True,
            side_effect=verify_sample,
        )

    def test_complete_receipt_verifies_but_does_not_certify(self) -> None:
        trust_digest = _load_trust(self.trust_path).store.digest
        receipt = self.make_receipt(
            controlled_index=True, sampled_signatures=True
        )
        environment_path = Path(
            receipt["binding"]["environment"]["uri"].removeprefix("file://")
        )
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
        with self.sampled_signature_verification():
            result = self.verify(
                receipt,
                expected_trust_store_digest=trust_digest,
                expected_environment_id="staging-one",
                expected_deployment_id="deployment-one",
                expected_provider="private-linux",
                expected_region="cn-test-one",
                expected_environment_class="STAGING",
                expected_configuration_digest="sha256:" + "1" * 64,
                expected_application_environment_commitment_digest=(
                    application_environment_commitment_digest({})
                ),
                expected_effective_spring_configuration_digest=environment[
                    "effective_spring_configuration_digest"
                ],
                expected_effective_web_console_configuration_digest=environment[
                    "effective_web_console_configuration_digest"
                ],
                expected_web_console_environment_names_digest=environment[
                    "web_console_environment_names_digest"
                ],
                expected_application_mount_sources_digest=environment[
                    "application_mount_sources_digest"
                ],
                expected_worker_application_artifact_digest=environment[
                    "worker_application_artifact_digest"
                ],
            )
        self.assertEqual("VERIFIED_EXTERNAL_RECEIPT", result["evidence_status"])
        self.assertEqual("NOT_CERTIFIED", result["certification"])
        self.assertFalse(result["certification_promoted"])
        self.assertEqual(list(GATE_IDS), result["verified_gate_ids"])
        self.assertEqual("sha256:" + "1" * 64, result["configuration_digest"])
        self.assertEqual(
            application_environment_commitment_digest({}),
            result["application_environment_commitment_digest"],
        )
        self.assertEqual(
            environment["container_inspect"]["digest"],
            result["container_inspect_digest"],
        )
        self.assertEqual(
            environment["web_console_runtime_attestation"]["digest"],
            result["web_console_runtime_attestation_digest"],
        )
        self.assertEqual(
            "sha256:" + "c" * 64,
            result["worker_application_artifact_digest"],
        )
        self.assertEqual("staging-one", result["environment_id"])

        with self.assertRaisesRegex(SpringLaunchEvidenceError, "expected trust store digest"):
            self.verify(
                self.make_receipt(),
                expected_trust_store_digest="sha256:" + "0" * 64,
            )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "expected environment_id"):
            self.verify(
                self.make_receipt(),
                expected_environment_id="different-environment",
            )
        with self.assertRaisesRegex(
            SpringLaunchEvidenceError,
            "expected application_environment_commitment_digest",
        ):
            self.verify(
                self.make_receipt(),
                expected_application_environment_commitment_digest=(
                    "sha256:" + "0" * 64
                ),
            )
        with self.assertRaisesRegex(
            SpringLaunchEvidenceError,
            "expected effective_spring_configuration_digest",
        ):
            self.verify(
                self.make_receipt(),
                expected_effective_spring_configuration_digest="sha256:" + "0" * 64,
            )
        for option, field in (
            (
                "expected_effective_web_console_configuration_digest",
                "effective_web_console_configuration_digest",
            ),
            (
                "expected_web_console_environment_names_digest",
                "web_console_environment_names_digest",
            ),
            (
                "expected_application_mount_sources_digest",
                "application_mount_sources_digest",
            ),
            (
                "expected_worker_application_artifact_digest",
                "worker_application_artifact_digest",
            ),
        ):
            with self.subTest(option=option):
                with self.assertRaisesRegex(SpringLaunchEvidenceError, f"expected {field}"):
                    self.verify(
                        self.make_receipt(),
                        **{option: "sha256:" + "0" * 64},
                    )

    def test_launch_profile_must_match_the_committed_revision(self) -> None:
        receipt = self.make_receipt()
        with mock.patch(
            "scripts.batch30.spring_launch_evidence.read_regular_file_once",
            return_value=b"dirty working-tree profile",
        ):
            with self.assertRaisesRegex(
                SpringLaunchEvidenceError,
                "working-tree bytes do not match the expected revision",
            ):
                self.verify(receipt)

    def test_container_inspect_bytes_and_strict_json_are_bound(self) -> None:
        receipt = self.make_receipt()
        environment_path = Path(
            receipt["binding"]["environment"]["uri"].removeprefix("file://")
        )
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
        inspect_path = Path(
            environment["container_inspect"]["verification"]["local_uri"].removeprefix(
                "file://"
            )
        )
        inspect_path.write_bytes(inspect_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "byte count mismatch"):
            self.verify(receipt)

        receipt = self.make_receipt()
        document = self.container_inspect_document(receipt)
        duplicate_key_json = json.dumps(document, sort_keys=True).replace(
            '"Env":', '"Env": [], "Env":', 1
        ).encode("utf-8")
        self.rewrite_container_inspect(receipt, raw=duplicate_key_json)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "duplicate object key 'Env'"):
            self.verify(receipt)

        receipt = self.make_receipt()
        document = self.container_inspect_document(receipt)
        non_finite_json = json.dumps(document, sort_keys=True).replace(
            '"Config":', '"NonFinite": NaN, "Config":', 1
        ).encode("utf-8")
        self.rewrite_container_inspect(receipt, raw=non_finite_json)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "non-finite JSON number NaN"):
            self.verify(receipt)

    def test_container_inspect_requires_one_exact_worker_and_unique_env(self) -> None:
        receipt = self.make_receipt()
        document = self.container_inspect_document(receipt)
        self.rewrite_container_inspect(receipt, value=[document[0], document[0]])
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "exactly one java-engine-worker"):
            self.verify(receipt)

        receipt = self.make_receipt()
        document = self.container_inspect_document(receipt)
        document[0]["Config"]["Labels"]["com.docker.compose.service"] = "other-service"
        self.rewrite_container_inspect(receipt, value=document)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "unique java-engine-worker Compose service"):
            self.verify(receipt)

        receipt = self.make_receipt()
        document = self.container_inspect_document(receipt)
        document[0]["Config"]["Env"].append(
            document[0]["Config"]["Env"][0]
        )
        self.rewrite_container_inspect(receipt, value=document)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "contains duplicate key"):
            self.verify(receipt)

        receipt = self.make_receipt()
        document = self.container_inspect_document(receipt)
        document[0]["Config"]["Env"].extend(
            ["CUSTOM_APP_SETTING=1", "custom_app_setting=1"]
        )
        self.rewrite_container_inspect(receipt, value=document)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "relaxed-binding aliases"):
            self.verify(receipt)

    def test_container_inspect_binds_image_and_exact_command(self) -> None:
        receipt = self.make_receipt()
        document = self.container_inspect_document(receipt)
        document[0]["Image"] = "sha256:" + "9" * 64
        self.rewrite_container_inspect(receipt, value=document)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "immutable java-engine-worker image digest"):
            self.verify(receipt)

        for field, value, message in (
            ("Image", "elmos-java-engine-worker:latest", "non-latest image reference"),
            (
                "Entrypoint",
                ["java", "-jar", "/app/app.jar", "--elmos.worker.spring-upgrade.enabled=false"],
                "must exactly match",
            ),
            (
                "Cmd",
                ["--spring.application.json={}"],
                "Config.Cmd must be null or an empty array",
            ),
        ):
            with self.subTest(field=field):
                receipt = self.make_receipt()
                document = self.container_inspect_document(receipt)
                document[0]["Config"][field] = value
                self.rewrite_container_inspect(receipt, value=document)
                with self.assertRaisesRegex(SpringLaunchEvidenceError, message):
                    self.verify(receipt)

    def test_container_inspect_rejects_effective_security_overrides(self) -> None:
        for assignment, message in (
            (
                "SPRING_PROFILES_ACTIVE=production",
                "dangerous override SPRING_PROFILES_ACTIVE",
            ),
            ("spring_main_lazy_initialization=true", "dangerous override spring_main"),
            (
                "spring_application_json={}",
                "must use exact key SPRING_APPLICATION_JSON",
            ),
            ("JVM_OPTS=-Dserver.servlet.context-path=/hidden", "dangerous override JVM_OPTS"),
            ("JVM_OPTS=", "dangerous override JVM_OPTS"),
            ("SERVER_PORT=", "dangerous override SERVER_PORT"),
            (
                "management_endpoints_web_exposure_include=",
                "dangerous override management_endpoints",
            ),
            (
                "ELMOS_WORKER_SPRING_UPGRADE_INGRESS_AUTH_ENABLED=",
                "dangerous override ELMOS_WORKER",
            ),
            (
                "ELMOS_SPRING_UNDECLARED_SWITCH=true",
                "unsupported Spring worker override",
            ),
            (
                "ELMOS_SPRING_UNDECLARED_SWITCH=",
                "unsupported Spring worker override",
            ),
            (
                "elmos_spring_undeclared_switch=true",
                "unsupported Spring worker override",
            ),
            (
                "elmos_spring_coding_agent_enabled=false",
                "must use exact key ELMOS_SPRING_CODING_AGENT_ENABLED",
            ),
            (
                "elmos_allowed_git_hosts=github.com",
                "must use exact key ELMOS_ALLOWED_GIT_HOSTS",
            ),
            (
                "spring_application_json=",
                "must use exact key SPRING_APPLICATION_JSON",
            ),
            (
                "HTTPS_PROXY=http://attacker.invalid:8080",
                "undeclared worker environment HTTPS_PROXY",
            ),
            (
                "LD_PRELOAD=/workspace/private-runner/evil.so",
                "dangerous override LD_PRELOAD",
            ),
            (
                "SPRING_APPLICATION_JSON={}",
                "dangerous override SPRING_APPLICATION_JSON must be exactly empty",
            ),
        ):
            with self.subTest(assignment=assignment):
                receipt = self.make_receipt()
                document = self.container_inspect_document(receipt)
                name = assignment.partition("=")[0]
                normalized_name = "".join(character for character in name if character.isalnum()).upper()
                document[0]["Config"]["Env"] = [
                    entry
                    for entry in document[0]["Config"]["Env"]
                    if "".join(
                        character
                        for character in entry.partition("=")[0]
                        if character.isalnum()
                    ).upper()
                    != normalized_name
                ]
                document[0]["Config"]["Env"].append(assignment)
                self.rewrite_container_inspect(receipt, value=document)
                with self.assertRaisesRegex(SpringLaunchEvidenceError, message):
                    self.verify(receipt)

        receipt = self.make_receipt()
        environment_path = Path(
            receipt["binding"]["environment"]["uri"].removeprefix("file://")
        )
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
        environment["effective_spring_configuration_digest"] = "sha256:" + "a" * 64
        self.write_json(environment_path, environment, canonical=True)
        receipt["binding"]["environment"] = self.ref(environment_path)
        with self.assertRaisesRegex(
            SpringLaunchEvidenceError,
            "does not match container inspect bytes",
        ):
            self.verify(receipt)

    def test_worker_mount_sources_bind_the_signed_application_host_digest(self) -> None:
        receipt = self.make_receipt()
        document = self.container_inspect_document(receipt)
        for mount in document[0]["Mounts"]:
            if mount["Destination"] == "/workspace/private-runner":
                mount["Source"] = "/srv/elmos/other-controlled-workspace"
        document[0]["HostConfig"]["Binds"] = [
            f"{mount['Source']}:{mount['Destination']}:{mount['Mode']}"
            for mount in document[0]["Mounts"]
        ]
        self.rewrite_container_inspect(receipt, value=document)
        with self.assertRaisesRegex(
            SpringLaunchEvidenceError, "worker inspect digest"
        ):
            self.verify(receipt)

    def test_mount_object_commitment_detects_same_path_atomic_replacement(self) -> None:
        self.make_receipt()
        self.assertRegex(
            application_mount_sources_digest(
                self.application_mount_sources,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
            ),
            r"^sha256:[0-9a-f]{64}$",
        )
        before = application_mount_sources_digest(
            self.application_mount_sources,
            _identity_provider=lambda name, source: self.mount_source_snapshot(source),
        )
        workspace_child = (
            Path(self.application_mount_sources["worker_workspace"]) / "completed-run"
        )
        workspace_child.write_text("content-addressed result", encoding="utf-8")
        after_directory_write = application_mount_sources_digest(
            self.application_mount_sources,
            _identity_provider=lambda name, source: self.mount_source_snapshot(source),
        )
        self.assertEqual(before, after_directory_write)
        secret = Path(self.application_mount_sources["worker_verifier_hmac"])
        replacement = secret.with_name("replacement-verifier.secret")
        replacement.write_bytes(b"replacement-verifier-secret-value")
        os.chmod(replacement, 0o600)
        os.replace(replacement, secret)
        after = application_mount_sources_digest(
            self.application_mount_sources,
            _identity_provider=lambda name, source: self.mount_source_snapshot(source),
        )
        self.assertNotEqual(after_directory_write, after)

        def wrong_owner(name: str, source: str) -> dict[str, object]:
            snapshot = self.mount_source_snapshot(source)
            snapshot["object_identity"] = {
                **snapshot["object_identity"],
                "uid": 10002,
            }
            return snapshot

        with self.assertRaisesRegex(SpringLaunchEvidenceError, "UID/GID 10001:10001"):
            application_mount_sources_digest(
                self.application_mount_sources,
                _identity_provider=wrong_owner,
            )

        def short_resend(name: str, source: str) -> dict[str, object]:
            snapshot = self.mount_source_snapshot(source)
            if name == "web_resend_secret":
                snapshot["object_identity"] = {
                    **snapshot["object_identity"],
                    "size_bytes": 31,
                }
            return snapshot

        with self.assertRaisesRegex(SpringLaunchEvidenceError, "32-4096 bytes"):
            application_mount_sources_digest(
                self.application_mount_sources,
                _identity_provider=short_resend,
            )

        def ancestor_mode(mode: int):
            def provide(name: str, source: str) -> dict[str, object]:
                snapshot = self.mount_source_snapshot(source)
                ancestors = [dict(item) for item in snapshot["ancestor_identities"]]
                ancestors[0] = {**ancestors[0], "mode": mode, "uid": 0, "gid": 0}
                snapshot["ancestor_identities"] = ancestors
                return snapshot

            return provide

        with self.assertRaisesRegex(SpringLaunchEvidenceError, "unsafely group/other writable"):
            application_mount_sources_digest(
                self.application_mount_sources,
                _identity_provider=ancestor_mode(0o777),
            )
        self.assertRegex(
            application_mount_sources_digest(
                self.application_mount_sources,
                _identity_provider=ancestor_mode(0o1777),
            ),
            r"^sha256:[0-9a-f]{64}$",
        )

    def test_live_mount_collector_rejects_inode_and_restart_skew(self) -> None:
        self.make_receipt()

        def mismatched_target(
            source: str, process_id: int, destination: str, label: str
        ) -> tuple[
            dict[str, object],
            dict[str, object],
            dict[str, object],
            list[dict[str, object]],
            str,
        ]:
            host, target, parent, ancestors, process = self.live_mount_observer(
                source, process_id, destination, label
            )
            if destination == "/run/secrets/elmos-verifier-hmac":
                target = {**target, "inode": int(target["inode"]) + 1}
            return host, target, parent, ancestors, process

        with self.assertRaisesRegex(
            SpringLaunchEvidenceError, "does not match the host source object"
        ):
            self.collect_web_runtime(
                self.web_inspect_value, observer=mismatched_target
            )

        restarted_web = copy.deepcopy(self.web_inspect_value)
        restarted_web[0]["State"]["Pid"] += 1
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "changed during"):
            self.collect_web_runtime(
                self.web_inspect_value,
                reinspection_web_value=restarted_web,
            )

        restarted_worker = copy.deepcopy(self.worker_inspect_value)
        restarted_worker[0]["Id"] = "d" * 64
        restarted_worker_bytes = canonical_bytes(restarted_worker)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "changed during"):
            self.collect_web_runtime(
                self.web_inspect_value,
                reinspection_worker_bytes=restarted_worker_bytes,
            )

    def test_web_runtime_collector_redacts_secrets_and_rejects_dangerous_env(self) -> None:
        self.make_receipt()
        raw_value = copy.deepcopy(self.web_inspect_value)
        raw_value[0]["Config"]["Env"].append("DATABASE_PASSWORD=top-secret-value")
        sanitized = self.collect_web_runtime(raw_value)
        rendered = canonical_bytes(sanitized)
        self.assertNotIn(b"top-secret-value", rendered)
        for source in self.application_mount_sources.values():
            self.assertNotIn(source.encode("utf-8"), rendered)
        self.assertIn("DATABASE_PASSWORD", sanitized["environment_names"])
        self.assertFalse(sanitized["secrets_embedded"])
        self.assertTrue(sanitized["stable_reinspection"])
        alternate_value = copy.deepcopy(self.web_inspect_value)
        alternate_value[0]["Config"]["Env"].append(
            "DATABASE_PASSWORD=different-secret-guess"
        )
        self.assertEqual(
            sanitized,
            self.collect_web_runtime(alternate_value),
            "portable sanitized evidence must not act as an offline secret oracle",
        )
        self.assertIn(
            "inode",
            sanitized["mount_sources"]["application_engine_hmac"][
                "object_identity"
            ],
        )
        self.assertIn(
            "ancestor_identities",
            sanitized["mount_sources"]["application_engine_hmac"],
        )

        for assignment, message in (
            ("HTTPS_PROXY=http://attacker.invalid:8080", "dangerous process or routing"),
            ("https_proxy=http://attacker.invalid:8080", "dangerous process or routing"),
            ("ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID=attacker", "dangerous process or routing"),
            ("SPRING_APPLICATION_JSON={}", "dangerous process or routing"),
        ):
            with self.subTest(assignment=assignment):
                value = copy.deepcopy(self.web_inspect_value)
                value[0]["Config"]["Env"].append(assignment)
                with self.assertRaisesRegex(SpringLaunchEvidenceError, message):
                    self.collect_web_runtime(value)

        value = copy.deepcopy(self.web_inspect_value)
        value[0]["Config"]["Env"] = [
            "JAVA_ENGINE_BASE_URL=http://attacker.invalid:8081"
            if entry.startswith("JAVA_ENGINE_BASE_URL=")
            else entry
            for entry in value[0]["Config"]["Env"]
        ]
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "JAVA_ENGINE_BASE_URL"):
            self.collect_web_runtime(value)

        value = copy.deepcopy(self.web_inspect_value)
        value[0]["Config"]["Env"] = [
            "java_engine_base_url=http://java-engine-worker:8081"
            if entry.startswith("JAVA_ENGINE_BASE_URL=")
            else entry
            for entry in value[0]["Config"]["Env"]
        ]
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "must use exact key"):
            self.collect_web_runtime(value)

    def test_web_runtime_attestation_binds_engine_source_without_raw_web_oracle(self) -> None:
        receipt = self.make_receipt()
        _, environment = self.environment_document(receipt)
        reference = environment["web_console_runtime_attestation"]
        self.assertNotIn("container_inspect", reference)
        self.assertFalse((self.evidence_root / "web-console.inspect.json").exists())
        attestation_path = Path(
            reference["verification"]["local_uri"].removeprefix("file://")
        )
        attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
        self.assertNotIn("Env", json.dumps(attestation, sort_keys=True))
        self.assertNotIn("raw_inspect_digest", attestation)
        self.assertNotIn("raw_inspect_size_bytes", attestation)
        self.assertEqual(
            "sha256:" + hashlib.sha256(self.worker_inspect_bytes).hexdigest(),
            attestation["raw_worker_inspect_digest"],
        )

        web_value = copy.deepcopy(self.web_inspect_value)
        new_source_path = self.case / "runtime-mounts" / "other-engine.secret"
        new_source_path.write_bytes(b"other-engine-secret-value-32-bytes")
        os.chmod(new_source_path, 0o600)
        new_source = str(new_source_path)
        for mount in web_value[0]["Mounts"]:
            if mount["Destination"] == "/run/secrets/elmos-spring-engine-hmac":
                mount["Source"] = new_source
        web_value[0]["HostConfig"]["Binds"] = [
            f"{mount['Source']}:{mount['Destination']}:{mount['Mode']}"
            for mount in web_value[0]["Mounts"]
        ]
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "identical host source"):
            self.collect_web_runtime(web_value)

    def test_web_runtime_collector_rejects_process_mount_and_network_drift(self) -> None:
        self.make_receipt()
        mutations = (
            (
                "command",
                lambda value: value[0]["Config"].update(
                    {"Cmd": ["/usr/local/bin/node", "attacker.js"]}
                ),
                "Config.Cmd must exactly match",
            ),
            (
                "privileged",
                lambda value: value[0]["HostConfig"].update({"Privileged": True}),
                "Privileged",
            ),
            (
                "mount-propagation",
                lambda value: value[0]["Mounts"][0].update(
                    {"Propagation": "rshared"}
                ),
                "exact ro rprivate bind",
            ),
            (
                "extra-network",
                lambda value: value[0]["NetworkSettings"]["Networks"].update(
                    {"attacker": {}}
                ),
                "networks must exactly match",
            ),
        )
        for name, mutate, message in mutations:
            with self.subTest(name=name):
                value = copy.deepcopy(self.web_inspect_value)
                mutate(value)
                with self.assertRaisesRegex(SpringLaunchEvidenceError, message):
                    self.collect_web_runtime(value)

    def test_sanitized_web_runtime_attestation_tamper_fails_closed(self) -> None:
        mutations = (
            (
                "names-digest",
                lambda value: value.update(
                    {"environment_names_digest": "sha256:" + "a" * 64}
                ),
                "environment names digest mismatch",
            ),
            (
                "required-url",
                lambda value: value["required_environment"].update(
                    {"JAVA_ENGINE_BASE_URL": "http://attacker.invalid:8081"}
                ),
                "JAVA_ENGINE_BASE_URL",
            ),
            (
                "secrets-flag",
                lambda value: value.update({"secrets_embedded": True}),
                "secrets_embedded must be exactly false",
            ),
            (
                "stale",
                lambda value: value.update({"captured_at": "2026-08-01T00:00:00Z"}),
                "older than",
            ),
            (
                "published-port",
                lambda value: value["runtime"].update(
                    {"published_ports": ["0.0.0.0:3000"]}
                ),
                "published_ports is invalid",
            ),
            (
                "mount-object",
                lambda value: value["mount_sources"]["worker_verifier_hmac"][
                    "object_identity"
                ].update(
                    {
                        "inode": value["mount_sources"]["worker_verifier_hmac"][
                            "object_identity"
                        ]["inode"]
                        + 1
                    }
                ),
                "application mount object digest mismatch",
            ),
            (
                "mount-unsafe-ancestor",
                lambda value: value["mount_sources"]["worker_verifier_hmac"][
                    "ancestor_identities"
                ][0].update({"mode": 0o777}),
                "unsafely group/other writable",
            ),
        )
        for name, mutate, message in mutations:
            with self.subTest(name=name):
                receipt = self.make_receipt()
                _, environment = self.environment_document(receipt)
                reference = environment["web_console_runtime_attestation"]
                path = Path(
                    reference["verification"]["local_uri"].removeprefix("file://")
                )
                attestation = json.loads(path.read_text(encoding="utf-8"))
                mutate(attestation)
                self.rewrite_environment_supporting_document(
                    receipt, "web_console_runtime_attestation", attestation
                )
                with self.assertRaisesRegex(SpringLaunchEvidenceError, message):
                    self.verify(receipt)

    def test_worker_runtime_rejects_shadow_mounts_ports_and_security_drift(self) -> None:
        mutations = (
            (
                "shadow-app",
                lambda doc: doc[0]["Mounts"].append(
                    {
                        "Type": "bind",
                        "Source": "/tmp/evil.jar",
                        "Destination": "/app/app.jar",
                        "RW": False,
                        "Mode": "ro",
                        "Propagation": "rprivate",
                    }
                ),
                "undeclared mount destination",
            ),
            (
                "docker-socket",
                lambda doc: doc[0]["Mounts"].append(
                    {
                        "Type": "bind",
                        "Source": "/var/run/docker.sock",
                        "Destination": "/var/run/docker.sock",
                        "RW": True,
                        "Mode": "rw",
                        "Propagation": "rprivate",
                    }
                ),
                "undeclared mount destination",
            ),
            (
                "propagation",
                lambda doc: doc[0]["Mounts"][0].update({"Propagation": "rshared"}),
                "exact rw rprivate bind",
            ),
            (
                "privileged",
                lambda doc: doc[0]["HostConfig"].update({"Privileged": True}),
                "Privileged",
            ),
            (
                "host-port",
                lambda doc: doc[0]["HostConfig"].update(
                    {"PortBindings": {"8081/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8081"}]}}
                ),
                "PortBindings must be empty",
            ),
            (
                "wrong-user",
                lambda doc: doc[0]["Config"].update({"User": "0:0"}),
                "Config.User must equal",
            ),
        )
        for name, mutate, message in mutations:
            with self.subTest(name=name):
                receipt = self.make_receipt()
                document = self.container_inspect_document(receipt)
                mutate(document)
                self.rewrite_container_inspect(receipt, value=document)
                with self.assertRaisesRegex(SpringLaunchEvidenceError, message):
                    self.verify(receipt)

    def test_worker_image_artifact_attestation_is_separate_and_bound(self) -> None:
        receipt = self.make_receipt()
        _, environment = self.environment_document(receipt)
        self.assertNotEqual(
            receipt["binding"]["artifact"]["digest"],
            environment["worker_application_artifact_digest"],
        )
        environment["worker_application_artifact_digest"] = receipt["binding"]["artifact"]["digest"]
        self.rewrite_environment_document(receipt, environment)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "distinct from the migrated customer artifact"):
            self.verify(receipt)

        for field, value, message in (
            ("deployed_revision", "0" * 40, "deployed_revision"),
            ("image_digest", "sha256:" + "0" * 64, "image_digest"),
            ("image_reference", "other-worker:staging", "image_reference"),
            ("artifact_path", "/customer/migrated.jar", "artifact_path"),
            ("worker_application_artifact_digest", "sha256:" + "0" * 64, "worker_application_artifact_digest"),
            ("extracted_at", "2026-08-01T00:00:00Z", "older than"),
        ):
            with self.subTest(field=field):
                receipt = self.make_receipt()
                _, environment = self.environment_document(receipt)
                reference = environment["worker_image_artifact_attestation"]
                path = Path(reference["verification"]["local_uri"].removeprefix("file://"))
                attestation = json.loads(path.read_text(encoding="utf-8"))
                attestation[field] = value
                self.rewrite_environment_supporting_document(
                    receipt, "worker_image_artifact_attestation", attestation
                )
                with self.assertRaisesRegex(SpringLaunchEvidenceError, message):
                    self.verify(receipt)

    def test_container_inspect_reference_must_be_local_bytes(self) -> None:
        receipt = self.make_receipt()
        environment_path = Path(
            receipt["binding"]["environment"]["uri"].removeprefix("file://")
        )
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
        environment["container_inspect"]["verification"]["mode"] = "CONTROLLED_INDEX"
        self.write_json(environment_path, environment, canonical=True)
        receipt["binding"]["environment"] = self.ref(environment_path)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "exactly LOCAL_BYTES"):
            self.verify(receipt)

        receipt = self.make_receipt()
        environment_path = Path(
            receipt["binding"]["environment"]["uri"].removeprefix("file://")
        )
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
        environment["container_inspect"]["verification"]["local_uri"] = (
            self.evidence_root / "different.inspect.json"
        ).as_uri()
        self.write_json(environment_path, environment, canonical=True)
        receipt["binding"]["environment"] = self.ref(environment_path)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "must equal its immutable local URI"):
            self.verify(receipt)

    def test_signed_controlled_index_closes_remote_evidence(self) -> None:
        with self.fast_signature_verification():
            result = self.verify(self.make_receipt(controlled_index=True))
        self.assertEqual("VALIDATED_NOT_CERTIFIED", result["external_evidence_intake"])

    def test_receipt_and_supporting_schemas_accept_fixture(self) -> None:
        from jsonschema import Draft202012Validator

        schemas = {}
        for name in (
            "spring-launch-external-evidence.schema.json",
            "spring-launch-trust-store.schema.json",
            "spring-launch-evidence-index.schema.json",
            "spring-launch-environment-manifest.schema.json",
        ):
            schema = json.loads((ROOT / "schemas" / "batch30" / name).read_text())
            Draft202012Validator.check_schema(schema)
            schemas[name] = schema
        receipt = self.make_receipt(controlled_index=True)
        Draft202012Validator(
            schemas["spring-launch-external-evidence.schema.json"]
        ).validate(receipt)
        trust = json.loads(self.trust_path.read_text(encoding="utf-8"))
        Draft202012Validator(
            schemas["spring-launch-trust-store.schema.json"]
        ).validate(trust)
        assert receipt["evidence_index"] is not None
        index_path = Path(
            receipt["evidence_index"]["content"]["uri"].removeprefix("file://")
        )
        index = json.loads(index_path.read_text(encoding="utf-8"))
        Draft202012Validator(
            schemas["spring-launch-evidence-index.schema.json"]
        ).validate(index)
        environment_path = Path(
            receipt["binding"]["environment"]["uri"].removeprefix("file://")
        )
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
        environment_schema = schemas[
            "spring-launch-environment-manifest.schema.json"
        ]
        Draft202012Validator(environment_schema).validate(environment)

        for required_field in (
            "application_environment_commitment_digest",
            "container_inspect",
            "web_console_runtime_attestation",
            "effective_spring_configuration_digest",
            "effective_web_console_configuration_digest",
            "web_console_environment_names_digest",
            "application_mount_sources_digest",
            "worker_image_artifact_attestation",
            "worker_application_artifact_digest",
        ):
            invalid = copy.deepcopy(environment)
            del invalid[required_field]
            self.assertTrue(
                list(Draft202012Validator(environment_schema).iter_errors(invalid)),
                required_field,
            )
        invalid_images = copy.deepcopy(environment)
        invalid_images["runtime_image_digests"]["uncontrolled"] = "sha256:" + "d" * 64
        self.assertTrue(
            list(Draft202012Validator(environment_schema).iter_errors(invalid_images))
        )
        zero_digest = copy.deepcopy(environment)
        zero_digest["worker_application_artifact_digest"] = "sha256:" + "0" * 64
        self.assertTrue(
            list(Draft202012Validator(environment_schema).iter_errors(zero_digest))
        )

    def test_tampered_evidence_bytes_and_signature_fail_closed(self) -> None:
        receipt = self.make_receipt()
        evidence_path = Path(
            receipt["gates"][0]["evidence"]["verification"]["local_uri"].removeprefix("file://")
        )
        evidence_path.write_bytes(evidence_path.read_bytes() + b"tampered")
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "byte count mismatch"):
            self.verify(receipt)

        receipt = self.make_receipt()
        receipt["gates"][0]["execution_attestation"] = self.sign(
            "executor",
            copy.deepcopy(receipt["gates"][0]["execution_attestation"]["payload"]),
        )
        receipt["gates"][0]["verification_attestation"]["signature"] = base64.b64encode(
            b"x" * 64
        ).decode("ascii")
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "signature verification failed"):
            self.verify(receipt)

    def test_revision_freshness_order_and_approval_counts_fail_closed(self) -> None:
        receipt = self.make_receipt()
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "expected repository revision"):
            verify_spring_launch_receipt(
                receipt,
                trust_store=self.trust_path,
                evidence_roots=[self.evidence_root],
                expected_revision="b" * 40,
                now=self.NOW,
            )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "stale"):
            verify_spring_launch_receipt(
                receipt,
                trust_store=self.trust_path,
                evidence_roots=[self.evidence_root],
                expected_revision=self.REVISION,
                now=self.NOW + timedelta(days=5),
            )
        receipt["gates"][0], receipt["gates"][1] = receipt["gates"][1], receipt["gates"][0]
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "must be STAGING_DEPLOYMENT"):
            self.verify(receipt)
        receipt = self.make_receipt()
        receipt["approvals"] = receipt["approvals"][:1]
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "two signed external approvals"):
            with self.fast_signature_verification():
                self.verify(receipt)

    def test_approval_organizations_are_external_and_distinct(self) -> None:
        receipt = self.make_receipt()
        trust = json.loads(self.trust_path.read_text())
        for key in trust["keys"]:
            if key["key_id"] == "key-risk":
                key["organization_id"] = "release-org"
        self.write_json(self.trust_path, trust)
        risk_payload = receipt["approvals"][1]["payload"]
        risk_payload["organization_id"] = "release-org"
        receipt["approvals"][1] = self.fixture_envelope("risk", risk_payload)
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "two distinct organizations"):
            with self.fast_signature_verification():
                self.verify(receipt)

    def test_design_partners_require_distinct_signed_organizations(self) -> None:
        receipt = self.make_receipt()
        trust = json.loads(self.trust_path.read_text())
        for key in trust["keys"]:
            if key["key_id"] == "key-partner-b":
                key["organization_id"] = "partner-a-org"
        self.write_json(self.trust_path, trust)
        partner_payload = receipt["design_partner_acceptances"][1]["payload"]
        partner_payload["organization_id"] = "partner-a-org"
        partner_payload["partner_organization_id"] = "partner-a-org"
        receipt["design_partner_acceptances"][1] = self.fixture_envelope(
            "partner-b", partner_payload
        )
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "two distinct organizations"):
            with self.fast_signature_verification():
                self.verify(receipt)

    def test_strict_json_rejects_duplicate_receipt_and_trust_keys(self) -> None:
        receipt = self.make_receipt()
        receipt_file = self.evidence_root / "duplicate-receipt.json"
        raw_receipt = json.dumps(receipt, sort_keys=True)
        raw_receipt = raw_receipt.replace(
            '"schema_version": 1',
            '"schema_version": 1, "schema_version": 1',
            1,
        )
        receipt_file.write_text(raw_receipt, encoding="utf-8")
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "duplicate object key"):
            verify_spring_launch_receipt_file(
                receipt_file,
                trust_store=self.trust_path,
                evidence_roots=[self.evidence_root],
                expected_revision=self.REVISION,
                now=self.NOW,
            )

        trust_bytes = self.trust_path.read_text(encoding="utf-8")
        namespace_field = f'"namespace": "{NAMESPACE}"'
        trust_bytes = trust_bytes.replace(
            namespace_field,
            f'{namespace_field}, {namespace_field}',
            1,
        )
        self.trust_path.write_text(trust_bytes, encoding="utf-8")
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "duplicate object key"):
            self.verify(receipt)

    def test_crypto_rejects_short_signatures_and_mislabeled_rsa_keys(self) -> None:
        receipt = self.make_receipt()
        receipt["gates"][0]["execution_attestation"]["signature"] = base64.b64encode(
            b"short"
        ).decode("ascii")
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "exactly 64 bytes"):
            self.verify(receipt)

        receipt = self.make_receipt()
        rsa_private = self.case / "rsa-private.pem"
        rsa_public = self.trust_root / "keys" / "executor.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(rsa_private)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(rsa_private), "-pubout", "-out", str(rsa_public)],
            check=True,
            capture_output=True,
        )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "must be an Ed25519"):
            self.verify(receipt)

    def test_canonical_spki_detects_same_key_with_different_pem_encoding(self) -> None:
        receipt = self.make_receipt()
        executor_pem = self.public_keys["executor"].read_text(encoding="ascii")
        body = "".join(
            line
            for line in executor_pem.splitlines()
            if not line.startswith("-----")
        )
        rewrapped = "-----BEGIN PUBLIC KEY-----\n"
        rewrapped += "\n".join(body[index:index + 32] for index in range(0, len(body), 32))
        rewrapped += "\n-----END PUBLIC KEY-----\n"
        (self.trust_root / "keys" / "verifier.pem").write_text(
            rewrapped, encoding="ascii"
        )
        verification = self.fixture_envelope(
            "verifier",
            copy.deepcopy(receipt["gates"][0]["verification_attestation"]["payload"]),
        )
        receipt["gates"][0]["verification_attestation"] = verification
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "public-key material was reused"):
            with self.fast_signature_verification():
                self.verify(receipt)

    def test_environment_and_controlled_index_freshness_fail_closed(self) -> None:
        receipt = self.make_receipt()
        environment_path = Path(
            receipt["binding"]["environment"]["uri"].removeprefix("file://")
        )
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
        environment["captured_at"] = "2026-08-01T00:00:00Z"
        self.write_json(environment_path, environment, canonical=True)
        receipt["binding"]["environment"] = self.ref(environment_path)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "capture is older"):
            self.verify(receipt)

        receipt = self.make_receipt(controlled_index=True)
        index_path = Path(
            receipt["evidence_index"]["content"]["uri"].removeprefix("file://")
        )
        index_value = json.loads(index_path.read_text(encoding="utf-8"))
        index_value["generated_at"] = "2026-08-01T00:00:00Z"
        index_value["entries"][0]["recorded_at"] = "2026-08-01T00:00:00Z"
        self.write_json(index_path, index_value, canonical=True)
        receipt["evidence_index"]["content"] = self.ref(index_path)
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "index is older"):
            self.verify(receipt)

    def test_placeholders_and_bool_integer_confusion_fail_closed(self) -> None:
        receipt = self.make_receipt()
        receipt["principals"]["execution"]["actor_id"] = "CHANGE_ME_ACTOR"
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "placeholder sentinel"):
            self.verify(receipt)

        receipt = self.make_receipt()
        receipt["schema_version"] = True
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "receipt identity"):
            self.verify(receipt)

        receipt = self.make_receipt()
        environment_path = Path(
            receipt["binding"]["environment"]["uri"].removeprefix("file://")
        )
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
        environment["secrets_embedded"] = 0
        self.write_json(environment_path, environment, canonical=True)
        receipt["binding"]["environment"] = self.ref(environment_path)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "exactly false"):
            self.verify(receipt)

        receipt = self.make_receipt()
        execution_payload = copy.deepcopy(
            receipt["gates"][0]["execution_attestation"]["payload"]
        )
        execution_payload["synthetic"] = 0
        receipt["gates"][0]["execution_attestation"]["payload"] = execution_payload
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "synthetic must be false"):
            self.verify(receipt)

    def test_controlled_index_rejects_local_and_mismatched_digest_uris(self) -> None:
        receipt = self.make_receipt(controlled_index=True)
        receipt["gates"][0]["evidence"]["uri"] = (
            self.evidence_root / "gate-0.json"
        ).as_uri()
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "cannot authorize a file URI"):
            with self.fast_signature_verification():
                self.verify(receipt)

        from jsonschema import Draft202012Validator

        schema = json.loads(
            (ROOT / "schemas/batch30/spring-launch-external-evidence.schema.json").read_text()
        )
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(receipt)))

        receipt = self.make_receipt(controlled_index=True)
        receipt["gates"][0]["evidence"]["uri"] += "&sha256=" + "0" * 64
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "digest query pin must equal"):
            with self.fast_signature_verification():
                self.verify(receipt)

        with self.assertRaisesRegex(SpringLaunchEvidenceError, "mutable or placeholder"):
            _immutable_uri(
                "s3://spring-evidence/staging.json?versionId=latest",
                "sha256:" + "1" * 64,
                "test evidence URI",
            )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "mutable or placeholder"):
            _immutable_uri(
                "s3://spring-evidence/staging.json?versionId=CHANGE_ME",
                "sha256:" + "1" * 64,
                "test evidence URI",
            )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "digest query pin must equal"):
            _immutable_uri(
                "https://evidence.example/staging.json?sha256="
                + "1" * 64
                + "&SHA256="
                + "0" * 64,
                "sha256:" + "1" * 64,
                "test evidence URI",
            )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "invalid length"):
            _immutable_uri(
                "s3://spring-evidence/staging.json?versionId=%20",
                "sha256:" + "1" * 64,
                "test evidence URI",
            )

    def test_trust_store_requires_owner_only_out_of_band_file(self) -> None:
        receipt = self.make_receipt()
        os.chmod(self.trust_path, 0o644)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "owner-only mode"):
            self.verify(receipt)

        inside = self.evidence_root / "trust.json"
        inside.write_bytes(self.trust_path.read_bytes())
        os.chmod(inside, 0o600)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "outside all evidence roots"):
            verify_spring_launch_receipt(
                receipt,
                trust_store=inside,
                evidence_roots=[self.evidence_root],
                expected_revision=self.REVISION,
                now=self.NOW,
            )

    def test_openat_reference_and_assemble_output_reject_symlink_or_repo_paths(self) -> None:
        real_directory = self.case / "real-evidence"
        real_directory.mkdir()
        evidence = real_directory / "report.bin"
        evidence.write_bytes(b"evidence")
        linked_directory = self.case / "linked-evidence"
        linked_directory.symlink_to(real_directory, target_is_directory=True)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "canonical"):
            content_reference(
                linked_directory / "report.bin",
                evidence_roots=[self.case],
            )

        with self.assertRaisesRegex(SpringLaunchEvidenceError, "outside the repository"):
            _write_new_owner_only(
                ROOT / "spring-launch-receipt-should-not-exist.json",
                b"{}\n",
            )

        output_parent = self.case / "safe-output"
        output_parent.mkdir(mode=0o700)
        linked_parent = self.case / "linked-output"
        linked_parent.symlink_to(output_parent, target_is_directory=True)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "ancestors"):
            _write_new_owner_only(linked_parent / "receipt.json", b"{}\n")

        failed_output = output_parent / "failed-receipt.json"
        with mock.patch(
            "scripts.batch30.spring_launch_evidence.os.write", return_value=0
        ):
            with self.assertRaisesRegex(SpringLaunchEvidenceError, "no forward progress"):
                _write_new_owner_only(failed_output, b"{}\n")
        self.assertFalse(failed_output.exists())

    def test_global_actor_and_organization_roles_cannot_overlap(self) -> None:
        def verified(
            *, actor: str, organization: str, role: str, record_id: str
        ) -> VerifiedEnvelope:
            return VerifiedEnvelope(
                payload={"record_id": record_id},
                key_id=f"key-{record_id}",
                actor_id=actor,
                organization_id=organization,
                role=role,
                public_key_digest="sha256:" + hashlib.sha256(record_id.encode()).hexdigest(),
                payload_digest="sha256:" + "1" * 64,
                envelope_digest="sha256:" + "2" * 64,
                issued_at=self.NOW,
            )

        controls = {
            "record_ids": set(),
            "key_owners": {},
            "public_key_owners": {},
            "actor_roles": {},
            "organization_roles": {},
        }
        _register_signer(
            verified(
                actor="approval-actor",
                organization="shared-org",
                role=APPROVER_ROLE,
                record_id="approval-record",
            ),
            **controls,
        )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "organization cannot occupy"):
            _register_signer(
                verified(
                    actor="partner-actor",
                    organization="shared-org",
                    role=DESIGN_PARTNER_ROLE,
                    record_id="partner-record",
                ),
                **controls,
            )

        actor_controls = {
            "record_ids": set(),
            "key_owners": {},
            "public_key_owners": {},
            "actor_roles": {},
            "organization_roles": {},
        }
        _register_signer(
            verified(
                actor="shared-actor",
                organization="approval-org",
                role=APPROVER_ROLE,
                record_id="actor-approval-record",
            ),
            **actor_controls,
        )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "actor identity cannot occupy"):
            _register_signer(
                verified(
                    actor="shared-actor",
                    organization="partner-org",
                    role=DESIGN_PARTNER_ROLE,
                    record_id="actor-partner-record",
                ),
                **actor_controls,
            )

    def test_review_must_follow_controlled_index_attestation(self) -> None:
        receipt = self.make_receipt(controlled_index=True)
        index_payload = copy.deepcopy(receipt["evidence_index"]["attestation"]["payload"])
        index_payload["issued_at"] = "2026-09-04T09:25:00Z"
        receipt["evidence_index"]["attestation"] = self.fixture_envelope(
            "index", index_payload
        )
        review_subject = canonical_digest(
            {
                "receipt_id": receipt["receipt_id"],
                "binding_digest": receipt["binding_digest"],
                "evidence_set_digest": receipt["independent_review"]["payload"]["evidence_set_digest"],
                "controlled_index_attestation_digest": canonical_digest(
                    receipt["evidence_index"]["attestation"]
                ),
                "gate_attestations": [
                    {
                        "gate_id": gate["id"],
                        "execution_envelope_digest": canonical_digest(gate["execution_attestation"]),
                        "verification_envelope_digest": canonical_digest(gate["verification_attestation"]),
                    }
                    for gate in receipt["gates"]
                ],
                "approval_envelope_digests": sorted(
                    canonical_digest(item) for item in receipt["approvals"]
                ),
                "design_partner_envelope_digests": sorted(
                    canonical_digest(item)
                    for item in receipt["design_partner_acceptances"]
                ),
            }
        )
        review_payload = copy.deepcopy(receipt["independent_review"]["payload"])
        review_payload["review_subject_digest"] = review_subject
        receipt["independent_review"] = self.fixture_envelope(
            "reviewer", review_payload
        )
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "review predates"):
            with self.fast_signature_verification():
                self.verify(receipt)

    def test_assemble_adds_only_digest_to_complete_signed_draft(self) -> None:
        receipt = self.make_receipt()
        draft = copy.deepcopy(receipt)
        del draft["receipt_digest"]
        with self.fast_signature_verification():
            assembled, result = assemble_spring_launch_receipt(
                draft,
                trust_store=self.trust_path,
                evidence_roots=[self.evidence_root],
                expected_revision=self.REVISION,
                now=self.NOW,
            )
        self.assertEqual(receipt["receipt_digest"], assembled["receipt_digest"])
        self.assertEqual("NOT_CERTIFIED", result["certification"])


if __name__ == "__main__":
    unittest.main()
