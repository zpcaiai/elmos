from __future__ import annotations
from dataclasses import asdict, dataclass
from enum import StrEnum
import hashlib
import json
import re


class Denied(ValueError):
    """Safe, stable error codes only; never include provider payloads or secrets."""


class Pending(RuntimeError):
    """No retry until the persisted operation is reconciled."""


def require(ok: bool, code: str):
    if not ok:
        raise Denied(code)


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value) -> str:
    raw = value if isinstance(value, bytes) else canonical(value)
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def sha(value: str):
    require(isinstance(value, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', value) is not None, 'invalid_digest')


def identifier(value: str):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value) is not None, 'invalid_id')


@dataclass(frozen=True)
class Scope:
    tenant_id: str
    workspace_id: str
    project_id: str
    environment_id: str
    account_id: str

    def __post_init__(self):
        for value in asdict(self).values():
            identifier(value)

    @property
    def key(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class Principal:
    """Construct only in the host authentication adapter, never from request JSON."""
    actor_id: str
    scope: Scope
    permissions: frozenset[str]

    def allow(self, permission):
        identifier(self.actor_id)
        require(permission in self.permissions, 'permission_denied')


class MigrationRisk(StrEnum):
    NONE = 'NONE'
    SAFE_EXPAND = 'SAFE_EXPAND'
    CONDITIONAL = 'CONDITIONAL'
    DESTRUCTIVE = 'DESTRUCTIVE'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True)
class Artifact:
    name: str
    repository: str
    image_digest: str
    sbom_digest: str
    provenance_digest: str
    scan_digest: str
    profile: str
    port: int

    def __post_init__(self):
        require(re.fullmatch(r'[a-z][a-z0-9-]{0,47}', self.name) is not None, 'invalid_service_name')
        require(re.fullmatch(r'[a-z0-9.-]+(?::[0-9]{1,5})?/[a-z0-9][a-z0-9/._-]*', self.repository) is not None,
                'repository_must_not_contain_tag_or_credentials')
        require('..' not in self.repository and '//' not in self.repository, 'invalid_repository')
        for value in (self.image_digest, self.sbom_digest, self.provenance_digest, self.scan_digest):
            sha(value)
        require(self.profile in {'spring', 'vue', 'python', 'dotnet'}, 'unsupported_profile')
        require(type(self.port) is int and 1024 <= self.port <= 65535, 'invalid_nonroot_port')

    @property
    def image(self):
        return self.repository + '@' + self.image_digest


