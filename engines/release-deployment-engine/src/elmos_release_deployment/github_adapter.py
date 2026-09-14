"""Exact GitHub Git Data/PR adapter. Never merges, force-pushes or deletes.

The host broker must enforce the canonical SCM write policy and claim every
dispatch in its tool-call ledger. Reconciliation here is read-only: a partially
published or unknown request cannot manufacture permission for another write.
"""
import base64
from dataclasses import asdict, dataclass
import http.client
import re
import ssl
import time
from urllib.parse import quote, urlencode, urlsplit

from .contracts import Scope, Pending, canonical, digest, require
from .host_bridge import strict_json


def commit_id(value):
    require(type(value) is str and re.fullmatch(r'[0-9a-f]{40}', value), 'github_commit_id')
    return value


@dataclass(frozen=True)
class GitHubRepositoryBinding:
    scope: Scope
    repository_id: str
    native_id: int
    owner: str
    name: str
    base_branch: str
    directory: str
    application_id: str

    def __post_init__(self):
        require(type(self.native_id) is int and self.native_id > 0, 'github_native_id')
        for value in (self.owner, self.name):
            require(type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value), 'github_repository_name')
        for value in (self.base_branch, self.directory):
            require(type(value) is str and len(value) <= 200
                    and re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', value), 'github_bound_path')


class GitHubHttpsTransport:
    def __init__(self, endpoint, ca_file, provider_id, broker, clock=time.time):
        uri = urlsplit(endpoint)
        require(uri.scheme == 'https' and uri.hostname and not uri.username and not uri.password
                and not uri.query and not uri.fragment and uri.path in ('', '/', '/api/v3'), 'github_endpoint')
        self.host, self.port, self.prefix = uri.hostname, uri.port or 443, uri.path.rstrip('/')
        self.context = ssl.create_default_context(cafile=str(ca_file))
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.provider_id, self.broker, self.clock = provider_id, broker, clock

    def call(self, binding, method, route, body, query, lease):
        require(method in {'GET', 'POST'} and (route == '' or route.startswith('/')) and not any(
            x in route for x in ('..', '?', '#', '\\')), 'github_route')
        require(method != 'GET' or route == '' or re.fullmatch(
            r'/(?:branches/[A-Za-z0-9_%/-]+|git/(?:commits|trees)/[0-9a-f]{40}|pulls(?:/[1-9][0-9]*(?:/files)?)?|contents/[A-Za-z0-9_%/.-]+)',
            route), 'github_read_route')
        require(method != 'POST' or route in {'/git/trees', '/git/commits', '/git/refs', '/pulls'},
                'github_write_route')
        require(method != 'POST' or 'gitops.proposal' in lease.actions, 'github_write_permission')
        lease.check(binding.scope, lease.deployment_id, lease.plan_digest,
                    (binding.repository_id, binding.application_id),
                    'gitops.proposal' if 'gitops.proposal' in lease.actions else 'gitops.reconcile',
                    self.clock(), lease.generation)
        request = {'provider_id': self.provider_id, 'binding': asdict(binding), 'method': method,
                   'route': route, 'body': body, 'query': query}
        session = self.broker.authorize_call(lease, request)
        require(type(session) is dict and set(session) == {
            'token', 'expires_at', 'session_identity', 'provider_id', 'repository_native_id'}, 'github_session_fields')
        require(session['provider_id'] == self.provider_id and session['repository_native_id'] == binding.native_id
                and session['session_identity'] == lease.session_identity
                and type(session['expires_at']) is int and self.clock() < session['expires_at']
                and type(session['token']) is str and re.fullmatch(r'[!-~]{1,16384}', session['token']),
                'github_session_binding')
        raw_body = canonical(body) if body is not None else None
        require(raw_body is None or len(raw_body) <= 1048576, 'github_request_bounds')
        path = self.prefix + '/repos/' + binding.owner + '/' + binding.name + route
        if query:
            path += '?' + urlencode(query)
        connection = http.client.HTTPSConnection(self.host, self.port, context=self.context, timeout=15)
        started = time.monotonic()
        try:
            connection.request(method, path, raw_body, {
                'Authorization': 'Bearer ' + session['token'], 'Accept': 'application/vnd.github+json',
                'Content-Type': 'application/json', 'Accept-Encoding': 'identity',
                'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'elmos-release-deployment'})
            response = connection.getresponse()
            require(response.status in ({200} if method == 'GET' else {201}), 'github_http_rejected')
            require(response.getheader('Content-Encoding', 'identity') == 'identity', 'github_encoding')
            raw = bytearray()
            while True:
                remaining = 15 - (time.monotonic() - started)
                if remaining <= 0: raise TimeoutError()
                if connection.sock: connection.sock.settimeout(remaining)
                chunk = response.read1(min(65536, 2097153-len(raw)))
                if not chunk: break
                raw.extend(chunk)
                require(len(raw) <= 2097152, 'github_response_bounds')
            result = strict_json(bytes(raw))
            require(type(result) in (dict, list), 'github_response_contract')
            self.broker.record_response(lease, digest(request), digest(bytes(raw)), response.getheader('X-GitHub-Request-Id'))
            return result
        except (OSError, http.client.HTTPException):
            raise Pending('github_outcome_unknown') from None
        finally:
            connection.close()


class GitHubProposalAdapter:
    def __init__(self, bindings, transport, receipt_signer, clock=time.time):
        bindings = tuple(bindings)
        self.bindings = {(b.scope.key, b.repository_id): b for b in bindings}
        require(len(self.bindings) == len(bindings), 'github_duplicate_binding')
        self.transport, self.signer, self.clock = transport, receipt_signer, clock

    def _binding(self, request, lease):
        plan = request['plan']
        binding = self.bindings.get((lease.scope.key, plan['repository_id']))
        require(binding is not None and plan['scope'] == asdict(binding.scope), 'github_scope')
        require(plan['branch'] == binding.base_branch and plan['directory'] == binding.directory
                and plan['application_id'] == binding.application_id, 'github_target_binding')
        commit_id(plan['base_commit'])
        lease.check(binding.scope, lease.deployment_id, lease.plan_digest,
                    (binding.repository_id, binding.application_id), 'gitops.'+plan['mode'],
                    self.clock(), lease.generation)
        files = request['files']
        require(type(files) is dict and 0 < len(files) <= 100 and len(canonical(files)) <= 524288, 'github_files_bounds')
        for path in files:
            require(re.fullmatch(re.escape(binding.directory)+r'/[a-z0-9-]{1,63}\.json', path), 'github_path_grant')
        return binding

    @staticmethod
    def _head(request):
        # Canonical SCM policy already permits the elmos/migration/ namespace.
        # Proposal and reconcile modes identify the same publication.
        identity = {**request['plan'], 'mode': 'proposal'}
        return 'elmos/migration/deployment/' + digest(identity)[7:]

    def _call(self, binding, lease, method, route, body=None, query=None):
        return self.transport.call(binding, method, route, body, query or {}, lease)

    def propose(self, request, lease):
        b = self._binding(request, lease)
        # Reconcile mode never creates another proposal or branch.
        if request['plan']['mode'] == 'reconcile':
            found = self.reconcile(request, lease)
            if found is None: raise Pending('github_proposal_not_found')
            return found
        base = request['plan']['base_commit']
        repository = self._call(b, lease, 'GET', '')
        require(repository.get('id') == b.native_id and not repository.get('archived')
                and not repository.get('disabled'), 'github_repository_identity')
        branch = self._call(b, lease, 'GET', '/branches/'+quote(b.base_branch, safe=''))
        require(branch.get('protected') is True and branch.get('commit', {}).get('sha') == base,
                'github_base_not_protected_or_changed')
        commit = self._call(b, lease, 'GET', '/git/commits/'+base)
        require(commit.get('sha') == base, 'github_base_commit')
        tree = self._call(b, lease, 'POST', '/git/trees', {
            'base_tree': commit_id(commit['tree']['sha']), 'tree': [
                {'path': path, 'mode': '100644', 'type': 'blob', 'content': canonical(value).decode()}
                for path, value in sorted(request['files'].items())]})
        head = self._call(b, lease, 'POST', '/git/commits', {
            'message': 'ELMOS deployment proposal '+digest(request['files']),
            'tree': commit_id(tree.get('sha')), 'parents': [base]})
        head_sha = commit_id(head.get('sha'))
        ref = self._call(b, lease, 'POST', '/git/refs', {'ref': 'refs/heads/'+self._head(request), 'sha': head_sha})
        require(ref.get('ref') == 'refs/heads/'+self._head(request)
                and ref.get('object', {}).get('sha') == head_sha, 'github_ref_binding')
        result = self._call(b, lease, 'POST', '/pulls', {
            'title': 'ELMOS deployment proposal', 'head': self._head(request), 'base': b.base_branch,
            'body': 'Deployment manifests: '+digest(request['files'])+'. Requires normal review and approval.',
            'maintainer_can_modify': False})
        require(type(result.get('number')) is int and result['number'] > 0, 'github_proposal_number')
        return str(result['number'])

    def reconcile(self, request, lease):
        b = self._binding(request, lease)
        proposals = self._call(b, lease, 'GET', '/pulls', query={
            'state': 'all', 'head': b.owner+':'+self._head(request), 'base': b.base_branch, 'per_page': 2})
        require(type(proposals) is list and len(proposals) <= 1, 'github_ambiguous_proposals')
        if not proposals: return None
        require(type(proposals[0].get('number')) is int and proposals[0]['number'] > 0, 'github_proposal_number')
        return str(proposals[0]['number'])

    def poll(self, invocation, request, lease):
        b = self._binding(request, lease)
        require(type(invocation) is str and re.fullmatch(r'[1-9][0-9]{0,15}', invocation), 'github_invocation')
        pr = self._call(b, lease, 'GET', '/pulls/'+invocation)
        require(str(pr.get('number')) == invocation and pr.get('head', {}).get('ref') == self._head(request)
                and pr.get('base', {}).get('ref') == b.base_branch
                and all(pr.get(side, {}).get('repo', {}).get('id') == b.native_id for side in ('head', 'base')),
                'github_proposal_identity')
        head = commit_id(pr['head'].get('sha'))
        commit = self._call(b, lease, 'GET', '/git/commits/'+head)
        require(commit.get('sha') == head and [p.get('sha') for p in commit.get('parents', [])]
                == [request['plan']['base_commit']], 'github_proposal_parent')
        changes = self._call(b, lease, 'GET', '/pulls/'+invocation+'/files', query={'per_page': 100})
        require(type(changes) is list and pr.get('changed_files') == len(changes)
                and len(changes) == len(request['files'])
                and {c.get('filename') for c in changes} == set(request['files'])
                and all(c.get('status') in ('added', 'modified') for c in changes), 'github_changed_paths')
        require(type(pr.get('merged')) is bool, 'github_merge_state')
        if not pr['merged']:
            require(pr.get('state') == 'open', 'github_proposal_closed')
        revision = commit_id(pr.get('merge_commit_sha')) if pr['merged'] else head
        revision_commit = self._call(b, lease, 'GET', '/git/commits/'+revision)
        require(revision_commit.get('sha') == revision, 'github_revision_binding')
        tree = self._call(b, lease, 'GET', '/git/trees/'+commit_id(revision_commit['tree']['sha']),
                          query={'recursive': '1'})
        require(tree.get('truncated') is False and type(tree.get('tree')) is list
                and len(tree['tree']) <= 10000, 'github_tree_incomplete')
        selected = [item for item in tree['tree'] if item.get('path', '').startswith(b.directory+'/')]
        require(len(selected) == len(request['files']) and {item.get('path') for item in selected}
                == set(request['files']) and all(item.get('mode') == '100644' and item.get('type') == 'blob'
                                                 for item in selected), 'github_tree_path_or_mode')
        blob_ids = {item['path']: commit_id(item.get('sha')) for item in selected}
        for path, expected in request['files'].items():
            content = self._call(b, lease, 'GET', '/contents/'+quote(path, safe='/'), query={'ref': revision})
            require(content.get('type') == 'file' and content.get('path') == path
                    and content.get('encoding') == 'base64' and content.get('sha') == blob_ids[path], 'github_file_kind')
            try:
                raw = base64.b64decode(content['content'].replace('\n', ''), validate=True)
            except (KeyError, TypeError, ValueError):
                require(False, 'github_file_encoding')
            require(raw == canonical(expected), 'github_file_content_drift')
        return self.signer.seal('gitops_scm_receipt', {
            'request_digest': digest(request), 'invocation_id': invocation, 'repository_id': b.repository_id,
            'base_commit': request['plan']['base_commit'], 'commit': revision,
            'files_digest': digest(request['files']), 'proposal_id': invocation, 'merged': pr['merged']})
