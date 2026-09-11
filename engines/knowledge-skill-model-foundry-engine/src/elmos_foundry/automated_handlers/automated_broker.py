from __future__ import annotations

import hashlib
import time
from typing import Any, Mapping

from ..adapters import (
    AdapterBinding,
    ExternalAdapterRoute,
    ExternalExecutionBroker,
    InvocationPermit,
    InvocationRequest,
    PermitVerifier,
)
from ..canonical import canonical_digest
from ..domain import TenantScope
from ..exact_skills.compiler import ExactSkillError
from ..exact_skills.registry import run_exact_skill
from ..industrial_runtime.host_broker import INDUSTRIAL_BROKER_ID

AUTOMATED_BROKER_ID = 'automated_host_broker'
AUTOMATED_BROKER_VERSION = '1.0.0'
AUTOMATED_BROKER_DIGEST = hashlib.sha256(b'elmos.foundry.automated_host_broker.v1').hexdigest()

def automated_broker_executor(
    route: ExternalAdapterRoute,
    binding: AdapterBinding,
    request: InvocationRequest,
    permit: InvocationPermit,
    payload: Mapping[str, Any],
    tenant_scope: TenantScope,
) -> Mapping[str, Any]:
    """Production automated broker executor for native semantic programs."""
    program = route.semantic_program
    if program is None:
        raise ValueError(f"Route {route.route_id} lacks a semantic program")

    skill_name = program.skill_name
    invocation_id = request.invocation_id
    req_binding_digest = request.binding_digest
    try:
        executed = run_exact_skill(
            skill_name,
            payload,
            tenant_scope=tenant_scope,
            invocation_id=invocation_id,
            request_binding_digest=req_binding_digest,
        )
    except ExactSkillError as exc:
        raise ValueError(f"Exact handler failed for {skill_name}: {exc}") from exc
    if executed.get("status") != "SUCCEEDED" or executed.get("semantic_execution") is None:
        raise ValueError(f"Exact handler failed for {skill_name}: {executed.get('error')}")

    program.validate_result(
        {"semantic_execution": executed["semantic_execution"]},
        request_binding_digest=req_binding_digest,
    )

    provider_receipt = {
        'receipt_digest': canonical_digest({
            'provider': 'elmos-native-automated-broker',
            'request_binding_digest': req_binding_digest,
            'skill': skill_name,
            'handler_id': executed.get('handler_id'),
            'program_digest': executed.get('program_digest'),
            'output_digest': executed.get('output_digest'),
        }),
        'request_binding_digest': req_binding_digest,
        'outcome': 'CONFIRMED',
        'provider': INDUSTRIAL_BROKER_ID,
        'kernel_family': executed.get('kernel_family'),
        'algorithm': executed.get('algorithm'),
        'input_digest': executed.get('input_digest'),
        'output_digest': executed.get('output_digest'),
        'llm_required': False,
        'exact': True,
    }

    return {
        'status': 'SUCCEEDED',
        'outputs': executed['outputs'],
        'provider_receipt': provider_receipt,
        'semantic_execution': executed['semantic_execution'],
    }

def automated_result_verifier(
    route: ExternalAdapterRoute,
    binding: AdapterBinding,
    request: InvocationRequest,
    permit: InvocationPermit,
    result: Mapping[str, Any],
    tenant_scope: TenantScope,
) -> bool:
    if not isinstance(result, Mapping):
        return False
    if result.get('status') != 'SUCCEEDED':
        return False
    receipt = result.get('provider_receipt')
    if not isinstance(receipt, Mapping):
        return False
    if receipt.get('outcome') != 'CONFIRMED':
        return False
    if receipt.get('request_binding_digest') != request.binding_digest:
        return False
    return True

def create_automated_execution_broker(
    broker_id: str = AUTOMATED_BROKER_ID,
    version: str = AUTOMATED_BROKER_VERSION,
    digest: str = AUTOMATED_BROKER_DIGEST,
) -> ExternalExecutionBroker:
    return ExternalExecutionBroker(
        broker_id=broker_id,
        version=version,
        digest=digest,
        execute=automated_broker_executor,
        verify_result=automated_result_verifier,
    )

def create_automated_permit_verifier() -> PermitVerifier:
    """Permit verifier that validates permit integrity and authorization claims."""
    def _verify(permit: InvocationPermit, binding: AdapterBinding, scope: TenantScope, req: InvocationRequest) -> bool:
        if not permit.authorized:
            return False
        if permit.tenant_id != scope.tenant_id or permit.project_id != scope.project_id:
            return False
        if permit.actor_id != scope.actor_id or permit.environment_id != scope.environment_id:
            return False
        if permit.invocation_id != req.invocation_id:
            return False
        if permit.adapter_id != binding.adapter_id:
            return False
        if time.time() > permit.expires_at:
            return False
        return True
    return _verify

class AutomatedExecutionBrokerFactory:
    @staticmethod
    def get_broker() -> ExternalExecutionBroker:
        return create_automated_execution_broker()

    @staticmethod
    def get_permit_verifier() -> PermitVerifier:
        return create_automated_permit_verifier()
