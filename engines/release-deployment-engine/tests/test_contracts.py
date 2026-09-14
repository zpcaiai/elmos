from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
sys.path.insert(0,str(ROOT/'tooling'))
from elmos_release_deployment.contracts import Denied
from elmos_release_deployment.temporal_adapter import definitions
import integrate_release_deployment_skills as importer
import test_runtime as fixture


class ContractsTest(unittest.TestCase):
    def setUp(self):
        self.f=fixture.RuntimeTest(); self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def test_actual_evidence_validates_original_package_schema(self):
        from jsonschema import Draft202012Validator, FormatChecker
        path=ROOT/'skills/elmos-release-deployment-skills-v1.0.0/elmos-release-deployment/schemas/deployment-evidence.schema.json'
        schema=json.loads(path.read_text())
        validator=Draft202012Validator(schema,format_checker=FormatChecker())
        for fail in (set(),{'health.verify'},{'health.verify','rollback.verify'},{'target.preflight'}):
            self.f.host.fail=fail
            dep=self.f.deploy(); self.f.finish(dep)
            validator.validate(self.f.journal.evidence(self.f.scope,dep))
            self.f.doCleanups(); self.f.setUp()

    def test_concurrent_same_request_is_one_deployment(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids=list(pool.map(lambda _:self.f.deploy(),range(8)))
        self.assertEqual(1,len(set(ids)))

    def test_production_flag_cannot_be_downgraded_by_client(self):
        with self.assertRaisesRegex(Denied,'environment_classification'):
            self.f.service.preview(self.f.principal,replace(self.f.plan,production=False,rollback_required=False))

    def test_real_temporal_sdk_registers_workflow_and_activity(self):
        from temporalio import workflow,activity
        worker, reconcile=definitions(self.f.workflow,lambda dep:self.f.principal)
        self.assertEqual('ElmosDeployReleaseV1',workflow._Definition.must_from_class(worker).name)
        self.assertEqual('elmos.rd.reconcile.v1',activity._Definition.must_from_callable(reconcile).name)

    def test_pinned_archive_dual_root_and_immutable_mirror(self):
        self.assertEqual(24,importer.run(check=True)['files'])


if __name__=='__main__': unittest.main()
