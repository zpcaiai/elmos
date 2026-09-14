"""Exact provider adapters. SDK clients and credential material stay host-owned.

No adapter reads environment credentials or enables network access on import.
Alibaba request methods below are bound to reviewed OpenAPI action/version pairs.
"""
from __future__ import annotations
from dataclasses import asdict
import base64
import json
import re
from typing import Protocol
from .contracts import (Artifact, CapabilityLease, DeploymentTarget, Denied,
                        canonical, digest, identifier, require, sha)


class AlibabaTransport(Protocol):
    def call(self, service: str, version: str, action: str, parameters: dict,
             lease: CapabilityLease) -> dict:
        """Canonical host SDK adapter: STS, network policy, timeout, audit and dispatch ledger."""
        ...


class AlibabaEcsAdapter:
    def __init__(self, transport: AlibabaTransport, clock):
        self.transport, self.clock = transport, clock

    def discover(self, target: DeploymentTarget, lease: CapabilityLease):
        lease.check(target.scope, lease.deployment_id, lease.plan_digest, target.resources,
                    'target.discover', self.clock(), lease.generation)
        response = self.transport.call('ecs', '2014-05-26', 'DescribeInstances', {
            'RegionId': target.region, 'InstanceIds': json.dumps(target.resources),
            'ResourceGroupId': target.resource_group, 'MaxResults': 100}, lease)
        instances = response.get('Instances', {}).get('Instance', [])
        require(response.get('NextToken') in {None, ''}, 'discovery_incomplete')
        require(len(instances) == len(target.resources) and
                {i.get('InstanceId') for i in instances} == set(target.resources), 'target_resource_mismatch')
        facts = []
        for instance in instances:
            tags = {t['TagKey']: t['TagValue'] for t in instance.get('Tags', {}).get('Tag', [])}
            require(instance.get('RegionId') == target.region and
                    instance.get('ResourceGroupId') == target.resource_group and
                    all(tags.get(k) == v for k, v in target.tags), 'target_region_group_tag_mismatch')
            require(instance.get('Status') == 'Running', 'instance_not_running')
            facts.append({'instance_id': instance['InstanceId'], 'status': instance['Status'],
                          'vpc_id': instance.get('VpcAttributes', {}).get('VpcId'),
                          'vswitch_id': instance.get('VpcAttributes', {}).get('VSwitchId'),
                          'security_groups': instance.get('SecurityGroupIds', {}).get('SecurityGroupId', []),
                          'os': instance.get('OSType'), 'cpu': instance.get('Cpu'), 'memory': instance.get('Memory')})
        assistant = self.transport.call('ecs', '2014-05-26', 'DescribeCloudAssistantStatus', {
            'RegionId': target.region, **{'InstanceId.'+str(n+1): r for n, r in enumerate(target.resources)}}, lease)
        statuses = assistant.get('InstanceCloudAssistantStatusSet', {}).get('InstanceCloudAssistantStatus', [])
        require({s.get('InstanceId') for s in statuses} == set(target.resources) and
                all(s.get('CloudAssistantStatus') == 'true' for s in statuses), 'cloud_assistant_not_ready')
        return {'target_digest': digest(asdict(target)), 'instances': facts, 'assistant_ready': True}


