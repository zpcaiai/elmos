"""OPA is a deterministic policy evaluator, never a signing/authorization service."""
import json
from pathlib import Path
import subprocess
from .contracts import canonical, digest, require, sha


class PolicyEngine:
    def __init__(self, executable, executable_digest, policy_file, policy_digest):
        self.executable,self.policy_file=Path(executable).resolve(),Path(policy_file).resolve()
        sha(executable_digest); sha(policy_digest)
        self.executable_digest,self.policy_digest=executable_digest,policy_digest

    def evaluate(self, host_input):
        require(digest(self.executable.read_bytes())==self.executable_digest,'opa_binary_drift')
        require(digest(self.policy_file.read_bytes())==self.policy_digest,'opa_policy_drift')
        payload=canonical(host_input)
        require(len(payload)<=262144,'opa_input_bounds')
        result=subprocess.run([str(self.executable),'eval','--strict','--format=json','--data',str(self.policy_file),
                               '--stdin-input','data.elmos.release_deploy.allow'],input=payload,
                              stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,check=False)
        require(result.returncode==0 and len(result.stdout)<=65536,'opa_evaluation_failed')
        parsed=json.loads(result.stdout)
        results=parsed.get('result',[])
        require(len(results)==1 and len(results[0].get('expressions',[]))==1,'opa_indeterminate')
        return results[0]['expressions'][0].get('value') is True
