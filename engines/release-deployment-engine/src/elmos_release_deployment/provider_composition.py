"""Operator-owned composition for GitHub proposals and Argo CD observation.

No credential, signer, policy or journal defaults. The caller supplies canonical
host brokers; request JSON cannot instantiate a provider or select an endpoint.
"""
from dataclasses import dataclass

from .contracts import require
from .argocd_adapter import ArgoCdAdapter, ArgoCdHttpsTransport
from .github_adapter import GitHubProposalAdapter, GitHubHttpsTransport
from .gitops_controller import GitOpsController
from .flux_adapter import FluxAdapter, FluxHttpsTransport


@dataclass(frozen=True)
class ProviderEndpoint:
    url: str
    ca_file: str
    provider_id: str


class GitOpsProviderHost:
    def __init__(self, journal, trust, signer, github_endpoint, argocd_endpoint,
                 repository_bindings, application_bindings, scm_broker, cluster_broker, clock,
                 gitops_backend='argocd'):
        repos, apps = tuple(repository_bindings), tuple(application_bindings)
        require(bool(repos) and bool(apps), 'gitops_provider_bindings_required')
        repo_keys = {(b.scope.key, b.repository_id, b.application_id) for b in repos}
        app_keys = {(b.scope.key, b.repository_id, b.application_id) for b in apps}
        require(repo_keys == app_keys and len(repo_keys) == len(repos) == len(apps),
                'gitops_provider_binding_mismatch')
        self.scm = GitHubProposalAdapter(repos, GitHubHttpsTransport(
            github_endpoint.url, github_endpoint.ca_file, github_endpoint.provider_id, scm_broker, clock),
            signer, clock)
        require(gitops_backend in {'argocd','flux'}, 'gitops_backend')
        if gitops_backend == 'argocd':
            self.gitops = ArgoCdAdapter(apps, ArgoCdHttpsTransport(
                argocd_endpoint.url, argocd_endpoint.ca_file, argocd_endpoint.provider_id, cluster_broker, clock),
                signer, clock)
        else:
            self.gitops = ScopedFluxObservers({(b.scope.key,b.application_id):FluxAdapter([b],FluxHttpsTransport(
                argocd_endpoint.url,argocd_endpoint.ca_file,argocd_endpoint.provider_id,b.namespace,cluster_broker,clock),
                signer,clock) for b in apps})
        self.controllers = {b.scope.key: GitOpsController(journal, self.scm, self.gitops, trust, b.scope, clock)
                            for b in repos}

    def publish(self, plan, manifests, approval, lease):
        controller = self.controllers.get(lease.scope.key)
        require(controller is not None, 'gitops_host_scope_not_configured')
        return controller.publish(plan, manifests, approval, lease)


class ScopedFluxObservers:
    def __init__(self, observers): self.observers = dict(observers)

    def observe(self, application_id, lease):
        observer = self.observers.get((lease.scope.key,application_id))
        require(observer is not None, 'flux_host_scope_not_configured')
        return observer.observe(application_id,lease)
