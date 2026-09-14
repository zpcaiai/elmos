"""Native Runner lifecycle over the canonical host dispatch and evidence services.

The host supplies a scope-bound isolated worker, current authorization/attestation,
canonical tool ledger and immutable evidence repository. None are synthesized from
browser requests. Unknown dispatches are read/reconciled, never re-executed here.
"""
from dataclasses import asdict
from copy import copy
from .contracts import Pending, digest, require, sha
from .service import verified


class NativeRunnerHost:
    def __init__(self, workers, authority, ledger, evidence, trust, signer, clock):
        self.workers,self.authority,self.ledger,self.evidence = workers,authority,ledger,evidence
        self.trust,self.signer,self.clock = trust,signer,clock

    def _worker(self, request, lease, kind):
        require(request.get('scope') == asdict(lease.scope), 'native_host_scope')
        sha(request.get('runtime_digest'))
        require(self.clock() < lease.expires_at, 'lease_expired')
        action = 'helm.render' if kind == 'helm' else 'iac.'+request['mode']
        require(action in lease.actions, 'native_host_action')
        # Recheck current revocation, workspace ownership, provider credentials,
        # image/toolchain digests and sandbox policy before every native action.
        self.authority.require(request,lease,action)
        worker = self.workers.resolve(lease.scope,request,kind)
        from .native_worker import NativeTerraformWorker, NativeHelmWorker, PinnedNativeProcess
        if isinstance(worker,(NativeTerraformWorker,NativeHelmWorker)):
            require(isinstance(worker.process,PinnedNativeProcess), 'native_supervised_process_required')
            # Per-invocation copies prevent concurrent leases replacing each
            # other's authorization callback on a registered worker instance.
            worker = copy(worker)
            worker.process = copy(worker.process)
            prior_guard = worker.process.guard
            def guard():
                require(self.clock() < lease.expires_at, 'lease_expired')
                self.authority.require(request,lease,action)
                if prior_guard is not None: prior_guard()
            worker.process.guard = guard
        return worker

    def admit(self, request, lease):
        worker = self._worker(request,lease,'terraform')
        admission = verified(self.trust,'native_sandbox_attestation',self.authority.attest(request,lease))
        require(admission == {'scope':asdict(lease.scope),'request_digest':digest(request),
            'runtime_digest':request['runtime_digest'],'generation':lease.generation,
            'isolated':True,'providers_pinned':True,'expires_at':admission.get('expires_at')}, 'native_sandbox_binding')
        require(type(admission['expires_at']) is int and self.clock() < admission['expires_at'], 'native_sandbox_expired')
        observed = worker.inspect(request)
        lease.check(lease.scope,lease.deployment_id,lease.plan_digest,observed['plan_resources'],
                    'iac.'+request['mode'],self.clock(),lease.generation)
        return self.signer.seal('iac_sandbox_admission',{'request_digest':digest(request),
            'isolated':True,'providers_pinned':True,'plan_mode':observed['plan_mode'],
            'plan_resources':observed['plan_resources'],'before_state_digest':observed['before_state_digest']})

    def submit(self, request, lease):
        self.admit(request,lease)
        # prepare and claim are backed by ProductionToolCallPort. A lost claim
        # response prevents entry to worker.execute. There is no local retry ledger.
        invocation = self.ledger.prepare(request,lease)
        self.ledger.claim(invocation,request,lease)
        try:
            worker = self._worker(request,lease,'terraform')
            result = worker.execute(request)
            require(not {'request_digest','invocation_id'} & set(result), 'native_result_reserved_fields')
            envelope = self.signer.seal('iac_native_result',{'request_digest':digest(request),
                'invocation_id':invocation,**result})
            reference = self.evidence.commit(lease.scope,invocation,digest(request),envelope)
            self.evidence.require_verified(lease.scope,invocation,digest(request),reference)
            self.ledger.complete(invocation,request,lease,reference)
        except Exception:
            self.ledger.unknown(invocation,request,lease)
            raise Pending('native_dispatch_requires_reconciliation') from None
        return invocation

    def reconcile(self, request, lease):
        self._worker(request,lease,'terraform')
        invocation = self.ledger.find(request,lease)
        if invocation is None: return None
        reference = self.evidence.find(lease.scope,invocation,digest(request))
        if reference is not None:
            envelope = self.evidence.read(lease.scope,invocation,digest(request),reference)
            result = verified(self.trust,'iac_native_result',envelope)
            require(result.get('request_digest') == digest(request) and result.get('invocation_id') == invocation,
                    'native_reconciliation_binding')
            self.evidence.require_verified(lease.scope,invocation,digest(request),reference)
            self.ledger.complete(invocation,request,lease,reference)
        return invocation

    def poll(self, invocation, request, lease):
        self._worker(request,lease,'terraform')
        reference = self.ledger.completed_reference(invocation,request,lease)
        if reference is None: return None
        self.evidence.require_verified(lease.scope,invocation,digest(request),reference)
        envelope = self.evidence.read(lease.scope,invocation,digest(request),reference)
        body = verified(self.trust,'iac_native_result',envelope)
        require(body.get('request_digest') == digest(request) and body.get('invocation_id') == invocation,
                'native_result_binding')
        return envelope

    def render(self, request, lease):
        worker = self._worker(request,lease,'helm')
        lease.check(lease.scope,lease.deployment_id,lease.plan_digest,(request['chart_digest'],),
                    'helm.render',self.clock(),lease.generation)
        # Rendering has no provider mutation. Its host admission still must
        # enforce no network and the exact runtime before template evaluation.
        attestation = verified(self.trust,'helm_sandbox_attestation',self.authority.attest(request,lease))
        require(attestation == {'request_digest':digest(request),'scope':asdict(lease.scope),
            'runtime_digest':request['runtime_digest'],'network':'none','isolated':True,
            'expires_at':attestation.get('expires_at')}, 'helm_sandbox_binding')
        require(type(attestation['expires_at']) is int and self.clock() < attestation['expires_at'], 'helm_sandbox_expired')
        result = worker.render(request)
        return self.signer.seal('helm_render_receipt',{'request_digest':digest(request),**result})
