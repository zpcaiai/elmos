"""Mountable P0 HTTP application. Authentication is injected by the ELMOS host.

No default authentication, web server, credential discovery or background worker.
The authenticator must verify the host principal; forwarding identity headers
or using JSON scope fields as Principal is explicitly outside this contract.
"""
from __future__ import annotations
from dataclasses import asdict
import json
import re
from .contracts import (Artifact, ReleaseManifest, DeploymentTarget, DeploymentPlan,
                        MigrationRisk, Denied, Pending, Principal, canonical, require)


def fields(body, expected):
    require(type(body) is dict and set(body) == set(expected), 'request_fields')


class DeploymentAPI:
    def __init__(self, service, authenticator, discovery=None, extensions=None):
        self.service, self.authenticator, self.discovery = service, authenticator, discovery
        self.extensions = extensions

    def dispatch(self, principal, method, path, body):
        require(isinstance(principal, Principal), 'authentication_required')
        service, scope = self.service, principal.scope
        extension = re.fullmatch(r'/v1/deployments/([A-Za-z0-9_.:-]{1,128})/extensions/([a-z-]{1,32})',path)
        if method == 'POST' and extension:
            require(self.extensions is not None,'extension_host_not_configured')
            return self.extensions.execute(principal,*extension.groups(),body)
        if (method,path) == ('POST','/v1/deployment-health-policies'):
            return {'health_policy_digest':service.register_health_policy(principal,body)}
        if (method,path) == ('POST','/v1/releases/from-certification'):
            fields(body, {'manifest','certification'})
            fields(body['manifest'], {'release_id','commit','artifacts','evidence_digest','config_schema_digest',
                                     'migration_digest','health_policy_digest','compatibility_digest'})
            manifest = dict(body['manifest'])
            manifest['artifacts'] = tuple(Artifact(**a) for a in manifest['artifacts'])
            release = ReleaseManifest(scope=scope, **manifest)
            return {'release_digest':service.create_release(principal,release,body['certification'])}
        if (method,path) == ('POST','/v1/deployment-targets/alibaba/ecs/discover'):
            principal.allow('target:discover')
            require(self.discovery is not None, 'discovery_host_not_configured')
            fields(body, {'target_id'})
            # Trusted host owns account/role/resource lookup, never browser SDKs.
            return self.discovery(principal,body['target_id'])
        if (method,path) == ('POST','/v1/deployment-targets'):
            fields(body, {'target','discovery'})
            fields(body['target'], {'target_id','provider','region','resource_group','resources','tags',
                                    'architecture','runtime_version','cloud_account_id','exposure'})
            target = dict(body['target'])
            target['resources'] = tuple(target['resources'])
            target['tags'] = tuple(tuple(pair) for pair in target['tags'])
            return {'target_digest':service.register_target(principal,DeploymentTarget(scope=scope,**target),body['discovery'])}
        if (method,path) == ('POST','/v1/deployment-configs'):
            fields(body, {'schema','config','secret_refs'})
            return {'config_digest':service.prepare_config(principal,body['schema'],body['config'],tuple(body['secret_refs']))}
        if (method,path) == ('POST','/v1/deployment-plans/preview'):
            fields(body, {'release_digest','target_digest','config_digest','secret_refs','strategy','migration_risk',
                          'migration_authorization','backup_evidence','previous_snapshot','rollback_required',
                          'production','policy_digest','batches'})
            plan = {**body, 'secret_refs':tuple(body['secret_refs']),
                    'batches':tuple(tuple(b) for b in body['batches']), 'migration_risk':MigrationRisk(body['migration_risk'])}
            return service.preview(principal,DeploymentPlan(scope=scope,**plan))
        if (method,path) == ('POST','/v1/deployment-tickets'):
            fields(body, {'plan_digest','expires_at'})
            return {'ticket_id':service.issue_ticket(principal,body['plan_digest'],body['expires_at'])}
        if (method,path) == ('POST','/v1/deployments'):
            fields(body, {'ticket_id','plan_digest','idempotency_key'})
            return {'deployment_id':service.deploy(principal,**body)}
        match = re.fullmatch(r'/v1/(releases|deployment-targets|deployment-tickets|deployments)/([A-Za-z0-9_.:-]{1,128})(?:/(revoke|approve|capabilities|timeline|evidence|rollback))?',path)
        require(match is not None, 'route_not_found')
        kind, key, action = match.groups()
        if kind == 'releases' and method == 'GET' and action is None:
            return service.release(principal,key)
        if kind == 'releases' and method == 'POST' and action == 'revoke':
            fields(body, {})
            service.revoke_release(principal,key)
            return {'status':'REVOKED'}
        if kind == 'deployment-targets' and method == 'GET' and action == 'capabilities':
            principal.allow('target:read')
            reference = service.journal.get(scope,'target-id',key)
            return service.journal.get(scope,'target',reference['digest'])
        if kind == 'deployment-tickets' and method == 'POST' and action in {'approve','revoke'}:
            fields(body, {})
            if action == 'approve':
                return service.approve_ticket(principal,key)
            service.revoke_ticket(principal,key)
            return {'status':'REVOKED'}
        if kind == 'deployments' and method == 'GET' and action in {None,'timeline','evidence'}:
            principal.allow('deployment:read')
            if action == 'timeline': return {'events':service.journal.timeline(scope,key)}
            if action == 'evidence': return service.journal.evidence(scope,key)
            row = service.journal.load(scope,key)
            return {k:row[k] for k in ('id','state','version','plan','evidence')}
        if kind == 'deployments' and method == 'POST' and action == 'rollback':
            fields(body, {'ticket_id','idempotency_key'})
            return {'deployment_id':service.rollback(principal,key,body['ticket_id'],body['idempotency_key'])}
        raise Denied('route_not_found')

    def __call__(self, environ, start_response):
        try:
            principal = self.authenticator(environ)
            require(isinstance(principal,Principal), 'authentication_required')
            if environ['REQUEST_METHOD'] == 'POST':
                require(environ.get('CONTENT_TYPE','').split(';')[0].strip()=='application/json', 'json_content_type_required')
            length = int(environ.get('CONTENT_LENGTH') or '0')
            require(0 <= length <= 65536, 'request_too_large')
            raw = environ['wsgi.input'].read(length) if length else b'{}'
            require(len(raw) == length or length == 0, 'truncated_request')
            def strict_pairs(pairs):
                obj = {}
                for key,value in pairs:
                    require(key not in obj,'duplicate_json_key')
                    obj[key] = value
                return obj
            def reject_constant(value): raise Denied('nonfinite_json')
            body = json.loads(raw,object_pairs_hook=strict_pairs,parse_constant=reject_constant)
            response = self.dispatch(principal,environ['REQUEST_METHOD'],environ['PATH_INFO'],body)
            status = '200 OK'
        except Pending:
            response, status = {'status':'PENDING','reconciliation_required':True}, '202 Accepted'
        except Denied as error:
            response, status = {'error':str(error)}, '403 Forbidden'
        except (ValueError,TypeError,KeyError,AttributeError):
            response, status = {'error':'invalid_request'}, '400 Bad Request'
        except Exception:
            response, status = {'error':'host_operation_unavailable'}, '503 Service Unavailable'
        encoded = canonical(response)
        start_response(status,[('Content-Type','application/json'),('Cache-Control','no-store'),
                               ('X-Content-Type-Options','nosniff'),('Content-Length',str(len(encoded)))])
        return [encoded]
