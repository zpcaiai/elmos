from dataclasses import asdict
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from elmos_release_deployment.contracts import *
from elmos_release_deployment.adapters import *


class Transport:
    def __init__(self): self.calls=[]; self.responses={}
    def call(self,service,version,action,params,lease):
        self.calls.append((service,version,action,params))
        return self.responses[action]


class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.scope=Scope('tenant','workspace','project','prod','123456789')
        self.target=DeploymentTarget('target',self.scope,'alibaba_ecs','cn-shanghai','rg-a',('i-a',),(('env','prod'),),'amd64','27.5.1','123456789')
        self.lease=CapabilityLease('lease',self.scope,'dep',digest(b'plan'),('i-a',),
            frozenset({'remote.submit','remote.poll','remote.cancel','target.discover'}),1,2000,'session')
        self.transport=Transport()

    def test_cloud_assistant_request_idempotency_and_redaction(self):
        self.transport.responses={'RunCommand':{'InvokeId':'inv-a','RequestId':'req-a'},
            'DescribeInvocationResults':{'Invocation':{'InvocationResults':{'InvocationResult':[
                {'InstanceId':'i-a','InvokeId':'inv-a','InvocationStatus':'Success','ExitCode':0,'Output':'secret-value'}]}}},
            'StopInvocation':{'RequestId':'cancel-a'}}
        executor=CloudAssistantExecutor(self.transport,lambda:1000)
        receipt=executor.submit(self.target,self.lease,digest(b'bundle'),digest(b'op'),'apply')
        params=self.transport.calls[-1][3]
        self.assertEqual(digest(b'op')[7:],params['ClientToken'])
        self.assertEqual('i-a',params['InstanceId.1'])
        self.assertEqual('rg-a',params['ResourceGroupId'])
        result=executor.poll(self.target,self.lease,receipt['invocation_id'])
        self.assertNotIn('secret-value',json.dumps(result))
        executor.cancel(self.target,self.lease,'inv-a')
        self.assertEqual('StopInvocation',self.transport.calls[-1][2])

    def test_ecs_discovery_checks_resources_region_tags_and_status(self):
        instance={'InstanceId':'i-a','Status':'Running','RegionId':'cn-shanghai','ResourceGroupId':'rg-a',
                  'Tags':{'Tag':[{'TagKey':'env','TagValue':'prod'}]}}
        self.transport.responses={'DescribeInstances':{'Instances':{'Instance':[instance]}},
            'DescribeCloudAssistantStatus':{'InstanceCloudAssistantStatusSet':{'InstanceCloudAssistantStatus':[
                {'InstanceId':'i-a','CloudAssistantStatus':'true'}]}}}
        adapter=AlibabaEcsAdapter(self.transport,lambda:1000)
        self.assertTrue(adapter.discover(self.target,self.lease)['assistant_ready'])
        instance['Status']='Stopped'
        with self.assertRaises(Denied): adapter.discover(self.target,self.lease)
        instance['Status']='Running'; instance['RegionId']='cn-beijing'
        with self.assertRaises(Denied): adapter.discover(self.target,self.lease)

    def test_sts_session_policy_never_broadens_resource_or_action(self):
        policy=AlibabaStsCredentialBroker.session_policy(self.target,'remote.submit')
        self.assertNotIn('*',json.dumps(policy))
        self.assertEqual(['ecs:RunCommand'],policy['Statement'][0]['Action'])
        self.transport.responses={'AssumeRole':{'session_ref':'host-session','expires_at':1900,'account_id':'123456789'}}
        broker=AlibabaStsCredentialBroker(self.transport,lambda:1000)
        broker.acquire(self.target,'acs:ram::123456789:role/deploy',self.lease,'remote.submit')
        with self.assertRaises(Denied): broker.acquire(self.target,'acs:ram::999:role/deploy',self.lease,'remote.submit')

    def test_acr_verifies_manifest_config_bytes_and_architecture(self):
        config=canonical({'architecture':'amd64','os':'linux'})
        manifest=canonical({'schemaVersion':2,'mediaType':'application/vnd.oci.image.manifest.v1+json',
            'config':{'digest':digest(config),'size':len(config)},'layers':[]})
        artifact=Artifact('web','registry.test/web',digest(manifest),digest(b'sbom'),digest(b'prov'),digest(b'scan'),'vue',8080)
        blobs={digest(config):config,digest(manifest):manifest}
        registry=AcrArtifactRegistry(lambda repo,key:blobs[key])
        self.assertEqual(artifact.image,registry.resolve(artifact,'amd64'))
        with self.assertRaises(Denied): registry.resolve(artifact,'arm64')
        blobs[digest(manifest)]=b'tag-changed-or-tampered'
        with self.assertRaises(Denied): registry.resolve(artifact,'amd64')

    def test_full_stack_all_four_profiles_are_pinned_nonroot(self):
        for profile in ('spring','python','dotnet'):
            backend=Artifact('backend','registry.test/backend',digest(profile.encode()),digest(b'sbom'),digest(b'prov'),digest(b'scan'),profile,8080)
            web=Artifact('frontend','registry.test/frontend',digest(b'vue'),digest(b'sbom'),digest(b'prov'),digest(b'scan'),'vue',8081)
            compose=json.loads(DockerHostRuntime.compose((backend,web),digest(b'config'),('secret-ref:db',),self.scope.key))
            for service in compose['services'].values():
                self.assertEqual('10001:10001',service['user'])
                self.assertTrue(service['read_only'])
                self.assertIn('@sha256:',service['image'])
            self.assertEqual({'backend','frontend'},set(compose['services']))


if __name__=='__main__': unittest.main()
