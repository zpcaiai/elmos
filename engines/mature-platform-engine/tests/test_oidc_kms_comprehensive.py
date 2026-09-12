import sys
from pathlib import Path
import unittest
import time
import base64
import json
from unittest import mock

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from elmos_mature_platform.oidc_service import EnterpriseOidcProvider
from elmos_mature_platform.kms_service import EnterpriseKmsService
from elmos_mature_platform.types import JwtClaims, OidcTokenResult, RbacRule

class TestEnterpriseOidcProvider(unittest.TestCase):
    def setUp(self):
        self.provider = EnterpriseOidcProvider(issuer="https://test.elmos.io", key_id="test-key-1")

    def test_mint_token_basic(self):
        """Test minting a token with basic properties."""
        result = self.provider.mint_token(tenant_id="tenant-1", subject="user-1")
        self.assertIsInstance(result, OidcTokenResult)
        self.assertTrue(result.token.startswith("ey"))
        self.assertEqual(result.claims.tenant_id, "tenant-1")
        self.assertEqual(result.claims.sub, "user-1")
        self.assertEqual(result.claims.roles, ["tenant_operator"])

    def test_mint_token_custom_roles(self):
        """Test minting a token with custom roles and permissions."""
        result = self.provider.mint_token(
            tenant_id="tenant-2", 
            subject="admin-1", 
            roles=["platform_admin"], 
            permissions=["*"]
        )
        self.assertEqual(result.claims.roles, ["platform_admin"])
        self.assertEqual(result.claims.permissions, ["*"])

    def test_token_validation_valid(self):
        """Test validation of a valid token."""
        result = self.provider.mint_token(tenant_id="tenant-1", subject="user-1")
        is_valid, claims, msg = self.provider.validate_token(result.token)
        self.assertTrue(is_valid)
        self.assertIsNotNone(claims)
        self.assertEqual(claims.sub, "user-1")
        self.assertTrue(msg.startswith("OK"))

    def test_token_validation_expired(self):
        """Test validation of an expired token fails."""
        # Expire immediately
        result = self.provider.mint_token(tenant_id="tenant-1", subject="user-1", expires_in=-10)
        is_valid, claims, msg = self.provider.validate_token(result.token)
        self.assertFalse(is_valid)
        self.assertIsNone(claims)
        self.assertIn("E_TOKEN_EXPIRED", msg)

    def test_token_validation_not_yet_valid(self):
        """Test validation of a not-yet-valid token fails."""
        with mock.patch("time.time", return_value=time.time() + 100):
            result = self.provider.mint_token(tenant_id="tenant-1", subject="user-1")
            
        is_valid, claims, msg = self.provider.validate_token(result.token)
        self.assertFalse(is_valid)
        self.assertIsNone(claims)
        self.assertIn("E_TOKEN_NOT_YET_VALID", msg)

    def test_token_revocation(self):
        """Test revoking a token and verifying it is rejected."""
        result = self.provider.mint_token(tenant_id="tenant-1", subject="user-1")
        
        # Valid initially
        is_valid, _, _ = self.provider.validate_token(result.token)
        self.assertTrue(is_valid)
        
        # Revoke
        self.provider.revoke_token(jti=result.claims.jti, tenant_id="tenant-1", actor="admin")
        
        # Invalid after revocation
        is_valid, claims, msg = self.provider.validate_token(result.token)
        self.assertFalse(is_valid)
        self.assertIsNone(claims)
        self.assertIn("E_TOKEN_REVOKED", msg)

    def test_cross_tenant_token_isolation(self):
        """Test that tokens isolate tenants correctly."""
        result = self.provider.mint_token(tenant_id="tenant-A", subject="user-1")
        is_valid, claims, _ = self.provider.validate_token(result.token)
        self.assertTrue(is_valid)
        self.assertEqual(claims.tenant_id, "tenant-A")
        self.assertNotEqual(claims.tenant_id, "tenant-B")

    def test_multiple_tokens_same_user(self):
        """Test generating multiple tokens for the same user yields different JTIs."""
        res1 = self.provider.mint_token(tenant_id="tenant-1", subject="user-1")
        res2 = self.provider.mint_token(tenant_id="tenant-1", subject="user-1")
        
        self.assertNotEqual(res1.token, res2.token)
        self.assertNotEqual(res1.claims.jti, res2.claims.jti)

    def test_invalid_malformed_token(self):
        """Test handling of completely invalid or malformed tokens."""
        is_valid, claims, msg = self.provider.validate_token("not.a.jwt")
        self.assertFalse(is_valid)
        self.assertIn("E_DECODE_FAILED", msg)
        
        is_valid, claims, msg = self.provider.validate_token("invalid-token")
        self.assertFalse(is_valid)
        self.assertIn("E_MALFORMED_JWT", msg)

    def test_jwk_discovery_endpoint(self):
        """Test JWKS endpoint exposes correct claims."""
        jwks = self.provider.get_jwks()
        self.assertIn("keys", jwks)
        self.assertEqual(len(jwks["keys"]), 1)
        key = jwks["keys"][0]
        self.assertEqual(key["kty"], "RSA")
        self.assertEqual(key["use"], "sig")
        self.assertEqual(key["alg"], "RS256")
        self.assertEqual(key["kid"], "test-key-1")
        self.assertIn("pem", key)

    def test_token_claims_structure(self):
        """Test JWT token contains standard required claims."""
        result = self.provider.mint_token(tenant_id="tenant-1", subject="user-1")
        payload_b64 = result.token.split(".")[1]
        pad = 4 - (len(payload_b64) % 4)
        if pad != 4:
            payload_b64 += "=" * pad
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
        
        self.assertEqual(payload["iss"], "https://test.elmos.io")
        self.assertEqual(payload["sub"], "user-1")
        self.assertIn("aud", payload)
        self.assertIn("exp", payload)
        self.assertIn("nbf", payload)
        self.assertIn("iat", payload)
        self.assertIn("jti", payload)

    def test_rbac_evaluation_allowed(self):
        """Test RBAC evaluation for allowed action."""
        result = self.provider.mint_token(tenant_id="tenant-1", subject="user-1", roles=["tenant_operator"])
        allowed, msg = self.provider.evaluate_access(
            claims=result.claims,
            action="deploy",
            resource_type="deployment",
            target_tenant_id="tenant-1"
        )
        self.assertTrue(allowed)
        self.assertIn("OK", msg)

    def test_rbac_evaluation_cross_tenant_denied(self):
        """Test RBAC denies access across tenants."""
        result = self.provider.mint_token(tenant_id="tenant-1", subject="user-1", roles=["tenant_operator"])
        allowed, msg = self.provider.evaluate_access(
            claims=result.claims,
            action="deploy",
            resource_type="deployment",
            target_tenant_id="tenant-2" # Different tenant
        )
        self.assertFalse(allowed)
        self.assertIn("E_CROSS_TENANT_VIOLATION", msg)

    def test_rbac_evaluation_platform_admin_cross_tenant(self):
        """Test RBAC allows cross-tenant for platform_admin."""
        result = self.provider.mint_token(tenant_id="tenant-1", subject="user-1", roles=["platform_admin"])
        allowed, msg = self.provider.evaluate_access(
            claims=result.claims,
            action="deploy",
            resource_type="deployment",
            target_tenant_id="tenant-2" # Allowed for platform_admin
        )
        self.assertTrue(allowed)
        self.assertIn("OK", msg)

    def test_rbac_evaluation_unknown_role(self):
        """Test RBAC evaluation with unknown role."""
        result = self.provider.mint_token(tenant_id="tenant-1", subject="user-1", roles=["unknown_role"])
        allowed, msg = self.provider.evaluate_access(
            claims=result.claims,
            action="read",
            resource_type="deployment",
            target_tenant_id="tenant-1"
        )
        self.assertFalse(allowed)
        self.assertIn("E_FORBIDDEN", msg)

    def test_batch_revocation(self):
        """Test revoking multiple tokens in batch (simulate)."""
        tokens = [self.provider.mint_token(tenant_id="tenant-1", subject=f"user-{i}") for i in range(3)]
        for t in tokens:
            self.provider.revoke_token(t.claims.jti, "tenant-1", "admin")
            
        for t in tokens:
            is_valid, _, msg = self.provider.validate_token(t.token)
            self.assertFalse(is_valid)
            self.assertIn("E_TOKEN_REVOKED", msg)


