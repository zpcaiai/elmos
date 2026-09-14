"""One durable reconciliation tick, suitable for Temporal activities or host workers.

No cloud operation is retried from an exception. Reconciliation is the only
path from DISPATCHING/ACCEPTED to completion. An unknown mutation retains locks.
"""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
import json
import time
from .contracts import (Denied, Pending, Principal, TERMINAL, FORWARD, digest, require, sha)
from .service import ReleaseDeploymentService, verified
from .ports import ExecutionHost, EvidenceHost

CHECKS = frozenset({'ticket', 'scope', 'release', 'policy', 'instance_running', 'ownership',
                    'cloud_assistant', 'deployment_user', 'runtime_version', 'architecture',
                    'disk', 'memory', 'ports', 'registry', 'config', 'secrets', 'ingress',
                    'migration', 'rollback', 'network', 'tls', 'icp', 'external_stateful_services'})
HEALTH = frozenset({'instance', 'runtime', 'container', 'tcp', 'http'})
ACTION = {
    'REQUESTED': ('policy.evaluate', False),
    'POLICY_CHECKED': ('target.preflight', False),
    'PREFLIGHT': ('identity.lease_ready', False),
    'LEASED': ('artifact.resolve', False),
    'ARTIFACT_RESOLVED': ('migration.preflight', False),
    'MIGRATION_PREFLIGHT': ('migration.apply', True),
    'DEPLOYING': ('runtime.activate', True),
    'RUNTIME_HEALTH': ('health.verify', False),
    'SMOKE_VERIFY': ('smoke.verify', False),
    'TRAFFIC_PROMOTION': ('traffic.promote', True),
    'FAILED': ('rollback.plan', False),
    'ROLLBACK_PLANNED': ('runtime.restore', True),
    'ROLLING_BACK': ('rollback.verify', False),
}


