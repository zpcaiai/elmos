from __future__ import annotations
from dataclasses import asdict, replace
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from elmos_release_deployment.contracts import *
from elmos_release_deployment.journal import Journal
from elmos_release_deployment.service import ReleaseDeploymentService
from elmos_release_deployment.workflow import DeploymentWorkflow, CHECKS, HEALTH
from elmos_release_deployment.adapters import DockerHostRuntime, MigrationController, HealthVerifier, CloudAssistantExecutor


class FixtureAuthority:
    """Test-only authority. Its HMAC is never production or independent evidence."""
    def __init__(self):
        self.key = b'local-test-authority-do-not-use-in-production'
        self.now = 1000
        self.lease_expired = False

    def seal(self, purpose, body):
        return {'body': body, 'signature': hmac.new(self.key, purpose.encode()+canonical(body), hashlib.sha256).hexdigest()}

    def verify(self, purpose, body, signature):
        return hmac.compare_digest(self.seal(purpose, body)['signature'], signature)

    def authorize(self, principal, action, body):
        return self.seal('ticket', body)

    def lease(self, principal, deployment_id, plan_digest, resources, action, generation):
        return CapabilityLease('lease-1', principal.scope, deployment_id, plan_digest, resources,
                               frozenset({action}), generation, self.now-1 if self.lease_expired else self.now+60, 'session-test')


class FixtureEvidence:
    def __init__(self, authority):
        self.authority = authority
        self.objects = {}
        self.crash = False

    def commit(self, scope, operation_key, bundle):
        if operation_key in self.objects:
            assert self.objects[operation_key] == bundle
        self.objects[operation_key] = bundle
        if self.crash:
            self.crash = False
            raise RuntimeError('simulated_evidence_commit_crash')
        return self.authority.seal('evidence_commit', {'scope': asdict(scope), 'bundle_digest': digest(bundle),
                                      'committed': True, 'receipt_digest': digest(['receipt', bundle])})


