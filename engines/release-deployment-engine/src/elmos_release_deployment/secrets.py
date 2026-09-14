"""Host-owned secret materialization and bounded redaction, not a secret registry."""
from __future__ import annotations
import base64
import os
from pathlib import Path
import re
from urllib.parse import quote_from_bytes
from .contracts import canonical, digest, require


class SecretResolver:
    def __init__(self, root, fetcher, clock):
        self.root=Path(root)
        require(self.root.is_dir() and not self.root.is_symlink(),'secret_root_not_provisioned')
        self.fetcher,self.clock=fetcher,clock

    def materialize(self, scope, references, lease, deployment_id, plan_digest, generation):
        lease.check(scope,deployment_id,plan_digest,lease.resources,'secrets.resolve',self.clock(),generation)
        require(type(references) is tuple and len(references)<=100 and len(set(references))==len(references),'secret_reference_bounds')
        output=[]
        for reference in references:
            require(re.fullmatch(r'secret-ref:[A-Za-z0-9_.:/-]{1,200}',reference) is not None,'secret_reference_required')
            # Fetcher must use the canonical secret adapter with this full scope.
            value=self.fetcher(scope,reference,lease)
            require(type(value) is bytes and 0<len(value)<=65536,'secret_value_bounds')
            key=digest([scope.key,reference])[7:]
            path=self.root/key
            flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)
            try:
                descriptor=os.open(path,flags,0o600)
            except FileExistsError:
                # Immutable scoped reference. Rotation uses a new versioned ref.
                from .remote_agent import read_owned
                require(read_owned(path,65536)==value,'secret_reference_version_conflict')
            else:
                try:
                    with os.fdopen(descriptor,'wb') as stream:
                        stream.write(value); stream.flush(); os.fsync(stream.fileno())
                except BaseException:
                    # Partial file blocks reuse; do not silently retry/write over it.
                    raise
            output.append({'reference':reference,'mount_key':key})
        return output


class RedactingEvidenceCapture:
    def __init__(self, sink, secret_values):
        require(type(secret_values) is tuple and all(type(v) is bytes and v for v in secret_values),'redaction_secret_set')
        variants=set()
        for value in secret_values:
            variants.update((value,base64.b64encode(value),quote_from_bytes(value).encode()))
        self.variants=tuple(sorted(variants,key=len,reverse=True))
        self.sink=sink

    def capture(self, scope, operation_key, stdout, stderr):
        for value in (stdout,stderr):
            require(type(value) is bytes and len(value)<=1_000_000,'log_capture_bounds')
        redacted=[]
        for value in (stdout,stderr):
            for secret in self.variants:
                value=value.replace(secret,b'[REDACTED]')
            value=re.sub(rb'(?i)(authorization\s*[:=]\s*(?:bearer|basic)\s+)\S+',rb'\1[REDACTED]',value)
            redacted.append(value)
        payload={'scope':scope.key,'operation_key':operation_key,
                 'stdout':base64.b64encode(redacted[0]).decode(),'stderr':base64.b64encode(redacted[1]).decode()}
        blob=canonical(payload)
        # sink is the canonical scoped immutable evidence/CAS service.
        uri=self.sink(scope,digest(blob),blob)
        require(uri=='cas:'+digest(blob),'scoped_cas_receipt_required')
        return {'stdout_hash':digest(redacted[0]),'stderr_hash':digest(redacted[1]),
                'artifact_uri':uri,'evidence_digest':digest(blob)}
