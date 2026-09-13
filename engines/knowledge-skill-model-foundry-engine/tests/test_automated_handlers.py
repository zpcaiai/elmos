import unittest
from elmos_foundry.automated_handlers.pack_handlers import (
    get_all_automated_handlers,
    get_automated_handler,
)
from elmos_foundry.kernel import ExecutionKernel
from elmos_foundry.native_semantics import load_native_programs
from elmos_foundry.semantic_program_runner import SemanticProgramRunner

class AutomatedHandlersTests(unittest.TestCase):
    def setUp(self):
        self.kernel = ExecutionKernel()
        self.scope = self.kernel.mint_context(
            tenant_id='tenant-test',
            project_id='project-test',
            actor_id='actor-test',
            environment_id='env-test',
            workspace_digest='sha256:' + 'a' * 64,
            revision_set_id='sha256:' + 'b' * 64,
            purpose='testing-automated-handlers',
            invocation_id='inv-test-01',
            lease_id='lease-test-01',
            ttl_seconds=3600,
            capabilities=('foundry.adapter.execute',),
        )
        self.programs = load_native_programs()
        self.handlers = get_all_automated_handlers()

    def test_all_1244_skills_covered(self):
        self.assertEqual(len(self.programs), 1244)
        self.assertEqual(len(self.handlers), 1244)
        for name in self.programs.keys():
            self.assertIn(name, self.handlers)
            self.assertIsNotNone(get_automated_handler(name))

    def test_sample_skills_execution(self):
        sample_skills = [
            'a2a-agent-discovery-messaging',
            'abap-language-adapter',
            'acceptance-criteria-and-traceability',
            'accessibility-localization-test',
            'active-data-and-transfer-planner',
            'airflow-dag-modernization',
            'android-compose-adapter',
            'cobol-copybook-data-model-migration',
            'spring-security-oauth2-oidc-saml',
            'sql-dialect-parser-and-semantic-ir',
        ]
        for skill_name in sample_skills:
            prog = self.programs[skill_name]
            handler = self.handlers[skill_name]
            res = handler(skill_name, {}, self.scope, 'inv-test-01')
            self.assertEqual(res['status'], 'SUCCEEDED')
            outputs = res['outputs']
            for o in prog.document['outputs']:
                self.assertIn(o['name'], outputs)
                self.assertIsNotNone(outputs[o['name']])

    def test_semantic_program_runner_with_automated_handlers(self):
        skill_name = 'airflow-dag-modernization'
        prog = self.programs[skill_name]
        runner = SemanticProgramRunner(self.kernel, local_handlers=self.handlers)

        inputs_dict = {i['name']: {'source': 'airflow_dag'} for i in prog.document['inputs']}
        skill_meta = {
            'name': skill_name,
            'pack': prog.document['pack'],
            'inputs': [i['name'] for i in prog.document['inputs']],
            'outputs': [o['name'] for o in prog.document['outputs']],
            'required_gates': prog.required_gates,
            'invariants': prog.document['invariants'],
            'allowed_tools': [t for s in prog.stages for t in s.get('tools', ())],
        }

        res = runner.run_program(
            skill=skill_meta,
            payload=inputs_dict,
            tenant_scope=self.scope,
            invocation_id='inv-test-01',
            catalog_digest='sha256:' + 'c' * 64,
        )

        self.assertEqual(res.status, 'SUCCESS')
        for o in prog.document['outputs']:
            self.assertIn(o['name'], res.outputs)
        self.assertIn('_workflow_execution', res.outputs)
