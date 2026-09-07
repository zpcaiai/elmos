from __future__ import annotations

import base64
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from elmos_proof_harness.cli import build_parser
from elmos_proof_harness.control_plane import DurableControlPlane
from elmos_proof_harness.domains import DOMAIN_PACKS, DomainPackOrchestrator
from elmos_proof_harness.service import (
    AuthenticationError,
    AuthPrincipal,
    FileJwksAuthenticator,
    HarnessService,
)
from elmos_proof_harness.skills import (
    COMPONENT_REGISTRY,
    SKILL_REGISTRY,
    SkillRuntime,
)
from elmos_proof_harness.store import SQLiteStore


_DIGEST = "sha256:" + "a" * 64
_RSA_N = int(
    "b2ac0d008c3b49c5ee947d3e70339fc5aec31795da7d3edd3b643a5b187c067f029e66695c99b85d0e82304b3fadb185cbf886689909d37be49453b036f0d6ff7690d68423dd2d804abfa4c67cd297a631b9a3dbcb74118589066e60ee6aa7e910f91d2926abcf446915d109f528bda8f6362f77b53c860ec7240bd5d5474a59b6aaeaf22e5c6416c15af8c0ab710993a2c35d69011e982a4e6d9796e1abf4f97279a51260141a5e13fb676e7700f9172f4ae4f73572caf93ae3f3dcd0bd2c2313959e8e6da1787a68bbf9aa1c1b8f35bf9a197033d2cb4d142798dac43fbbe969e2252ecd9f9fa5dff5f423097d8e41c5a2afcd0af08a3f925a56d449ba2d67",
    16,
)
_RSA_D = int(
    "1671384989d3b1495c8027ed22fb1bb0a114c88e73925e1b916808fbc3eb0c312c3b338ce76b38364414c3e127c9f6ed8c8dc115915223cf6b8a300031c9203aed5720581a5dca91d33c6d8385a3e4157ad3210b0216a8541813dd386d54ab40eca205c628a12b0322449c6c539abef137f532bd7c0a72a242399107abbc427bcfc3d1d183e4df76b4114a306b1c085e195c41c1ef08a6f70445e2fda46166046f99cc97caf1fb4007e286a15c9c8cf82862fc48c5b100b7e3f624100192b9156d2a6157b69a1d904d306f512528a9a0504584155fd815282800b0b09503cc985af36bf079d8db2148cfd556b5d7e8c6dec40864795b15e92843d62f48bf934d",
    16,
)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _jwt(claims: dict, *, header: dict | None = None) -> str:
    protected = header or {"alg": "RS256", "kid": "test-key", "typ": "JWT"}
    encoded_header = _b64(json.dumps(protected, separators=(",", ":"), sort_keys=True).encode())
    encoded_claims = _b64(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{encoded_header}.{encoded_claims}".encode()
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(signing_input).digest()
    width = (_RSA_N.bit_length() + 7) // 8
    encoded = b"\x00\x01" + b"\xff" * (width - len(digest_info) - 3) + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded, "big"), _RSA_D, _RSA_N).to_bytes(width, "big")
    return f"{encoded_header}.{encoded_claims}.{_b64(signature)}"


