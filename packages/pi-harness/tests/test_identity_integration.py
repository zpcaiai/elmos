from __future__ import annotations

import base64
import json
import os
import ssl
import tempfile
import threading
import unittest
import urllib.request
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from elmos_pi_harness.identity import (
    CRLRevocationChecker,
    HTTPCompositeAuthenticator,
    MTLSAuthenticator,
    OIDCAuthenticator,
    OIDCConfig,
)
from elmos_pi_harness.independent_verifier import (
    EvidenceStatement,
    IndependentVerifierSigner,
    TrustedVerifier,
    VerifierTrustStore,
)
from elmos_pi_harness.models import PolicyDeniedError

try:
    import jwt
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
except ImportError:  # pragma: no cover - optional integration profile
    jwt = None
    x509 = None


def uid() -> str:
    return str(uuid.uuid4())


def b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        return


@unittest.skipUnless(
    os.environ.get("ELMOS_PI_IDENTITY_INTEGRATION") == "1" and jwt is not None,
    "real identity integration profile is not configured",
)
class IdentityIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="pi-identity-")
        self.root = Path(self.temporary.name).resolve()
        self.now = datetime.now(timezone.utc)
        self.ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.ca_cert = (
            x509.CertificateBuilder()
            .subject_name(
                x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "PI Test CA")])
            )
            .issuer_name(
                x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "PI Test CA")])
            )
            .public_key(self.ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(self.now - timedelta(minutes=5))
            .not_valid_after(self.now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(self.ca_key, hashes.SHA256())
        )
        self.ca_path = self.root / "ca.pem"
        self.ca_path.write_bytes(self.ca_cert.public_bytes(serialization.Encoding.PEM))
        self.servers: list[ThreadingHTTPServer] = []

    def tearDown(self) -> None:
        for server in self.servers:
            server.shutdown()
            server.server_close()
        self.temporary.cleanup()

    def certificate(
        self,
        common_name: str,
        *,
        san: x509.SubjectAlternativeName,
        usage: ExtendedKeyUsageOID,
    ):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert = (
            x509.CertificateBuilder()
            .subject_name(
                x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
            )
            .issuer_name(self.ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(self.now - timedelta(minutes=2))
            .not_valid_after(self.now + timedelta(hours=1))
            .add_extension(san, critical=False)
            .add_extension(x509.ExtendedKeyUsage([usage]), critical=False)
            .sign(self.ca_key, hashes.SHA256())
        )
        return key, cert

    def write_keypair(self, name: str, key, cert) -> tuple[Path, Path]:
        key_path = self.root / f"{name}.key"
        cert_path = self.root / f"{name}.pem"
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        return key_path, cert_path

    def crl(self, name: str, revoked_serials: tuple[int, ...] = ()) -> Path:
        builder = (
            x509.CertificateRevocationListBuilder()
            .issuer_name(self.ca_cert.subject)
            .last_update(self.now - timedelta(minutes=1))
            .next_update(self.now + timedelta(hours=1))
        )
        for serial in revoked_serials:
            builder = builder.add_revoked_certificate(
                x509.RevokedCertificateBuilder()
                .serial_number(serial)
                .revocation_date(self.now - timedelta(seconds=30))
                .build()
            )
        path = self.root / f"{name}.crl.pem"
        path.write_bytes(
            builder.sign(self.ca_key, hashes.SHA256()).public_bytes(
                serialization.Encoding.PEM
            )
        )
        return path

    def serve(self, handler, context: ssl.SSLContext) -> ThreadingHTTPServer:
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.servers.append(server)
        return server

    def test_real_jwks_tls_mtls_spiffe_and_crl_revocation(self) -> None:
        tenant_id, project_id = uid(), uid()
        server_key, server_cert = self.certificate(
            "localhost",
            san=x509.SubjectAlternativeName([x509.DNSName("localhost")]),
            usage=ExtendedKeyUsageOID.SERVER_AUTH,
        )
        server_key_path, server_cert_path = self.write_keypair(
            "server", server_key, server_cert
        )
        oidc_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        numbers = oidc_key.public_key().public_numbers()
        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": "oidc-key-1",
                    "use": "sig",
                    "alg": "RS256",
                    "n": b64url_uint(numbers.n),
                    "e": b64url_uint(numbers.e),
                }
            ]
        }

        class JWKSHandler(QuietHandler):
            def do_GET(self) -> None:
                if self.path != "/jwks":
                    self.send_error(404)
                    return
                raw = json.dumps(jwks).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        jwks_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        jwks_context.minimum_version = ssl.TLSVersion.TLSv1_2
        jwks_context.load_cert_chain(server_cert_path, server_key_path)
        jwks_server = self.serve(JWKSHandler, jwks_context)
        issuer = f"https://localhost:{jwks_server.server_port}"
        token = jwt.encode(
            {
                "iss": issuer,
                "aud": "pi-api",
                "sub": "user-1",
                "preferred_username": "alice",
                "tenant_id": tenant_id,
                "project_ids": [project_id],
                "roles": ["operator"],
                "iat": int(self.now.timestamp()),
                "exp": int((self.now + timedelta(minutes=10)).timestamp()),
            },
            oidc_key,
            algorithm="RS256",
            headers={"kid": "oidc-key-1"},
        )

        client_key, client_cert = self.certificate(
            "pi-workload",
            san=x509.SubjectAlternativeName(
                [
                    x509.UniformResourceIdentifier(
                        f"spiffe://mesh.example/tenant/{tenant_id}/workload/runner-1"
                    )
                ]
            ),
            usage=ExtendedKeyUsageOID.CLIENT_AUTH,
        )
        client_key_path, client_cert_path = self.write_keypair(
            "client", client_key, client_cert
        )
        valid_crl = self.crl("valid")
        trust_bundle = self.root / "ca-and-crl.pem"
        trust_bundle.write_bytes(self.ca_path.read_bytes() + valid_crl.read_bytes())

        class MTLSHandler(QuietHandler):
            def do_GET(self) -> None:
                self.server.peer_der = self.connection.getpeercert(binary_form=True)
                raw = b"ok"
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        mtls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        mtls_context.minimum_version = ssl.TLSVersion.TLSv1_2
        mtls_context.load_cert_chain(server_cert_path, server_key_path)
        mtls_context.load_verify_locations(cafile=trust_bundle)
        mtls_context.verify_mode = ssl.CERT_REQUIRED
        mtls_context.verify_flags |= ssl.VERIFY_CRL_CHECK_LEAF
        mtls_server = self.serve(MTLSHandler, mtls_context)
        client_context = ssl.create_default_context(cafile=self.ca_path)
        client_context.minimum_version = ssl.TLSVersion.TLSv1_2
        client_context.load_cert_chain(client_cert_path, client_key_path)
        with urllib.request.urlopen(
            f"https://localhost:{mtls_server.server_port}/probe",
            context=client_context,
            timeout=5,
        ) as response:
            self.assertEqual(response.read(), b"ok")
        certificate_der = mtls_server.peer_der

        with patch.dict(os.environ, {"SSL_CERT_FILE": str(self.ca_path)}):
            authenticator = HTTPCompositeAuthenticator(
                OIDCAuthenticator(
                    OIDCConfig(
                        issuer, "pi-api", issuer + "/jwks", algorithms=("RS256",)
                    )
                ),
                MTLSAuthenticator(
                    "mesh.example",
                    revocation_checker=CRLRevocationChecker([valid_crl]),
                ),
            )
            principal = authenticator.authenticate(
                {"Authorization": "Bearer " + token},
                certificate_der,
                transport_chain_verified=True,
            )
        self.assertEqual(principal.tenant_id, tenant_id)
        self.assertEqual(principal.project_ids, frozenset({project_id}))
        self.assertEqual(principal.authentication_methods, frozenset({"oidc", "mtls"}))

        with self.assertRaises(PolicyDeniedError):
            authenticator.authenticate(
                {"Authorization": "Bearer " + token, "X-Tenant-Id": uid()},
                certificate_der,
                transport_chain_verified=True,
            )
        revoked_crl = self.crl("revoked", (client_cert.serial_number,))
        revoked_authenticator = MTLSAuthenticator(
            "mesh.example",
            revocation_checker=CRLRevocationChecker([revoked_crl]),
        )
        with self.assertRaises(PolicyDeniedError):
            revoked_authenticator.authenticate(
                certificate_der, transport_chain_verified=True
            )

    def test_real_ed25519_independent_receipt_and_tamper_rejection(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        seed = private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        public_key = private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        started = self.now - timedelta(minutes=2)
        completed = self.now - timedelta(minutes=1)
        statement = EvidenceStatement(
            statement_id=uid(),
            scope="external_gate:P0-G05",
            producer_id="external-runner",
            producer_trust_domain="engineering.example",
            subject_digest="sha256:" + "a" * 64,
            environment_digest="sha256:" + "b" * 64,
            raw_evidence_digests=("sha256:" + "c" * 64,),
            authorization_id="AUTH-VERIFY",
            executor_id="external-runner",
            started_at=started.isoformat().replace("+00:00", "Z"),
            completed_at=completed.isoformat().replace("+00:00", "Z"),
            result="PASS",
        )
        receipt = IndependentVerifierSigner(
            verifier_id="independent-auditor",
            trust_domain="audit.example",
            key_id="audit-key-1",
            private_key=seed,
        ).sign(
            statement,
            receipt_id=uid(),
            verdict="VERIFIED",
            issued_at=completed.isoformat().replace("+00:00", "Z"),
            expires_at=(self.now + timedelta(hours=1))
            .isoformat()
            .replace("+00:00", "Z"),
        )
        trust = VerifierTrustStore(
            [
                TrustedVerifier(
                    verifier_id="independent-auditor",
                    trust_domain="audit.example",
                    key_id="audit-key-1",
                    public_key=public_key,
                    not_before=(self.now - timedelta(hours=1))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    not_after=(self.now + timedelta(hours=2))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    allowed_scopes=frozenset({"external_gate:P0-G05"}),
                )
            ]
        )
        verified = trust.verify(
            receipt, expected_subject_digest=statement.subject_digest, now=self.now
        )
        self.assertTrue(verified["independent"])
        with self.assertRaises(PolicyDeniedError):
            trust.verify(
                replace(receipt, signature=receipt.signature[:-2] + "AA"),
                expected_subject_digest=statement.subject_digest,
                now=self.now,
            )


if __name__ == "__main__":
    unittest.main()
