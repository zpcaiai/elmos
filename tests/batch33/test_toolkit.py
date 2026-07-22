from __future__ import annotations
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts' / 'batch33'

def complete_pack(pack: Path) -> None:
    manifest = json.loads((pack/'pack.json').read_text())
    manifest['owner'] = 'cloud-platform-team'; manifest['maintenance_owner'] = 'cloud-platform-team'
    manifest['source']['state_backend'] = {'type':'s3-dynamodb','locking':'enabled','encryption':'kms'}
    manifest['target']['state_backend'] = {'type':'azurerm','locking':'lease','encryption':'cmk'}
    (pack/'pack.json').write_text(json.dumps(manifest,indent=2)+'\n')

    support = json.loads((pack/'support-matrix.json').read_text())
    support['capabilities'][0]['owner']='cloud-platform-team'
    (pack/'support-matrix.json').write_text(json.dumps(support,indent=2)+'\n')

    fp=json.loads((pack/'source-fingerprint'/'fingerprint.json').read_text())
    fp['snapshot_digest']='sha256:source'; fp['coverage']=.5; fp['source_tuple']=manifest['source']
    fp['resources']=[{'id':'source.compute'}]; fp['runtime_evidence']=[{'ref':'runtime'}]
    (pack/'source-fingerprint'/'fingerprint.json').write_text(json.dumps(fp,indent=2)+'\n')

    rc=json.loads((pack/'runtime-architecture'/'contract.json').read_text())
    rc['source_snapshot_digest']='sha256:source'
    rc['components']=[{'id':'component.api','kind':'service','name':'api','source_refs':[{'path':'infra/main.tf'}],'references':[]}]
    rc['identities']=[{'id':'identity.api','kind':'workload-identity','name':'api','source_refs':[{'path':'infra/iam.tf'}],'references':['component.api']}]
    rc['source_map']=[{'node_id':'component.api','source_refs':[{'path':'infra/main.tf'}]},{'node_id':'identity.api','source_refs':[{'path':'infra/iam.tf'}]}]
    (pack/'runtime-architecture'/'contract.json').write_text(json.dumps(rc,indent=2)+'\n')

    ir=json.loads((pack/'iac-ir'/'model.json').read_text()); ir['source_snapshot_digest']='sha256:source'
    ir['resources']=[{'id':'resource.api','kind':'compute','logical_name':'api','provider_neutral_type':'runtime.service','source_refs':[{'path':'infra/main.tf'}],'depends_on':[],'properties':{},'lifecycle':{'replace':'controlled'},'security':{'public':False}}]
    ir['source_map']=[{'node_id':'resource.api','source_refs':[{'path':'infra/main.tf'}]}]
    (pack/'iac-ir'/'model.json').write_text(json.dumps(ir,indent=2)+'\n')

    target=json.loads((pack/'target-profile'/'profile.json').read_text())
    target['owner']='cloud-platform-team'; target['state_backend']={'type':'azurerm','locking':'lease','encryption':'cmk'}
    target['container']={'builder':'buildkit-0.24','base_image_policy':'signed-digest-only'}
    target['orchestrator']={'name':'aks','version':'1.33'}
    target['identity']={'workload_identity':'federated','human_identity':'entra-id'}
    target['network']={'topology':'hub-spoke','default_egress':'deny'}
    target['dns']={'provider':'azure-dns','strategy':'private-public-split'}
    target['api_gateway']={'provider':'application-gateway','strategy':'private'}
    target['observability']={'telemetry':'otel','retention':'30d'}
    target['security']={'policy_bundle':'baseline-v1','encryption':'cmk'}
    target['cost']={'budget_currency':'USD','monthly_limit':100}
    target['provision']={'commands':['terraform plan -out=apply.tfplan','terraform apply apply.tfplan']}; target['validate']={'commands':['terraform validate']}; target['destroy']={'commands':['terraform plan -destroy -out=destroy.tfplan','terraform apply destroy.tfplan']}
    target['lifecycle']={'support_until':'2028-12-31','upgrade_policy':'quarterly'}
    (pack/'target-profile'/'profile.json').write_text(json.dumps(target,indent=2)+'\n')

    val=json.loads((pack/'validation'/'validation-profile.json').read_text())
    val['owner']='quality-team'; val['p0_workloads']=[{'key':'api','contract':'health-and-private-access'}]
    val['representative_workloads']=['workload.api']; val['evidence_refs']=[]
    (pack/'validation'/'validation-profile.json').write_text(json.dumps(val,indent=2)+'\n')

    cert=json.loads((pack/'certification'/'certification.json').read_text()); cert['owner']='quality-team'; cert['exact_tuple']={'source':manifest['source'],'target':manifest['target']}
    (pack/'certification'/'certification.json').write_text(json.dumps(cert,indent=2)+'\n')

