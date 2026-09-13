"""External signature authority for effectful Foundry permits."""

from __future__ import annotations

from dataclasses import replace
import unittest

from elmos_foundry.adapters import (
    AdapterBinding,
    EffectClass,
    InvocationPermit,
    InvocationRequest,
)
from elmos_foundry.kernel import ExecutionKernel
from elmos_foundry.permit_authority import (
    SignedPermitTrustPolicy,
    build_signed_permit_verifier,
)


class SignedPermitAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 2_000_000_000
        kernel = ExecutionKernel(clock=lambda: self.now)
        self.scope = kernel.mint_context(
            tenant_id="tenant-permit",
            project_id="project-permit",
            actor_id="actor-requester",
            environment_id="environment-prod",
            workspace_digest="sha256:" + "a" * 64,
            revision_set_id="sha256:" + "b" * 64,
            purpose="execute-exact-provider-route",
            invocation_id="invocation-permit-01",
            lease_id="lease-permit-01",
            ttl_seconds=600,
            capabilities=("foundry.adapter.execute",),
        )
        self.binding = AdapterBinding(
            adapter_id="external.example-skill",
            version="1.0.0",
            digest="c" * 64,
            exact_skills=("example-skill",),
            effect_class=EffectClass.PRIVILEGED_EXTERNAL,
        )
        self.request = InvocationRequest(
            skill_name="example-skill",
            operation="foundry.skill.example-skill.execute",
            payload_digest="sha256:" + "d" * 64,
            tenant_id=self.scope.tenant_id,
            project_id=self.scope.project_id,
            actor_id=self.scope.actor_id,
            purpose=self.scope.purpose,
            environment_id=self.scope.environment_id,
            workspace_digest=self.scope.workspace_digest,
            revision_set_id=self.scope.revision_set_id,
            invocation_id=self.scope.invocation_id,
            adapter_id=self.binding.adapter_id,
            adapter_version=self.binding.version,
            adapter_digest=self.binding.digest,
            broker_id="broker.production",
            broker_version="1.0.0",
            broker_digest="e" * 64,
            route_id="route.example-skill",
            route_digest="f" * 64,
            effect_class=EffectClass.PRIVILEGED_EXTERNAL,
            risk_class="high",
            required_inputs=("input",),
            allowed_tools=("provider.execute",),
            required_gates=("provider-receipt-valid",),
            semantic_program_digest="sha256:" + "1" * 64,
        )

    def signed_permit(self) -> InvocationPermit:
        permit = InvocationPermit(
            permit_id="permit-production-01",
            authorization_id="authorization-production-01",
            invocation_id=self.request.invocation_id,
            adapter_id=self.request.adapter_id,
            adapter_version=self.request.adapter_version,
            adapter_digest=self.request.adapter_digest,
            broker_id=self.request.broker_id,
            broker_version=self.request.broker_version,
            broker_digest=self.request.broker_digest,
            route_id=self.request.route_id,
            route_digest=self.request.route_digest,
            skill_name=self.request.skill_name,
            tenant_id=self.scope.tenant_id,
            project_id=self.scope.project_id,
            actor_id=self.scope.actor_id,
            effect_class=self.request.effect_class,
            operation=self.request.operation,
            payload_digest=self.request.payload_digest,
            purpose=self.scope.purpose,
            environment_id=self.scope.environment_id,
            workspace_digest=self.scope.workspace_digest,
            revision_set_id=self.scope.revision_set_id,
            issued_at=self.now,
            expires_at=self.now + 300,
            nonce="nonce-production-01",
            policy_decision_id="policy-production-01",
            policy_decision_digest="sha256:" + "2" * 64,
            authorized_tools=self.request.allowed_tools,
            authorized_gates=self.request.required_gates,
            gate_evidence_digest="sha256:" + "3" * 64,
            semantic_program_digest=self.request.semantic_program_digest,
            authorized=True,
            issuer_id="authorization-service",
            key_id="authorization-key-2026",
            trust_epoch=9,
            permit_digest="sha256:" + "0" * 64,
            signature="pending",
        )
        return replace(permit, permit_digest=permit.signing_digest, signature="valid-signature")

    def policy(self, **changes: object) -> SignedPermitTrustPolicy:
        values: dict[str, object] = {
            "trusted_issuer_keys": {
                "authorization-service": ("authorization-key-2026",),
            },
            "trust_epoch": 9,
        }
        values.update(changes)
        return SignedPermitTrustPolicy(**values)  # type: ignore[arg-type]

    def test_complete_signed_permit_is_verified(self) -> None:
        verifier = build_signed_permit_verifier(
            policy=self.policy(),
            signature_verifier=lambda issuer, key, digest, signature: (
                issuer == "authorization-service"
                and key == "authorization-key-2026"
                and digest == self.signed_permit().signing_digest
                and signature == "valid-signature"
            ),
            clock=lambda: self.now,
        )
        permit = self.signed_permit()
        self.assertTrue(verifier(permit, self.binding, self.scope, self.request))

    def test_trust_policy_is_deeply_immutable_and_rejects_string_sets(self) -> None:
        policy = self.policy()
        self.assertEqual(
            policy.trusted_issuer_keys["authorization-service"],
            ("authorization-key-2026",),
        )
        with self.assertRaises(TypeError):
            policy.trusted_issuer_keys["authorization-service"][0] = "different"  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "set of identifiers"):
            self.policy(revoked_keys="authorization-key-2026")

    def test_unsigned_tampered_and_revoked_permits_fail_closed(self) -> None:
        verifier = build_signed_permit_verifier(
            policy=self.policy(),
            signature_verifier=lambda *_args: True,
            clock=lambda: self.now,
        )
        signed = self.signed_permit()
        unsigned = replace(
            signed,
            issuer_id=None,
            key_id=None,
            trust_epoch=None,
            permit_digest=None,
            signature=None,
        )
        tampered = replace(signed, payload_digest="sha256:" + "9" * 64)
        self.assertFalse(verifier(unsigned, self.binding, self.scope, self.request))
        self.assertFalse(verifier(tampered, self.binding, self.scope, self.request))

        revoked = build_signed_permit_verifier(
            policy=self.policy(revoked_permits=frozenset({signed.permit_id})),
            signature_verifier=lambda *_args: True,
            clock=lambda: self.now,
        )
        self.assertFalse(revoked(signed, self.binding, self.scope, self.request))


if __name__ == "__main__":
    unittest.main()
