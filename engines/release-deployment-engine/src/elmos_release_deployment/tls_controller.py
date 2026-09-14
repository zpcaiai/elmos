"""Approved ALB default-certificate rotation with live TLS verification."""
import ipaddress
import socket
import ssl

from .cloud_controllers import AlibabaCloudControllers
from .contracts import Denied, Pending, digest, identifier, require, sha


class TlsProbe:
    """Operator-owned address allowlist prevents arbitrary probe destinations."""
    def __init__(self, bindings, context=None):
        self.bindings = dict(bindings)
        self.context = context or ssl.create_default_context()
        require(self.context.verify_mode == ssl.CERT_REQUIRED and self.context.check_hostname, 'tls_trust_required')

    def verify(self, domain, certificate_digest):
        sha(certificate_digest)
        require(domain in self.bindings, 'tls_domain_not_bound')
        addresses = tuple(self.bindings[domain])
        require(0 < len(addresses) <= 8, 'tls_address_bounds')
        for address in addresses:
            require(type(address) is dict and set(address)=={'ip','port'} and type(address['port']) is int
                    and 1<=address['port']<=65535,'tls_endpoint')
            ipaddress.ip_address(address['ip'])
            with socket.create_connection((address['ip'], address['port']), timeout=5) as stream:
                with self.context.wrap_socket(stream, server_hostname=domain) as secured:
                    require(secured.version() in {'TLSv1.2','TLSv1.3'}, 'tls_protocol')
                    require(digest(secured.getpeercert(binary_form=True)) == certificate_digest,
                            'tls_peer_certificate_mismatch')
        return {'domain':domain,'certificate_digest':certificate_digest,'addresses':list(addresses),
                'chain_and_hostname_verified':True}


class AlibabaTlsController(AlibabaCloudControllers):
    def rotate(self, plan, approval, lease, certificate_der, probe):
        from cryptography import x509
        from cryptography.hazmat.primitives.asymmetric import rsa, ec, ed25519, ed448
        from datetime import datetime, timezone
        require(set(plan) == {'scope','listener_id','load_balancer_id','domain','before_certificate_id',
                              'after_certificate_id','certificate_digest','invariant_digest'}, 'tls_plan_fields')
        for field in ('listener_id','load_balancer_id','before_certificate_id','after_certificate_id'):
            identifier(plan[field])
        require(type(certificate_der) is bytes and len(certificate_der)<=65536
                and digest(certificate_der)==plan['certificate_digest'], 'tls_certificate_bytes')
        try:
            cert=x509.load_der_x509_certificate(certificate_der)
            names=cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
        except (ValueError,x509.ExtensionNotFound):
            raise Denied('invalid_tls_certificate') from None
        key=cert.public_key()
        require((isinstance(key,rsa.RSAPublicKey) and key.key_size>=2048) or
                (isinstance(key,ec.EllipticCurvePublicKey) and key.key_size>=256) or
                isinstance(key,(ed25519.Ed25519PublicKey,ed448.Ed448PublicKey)), 'tls_weak_public_key')
        algorithm=cert.signature_hash_algorithm
        require(algorithm is None or algorithm.name in {'sha256','sha384','sha512'},'tls_weak_signature')
        now=datetime.fromtimestamp(self.clock(),timezone.utc)
        require(cert.not_valid_before_utc<=now<cert.not_valid_after_utc,'tls_certificate_expired')
        domain=plan['domain']
        require(type(domain) is str and domain.isascii() and domain == domain.lower()
                and any(domain==name or (name.startswith('*.') and domain.count('.')==name.count('.')
                                         and domain.endswith(name[1:])) for name in names), 'tls_certificate_hostname')
        operation=self._authorize('tls.rotate',plan,approval,lease,
                                  (plan['listener_id'],plan['load_balancer_id'],plan['after_certificate_id']))
        row,fresh,complete=self._step(operation,plan,lease,guarded=True,
            resource_locks=(digest(['alb',self.account,self.region,plan['listener_id']]),))
        if complete is not None: return complete
        def read():
            observed=self.transport.call('alb','2020-06-16','GetListenerAttribute',
                                          {'ListenerId':plan['listener_id']},lease)
            require(observed.get('ListenerId')==plan['listener_id'] and
                    observed.get('LoadBalancerId')==plan['load_balancer_id'] and
                    observed.get('ListenerProtocol')=='HTTPS', 'tls_listener_binding')
            invariants={k:v for k,v in observed.items() if k not in
                        {'RequestId','ListenerStatus','Certificates'}}
            require(digest(invariants)==plan['invariant_digest'],'tls_listener_configuration_drift')
            certificates=observed.get('Certificates',[])
            require(len(certificates)==1,'tls_additional_certificates_require_separate_controller')
            return observed,certificates[0].get('CertificateId')
        if fresh:
            observed,current=read()
            require(current==plan['before_certificate_id'] and observed.get('ListenerStatus')=='Running',
                    'tls_before_image_conflict')
            response=self.transport.call('alb','2020-06-16','UpdateListenerAttribute',
                {'ListenerId':plan['listener_id'],'ClientToken':digest(plan)[7:],
                 'Certificates':[{'CertificateId':plan['after_certificate_id']}]},lease)
            invocation=response.get('RequestId')
            identifier(invocation)
            self.journal.accepted(self.scope,lease.deployment_id,operation,invocation)
        else:
            invocation=row['invocation']
            if invocation is None: raise Pending('tls_dispatch_unknown_requires_reconciliation')
        observed,current=read()
        if current!=plan['after_certificate_id'] or observed.get('ListenerStatus')!='Running':
            raise Pending('tls_rotation_in_progress')
        verification=probe.verify(domain,plan['certificate_digest'])
        require(verification.get('chain_and_hostname_verified') is True and
                verification.get('certificate_digest')==plan['certificate_digest'] and
                verification.get('domain')==domain,'tls_probe_binding')
        return self._finish(operation,plan,lease,invocation,{'listener':observed,'tls':verification})