def _principal() -> AuthPrincipal:
    return AuthPrincipal(
        tenant_id="tenant-1",
        project_id="project-1",
        actor_id="actor-1",
        authority=("proof-harness.read",),
        authentication_context_digest=_DIGEST,
        authority_id="authority-1",
        authority_revision=_DIGEST,
        environment_id="environment-1",
        environment_revision=_DIGEST,
        execution_epoch=1,
        fencing_generation=1,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class RegistryTests(unittest.TestCase):
    def test_exact_registry_counts_distinct_handlers_and_resolvable_components(
        self,
    ) -> None:
        runtime = SkillRuntime()
        self.assertEqual(len(SKILL_REGISTRY), 16)
        self.assertEqual(len(COMPONENT_REGISTRY), 96)
        self.assertEqual(len(runtime.handlers), 16)
        self.assertEqual(len(runtime.describe()["adapters"]), 27)
        self.assertEqual(len({type(item) for item in runtime.handlers.values()}), 16)
        self.assertEqual(
            {item.component_id for item in COMPONENT_REGISTRY.values()},
            set(COMPONENT_REGISTRY),
        )
        for descriptor in COMPONENT_REGISTRY.values():
            module_name, _, symbol_name = descriptor.implementation.rpartition(".")
            self.assertTrue(module_name, descriptor.component_id)
            symbol = getattr(importlib.import_module(module_name), symbol_name)
            self.assertTrue(callable(symbol), descriptor.component_id)
            if descriptor.implementation_state == "LOCAL":
                self.assertNotIn(
                    descriptor.kernel,
                    {"K1", "K3", "K4", "K5", "K8"},
                    descriptor.component_id,
                )

    def test_domain_packs_preserve_proof_requirements(self) -> None:
        self.assertEqual(len(DOMAIN_PACKS), 5)
        orchestrator = DomainPackOrchestrator()
        plan = orchestrator.plan(
            "sql-dialect-routine-conversion",
            {"source": "PostgreSQL", "target": "Oracle"},
        )
        self.assertEqual(len(plan.kernel_sequence), 8)
        self.assertEqual(len(plan.obligations), 12)
        self.assertEqual(plan.obligations[0].unknown_policy, "BLOCK")
        decision = orchestrator.evaluate(
            "sql-dialect-routine-conversion",
            {
                obligation.template_id: [
                    {
                        "kind": obligation.required_evidence[0],
                        "status": "PASS",
                        "independent": True,
                    }
                ]
                for obligation in plan.obligations
            },
        )
        self.assertEqual(decision.decision, "BLOCKED")
        self.assertFalse(decision.to_dict()["certified"])


class ServiceSurfaceTests(unittest.TestCase):
    class _TrustedAuthenticator:
        trusted_for_production = True

        def __init__(self, principal: AuthPrincipal) -> None:
            self.principal = principal

        def authenticate(self, headers):
            return self.principal

        def readiness(self):
            return True, "test identity gateway ready"

    def test_readiness_fails_closed_without_durable_control_plane(self) -> None:
        runtime = SkillRuntime()
        service = HarnessService(
            runtime,
            auth_tokens={"test-token-0123456789": _principal()},
            runtime_mode="local-engineering",
        )
        response = service.handle_request("GET", "/readyz", {})
        self.assertEqual(response.status, 503)
        self.assertIn(b'"durableStore":"not-configured"', response.body)

    def test_cli_serve_keeps_host_and_port_contract(self) -> None:
        arguments = build_parser().parse_args(
            ["serve", "--host", "0.0.0.0", "--port", "8090"]
        )
        self.assertEqual(arguments.host, "0.0.0.0")
        self.assertEqual(arguments.port, 8090)

    def test_production_rejects_static_tokens_and_wrong_issuer_or_audience(self) -> None:
        runtime = SkillRuntime()
        with self.assertRaisesRegex(ValueError, "static token"):
            HarnessService(
                runtime,
                auth_tokens={"test-token-0123456789": _principal()},
                runtime_mode="production",
                expected_issuer="https://identity.example.test",
                expected_audience="proof-harness-api",
                transport_mode="trusted-proxy",
                trusted_proxy_cidrs=("127.0.0.1/32",),
            )
        trusted_principal = replace(
            _principal(),
            issuer="https://wrong-issuer.example.test",
            audience="proof-harness-api",
        )
        service = HarnessService(
            runtime,
            authenticator=self._TrustedAuthenticator(trusted_principal),
            runtime_mode="production",
            expected_issuer="https://identity.example.test",
            expected_audience="proof-harness-api",
            transport_mode="trusted-proxy",
            trusted_proxy_cidrs=("127.0.0.1/32",),
        )
        response = service.handle_request("GET", "/v3/skills", {})
        self.assertEqual(response.status, 401)
        trusted_principal = replace(
            trusted_principal,
            issuer="https://identity.example.test",
            audience="wrong-audience",
        )
        service = HarnessService(
            runtime,
            authenticator=self._TrustedAuthenticator(trusted_principal),
            runtime_mode="production",
            expected_issuer="https://identity.example.test",
            expected_audience="proof-harness-api",
            transport_mode="trusted-proxy",
            trusted_proxy_cidrs=("127.0.0.1/32",),
        )
        response = service.handle_request("GET", "/v3/skills", {})
        self.assertEqual(response.status, 401)

    def test_production_readiness_rejects_local_sqlite_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = SkillRuntime()
            store = SQLiteStore(Path(temporary) / "local.db")
            principal = replace(
                _principal(),
                issuer="https://identity.example.test",
                audience="proof-harness-api",
            )
            try:
                service = HarnessService(
                    runtime,
                    authenticator=self._TrustedAuthenticator(principal),
                    control_plane=DurableControlPlane(store, runtime),
                    runtime_mode="production",
                    expected_issuer="https://identity.example.test",
                    expected_audience="proof-harness-api",
                    transport_mode="trusted-proxy",
                    trusted_proxy_cidrs=("127.0.0.1/32",),
                )
                readiness = service.handle_request("GET", "/readyz", {})
                self.assertEqual(readiness.status, 503)
                self.assertIn(b'"durableStore":"not-ready"', readiness.body)
            finally:
                store.close()

    def test_builtin_jwks_authenticator_verifies_exact_signed_bindings(self) -> None:
        now = datetime.now(UTC).replace(microsecond=0)
        width = (_RSA_N.bit_length() + 7) // 8
        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": "test-key",
                    "use": "sig",
                    "key_ops": ["verify"],
                    "alg": "RS256",
                    "n": _b64(_RSA_N.to_bytes(width, "big")),
                    "e": _b64((65537).to_bytes(3, "big")),
                }
            ]
        }
        claims = {
            "iss": "https://identity.example.test",
            "aud": "proof-harness-api",
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "nbf": int((now - timedelta(seconds=1)).timestamp()),
            "scope": "proof-harness.invoke proof-harness.read",
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "actor_id": "actor-1",
            "authentication_context_digest": _DIGEST,
            "authority_id": "authority-1",
            "authority_revision": _DIGEST,
            "environment_id": "environment-1",
            "environment_revision": _DIGEST,
            "execution_epoch": 1,
            "fencing_generation": 1,
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "jwks.json"
            path.write_text(json.dumps(jwks), encoding="utf-8")
            path.chmod(0o600)
            authenticator = FileJwksAuthenticator(
                path,
                issuer=claims["iss"],
                audience=claims["aud"],
                refresh_seconds=1,
                leeway_seconds=0,
                clock=lambda: now,
            )
            principal = authenticator.authenticate(
                {"authorization": "Bearer " + _jwt(claims)}
            )
            self.assertEqual(principal.tenant_id, "tenant-1")
            self.assertEqual(
                principal.authority,
                ("proof-harness.invoke", "proof-harness.read"),
            )
            raw_jwt = _jwt({**claims, "tenant_id": "tenant-2"})
            tampered = raw_jwt[:-1] + ("B" if raw_jwt.endswith("A") else "A")
            with self.assertRaises(AuthenticationError):
                authenticator.authenticate({"authorization": "Bearer " + tampered})
            for changed in (
                {**claims, "iss": "https://wrong.example.test"},
                {**claims, "aud": "wrong-audience"},
                {**claims, "exp": int((now - timedelta(seconds=1)).timestamp())},
                {**claims, "nbf": int((now + timedelta(seconds=1)).timestamp())},
                {**claims, "scope": "proof-harness.invoke workspace.write"},
            ):
                with self.subTest(changed=changed):
                    with self.assertRaises(AuthenticationError):
                        authenticator.authenticate(
                            {"authorization": "Bearer " + _jwt(changed)}
                        )
            symlink = Path(temporary) / "jwks-link.json"
            symlink.symlink_to(path)
            with self.assertRaises(AuthenticationError):
                FileJwksAuthenticator(
                    symlink,
                    issuer=claims["iss"],
                    audience=claims["aud"],
                )

    def test_production_transport_configuration_is_mandatory(self) -> None:
        runtime = SkillRuntime()
        principal = replace(
            _principal(),
            issuer="https://identity.example.test",
            audience="proof-harness-api",
        )
        with self.assertRaisesRegex(ValueError, "TLS or"):
            HarnessService(
                runtime,
                authenticator=self._TrustedAuthenticator(principal),
                runtime_mode="production",
                expected_issuer=principal.issuer,
                expected_audience=principal.audience,
                transport_mode="local",
            )
        with self.assertRaisesRegex(ValueError, "proxy CIDRs"):
            HarnessService(
                runtime,
                authenticator=self._TrustedAuthenticator(principal),
                runtime_mode="production",
                expected_issuer=principal.issuer,
                expected_audience=principal.audience,
                transport_mode="trusted-proxy",
            )


if __name__ == "__main__":
    unittest.main()