class TestEnterpriseKmsService(unittest.TestCase):
    def setUp(self):
        self.kms = EnterpriseKmsService()

    def test_key_creation_and_retrieval(self):
        """Test creating a KMS key."""
        desc = self.kms.create_key("test-key-1")
        self.assertEqual(desc.key_id, "test-key-1")
        self.assertEqual(desc.version, 1)
        self.assertEqual(desc.algorithm, "AES-256-AUTHENTICATED")
        
        self.assertIn("test-key-1", self.kms.keys)
        self.assertEqual(self.kms.active_versions["test-key-1"], 1)

    def test_envelope_encryption_roundtrip(self):
        """Test envelope encryption and decryption roundtrip."""
        self.kms.create_key("my-key")
        plaintext = b"sensitive business data"
        payload = self.kms.envelope_encrypt(
            key_id="my-key",
            plaintext=plaintext,
            tenant_id="tenant-A",
            resource_id="res-1"
        )
        
        self.assertEqual(payload.key_id, "my-key")
        self.assertEqual(payload.key_version, 1)
        
        decrypted = self.kms.envelope_decrypt(
            payload=payload,
            tenant_id="tenant-A",
            resource_id="res-1"
        )
        self.assertEqual(decrypted, plaintext)

    def test_key_rotation(self):
        """Test key rotation and backwards compatibility of old versions."""
        self.kms.create_key("rotate-key")
        
        # Encrypt with v1
        payload_v1 = self.kms.envelope_encrypt("rotate-key", b"data1", "tenant-1", "res-1")
        
        # Rotate to v2
        desc_v2 = self.kms.rotate_key("rotate-key")
        self.assertEqual(desc_v2.version, 2)
        
        # Encrypt with v2
        payload_v2 = self.kms.envelope_encrypt("rotate-key", b"data2", "tenant-1", "res-1")
        self.assertEqual(payload_v2.key_version, 2)
        
        # Decrypt v1 payload
        dec1 = self.kms.envelope_decrypt(payload_v1, "tenant-1", "res-1")
        self.assertEqual(dec1, b"data1")
        
        # Decrypt v2 payload
        dec2 = self.kms.envelope_decrypt(payload_v2, "tenant-1", "res-1")
        self.assertEqual(dec2, b"data2")

    def test_cross_tenant_decryption_blocked(self):
        """Test decryption fails with PermissionError on cross-tenant AAD mismatch."""
        self.kms.create_key("shared-key")
        payload = self.kms.envelope_encrypt("shared-key", b"secret", "tenant-A", "res-1")
        
        with self.assertRaises(PermissionError) as ctx:
            self.kms.envelope_decrypt(payload, "tenant-B", "res-1")
        self.assertIn("AAD mismatch", str(ctx.exception))

    def test_crypto_shredding(self):
        """Test crypto-shredding zeroes out key and prevents decryption."""
        self.kms.create_key("shred-key")
        payload = self.kms.envelope_encrypt("shred-key", b"secret", "tenant-A", "res-1")
        
        # Verify it can be decrypted before shredding
        dec = self.kms.envelope_decrypt(payload, "tenant-A", "res-1")
        self.assertEqual(dec, b"secret")
        
        # Shred the key
        self.kms.crypto_shred_key("shred-key")
        
        # Verify key is zeroed out
        desc = self.kms.keys["shred-key"][1]
        self.assertTrue(all(b == 0 for b in desc.raw_key_bytes))
        self.assertTrue(desc.is_shredded)
        
        # Decryption should fail
        with self.assertRaises(PermissionError) as ctx:
            self.kms.envelope_decrypt(payload, "tenant-A", "res-1")
        self.assertIn("permanently unrecoverable", str(ctx.exception))
        
        # Encryption should fail
        with self.assertRaises(PermissionError) as ctx:
            self.kms.envelope_encrypt("shred-key", b"secret2", "tenant-A", "res-1")
        self.assertIn("Cannot encrypt with shredded/revoked key", str(ctx.exception))

    def test_multiple_keys_isolation(self):
        """Test encrypting with multiple different keys."""
        self.kms.create_key("key-1")
        self.kms.create_key("key-2")
        
        p1 = self.kms.envelope_encrypt("key-1", b"d1", "tenant-1", "r1")
        p2 = self.kms.envelope_encrypt("key-2", b"d2", "tenant-1", "r2")
        
        # Try to use wrong key mapping by changing key_id in payload
        p1_fake = p1
        p1_fake.key_id = "key-2"
        
        # Decrypting p1 with key-2 should fail AAD check or HMAC due to wrong DEK wrap
        with self.assertRaises(ValueError):
            # Because p1's DEK was encrypted with key-1, trying to unwrap it with key-2 will fail MAC check
            self.kms.envelope_decrypt(p1_fake, "tenant-1", "r1")

    def test_audit_log_hash_chain_integrity(self):
        """Test the cryptographic audit log maintains integrity."""
        self.kms.create_key("audit-key")
        self.kms.rotate_key("audit-key")
        self.kms.envelope_encrypt("audit-key", b"data", "tenant-A", "res-1")
        
        is_valid, length, msg = self.kms.verify_audit_ledger_integrity()
        self.assertTrue(is_valid)
        self.assertGreaterEqual(length, 3) # create, rotate, encrypt + master key create = 4
        
        # Tamper with the log
        self.kms.audit_log[1].actor = "hacker"
        is_valid_tampered, idx, msg_tampered = self.kms.verify_audit_ledger_integrity()
        self.assertFalse(is_valid_tampered)
        self.assertEqual(idx, 1)
        self.assertIn("Tampered entry", msg_tampered)

    def test_aad_binding_wrong_resource(self):
        """Test decryption fails with wrong resource ID."""
        self.kms.create_key("res-key")
        payload = self.kms.envelope_encrypt("res-key", b"secret", "tenant-A", "res-1")
        
        with self.assertRaises(PermissionError) as ctx:
            self.kms.envelope_decrypt(payload, "tenant-A", "res-2") # wrong resource
        self.assertIn("AAD mismatch", str(ctx.exception))

    def test_encrypt_nonexistent_key(self):
        """Test encryption fails if key does not exist."""
        with self.assertRaises(KeyError):
            self.kms.envelope_encrypt("nope", b"data", "tenant-A", "res-1")

    def test_large_payload_encryption(self):
        """Test encryption and decryption of large payloads (e.g., 1MB)."""
        self.kms.create_key("large-key")
        large_data = b"A" * (1024 * 1024) # 1 MB
        
        payload = self.kms.envelope_encrypt("large-key", large_data, "tenant-A", "res-1")
        decrypted = self.kms.envelope_decrypt(payload, "tenant-A", "res-1")
        
        self.assertEqual(decrypted, large_data)

    def test_sequential_encryptions_iv_uniqueness(self):
        """Test identical plaintexts yield different ciphertexts due to random IVs."""
        self.kms.create_key("seq-key")
        plaintext = b"identical message"
        
        p1 = self.kms.envelope_encrypt("seq-key", plaintext, "tenant-A", "res-1")
        p2 = self.kms.envelope_encrypt("seq-key", plaintext, "tenant-A", "res-1")
        
        self.assertNotEqual(p1.ciphertext_b64, p2.ciphertext_b64)
        self.assertNotEqual(p1.iv_b64, p2.iv_b64)
        self.assertNotEqual(p1.encrypted_dek_b64, p2.encrypted_dek_b64)

if __name__ == "__main__":
    unittest.main()