@dataclass(frozen=True)
class ReleaseManifest:
    release_id: str
    scope: Scope
    commit: str
    artifacts: tuple[Artifact, ...]
    evidence_digest: str
    config_schema_digest: str
    migration_digest: str
    health_policy_digest: str
    compatibility_digest: str

    def __post_init__(self):
        identifier(self.release_id)
        require(re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', self.commit) is not None, 'exact_commit_required')
        require(type(self.artifacts) is tuple and 1 <= len(self.artifacts) <= 16, 'artifact_bounds')
        require(len({a.name for a in self.artifacts}) == len(self.artifacts), 'duplicate_service')
        for value in (self.evidence_digest, self.config_schema_digest, self.migration_digest,
                      self.health_policy_digest, self.compatibility_digest):
            sha(value)

    @property
    def manifest_digest(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class DeploymentTarget:
    target_id: str
    scope: Scope
    provider: str
    region: str
    resource_group: str
    resources: tuple[str, ...]
    tags: tuple[tuple[str, str], ...]
    architecture: str
    runtime_version: str
    cloud_account_id: str
    exposure: str = 'private'

    def __post_init__(self):
        for value in (self.target_id, self.region, self.resource_group, self.runtime_version):
            identifier(value)
        require(self.provider in {'alibaba_ecs', 'kubernetes', 'host'}, 'unsupported_provider')
        identifier(self.cloud_account_id)
        if self.provider == 'alibaba_ecs':
            require(re.fullmatch(r'[0-9]{1,32}',self.cloud_account_id) is not None,'invalid_cloud_account_id')
        require(type(self.resources) is tuple and 1 <= len(self.resources) <= 100, 'resource_bounds')
        require(len(set(self.resources)) == len(self.resources), 'duplicate_resource')
        for resource in self.resources:
            identifier(resource)
        require(type(self.tags) is tuple and all(type(t) is tuple and len(t) == 2 for t in self.tags), 'invalid_tags')
        require(len(dict(self.tags)) == len(self.tags), 'duplicate_tag')
        require(self.architecture in {'amd64', 'arm64'}, 'unsupported_architecture')
        require(self.exposure in {'private', 'public'}, 'invalid_exposure')


@dataclass(frozen=True)
class DeploymentPlan:
    scope: Scope
    release_digest: str
    target_digest: str
    config_digest: str
    secret_refs: tuple[str, ...]
    strategy: str
    migration_risk: MigrationRisk
    migration_authorization: str | None
    backup_evidence: str | None
    previous_snapshot: str | None
    rollback_required: bool
    production: bool
    policy_digest: str
    batches: tuple[tuple[str, ...], ...]

    def __post_init__(self):
        for value in (self.release_digest, self.target_digest, self.config_digest, self.policy_digest):
            sha(value)
        require(type(self.secret_refs) is tuple and len(set(self.secret_refs)) == len(self.secret_refs), 'invalid_secret_refs')
        for ref in self.secret_refs:
            require(re.fullmatch(r'secret-ref:[A-Za-z0-9_.:/-]{1,200}', ref) is not None, 'secret_reference_required')
        require(self.strategy in {'single_replace', 'compose_replace', 'rolling', 'canary', 'blue_green', 'kubernetes', 'helm'}, 'unsupported_strategy')
        require(isinstance(self.migration_risk, MigrationRisk), 'typed_migration_risk_required')
        require(type(self.production) is bool and type(self.rollback_required) is bool, 'invalid_boolean')
        require(type(self.batches) is tuple and all(type(b) is tuple and b for b in self.batches), 'invalid_batches')
        require(1 <= len(self.batches) <= 100, 'batch_bounds')
        for optional in (self.migration_authorization, self.backup_evidence, self.previous_snapshot):
            if optional is not None:
                sha(optional)

    @property
    def plan_digest(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class CapabilityLease:
    lease_id: str
    scope: Scope
    deployment_id: str
    plan_digest: str
    resources: tuple[str, ...]
    actions: frozenset[str]
    generation: int
    expires_at: int
    session_identity: str

    def check(self, scope, deployment_id, plan_digest, resources, action, now, generation):
        require(self.scope == scope and self.deployment_id == deployment_id and self.plan_digest == plan_digest,
                'lease_binding_mismatch')
        require(type(self.expires_at) is int and now < self.expires_at, 'lease_expired')
        require(type(self.generation) is int and self.generation == generation, 'stale_lease')
        require(set(resources) <= set(self.resources) and action in self.actions, 'lease_overreach')


FORWARD = ('REQUESTED', 'POLICY_CHECKED', 'PREFLIGHT', 'LEASED', 'ARTIFACT_RESOLVED',
           'MIGRATION_PREFLIGHT', 'DEPLOYING', 'RUNTIME_HEALTH', 'SMOKE_VERIFY',
           'TRAFFIC_PROMOTION', 'EVIDENCE_COMMIT', 'SUCCEEDED')
ROLLBACK = ('FAILED', 'ROLLBACK_PLANNED', 'ROLLING_BACK', 'ROLLBACK_VERIFY', 'ROLLED_BACK')
TERMINAL = frozenset({'SUCCEEDED', 'ROLLED_BACK', 'REJECTED', 'FAILED_NO_MUTATION', 'FAILED_NEEDS_HUMAN'})


def allowed_transition(before, after):
    regular = dict(zip(FORWARD, FORWARD[1:])) | dict(zip(ROLLBACK, ROLLBACK[1:]))
    return (regular.get(before) == after or
            (before not in TERMINAL and after in {'FAILED', 'FAILED_NO_MUTATION', 'FAILED_NEEDS_HUMAN', 'REJECTED'}))