class AlibabaStsCredentialBroker:
    ACTIONS = {'remote.submit': ('ecs:RunCommand',), 'remote.poll': ('ecs:DescribeInvocationResults',),
               'remote.cancel': ('ecs:StopInvocation',)}

    @classmethod
    def session_policy(cls, target, action):
        require(action in cls.ACTIONS, 'unsupported_sts_action')
        # No wildcard action, account, region or instance set. If an API cannot
        # enforce this resource scope, the host must deny rather than widen it.
        return {'Version': '1', 'Statement': [{'Effect': 'Allow', 'Action': list(cls.ACTIONS[action]),
                 'Resource': [f'acs:ecs:{target.region}:{target.cloud_account_id}:instance/{r}' for r in target.resources]}]}

    def __init__(self, transport, clock):
        self.transport, self.clock = transport, clock

    def acquire(self, target, role_arn, lease, action, duration=900):
        require(re.fullmatch(r'acs:ram::[0-9]{1,32}:role/[a-zA-Z0-9_-]+', role_arn) is not None, 'invalid_role')
        require(role_arn.split(':')[3] == target.cloud_account_id, 'role_account_mismatch')
        require(type(duration) is int and 900 <= duration <= 3600, 'sts_duration_bounds')
        lease.check(target.scope, lease.deployment_id, lease.plan_digest, target.resources,
                    action, self.clock(), lease.generation)
        # The trusted transport retains credentials and returns only a session
        # handle, never the raw AssumeRole response to application callers.
        response = self.transport.call('sts', '2015-04-01', 'AssumeRole', {
            'RoleArn': role_arn, 'RoleSessionName': lease.lease_id,
            'DurationSeconds': duration, 'Policy': canonical(self.session_policy(target, action)).decode()}, lease)
        require(set(response) == {'session_ref', 'expires_at', 'account_id'} and
                response['account_id'] == target.cloud_account_id and
                self.clock() < response['expires_at'] <= self.clock()+duration, 'invalid_sts_session_handle')
        return response


class CloudAssistantExecutor:
    def __init__(self, transport, clock):
        self.transport, self.clock = transport, clock

    @staticmethod
    def command(bundle_digest, operation_key, action):
        sha(bundle_digest)
        sha(operation_key)
        require(action in {'apply', 'restore', 'verify', 'preflight', 'cleanup'}, 'unsupported_remote_action')
        # Host agent must verify signed bundle + ticket + lease before Docker.
        # No image tags, credentials, paths or repository-supplied shell here.
        return (f'exec /usr/local/bin/elmos-deployment-agent {action} '
                f'--bundle {bundle_digest} --operation {operation_key}')

    def submit(self, target, lease, bundle_digest, operation_key, action):
        lease.check(target.scope, lease.deployment_id, lease.plan_digest, target.resources,
                    'remote.submit', self.clock(), lease.generation)
        require(len(target.resources) == 1, 'one_remote_invocation_per_instance')
        text = self.command(bundle_digest, operation_key, action)
        result = self.transport.call('ecs', '2014-05-26', 'RunCommand', {
            'RegionId': target.region, 'InstanceId.1': target.resources[0], 'Type': 'RunShellScript',
            'CommandContent': base64.b64encode(text.encode()).decode(), 'ContentEncoding': 'Base64',
            'Name': 'elmos-rd-v1', 'Username': 'elmos-deploy', 'Timeout': 600,
            'ResourceGroupId': target.resource_group,
            'ClientToken': operation_key.removeprefix('sha256:'), 'KeepCommand': False}, lease)
        require(type(result.get('InvokeId')) is str and type(result.get('RequestId')) is str, 'missing_provider_id')
        return {'invocation_id': result['InvokeId'], 'request_id': result['RequestId']}

    def poll(self, target, lease, invocation_id):
        identifier(invocation_id)
        lease.check(target.scope, lease.deployment_id, lease.plan_digest, target.resources,
                    'remote.poll', self.clock(), lease.generation)
        response = self.transport.call('ecs', '2014-05-26', 'DescribeInvocationResults', {
            'RegionId': target.region, 'InvokeId': invocation_id, 'InstanceId': target.resources[0],
            'ResourceGroupId': target.resource_group, 'ContentEncoding': 'Base64'}, lease)
        results = response.get('Invocation', {}).get('InvocationResults', {}).get('InvocationResult', [])
        require(response.get('Invocation', {}).get('NextToken') in {None, ''}, 'invocation_result_incomplete')
        require(len(results) <= 1, 'ambiguous_invocation_result')
        if not results:
            return None
        row = results[0]
        require(row.get('InstanceId') == target.resources[0] and row.get('InvokeId') == invocation_id, 'remote_result_binding')
        status = row.get('InvocationStatus')
        if status in {'Pending', 'Scheduled', 'Running', 'Stopping'}:
            return None
        require(status in {'Success', 'Failed', 'Stopped', 'Timeout', 'Error', 'Invalid', 'Aborted', 'Cancelled', 'Terminated'}, 'remote_result_unknown')
        # Arbitrary stdout is not safe evidence. Keep it in the host redaction
        # boundary; application sees only outcome and IDs, never raw log text.
        return {'invocation_id': invocation_id, 'status': status, 'exit_code': row.get('ExitCode')}

    def cancel(self, target, lease, invocation_id):
        identifier(invocation_id)
        lease.check(target.scope, lease.deployment_id, lease.plan_digest, target.resources,
                    'remote.cancel', self.clock(), lease.generation)
        return self.transport.call('ecs', '2014-05-26', 'StopInvocation', {
            'RegionId': target.region, 'InvokeId': invocation_id, 'InstanceId.1': target.resources[0]}, lease)


