import tempfile
import unittest
from pathlib import Path

from elmos_foundry.adapters import (
    AdapterBinding,
    AdapterRegistry,
    EffectClass,
    ExternalAdapterRoute,
    InvocationPermit,
)
from elmos_foundry.automated_handlers.automated_broker import (
    AUTOMATED_BROKER_DIGEST,
    AUTOMATED_BROKER_ID,
    AUTOMATED_BROKER_VERSION,
    create_automated_execution_broker,
    create_automated_permit_verifier,
)
from elmos_foundry.kernel import ExecutionKernel
from elmos_foundry.native_semantics import load_native_programs
from elmos_foundry.store import FoundryStore

class AutomatedBrokerTests(unittest.TestCase):
    def setUp(self):
        self.kernel = ExecutionKernel()
        self.scope = self.kernel.mint_context(
            tenant_id='tenant-test',
            project_id='project-test',
            actor_id='actor-test',
            environment_id='env-test',
            workspace_digest='sha256:' + 'a' * 64,
            revision_set_id='sha256:' + 'b' * 64,
            purpose='testing-broker',
            invocation_id='inv-broker-01',
            lease_id='lease-broker-01',
            ttl_seconds=3600,
            capabilities=('foundry.adapter.execute', 'foundry.store.read', 'foundry.store.write'),
        )
        self.programs = load_native_programs()
        self.broker = create_automated_execution_broker()
        self.verifier = create_automated_permit_verifier()
        self.registry = AdapterRegistry(
            permit_verifier=self.verifier,
            external_broker=self.broker,
        )
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp_dir.name) / 'store.sqlite3'
        self.store = FoundryStore(self.store_path, context_verifier=self.kernel.require_context)

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_brokered_skill_invocation_lifecycle(self):
        skill_name = 'cobol-copybook-data-model-migration'
        prog = self.programs[skill_name]
        adapter_id = 'adapter_cobol_copybook'
        route_id = 'route_cobol_copybook'
        binding_digest = 'c' * 64
        route_digest = 'd' * 64

        route = ExternalAdapterRoute(
            route_id=route_id,
            version='1.0.0',
            digest=route_digest,
            operation=f'foundry.skill.{skill_name}.execute',
            semantic_program=prog,
        )
        binding = AdapterBinding(
            adapter_id=adapter_id,
            version='1.0.0',
            digest=binding_digest,
            exact_skills=(skill_name,),
            effect_class=EffectClass.PRIVILEGED_EXTERNAL,
        )
        self.registry.register(binding, route)

        inputs_dict = {i['name']: {'source': 'copybook'} for i in prog.document['inputs']}
        payload = {
            'operation': f'foundry.skill.{skill_name}.execute',
            'inputs': inputs_dict,
        }

        req = self.registry.prepare_external_request(
            skill_name=skill_name,
            payload=payload,
            tenant_scope=self.scope,
            invocation_id=self.scope.invocation_id,
            adapter_id=adapter_id,
            risk_class='high',
            required_inputs=tuple(sorted(i['name'] for i in prog.document['inputs'])),
            allowed_tools=tuple(sorted(set(t for s in prog.stages for t in s.get('tools', ())))),
            required_gates=prog.required_gates,
        )

        permit = InvocationPermit(
            permit_id='permit_01',
            authorization_id='auth_01',
            invocation_id=self.scope.invocation_id,
            adapter_id=adapter_id,
            adapter_version='1.0.0',
            adapter_digest=binding_digest,
            broker_id=AUTOMATED_BROKER_ID,
            broker_version=AUTOMATED_BROKER_VERSION,
            broker_digest=AUTOMATED_BROKER_DIGEST,
            route_id=route_id,
            route_digest=route_digest,
            skill_name=skill_name,
            tenant_id=self.scope.tenant_id,
            project_id=self.scope.project_id,
            actor_id=self.scope.actor_id,
            effect_class=EffectClass.PRIVILEGED_EXTERNAL,
            operation=f'foundry.skill.{skill_name}.execute',
            payload_digest=req.payload_digest,
            purpose=self.scope.purpose,
            environment_id=self.scope.environment_id,
            workspace_digest=self.scope.workspace_digest,
            revision_set_id=self.scope.revision_set_id,
            issued_at=self.scope.issued_at,
            expires_at=self.scope.expires_at,
            nonce='nonce_cobol',
            policy_decision_id='pol_cobol',
            policy_decision_digest='sha256:' + 'e' * 64,
            authorized_tools=req.allowed_tools,
            authorized_gates=req.required_gates,
            gate_evidence_digest='sha256:' + 'f' * 64,
            semantic_program_digest=req.semantic_program_digest,
            authorized=True,
        )

        res = self.registry.invoke(
            skill_name=skill_name,
            payload=payload,
            tenant_scope=self.scope,
            invocation_id=self.scope.invocation_id,
            adapter_id=adapter_id,
            permit=permit,
            risk_class='high',
            required_inputs=tuple(sorted(i['name'] for i in prog.document['inputs'])),
            required_outputs=tuple(sorted(o['name'] for o in prog.document['outputs'])),
            allowed_tools=req.allowed_tools,
            required_gates=prog.required_gates,
            store=self.store,
        )

        self.assertEqual(res.status, 'SUCCEEDED')
        self.assertTrue(res.external_effects_performed)
        self.assertIsNone(res.error)
        self.assertIn('result', res.outputs)
        inner_res = res.outputs['result']
        for o in prog.document['outputs']:
            self.assertIn(o['name'], inner_res['outputs'])
