from dataclasses import asdict
import base64
import http.server
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from elmos_release_deployment.contracts import *
from elmos_release_deployment.adapters import DockerHostRuntime
from elmos_release_deployment.remote_agent import RemoteAgent, Ed25519Trust


class RemoteAgentTest(unittest.TestCase):
    def setUp(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
        self.private=Ed25519PrivateKey.generate()
        public=self.private.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
        self.trust=Ed25519Trust({'test-key':base64.b64encode(public).decode()})
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'bundles').mkdir(); (self.root/'config').mkdir()
        self.scope=asdict(Scope('tenant','workspace','project','prod','123456789'))
        self.calls=[]
        self.agent=RemoteAgent(self.root,self.trust,self.scope,'i-a',lambda:1000,self.run_command)
        self.artifact=Artifact('app','registry.test/app',digest(b'image'),digest(b'sbom'),digest(b'prov'),digest(b'scan'),'python',8080)
        config=canonical({'port':8080}); config_digest=digest(config)
        (self.root/'config'/config_digest[7:]).write_bytes(config)
        compose=DockerHostRuntime.compose((self.artifact,),config_digest,(),digest(self.scope))
        (self.root/'bundles'/(digest(compose)[7:]+'.json')).write_bytes(compose)
        self.body={'scope':self.scope,'instance_id':'i-a','operation_key':digest(b'op'),'action':'apply',
                   'issued_at':900,'expires_at':1200,'fence':1,'target_id':'target-a','project_name':'team-app',
                   'artifacts':[asdict(self.artifact)],'config_digest':config_digest,'secret_refs':[],
                   'compose_digest':digest(compose),'probes':[{'id':'http','port':8080,'path':'/health','status':200,'body_digest':None}]}

    def run_command(self,argv,timeout):
        self.calls.append((argv,timeout))
        return 0

    def signed(self,body=None):
        body=self.body if body is None else body
        signature=self.private.sign(b'remote_permit\x00'+canonical(body))
        return {'body':body,'signature':'test-key:'+base64.b64encode(signature).decode()}

    def test_real_ed25519_verification_and_idempotent_command(self):
        signed=self.signed()
        first=self.agent.execute(signed,self.body['operation_key'],'apply')
        second=self.agent.execute(signed,self.body['operation_key'],'apply')
        self.assertEqual(first,second)
        self.assertEqual(1,len(self.calls))
        argv=self.calls[0][0]
        self.assertEqual(['docker','compose'],argv[:2])
        self.assertIn('--wait',argv)

    def test_tampered_expired_cross_target_and_revoked_key_rejected(self):
        signed=self.signed(); signed['body']={**self.body,'instance_id':'i-b'}
        with self.assertRaises(Denied): self.agent.execute(signed,self.body['operation_key'],'apply')
        for key,value in [('instance_id','i-b'),('expires_at',1000),('project_name','$(touch bad)')]:
            body={**self.body,key:value}
            with self.assertRaises(Denied): self.agent.execute(self.signed(body),body['operation_key'],'apply')
        self.trust.revoked=frozenset({'test-key'})
        with self.assertRaises(Denied): self.agent.execute(self.signed(),self.body['operation_key'],'apply')
        self.assertEqual([],self.calls)

    def test_unknown_runtime_outcome_prevents_replay_or_next_mutation(self):
        def timeout(argv,seconds):
            self.calls.append(argv)
            raise TimeoutError()
        self.agent.runner=timeout
        signed=self.signed()
        self.assertEqual('UNKNOWN',self.agent.execute(signed,self.body['operation_key'],'apply')['status'])
        self.agent=RemoteAgent(self.root,self.trust,self.scope,'i-a',lambda:1000,self.run_command)
        self.assertEqual('UNKNOWN',self.agent.execute(signed,self.body['operation_key'],'apply')['status'])
        other={**self.body,'operation_key':digest(b'next'),'fence':2,'target_id':'alias-same-physical-instance'}
        with self.assertRaises(Denied): self.agent.execute(self.signed(other),other['operation_key'],'apply')
        self.assertEqual(1,len(self.calls))

    def test_old_fence_and_compose_tamper_rejected(self):
        self.agent.execute(self.signed(),self.body['operation_key'],'apply')
        other={**self.body,'operation_key':digest(b'next')}
        with self.assertRaises(Denied): self.agent.execute(self.signed(other),other['operation_key'],'apply')
        other['fence']=2
        (self.root/'bundles'/(self.body['compose_digest'][7:]+'.json')).write_bytes(b'{"privileged":true}')
        with self.assertRaises(Denied): self.agent.execute(self.signed(other),other['operation_key'],'apply')

    def test_real_loopback_http_probe_hash_and_no_redirect(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200); self.end_headers(); self.wfile.write(b'healthy')
            def log_message(self,*args): pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        port=server.server_address[1]
        artifact=Artifact(**{**asdict(self.artifact),'port':port})
        compose=DockerHostRuntime.compose((artifact,),self.body['config_digest'],(),digest(self.scope))
        (self.root/'bundles'/(digest(compose)[7:]+'.json')).write_bytes(compose)
        body={**self.body,'action':'verify','artifacts':[asdict(artifact)],'compose_digest':digest(compose),
              'probes':[{'id':'health','port':port,'path':'/health','status':200,'body_digest':digest(b'healthy')}]}
        result=self.agent.execute(self.signed(body),body['operation_key'],'verify')
        self.assertEqual('PASS',result['status'])
        self.assertEqual({'health':'PASS'},result['probes'])
        self.assertEqual([],self.calls)


if __name__=='__main__': unittest.main()