class AcrArtifactRegistry:
    def __init__(self, manifest_fetcher):
        self.fetch = manifest_fetcher

    def resolve(self, artifact: Artifact, target_arch: str):
        # Fetcher is host-scoped OCI Distribution v2 GET by digest; credentials
        # never cross this interface. Hash the returned bytes, not a tag/header.
        raw = self.fetch(artifact.repository, artifact.image_digest)
        require(type(raw) is bytes and len(raw) <= 8_000_000 and digest(raw) == artifact.image_digest, 'registry_digest_mismatch')
        manifest = json.loads(raw)
        require(manifest.get('schemaVersion') == 2, 'unsupported_oci_schema')
        require(manifest.get('mediaType') in {'application/vnd.oci.image.manifest.v1+json',
                    'application/vnd.docker.distribution.manifest.v2+json'}, 'single_platform_manifest_required')
        config = manifest.get('config', {})
        sha(config.get('digest'))
        require(type(config.get('size')) is int and 0 < config['size'] <= 4_000_000, 'invalid_oci_config_size')
        config_raw = self.fetch(artifact.repository, config['digest'])
        require(type(config_raw) is bytes and len(config_raw) == config['size'] and digest(config_raw) == config['digest'], 'oci_config_integrity')
        require(json.loads(config_raw).get('architecture') == target_arch and json.loads(config_raw).get('os') == 'linux', 'oci_platform_mismatch')
        require(type(manifest.get('layers')) is list and len(manifest['layers']) <= 128, 'oci_layer_bounds')
        for layer in manifest['layers']:
            sha(layer.get('digest'))
            require(type(layer.get('size')) is int and layer['size'] >= 0, 'invalid_layer_size')
        return artifact.image