class ToolkitTests(unittest.TestCase):
    def test_skill_bundle(self):
        subprocess.run([sys.executable,str(SCRIPTS/'validate_skill_bundle.py'),str(ROOT/'.agents'/'skills')],check=True)

    def test_schemas_and_templates(self):
        import jsonschema
        for path in sorted((ROOT/'schemas'/'batch33').glob('*.schema.json')):
            schema=json.loads(path.read_text()); jsonschema.validators.validator_for(schema).check_schema(schema)
        pairs=[
            ('cloud-pack.json','cloud-pack.schema.json'),('support-matrix.json','cloud-support-matrix.schema.json'),
            ('source-fingerprint.json','source-fingerprint.schema.json'),('runtime-architecture-contract.json','runtime-architecture-contract.schema.json'),
            ('iac-ir.json','iac-ir.schema.json'),('target-profile.json','target-profile.schema.json'),
            ('validation-profile.json','validation-profile.schema.json'),('certification.json','cloud-certification.schema.json')]
        for template,schema_name in pairs:
            jsonschema.validate(json.loads((ROOT/'templates'/'batch33'/template).read_text()),json.loads((ROOT/'schemas'/'batch33'/schema_name).read_text()))

    def test_scaffold_and_validate(self):
        with tempfile.TemporaryDirectory() as d:
            repo=Path(d)
            subprocess.run([sys.executable,str(SCRIPTS/'scaffold_cloud_pack.py'),'--source-platform','aws','--target-platform','azure','--source-provider','aws','--target-provider','azurerm','--source-region','us-east-1','--target-region','eastus','--source-iac-tool','cloudformation','--source-iac-version','2010-09-09','--target-iac-tool','terraform','--target-iac-version','1.12.2','--source-runtime','eks','--source-runtime-version','1.32','--target-runtime','aks','--target-runtime-version','1.33','--source-ci','jenkins','--source-ci-version','2.516','--target-ci','github-actions','--target-ci-version','2026','--repo-root',str(repo)],check=True)
            pack=repo/'cloud-packs'/'cloudformation-aws-to-terraform-azurerm'; complete_pack(pack)
            subprocess.run([sys.executable,str(SCRIPTS/'validate_cloud_pack.py'),str(pack)],check=True)
            subprocess.run([sys.executable,str(SCRIPTS/'validate_runtime_contract.py'),str(pack/'runtime-architecture'/'contract.json')],check=True)
            subprocess.run([sys.executable,str(SCRIPTS/'validate_iac_ir.py'),str(pack/'iac-ir'/'model.json')],check=True)

    def test_graph_validators_reject_unknown_refs(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ir.json'; data=json.loads((ROOT/'templates'/'batch33'/'iac-ir.json').read_text()); data['source_snapshot_digest']='sha256:test'
            data['resources']=[{'id':'r.a','kind':'compute','logical_name':'a','provider_neutral_type':'runtime.service','source_refs':[{'path':'a.tf'}],'depends_on':['r.missing'],'properties':{},'lifecycle':{},'security':{}}]
            data['source_map']=[{'node_id':'r.a','source_refs':[{'path':'a.tf'}]}]; path.write_text(json.dumps(data))
            result=subprocess.run([sys.executable,str(SCRIPTS/'validate_iac_ir.py'),str(path)]); self.assertEqual(result.returncode,1)

    def test_candidate_scoring(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d); source=d/'candidates.json'; out=d/'result.json'
            source.write_text(json.dumps({'weights':{'customer_demand':2,'migration_value':2,'representative_workloads':1.5,'engineering_reuse':1,'source_complexity':-.5,'security_risk':-1,'provider_lock_in':-.5},'candidates':[{'pack_key':'cf-to-tf','customer_demand':4,'migration_value':4,'representative_workloads':3,'engineering_reuse':4,'source_complexity':2,'security_risk':1,'provider_lock_in':1,'evidence_notes':['design partner']}] }))
            subprocess.run([sys.executable,str(SCRIPTS/'score_cloud_candidates.py'),str(source),'--output',str(out)],check=True)
            self.assertEqual(json.loads(out.read_text())['results'][0]['decision'],'approve')

    def test_conservative_gate_rejects_fake_certification(self):
        with tempfile.TemporaryDirectory() as d:
            repo=Path(d)
            subprocess.run([sys.executable,str(SCRIPTS/'scaffold_cloud_pack.py'),'--source-platform','aws','--target-platform','azure','--source-provider','aws','--target-provider','azurerm','--source-region','us-east-1','--target-region','eastus','--source-iac-tool','cloudformation','--source-iac-version','2010-09-09','--target-iac-tool','terraform','--target-iac-version','1.12.2','--source-runtime','eks','--source-runtime-version','1.32','--target-runtime','aks','--target-runtime-version','1.33','--repo-root',str(repo)],check=True)
            pack=repo/'cloud-packs'/'cloudformation-aws-to-terraform-azurerm'; complete_pack(pack)
            manifest=json.loads((pack/'pack.json').read_text()); manifest['status']='certified'; (pack/'pack.json').write_text(json.dumps(manifest,indent=2)+'\n')
            cert=json.loads((pack/'certification'/'certification.json').read_text()); cert['status']='certified'; (pack/'certification'/'certification.json').write_text(json.dumps(cert,indent=2)+'\n')
            result=subprocess.run([sys.executable,str(SCRIPTS/'run_cloud_gate.py'),str(pack)])
            self.assertEqual(result.returncode,2)

    def test_validator_rejects_auto_approve(self):
        with tempfile.TemporaryDirectory() as d:
            repo=Path(d)
            subprocess.run([sys.executable,str(SCRIPTS/'scaffold_cloud_pack.py'),'--source-platform','aws','--target-platform','azure','--source-provider','aws','--target-provider','azurerm','--source-region','us-east-1','--target-region','eastus','--source-iac-tool','cloudformation','--source-iac-version','2010-09-09','--target-iac-tool','terraform','--target-iac-version','1.12.2','--source-runtime','eks','--source-runtime-version','1.32','--target-runtime','aks','--target-runtime-version','1.33','--repo-root',str(repo)],check=True)
            pack=repo/'cloud-packs'/'cloudformation-aws-to-terraform-azurerm'; complete_pack(pack)
            target=json.loads((pack/'target-profile'/'profile.json').read_text())
            target['destroy']={'commands':['terraform destroy -auto-approve']}
            (pack/'target-profile'/'profile.json').write_text(json.dumps(target,indent=2)+'\n')
            result=subprocess.run([sys.executable,str(SCRIPTS/'validate_cloud_pack.py'),str(pack)])
            self.assertEqual(result.returncode,1)

if __name__=='__main__': unittest.main()
