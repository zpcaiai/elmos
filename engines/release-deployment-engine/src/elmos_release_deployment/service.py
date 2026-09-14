from __future__ import annotations
from dataclasses import asdict
import time
import uuid
from .contracts import (Principal, Scope, ReleaseManifest, DeploymentTarget, DeploymentPlan,
                        MigrationRisk, canonical, digest, identifier, require, sha)
from .journal import Journal
from .ports import TrustVerifier, AuthorizationHost


def verified(trust: TrustVerifier, purpose: str, envelope: dict) -> dict:
    require(type(envelope) is dict and set(envelope) == {'body', 'signature'}, 'signed_envelope_required')
    body = envelope['body']
    require(type(body) is dict and type(envelope['signature']) is str, 'invalid_envelope')
    require(trust.verify(purpose, body, envelope['signature']) is True, 'untrusted_' + purpose)
    return body


class ReleaseDeploymentService:
    def __init__(self, journal: Journal, trust: TrustVerifier, authority: AuthorizationHost,
                 clock=time.time, account_quota=3):
        self.journal, self.trust, self.authority = journal, trust, authority
        self.clock, self.account_quota = clock, account_quota

    def create_release(self, principal: Principal, release: ReleaseManifest, certification: dict):
        principal.allow('release:create')
        require(principal.scope == release.scope, 'scope_mismatch')
        body = verified(self.trust, 'certification', certification)
        require(body.get('scope') == asdict(principal.scope) and body.get('release_digest') == release.manifest_digest,
                'certification_binding')
        require(body.get('evidence_digest') == release.evidence_digest and body.get('decision') == 'DEPLOY_ALLOWED',
                'certification_denied')
        require(body.get('executor') != body.get('verifier') and body.get('executor') and body.get('verifier'),
                'independent_verifier_required')
        require(type(body.get('expires_at')) is int and self.clock() < body['expires_at'], 'certification_expired')
        self.journal.get(principal.scope, 'health-policy', release.health_policy_digest)
        self.journal.put(principal.scope, 'release', release.manifest_digest,
                         {'manifest': asdict(release), 'certification': certification})
        self.journal.put(principal.scope, 'release-id', release.release_id, {'digest': release.manifest_digest})
        return release.manifest_digest

    def register_health_policy(self, principal, policy):
        principal.allow('plan:create')
        require(set(policy) == {'smoke_cases', 'rollback_smoke_cases', 'deadline_seconds', 'attempts'}, 'health_policy_fields')
        for key in ('smoke_cases', 'rollback_smoke_cases'):
            require(type(policy[key]) is list and 0 < len(policy[key]) <= 1000 and
                    len(set(policy[key])) == len(policy[key]), 'smoke_case_bounds')
            for case in policy[key]: identifier(case)
        require(type(policy['deadline_seconds']) is int and 1 <= policy['deadline_seconds'] <= 600 and
                type(policy['attempts']) is int and 1 <= policy['attempts'] <= 20, 'health_policy_budget')
        key = digest(policy)
        self.journal.put(principal.scope, 'health-policy', key, policy)
        return key

    def release(self, principal, release_id):
        principal.allow('release:read')
        key = self.journal.get(principal.scope, 'release-id', release_id)['digest']
        return self.journal.get(principal.scope, 'release', key)

    def revoke_release(self, principal, release_id):
        principal.allow('release:revoke')
        key = self.journal.get(principal.scope, 'release-id', release_id)['digest']
        self.journal.revoke(principal.scope, 'release', key)

    def register_target(self, principal, target: DeploymentTarget, discovery):
        principal.allow('target:register')
        require(target.scope == principal.scope, 'scope_mismatch')
        key = digest(asdict(target))
        body = verified(self.trust, 'target_discovery', discovery)
        require(body.get('scope') == asdict(target.scope) and body.get('target_digest') == key, 'target_binding')
        require(body.get('account_id') == target.cloud_account_id and body.get('region') == target.region
                and body.get('resources') == list(target.resources), 'target_ownership')
        require(type(body.get('expires_at')) is int and self.clock() < body['expires_at'], 'discovery_expired')
        require(type(body.get('production')) is bool, 'trusted_environment_classification_required')
        self.journal.put(principal.scope, 'target', key, {'target': asdict(target), 'discovery': discovery})
        self.journal.put(principal.scope, 'target-id', target.target_id, {'digest': key})
        return key

    def prepare_config(self, principal, schema: dict, config: dict, secret_refs: tuple[str, ...]):
        principal.allow('plan:create')
        # Narrow typed config contract, never arbitrary JSON Schema evaluation/code.
        require(set(schema) == {'fields'} and type(schema['fields']) is dict, 'unsupported_config_schema')
        require(set(config) == set(schema['fields']), 'config_fields_mismatch')
        types = {'string': str, 'integer': int, 'boolean': bool}
        for name, field in schema['fields'].items():
            identifier(name)
            require(type(field) is dict and set(field) == {'type', 'secret'}, 'unsupported_config_field')
            require(type(field['secret']) is bool and field['type'] in types, 'unsupported_config_type')
            if field['secret']:
                require(type(config[name]) is str and config[name] in secret_refs, 'secret_reference_required')
            else:
                require(type(config[name]) is types[field['type']], 'config_type_mismatch')
        value = {'schema_digest': digest(schema), 'values': config, 'secret_refs': list(secret_refs)}
        key = digest(value)
        self.journal.put(principal.scope, 'config', key, value)
        return key

    def preview(self, principal: Principal, plan: DeploymentPlan):
        principal.allow('plan:create')
        require(plan.scope == principal.scope, 'scope_mismatch')
        release = self.journal.get(principal.scope, 'release', plan.release_digest)['manifest']
        target_record = self.journal.get(principal.scope, 'target', plan.target_digest)
        target = target_record['target']
        discovery = verified(self.trust, 'target_discovery', target_record['discovery'])
        require(plan.production == discovery['production'], 'environment_classification_mismatch')
        config = self.journal.get(principal.scope, 'config', plan.config_digest)
        require(config['schema_digest'] == release['config_schema_digest'], 'config_schema_mismatch')
        require(config['secret_refs'] == list(plan.secret_refs), 'secret_refs_mismatch')
        resources = [r for batch in plan.batches for r in batch]
        require(len(set(resources)) == len(resources) and set(resources) == set(target['resources']), 'batch_resource_mismatch')
        if plan.strategy in {'single_replace', 'compose_replace'}:
            require(len(resources) == 1, 'single_host_required')
        if plan.strategy == 'single_replace':
            require(len(release['artifacts']) == 1, 'single_service_required')
        require(plan.migration_risk != MigrationRisk.UNKNOWN, 'unknown_migration_semantics')
        if plan.migration_risk in {MigrationRisk.CONDITIONAL, MigrationRisk.DESTRUCTIVE}:
            require(plan.migration_authorization is not None and plan.backup_evidence is not None,
                    'dedicated_migration_authorization_and_backup_required')
        if plan.rollback_required:
            require(plan.previous_snapshot is not None, 'previous_stable_snapshot_required')
            snapshot = self.journal.get(principal.scope, 'stable-snapshot', plan.previous_snapshot)
            require(snapshot['target_digest'] == plan.target_digest, 'rollback_target_mismatch')
        if plan.production:
            require(plan.rollback_required, 'production_requires_rollback')
        body = asdict(plan)
        self.journal.put(principal.scope, 'plan', plan.plan_digest, body)
        return {'plan_digest': plan.plan_digest, 'plan': body,
                'risks': [plan.migration_risk.value], 'status': 'DRAFT_REQUIRES_HOST_POLICY'}

    def register_stable_snapshot(self, principal, envelope):
        principal.allow('snapshot:register')
        body = verified(self.trust, 'stable_snapshot', envelope)
        require(set(body) == {'scope', 'target_digest', 'images', 'config_digest', 'traffic_digest', 'health_policy_digest',
                              'verification_digest', 'state'}, 'snapshot_fields')
        require(body['scope'] == asdict(principal.scope) and body['state'] == 'VERIFIED_STABLE', 'snapshot_scope_or_state')
        for key in ('target_digest', 'config_digest', 'traffic_digest', 'verification_digest', 'health_policy_digest'):
            sha(body[key])
        self.journal.get(principal.scope, 'health-policy', body['health_policy_digest'])
        require(type(body['images']) is list and 0 < len(body['images']) <= 16, 'snapshot_images')
        for image in body['images']:
            require(type(image) is str and '@sha256:' in image, 'snapshot_image_not_pinned')
            sha('sha256:' + image.rsplit('@sha256:', 1)[1])
        key = digest(body)
        self.journal.put(principal.scope, 'stable-snapshot', key, body)
        return key

    def issue_ticket(self, principal, plan_digest, expires_at):
        principal.allow('ticket:issue')
        plan = self.journal.get(principal.scope, 'plan', plan_digest)
        now = int(self.clock())
        require(type(expires_at) is int and now < expires_at <= now + 3600, 'ticket_expiry_bounds')
        body = {'ticket_id': 'dt_' + uuid.uuid4().hex, 'scope': asdict(principal.scope),
                'plan_digest': plan_digest, 'actor_id': principal.actor_id,
                'issued_at': now, 'expires_at': expires_at, 'status': 'ISSUED',
                'production': plan['production']}
        envelope = self.authority.authorize(principal, 'ticket:issue', body)
        require(verified(self.trust, 'ticket', envelope) == body, 'ticket_host_mismatch')
        self.journal.put(principal.scope, 'ticket', body['ticket_id'], envelope)
        return body['ticket_id']

    def approve_ticket(self, principal, ticket_id):
        principal.allow('ticket:approve')
        envelope = self.journal.get(principal.scope, 'ticket', ticket_id)
        body = verified(self.trust, 'ticket', envelope)
        require(body['scope'] == asdict(principal.scope) and self.clock() < body['expires_at'], 'ticket_expired_or_wrong_scope')
        require(not body['production'] or body['actor_id'] != principal.actor_id, 'separate_production_approver_required')
        approved = {**body, 'status': 'APPROVED', 'approved_by': principal.actor_id}
        approval = self.authority.authorize(principal, 'ticket:approve', approved)
        require(verified(self.trust, 'ticket', approval) == approved, 'ticket_host_mismatch')
        self.journal.put(principal.scope, 'approval', ticket_id, approval)
        return approval

    def revoke_ticket(self, principal, ticket_id):
        principal.allow('ticket:revoke')
        self.journal.revoke(principal.scope, 'ticket', ticket_id)

    def validate_ticket(self, principal, ticket_id, plan_digest):
        original = verified(self.trust, 'ticket', self.journal.get(principal.scope, 'ticket', ticket_id))
        body = verified(self.trust, 'ticket', self.journal.get(principal.scope, 'approval', ticket_id))
        require(body['scope'] == asdict(principal.scope) and body['ticket_id'] == ticket_id and
                body['plan_digest'] == plan_digest and body['status'] == 'APPROVED', 'ticket_binding')
        require(all(body[k] == v for k, v in original.items() if k != 'status'), 'approval_binding')
        require(self.clock() < body['expires_at'] and body['issued_at'] <= self.clock(), 'ticket_expired')
        return body

    def deploy(self, principal, ticket_id, plan_digest, idempotency_key):
        principal.allow('deployment:apply')
        identifier(idempotency_key)
        self.validate_ticket(principal, ticket_id, plan_digest)
        plan = self.journal.get(principal.scope, 'plan', plan_digest)
        self.journal.get(principal.scope, 'release', plan['release_digest'])
        target = self.journal.get(principal.scope, 'target', plan['target_digest'])['target']
        # Lock physical provider resources as well as logical environments.
        resources = [digest([target['provider'], target['cloud_account_id'], target['region'], r])
                     for r in target['resources']]
        return self.journal.admit(principal.scope, 'dep_' + uuid.uuid4().hex, idempotency_key,
                                  ticket_id, plan, resources, self.account_quota, int(self.clock()))

    def rollback(self, principal, original_id, ticket_id, idempotency_key):
        principal.allow('deployment:rollback')
        original = self.journal.load(principal.scope, original_id)
        require(original['state'] == 'SUCCEEDED' and original['evidence'], 'verified_deployment_required')
        require(original['plan']['previous_snapshot'] is not None, 'previous_snapshot_required')
        # Separate freshly approved ticket and deployment journal: never rewrite
        # the succeeded deployment or reuse its consumed ticket/evidence.
        require(ticket_id != original['ticket'], 'new_rollback_ticket_required')
        deployment = self.deploy(principal,ticket_id,digest(original['plan']),idempotency_key)
        current = self.journal.load(principal.scope,deployment)
        if current['state'] == 'REQUESTED':
            self.journal.transition(principal.scope,deployment,'REQUESTED','FAILED',int(self.clock()),'operator_requested_rollback')
        return deployment