class DockerHostRuntime:
    @staticmethod
    def compose(artifacts: tuple[Artifact, ...], config_digest: str, secret_refs: tuple[str, ...], scope_key: str):
        sha(config_digest)
        sha(scope_key)
        require(1 <= len(artifacts) <= 16 and len({a.name for a in artifacts}) == len(artifacts), 'invalid_services')
        services = {}
        secrets = {}
        for ref in secret_refs:
            require(re.fullmatch(r'secret-ref:[A-Za-z0-9_.:/-]{1,200}', ref) is not None, 'secret_reference_required')
            key = digest([scope_key,ref]).removeprefix('sha256:')
            secrets['s_'+key] = {'file': '/run/elmos/secrets/'+key}
        for a in artifacts:
            services[a.name] = {'image': a.image, 'pull_policy': 'always', 'read_only': True,
                'user': '10001:10001', 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
                'tmpfs': ['/tmp:rw,noexec,nosuid,size=64m'], 'restart': 'unless-stopped',
                'pids_limit': 256, 'mem_limit': '512m', 'cpus': '1.0',
                'ports': [f'127.0.0.1:{a.port}:{a.port}'],
                'volumes': [{'type': 'bind', 'source': '/var/lib/elmos/config/'+config_digest[7:],
                             'target': '/run/elmos/config', 'read_only': True}],
                'secrets': list(secrets), 'labels': {'io.elmos.config-digest': config_digest}}
        require(len({a.port for a in artifacts}) == len(artifacts), 'host_port_collision')
        return canonical({'services': services, 'secrets': secrets})

    @staticmethod
    def argv(manifest_digest, project_id, action):
        sha(manifest_digest)
        require(re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', project_id) is not None, 'invalid_compose_project')
        require(action in {'apply', 'inspect', 'cleanup'}, 'unsupported_docker_action')
        suffix = {'apply': ['up', '--detach', '--wait', '--wait-timeout', '120', '--remove-orphans'],
                  'inspect': ['ps', '--format', 'json'], 'cleanup': ['down', '--remove-orphans']}[action]
        return ['docker', 'compose', '--project-name', project_id, '--file',
                '/var/lib/elmos/bundles/'+manifest_digest[7:]+'.json', *suffix]


class MigrationController:
    TOOLS = {'flyway', 'liquibase', 'alembic', 'django', 'efcore'}
    RISK = {'create_table': 'SAFE_EXPAND', 'add_nullable_column': 'SAFE_EXPAND',
            'create_index_online': 'CONDITIONAL', 'backfill': 'CONDITIONAL',
            'add_constraint': 'CONDITIONAL', 'drop_table': 'DESTRUCTIVE',
            'drop_column': 'DESTRUCTIVE', 'rename_column': 'DESTRUCTIVE',
            'narrow_type': 'DESTRUCTIVE', 'rewrite_data': 'DESTRUCTIVE'}

    @classmethod
    def classify(cls, tool, operations):
        require(tool in cls.TOOLS and type(operations) is list and len(operations) <= 10000, 'unsupported_migration_tool')
        levels = ['NONE', 'SAFE_EXPAND', 'CONDITIONAL', 'DESTRUCTIVE', 'UNKNOWN']
        result = 'NONE'
        for operation in operations:
            require(type(operation) is dict and set(operation) == {'kind', 'source_digest'}, 'typed_migration_ir_required')
            sha(operation['source_digest'])
            risk = cls.RISK.get(operation['kind'], 'UNKNOWN')
            result = levels[max(levels.index(result), levels.index(risk))]
        return result


class HealthVerifier:
    def __init__(self, probe, clock, sleep):
        self.probe, self.clock, self.sleep = probe, clock, sleep

    def verify(self, cases, *, deadline_seconds=120, attempts=6, initial_backoff=1):
        require(0 < len(cases) <= 1000 and type(attempts) is int and 1 <= attempts <= 20 and
                0 < deadline_seconds <= 600 and 0 < initial_backoff <= 30, 'probe_budget')
        require(len(set(cases)) == len(cases), 'duplicate_probe_case')
        deadline = self.clock()+deadline_seconds
        results = {case: 'UNKNOWN' for case in cases}
        for attempt in range(attempts):
            for case in cases:
                remaining = deadline-self.clock()
                if remaining <= 0:
                    return results
                try:
                    outcome = self.probe(case, timeout=remaining)
                except Exception:
                    outcome = 'UNKNOWN'
                results[case] = outcome if outcome in {'PASS', 'FAIL', 'UNKNOWN'} else 'UNKNOWN'
                if self.clock() > deadline:
                    results[case] = 'UNKNOWN'
            if all(v == 'PASS' for v in results.values()) or attempt == attempts-1:
                break
            pause = min(initial_backoff*2**attempt, 30, max(0, deadline-self.clock()))
            if pause:
                self.sleep(pause)
        return results


class SmokeVerifier(HealthVerifier):
    """Smoke case identities and probe implementation are host allowlisted."""