class FixtureHost:
    def __init__(self, fixture):
        self.f = fixture
        self.calls = {}
        self.submit_count = 0
        self.fail = set()
        self.unknown = False
        self.crash_after_submit = False
        self.bad_data = {}

    def submit(self, request, lease):
        self.submit_count += 1
        key = request['operation_key']
        assert key not in self.calls, 'duplicate physical dispatch'
        self.calls[key] = ('invoke-'+str(self.submit_count), request)
        if self.crash_after_submit:
            self.crash_after_submit = False
            raise RuntimeError('crash after remote accepted')
        return self.calls[key][0]

    def recover(self, request, lease):
        saved = self.calls.get(request['operation_key'])
        return saved[0] if saved else None

    def poll(self, invocation, request, lease):
        if self.unknown:
            return None
        f, action = self.f, request['action']
        images = [a.image for a in f.release.artifacts]
        data = {
            'policy.evaluate': {'decision': 'ALLOW', 'policy_digest': f.plan.policy_digest},
            'target.preflight': {'checks': {k:'PASS' for k in CHECKS}, 'target_digest': f.plan.target_digest},
            'identity.lease_ready': {'ready': True},
            'artifact.resolve': {'release_digest': f.release.manifest_digest, 'images': images},
            'migration.preflight': {'risk': f.plan.migration_risk.value, 'migration_digest': f.release.migration_digest,
                                   'authorized': True, 'backup_verified': True, 'rollback_compatible': True},
            'migration.apply': {'migration_digest': f.release.migration_digest, 'rollback_compatible': True},
            'runtime.activate': {'images': images, 'config_digest': f.plan.config_digest, 'snapshot_digest': f.snapshot_digest},
            'health.verify': {'checks': {k:'PASS' for k in HEALTH}},
            'smoke.verify': {'cases': {'expected-smoke': 'PASS'}, 'policy_digest': f.release.health_policy_digest},
            'traffic.promote': {'plan_digest': f.plan.plan_digest},
            'rollback.plan': {'snapshot_digest': f.snapshot_digest, 'rollback_compatible': True},
            'runtime.restore': {'snapshot_digest': f.snapshot_digest, 'images': f.snapshot['images'],
                                'config_digest': f.snapshot['config_digest'], 'traffic_digest': f.snapshot['traffic_digest']},
            'rollback.verify': {'checks': {k:'PASS' for k in HEALTH}, 'cases': {'expected-smoke': 'PASS'},
                                'snapshot_digest': f.snapshot_digest}}
        payload = self.bad_data.get(action, data[action])
        return f.authority.seal('operation_receipt', {'request_digest': digest(request), 'invocation_id': invocation,
             'status': 'FAIL' if action in self.fail else 'PASS', 'data': payload,
             'evidence_digest': digest(['raw', request]), 'session_identity': 'session-test',
             'stdout_hash':digest(b''),'stderr_hash':digest(b''),'artifact_uri':'cas:'+digest(['raw',request]),
             'started_at': f.authority.now, 'finished_at': f.authority.now, 'exit_code': 1 if action in self.fail else 0})


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'journal.db'
        self.journal = Journal(self.path)
        self.authority = FixtureAuthority()
        self.scope = Scope('tenant-a', 'workspace-a', 'project-a', 'prod-a', '123456789')
        permissions = frozenset({'release:create','release:read','release:revoke','target:register',
            'plan:create','ticket:issue','ticket:approve','ticket:revoke','deployment:apply','deployment:work','snapshot:register'})
        self.principal = Principal('operator', self.scope, permissions)
        self.approver = replace(self.principal, actor_id='independent-approver')
        self.service = ReleaseDeploymentService(self.journal, self.authority, self.authority, lambda:self.authority.now)
        self.schema = {'fields': {'DATABASE': {'type':'string','secret':True}}}
        self.secrets = ('secret-ref:tenant-a/database',)
        self.config = self.service.prepare_config(self.principal, self.schema, {'DATABASE':self.secrets[0]}, self.secrets)
        self.artifact = Artifact('backend', 'registry.example.test/team/backend', digest(b'image'),
                                 digest(b'sbom'), digest(b'provenance'), digest(b'scan'), 'python', 8080)
        health_digest = self.service.register_health_policy(self.principal, {
            'smoke_cases':['expected-smoke'], 'rollback_smoke_cases':['expected-smoke'], 'deadline_seconds':120, 'attempts':6})
        self.release = ReleaseManifest('release-1', self.scope, 'a'*40, (self.artifact,),
            digest(b'evidence'), digest(self.schema), digest(b'migrations'), health_digest, digest(b'compatibility'))
        self.certification = self.authority.seal('certification', {'scope':asdict(self.scope),
            'release_digest':self.release.manifest_digest, 'evidence_digest':self.release.evidence_digest,
            'decision':'DEPLOY_ALLOWED','executor':'builder','verifier':'independent','expires_at':2000})
        self.service.create_release(self.principal, self.release, self.certification)
        self.target = DeploymentTarget('target-a', self.scope, 'alibaba_ecs', 'cn-shanghai', 'rg-a',
                                       ('i-a',), (('environment','prod'),), 'amd64', '27.5.1', '123456789')
        self.target_digest = self.service.register_target(self.principal, self.target,
            self.authority.seal('target_discovery', {'scope':asdict(self.scope),'target_digest':digest(asdict(self.target)),
                'account_id':self.scope.account_id,'region':self.target.region,'resources':list(self.target.resources),'expires_at':2000,'production':True}))
        self.snapshot = {'scope':asdict(self.scope), 'target_digest':self.target_digest,
            'images':['registry.example.test/team/backend@'+digest(b'old')], 'config_digest':digest(b'old-config'),
            'traffic_digest':digest(b'old-traffic'),'verification_digest':digest(b'old-verified'),
            'health_policy_digest':health_digest,'state':'VERIFIED_STABLE'}
        self.snapshot_digest = self.service.register_stable_snapshot(self.principal, self.authority.seal('stable_snapshot',self.snapshot))
        self.plan = DeploymentPlan(self.scope,self.release.manifest_digest,self.target_digest,self.config,self.secrets,
            'single_replace',MigrationRisk.NONE,None,None,self.snapshot_digest,True,True,digest(b'policy'),(('i-a',),))
        self.service.preview(self.principal,self.plan)
        self.ticket = self.service.issue_ticket(self.principal,self.plan.plan_digest,1500)
        self.service.approve_ticket(self.approver,self.ticket)
        self.host = FixtureHost(self)
        self.evidence = FixtureEvidence(self.authority)
        self.workflow = DeploymentWorkflow(self.service,self.host,self.evidence,lambda:self.authority.now)

    def deploy(self, key='request-1'):
        return self.service.deploy(self.principal,self.ticket,self.plan.plan_digest,key)

    def finish(self, deployment):
        for _ in range(40):
            state = self.workflow.tick(self.principal,deployment)
            if state in TERMINAL:
                return state
        self.fail('workflow did not finish')

    def advance(self, deployment, state):
        for _ in range(30):
            if self.journal.load(self.scope,deployment)['state'] == state:
                return
            self.workflow.tick(self.principal,deployment)
        self.fail('state not reached')

    def test_success_commits_immutable_exact_evidence(self):
        dep = self.deploy()
        self.assertEqual('SUCCEEDED',self.finish(dep))
        evidence = self.journal.evidence(self.scope,dep)
        self.assertEqual([self.artifact.image_digest],evidence['artifact_digests'])
        self.assertTrue(all(s['invocation'] for s in evidence['steps']))
        with self.journal.connection() as c:
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute("UPDATE evidence SET body='{}'")
        self.assertEqual(0,self.journal.load(self.scope,dep)['active'])

    def test_duplicate_request_and_conflicting_key(self):
        self.assertEqual(self.deploy(),self.deploy())
        with self.assertRaises(Denied):
            self.deploy('different-key-same-consumed-ticket')

    def test_expired_ticket_has_no_dispatch(self):
        self.authority.now=1500
        with self.assertRaisesRegex(Denied,'ticket_expired'):
            self.deploy()
        self.assertEqual(0,self.host.submit_count)

    def test_release_evidence_mismatch_and_self_verification(self):
        bad = {**self.certification['body'],'evidence_digest':digest(b'wrong')}
        with self.assertRaises(Denied):
            self.service.create_release(self.principal,self.release,self.authority.seal('certification',bad))
        bad = {**self.certification['body'],'verifier':'builder'}
        with self.assertRaises(Denied):
            self.service.create_release(self.principal,self.release,self.authority.seal('certification',bad))

    def test_forged_ticket_and_no_self_approval(self):
        with self.assertRaises(Denied):
            self.service.approve_ticket(self.principal,self.ticket)
        bad = {**self.certification,'signature':'forged'}
        with self.assertRaises(Denied):
            self.service.create_release(self.principal,self.release,bad)

    def test_cross_tenant_object_deployment_and_evidence_isolation(self):
        dep=self.deploy()
        other=replace(self.principal,scope=replace(self.scope,tenant_id='tenant-b'))
        for call in [lambda:self.service.release(other,'release-1'),
                     lambda:self.journal.load(other.scope,dep),lambda:self.journal.evidence(other.scope,dep),
                     lambda:self.service.deploy(other,self.ticket,self.plan.plan_digest,'request-1')]:
            with self.assertRaises(Denied): call()

    def test_scope_lease_target_and_generation_fencing(self):
        lease=self.authority.lease(self.principal,'dep',self.plan.plan_digest,('i-a',),'runtime.activate',1)
        for args in [(('i-b',),1000,1),(('i-a',),1060,1),(('i-a',),1000,2)]:
            with self.assertRaises(Denied):
                lease.check(self.scope,'dep',self.plan.plan_digest,args[0],'runtime.activate',args[1],args[2])

    def test_preflight_every_required_failure_denies_without_mutation(self):
        # Separate complete fixture per check avoids changing production outcomes.
        for check in CHECKS:
            with self.subTest(check=check):
                checks={k:'PASS' for k in CHECKS}; checks[check]='FAIL'
                self.host.bad_data['target.preflight']={'checks':checks,'target_digest':self.target_digest}
                dep=self.deploy()
                self.assertEqual('FAILED_NO_MUTATION',self.finish(dep))
                self.assertEqual(0,self.journal.load(self.scope,dep)['mutated'])
                # New fixture for next distinct request/ticket.
                self.setUp()

    def test_health_and_smoke_failure_restore_config_image_traffic(self):
        for action in ('health.verify','smoke.verify'):
            with self.subTest(action=action):
                self.host.fail={action}
                dep=self.deploy()
                self.assertEqual('ROLLED_BACK',self.finish(dep))
                restored=[s for s in self.journal.steps(self.scope,dep) if s['request']['action']=='runtime.restore'][0]['result']['data']
                self.assertEqual(self.snapshot['config_digest'],restored['config_digest'])
                self.assertEqual(self.snapshot['images'],restored['images'])
                self.assertEqual(self.snapshot['traffic_digest'],restored['traffic_digest'])
                self.setUp()

    def test_failed_rollback_keeps_resource_lock(self):
        self.host.fail={'health.verify','rollback.verify'}
        dep=self.deploy()
        self.assertEqual('FAILED_NEEDS_HUMAN',self.finish(dep))
        self.assertEqual(1,self.journal.load(self.scope,dep)['active'])

    def test_crash_after_submit_reopens_journal_without_resubmit(self):
        dep=self.deploy(); self.host.crash_after_submit=True
        self.assertEqual('REQUESTED',self.workflow.tick(self.principal,dep))
        self.assertEqual(1,self.host.submit_count)
        self.service.journal=self.journal=Journal(self.path)
        self.workflow=DeploymentWorkflow(self.service,self.host,self.evidence,lambda:self.authority.now)
        self.assertEqual('POLICY_CHECKED',self.workflow.tick(self.principal,dep))
        self.assertEqual(1,self.host.submit_count)
        self.assertEqual('SUCCEEDED',self.finish(dep))

    def test_crash_recovery_at_every_dispatched_state(self):
        for state in ('REQUESTED','POLICY_CHECKED','PREFLIGHT','LEASED','ARTIFACT_RESOLVED',
                      'DEPLOYING','RUNTIME_HEALTH','SMOKE_VERIFY','TRAFFIC_PROMOTION'):
            with self.subTest(state=state):
                dep=self.deploy(); self.advance(dep,state)
                count=self.host.submit_count; self.host.crash_after_submit=True
                self.assertEqual(state,self.workflow.tick(self.principal,dep))
                self.assertEqual(count+1,self.host.submit_count)
                self.assertNotEqual(state,self.workflow.tick(self.principal,dep))
                self.assertEqual(count+1,self.host.submit_count)
                self.assertEqual('SUCCEEDED',self.finish(dep))
                self.setUp()

    def test_unknown_remote_mutation_is_not_retried_or_rolled_back(self):
        dep=self.deploy(); self.advance(dep,'DEPLOYING'); self.host.unknown=True
        count=self.host.submit_count
        for _ in range(4): self.workflow.tick(self.principal,dep)
        self.assertEqual(count+1,self.host.submit_count)
        self.assertEqual('DEPLOYING',self.journal.load(self.scope,dep)['state'])
        self.assertEqual(1,self.journal.load(self.scope,dep)['active'])

    def test_evidence_commit_crash_reuses_same_content(self):
        dep=self.deploy(); self.advance(dep,'EVIDENCE_COMMIT'); self.evidence.crash=True
        with self.assertRaises(RuntimeError): self.workflow.tick(self.principal,dep)
        self.assertEqual('EVIDENCE_COMMIT',self.journal.load(self.scope,dep)['state'])
        self.assertEqual('SUCCEEDED',self.workflow.tick(self.principal,dep))
        self.assertEqual(1,len(self.evidence.objects))

    def test_revoke_after_mutation_rolls_back(self):
        dep=self.deploy(); self.advance(dep,'RUNTIME_HEALTH')
        self.service.revoke_ticket(self.principal,self.ticket)
        self.assertEqual('ROLLED_BACK',self.finish(dep))

    def test_environment_mutex_and_account_quota(self):
        self.deploy()
        ticket=self.service.issue_ticket(self.principal,self.plan.plan_digest,1500)
        self.service.approve_ticket(self.approver,ticket)
        with self.assertRaisesRegex(Denied,'busy'):
            self.service.deploy(self.principal,ticket,self.plan.plan_digest,'request-2')
        other=replace(self.scope,environment_id='prod-b')
        with self.assertRaisesRegex(Denied,'account_quota'):
            self.journal.admit(other,'dep-other','new','ticket-other',{},[],1)

    def test_secret_values_never_accepted_as_references(self):
        with self.assertRaises(Denied):
            self.service.prepare_config(self.principal,self.schema,{'DATABASE':'super-secret-value'},self.secrets)
        compose=DockerHostRuntime.compose((self.artifact,),self.config,self.secrets,self.scope.key)
        self.assertNotIn(b'super-secret-value',compose)
        self.assertNotIn(self.secrets[0].encode(),compose)
        for bad in ['sha256:bad','$(curl evil)','sha256:'+'a'*64+';id']:
            with self.assertRaises(Denied): CloudAssistantExecutor.command(bad,digest(b'op'),'apply')

    def test_mutable_tags_and_production_database_profiles_denied(self):
        with self.assertRaises(Denied): replace(self.artifact,repository='repo.test/app:latest')
        with self.assertRaises(Denied): replace(self.artifact,profile='postgres')
        with self.assertRaises(Denied): replace(self.artifact,image_digest='latest')

    def test_destructive_and_unknown_migrations_denied(self):
        for risk in (MigrationRisk.DESTRUCTIVE,MigrationRisk.CONDITIONAL,MigrationRisk.UNKNOWN):
            with self.assertRaises(Denied): self.service.preview(self.principal,replace(self.plan,migration_risk=risk))
        for tool in MigrationController.TOOLS:
            self.assertEqual('DESTRUCTIVE',MigrationController.classify(tool,[{'kind':'drop_column','source_digest':digest(b'sql')}]))
            self.assertEqual('UNKNOWN',MigrationController.classify(tool,[{'kind':'raw_sql','source_digest':digest(b'sql')}]))

    def test_health_delayed_start_and_deadline(self):
        now=[0]; count=[0]
        def probe(case,timeout):
            count[0]+=1
            return 'PASS' if count[0]>=3 else 'FAIL'
        verifier=HealthVerifier(probe,lambda:now[0],lambda seconds:now.__setitem__(0,now[0]+seconds))
        self.assertEqual({'http':'PASS'},verifier.verify(['http']))
        self.assertEqual(3,count[0])
        now[0]=0
        verifier=HealthVerifier(lambda case,timeout:'UNKNOWN',lambda:now[0],lambda seconds:now.__setitem__(0,now[0]+seconds))
        self.assertEqual({'tcp':'UNKNOWN'},verifier.verify(['tcp'],deadline_seconds=2))
        self.assertLessEqual(now[0],2)

    def test_wrong_target_batch_and_unverified_snapshot_rejected(self):
        with self.assertRaises(Denied): self.service.preview(self.principal,replace(self.plan,batches=(('i-b',),)))
        with self.assertRaises(Denied): self.service.preview(self.principal,replace(self.plan,previous_snapshot=digest(b'fake')))


if __name__ == '__main__': unittest.main()