class DeploymentWorkflow:
    def __init__(self, service: ReleaseDeploymentService, execution: ExecutionHost,
                 evidence: EvidenceHost, clock=time.time):
        self.service, self.journal = service, service.journal
        self.execution, self.evidence, self.clock = execution, evidence, clock

    def _receipt(self, envelope, request, invocation):
        body = verified(self.service.trust, 'operation_receipt', envelope)
        require(set(body) == {'request_digest', 'invocation_id', 'status', 'data', 'evidence_digest',
                              'stdout_hash', 'stderr_hash', 'artifact_uri',
                              'session_identity', 'started_at', 'finished_at', 'exit_code'}, 'receipt_fields')
        require(body['request_digest'] == digest(request) and body['invocation_id'] == invocation, 'receipt_binding')
        require(body['status'] in {'PASS', 'FAIL', 'UNKNOWN'}, 'receipt_status')
        require(type(body['exit_code']) is int and (body['status'] != 'PASS' or body['exit_code'] == 0), 'receipt_exit_code')
        require(type(body['started_at']) is int and type(body['finished_at']) is int and
                body['started_at'] <= body['finished_at'] <= self.clock(), 'receipt_time')
        sha(body['evidence_digest'])
        sha(body['stdout_hash']); sha(body['stderr_hash'])
        require(body['artifact_uri']=='cas:'+body['evidence_digest'],'raw_evidence_reference_mismatch')
        require(type(body['session_identity']) is str and 0 < len(body['session_identity']) <= 200, 'session_identity')
        require(type(body['data']) is dict, 'receipt_data')
        # Store only exact typed assessment results, never stdout/stderr/secret values.
        self._data_shape(request['action'], body['data'])
        return {**body, 'signature': envelope['signature']}

    @staticmethod
    def _data_shape(action, data):
        keys = {
            'policy.evaluate': {'decision', 'policy_digest'},
            'target.preflight': {'checks', 'target_digest'},
            'identity.lease_ready': {'ready'},
            'artifact.resolve': {'release_digest', 'images'},
            'migration.preflight': {'risk', 'migration_digest', 'authorized', 'backup_verified', 'rollback_compatible'},
            'migration.apply': {'migration_digest', 'rollback_compatible'},
            'runtime.activate': {'images', 'config_digest', 'snapshot_digest'},
            'health.verify': {'checks'},
            'smoke.verify': {'cases', 'policy_digest'},
            'traffic.promote': {'plan_digest'},
            'rollback.plan': {'snapshot_digest', 'rollback_compatible'},
            'runtime.restore': {'snapshot_digest', 'images', 'config_digest', 'traffic_digest'},
            'rollback.verify': {'checks', 'cases', 'snapshot_digest'},
        }
        require(action in keys and set(data) == keys[action], 'unexpected_receipt_data')
        for key, value in data.items():
            if key.endswith('_digest'):
                sha(value)
            elif key in {'checks', 'cases'}:
                require(type(value) is dict and 0 < len(value) <= 1000 and
                        all(type(k) is str and 0 < len(k) <= 100 and v in {'PASS', 'FAIL', 'UNKNOWN'}
                            for k, v in value.items()), 'invalid_probe_results')
            elif key in {'ready', 'authorized', 'backup_verified', 'rollback_compatible'}:
                require(type(value) is bool, 'invalid_receipt_boolean')
            elif key == 'images':
                require(type(value) is list and 0 < len(value) <= 16, 'invalid_image_receipt')
                for image in value:
                    require(type(image) is str and '@sha256:' in image and len(image) < 500, 'invalid_image_receipt')
                    sha('sha256:' + image.rsplit('@sha256:', 1)[1])
            elif key == 'risk':
                require(value in {'NONE', 'SAFE_EXPAND', 'CONDITIONAL', 'DESTRUCTIVE', 'UNKNOWN'}, 'invalid_risk')
            elif key == 'decision':
                require(value in {'ALLOW', 'DENY', 'UNKNOWN'}, 'invalid_decision')

    def _operation(self, principal, row, action, mutating, batch=None):
        plan = row['plan']
        target = self.journal.get(principal.scope, 'target', plan['target_digest'])['target']
        operation = row['state'] + ':' + action + (':' + str(batch) if batch is not None else '')
        resources = tuple(plan['batches'][batch]) if batch is not None else tuple(target['resources'])
        request = {'schema': 'rd.operation.v1', 'deployment_id': row['id'], 'scope': asdict(principal.scope),
                   'plan_digest': digest(plan), 'action': action, 'resources': list(resources),
                   'operation_key': digest([row['id'], operation, digest(plan)]),
                   'target_digest': plan['target_digest'], 'ticket_id': row['ticket'],
                   'generation': row['version'], 'deadline_seconds': 600}
        lease = self.service.authority.lease(principal, row['id'], digest(plan), resources, action, row['version'])
        lease.check(principal.scope, row['id'], digest(plan), resources, action, int(self.clock()), row['version'])
        step, fresh = self.journal.begin_step(principal.scope, row['id'], operation, request, int(self.clock()), mutating)
        if step['status'] == 'COMPLETE':
            receipt = json.loads(step['result'])
            verified(self.service.trust, 'operation_receipt', {
                'body': {k:v for k,v in receipt.items() if k != 'signature'}, 'signature': receipt['signature']})
        else:
            invocation = step['invocation']
            if invocation is None:
                # A crash after claim but before submit is deliberately uncertain.
                # Only the host's durable dispatch ledger may reconcile it.
                try:
                    invocation = (self.execution.submit(request, lease) if fresh
                                  else self.execution.recover(request, lease))
                except Exception:
                    raise Pending('provider_dispatch_requires_reconciliation') from None
                if invocation is None:
                    raise Pending('provider_dispatch_unknown')
                self.journal.accepted(principal.scope, row['id'], operation, invocation)
            try:
                envelope = self.execution.poll(invocation, request, lease)
            except Exception:
                raise Pending('provider_poll_requires_reconciliation') from None
            if envelope is None:
                raise Pending('provider_pending')
            receipt = self._receipt(envelope, request, invocation)
            if receipt['status'] == 'UNKNOWN':
                raise Pending('provider_result_unknown')
            self.journal.complete_step(principal.scope, row['id'], operation, receipt, int(self.clock()))
        require(receipt['status'] == 'PASS', 'operation_failed')
        self._assess(principal, row, action, receipt['data'])
        return receipt

    def _assess(self, principal, row, action, data):
        plan = row['plan']
        release = self.journal.get(principal.scope, 'release', plan['release_digest'], allow_revoked=action.startswith('rollback.') or action == 'runtime.restore')['manifest']
        health_policy = self.journal.get(principal.scope, 'health-policy', release['health_policy_digest'])
        images = [a['repository'] + '@' + a['image_digest'] for a in release['artifacts']]
        if action == 'policy.evaluate':
            require(data == {'decision': 'ALLOW', 'policy_digest': plan['policy_digest']}, 'policy_denied')
        elif action == 'target.preflight':
            require(data['target_digest'] == plan['target_digest'] and set(data['checks']) == CHECKS and
                    all(v == 'PASS' for v in data['checks'].values()), 'preflight_failed')
        elif action == 'identity.lease_ready':
            require(data['ready'], 'lease_not_ready')
        elif action == 'artifact.resolve':
            require(data['release_digest'] == plan['release_digest'] and data['images'] == images, 'artifact_mismatch')
        elif action == 'migration.preflight':
            require(data['risk'] == plan['migration_risk'] and data['migration_digest'] == release['migration_digest'], 'migration_mismatch')
            require(data['authorized'] and data['rollback_compatible'], 'migration_denied')
            if plan['migration_risk'] in {'CONDITIONAL', 'DESTRUCTIVE'}:
                require(data['backup_verified'] and plan['backup_evidence'] and plan['migration_authorization'], 'migration_backup_required')
        elif action == 'migration.apply':
            require(data['migration_digest'] == release['migration_digest'] and data['rollback_compatible'], 'migration_not_safe')
        elif action == 'runtime.activate':
            require(data['images'] == images and data['config_digest'] == plan['config_digest'], 'runtime_digest_mismatch')
            if plan['rollback_required']:
                require(data['snapshot_digest'] == plan['previous_snapshot'], 'previous_snapshot_mismatch')
        elif action == 'health.verify':
            require(set(data['checks']) == HEALTH and all(v == 'PASS' for v in data['checks'].values()), 'health_failed')
        elif action == 'smoke.verify':
            require(data['policy_digest'] == release['health_policy_digest'] and
                    set(data['cases']) == set(health_policy['smoke_cases']) and
                    all(v == 'PASS' for v in data['cases'].values()), 'smoke_failed')
        elif action == 'traffic.promote':
            require(data['plan_digest'] == digest(plan), 'traffic_plan_mismatch')
        elif action == 'rollback.plan':
            require(data['snapshot_digest'] == plan['previous_snapshot'] and data['rollback_compatible'], 'rollback_unsafe')
        elif action == 'runtime.restore':
            snapshot = self.journal.get(principal.scope, 'stable-snapshot', plan['previous_snapshot'])
            require(data['snapshot_digest'] == plan['previous_snapshot'] and
                    data['images'] == snapshot['images'] and data['config_digest'] == snapshot['config_digest'] and
                    data['traffic_digest'] == snapshot['traffic_digest'], 'rollback_restore_mismatch')
        elif action == 'rollback.verify':
            snapshot = self.journal.get(principal.scope, 'stable-snapshot', plan['previous_snapshot'])
            health_policy = self.journal.get(principal.scope, 'health-policy', snapshot['health_policy_digest'])
            require(data['snapshot_digest'] == plan['previous_snapshot'] and set(data['checks']) == HEALTH and
                    set(data['cases']) == set(health_policy['rollback_smoke_cases']) and
                    all(v == 'PASS' for v in [*data['checks'].values(), *data['cases'].values()]), 'rollback_verification_failed')

    def _finish(self, principal, row, final_state):
        steps = self.journal.steps(principal.scope, row['id'])
        require(all(s['status'] == 'COMPLETE' for s in steps) or final_state in {'FAILED_NEEDS_HUMAN', 'FAILED_NO_MUTATION'}, 'unreconciled_steps')
        release = self.journal.get(principal.scope, 'release', row['plan']['release_digest'], allow_revoked=True)['manifest']
        target = self.journal.get(principal.scope, 'target', row['plan']['target_digest'])['target']
        def iso(timestamp):
            return datetime.fromtimestamp(timestamp,timezone.utc).isoformat().replace('+00:00','Z')
        timeline=self.journal.timeline(principal.scope,row['id'])
        admitted_at=timeline[0]['at']
        evidence_steps=[]
        for step in steps:
            result=step['result']
            observed_status=result['status'] if result else 'UNKNOWN'
            normalized_status=observed_status if result else 'FAIL'
            if step['operation'].startswith(('tls.rotate:','iac.','gitops.')) and result:
                require(observed_status in {'PROVIDER_STATE_OBSERVED','IAC_STATE_RECONCILED','PROPOSED',
                                             'GITOPS_CONVERGED'},'invalid_extension_result')
                # PASS means the named operation completed. Keep its original receipt
                # and runtime/business-smoke limitations; do not invent process logs.
                normalized_status='PASS'
            evidence_steps.append({**step,'name':step['operation'],
                'status':normalized_status,
                'observed_status':observed_status,
                'started_at':iso(step['started']), 'finished_at':iso(step['finished'] or step['started']),
                **({key:result[key] for key in ('stdout_hash','stderr_hash','artifact_uri','exit_code') if key in result} if result else {}),
                **({'provider_invocation_id':step['invocation']} if step['invocation'] else {})})
        if not evidence_steps:
            evidence_steps=[{'name':'local_admission_validation','status':'FAIL','observed_status':'NO_MUTATION',
                             'started_at':iso(admitted_at),'finished_at':iso(admitted_at)}]
        bundle = {'schema': 'rd.evidence.v1', 'deployment_id': row['id'], 'ticket_id': row['ticket'],
                  'scope': asdict(principal.scope), 'release_id': release['release_id'], 'commit': release['commit'],
                  'plan_digest': digest(row['plan']), 'release_digest': row['plan']['release_digest'],
                  'certification_evidence_digest': release['evidence_digest'],
                  'target_digest': row['plan']['target_digest'],
                  'target_id': target['target_id'], 'target_resource_ids':target['resources'],
                  'artifact_digests': [a['image_digest'] for a in release['artifacts']],
                  'config_digest': row['plan']['config_digest'], 'final_state': final_state,
                  'steps': evidence_steps, 'timeline': timeline,
                  'started_at':iso(admitted_at),
                  'finished_at':iso(max((s['finished'] or s['started'] for s in steps),default=admitted_at)),
                  'certification': 'NOT_CERTIFIED'}
        # Host operation key and bundle bytes are stable across evidence-commit crashes.
        envelope = self.evidence.commit(principal.scope, row['id'] + ':evidence:v1', bundle)
        receipt = verified(self.service.trust, 'evidence_commit', envelope)
        require(receipt.get('scope') == asdict(principal.scope) and receipt.get('bundle_digest') == digest(bundle)
                and receipt.get('committed') is True, 'evidence_commit_not_verified')
        sha(receipt.get('receipt_digest'))
        return self.journal.commit_evidence(principal.scope, row['id'], row['state'], final_state,
                                           {**bundle, 'host_evidence_receipt': envelope})

    def tick(self, principal: Principal, deployment_id):
        principal.allow('deployment:work')
        row = self.journal.load(principal.scope, deployment_id)
        state = row['state']
        if state in TERMINAL:
            return state
        if state == 'EVIDENCE_COMMIT':
            self._finish(principal, row, 'SUCCEEDED')
            return 'SUCCEEDED'
        if state == 'ROLLBACK_VERIFY':
            self._finish(principal, row, 'ROLLED_BACK')
            return 'ROLLED_BACK'
        try:
            if state in FORWARD:
                self.service.validate_ticket(principal, row['ticket'], digest(row['plan']))
                release = self.journal.get(principal.scope, 'release', row['plan']['release_digest'])
                certification = verified(self.service.trust, 'certification', release['certification'])
                require(self.clock() < certification['expires_at'], 'certification_expired')
            action, mutating = ACTION[state]
            if state in {'DEPLOYING', 'RUNTIME_HEALTH', 'SMOKE_VERIFY', 'TRAFFIC_PROMOTION'}:
                for batch in range(len(row['plan']['batches'])):
                    self._operation(principal, row, action, mutating, batch)
                    if state == 'DEPLOYING' and len(row['plan']['batches']) > 1:
                        # Hold the next batch until this exact batch is healthy.
                        self._operation(principal, row, 'health.verify', False, batch)
                        self._operation(principal, row, 'smoke.verify', False, batch)
            elif state == 'MIGRATION_PREFLIGHT' and row['plan']['migration_risk'] == 'NONE':
                pass
            else:
                self._operation(principal, row, action, mutating)
            after = dict(zip(FORWARD, FORWARD[1:])).get(state) or {
                'FAILED': 'ROLLBACK_PLANNED', 'ROLLBACK_PLANNED': 'ROLLING_BACK', 'ROLLING_BACK': 'ROLLBACK_VERIFY'}[state]
            self.journal.transition(principal.scope, deployment_id, state, after, int(self.clock()))
            return after
        except Pending:
            return state
        except Denied as error:
            current = self.journal.load(principal.scope, deployment_id)
            if current['state'] != state:
                return current['state']
            # Do not compensate an in-flight unknown mutation. Preserve all locks.
            unknown = any(s['status'] != 'COMPLETE' for s in self.journal.steps(principal.scope, deployment_id))
            if current['mutated'] and (unknown or state not in FORWARD):
                self._finish(principal, current, 'FAILED_NEEDS_HUMAN')
                return 'FAILED_NEEDS_HUMAN'
            if current['mutated']:
                self.journal.transition(principal.scope, deployment_id, state, 'FAILED', int(self.clock()), str(error))
                return 'FAILED'
            # Failed reads may be incomplete; no mutation has occurred.
            self._finish(principal, current, 'FAILED_NO_MUTATION')
            return 'FAILED_NO_MUTATION'
