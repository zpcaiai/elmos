import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SCRIPTS=ROOT/'scripts'/'batch31'

class ToolkitTests(unittest.TestCase):
    def test_skill_bundle(self):
        subprocess.run([sys.executable,str(SCRIPTS/'validate_skill_bundle.py'),str(ROOT/'.agents'/'skills')],check=True)

    def test_schemas_and_templates(self):
        import jsonschema
        for schema_path in sorted((ROOT/'schemas'/'batch31').glob('*.schema.json')):
            schema=json.loads(schema_path.read_text()); jsonschema.validators.validator_for(schema).check_schema(schema)
        pairs=[('database-pack.json','database-pack.schema.json'),('support-matrix.json','database-support-matrix.schema.json'),('workload-fingerprint.json','workload-fingerprint.schema.json'),('canonical-db-ir.json','canonical-db-ir.schema.json'),('data-migration-plan.json','data-migration-plan.schema.json'),('certification.json','database-certification.schema.json')]
        for template,schema in pairs:
            data=json.loads((ROOT/'templates'/'batch31'/template).read_text()); sch=json.loads((ROOT/'schemas'/'batch31'/schema).read_text()); jsonschema.validate(data,sch)

    def test_scaffold_and_validate(self):
        with tempfile.TemporaryDirectory() as td:
            repo=Path(td)
            subprocess.run([sys.executable,str(SCRIPTS/'scaffold_database_pack.py'),'--source-engine','oracle','--target-engine','postgresql','--source-version','19.22','--target-version','16.4','--source-edition','enterprise','--target-edition','community','--repo-root',str(repo)],check=True)
            pack=repo/'database-packs'/'oracle-to-postgresql'
            m=json.loads((pack/'pack.json').read_text()); m['owner']='database-team'; m['maintenance_owner']='database-team'; m['data_owner']='order-data-owner'; m['source']['driver_versions']=['ojdbc11-23.4']; m['source']['charset']='AL32UTF8'; m['source']['collation']='BINARY'; m['target']['driver_versions']=['npgsql-8.0']; m['target']['charset']='UTF8'; m['target']['collation']='C'; (pack/'pack.json').write_text(json.dumps(m,indent=2)+'\n')
            s=json.loads((pack/'support-matrix.json').read_text())
            for cap in s['capabilities']: cap['owner']='database-team'
            (pack/'support-matrix.json').write_text(json.dumps(s,indent=2)+'\n')
            p=json.loads((pack/'target-profile'/'profile.json').read_text()); p['owner']='database-team'; p['driver_versions']=['npgsql-8.0']; p['charset']='UTF8'; p['collation']='C'; p['provision']={'commands':['docker compose up postgres'],'image_digests':['sha256:test']}; (pack/'target-profile'/'profile.json').write_text(json.dumps(p,indent=2)+'\n')
            d=json.loads((pack/'migration'/'data-migration-plan.json').read_text()); d['owner']='data-team'; d['source']={'engine':'oracle'}; d['target']={'engine':'postgresql'}; d['rollback']={'strategy':'restore-source-authority'}; (pack/'migration'/'data-migration-plan.json').write_text(json.dumps(d,indent=2)+'\n')
            ir=json.loads((pack/'canonical-ir'/'model.json').read_text()); ir['source_snapshot_digest']='sha256:source'; (pack/'canonical-ir'/'model.json').write_text(json.dumps(ir,indent=2)+'\n')
            subprocess.run([sys.executable,str(SCRIPTS/'validate_database_pack.py'),str(pack)],check=True)
            subprocess.run([sys.executable,str(SCRIPTS/'validate_canonical_ir.py'),str(pack/'canonical-ir'/'model.json')],check=True)

    def test_candidate_scoring(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); src=td/'candidates.json'; out=td/'result.json'
            src.write_text(json.dumps({'weights':{'customer_demand':2,'migration_value':2,'data_risk':-1},'candidates':[{'pack_key':'oracle-to-postgresql','customer_demand':4,'migration_value':4,'data_risk':1,'evidence_notes':['design partner']}]}))
            subprocess.run([sys.executable,str(SCRIPTS/'score_database_candidates.py'),str(src),'--output',str(out)],check=True)
            self.assertEqual(json.loads(out.read_text())['results'][0]['decision'],'approve')

    def test_conservative_gate_rejects_fake_certification(self):
        with tempfile.TemporaryDirectory() as td:
            repo=Path(td)
            subprocess.run([sys.executable,str(SCRIPTS/'scaffold_database_pack.py'),'--source-engine','mysql','--target-engine','postgresql','--source-version','8.0.39','--target-version','16.4','--source-edition','community','--target-edition','community','--repo-root',str(repo)],check=True)
            pack=repo/'database-packs'/'mysql-to-postgresql'
            m=json.loads((pack/'pack.json').read_text()); m['status']='certified'; m['owner']=m['maintenance_owner']='database-team'; m['data_owner']='data-owner'; m['source']['driver_versions']=['mysql-connector-8.4']; m['source']['charset']='utf8mb4'; m['source']['collation']='utf8mb4_0900_ai_ci'; m['target']['driver_versions']=['npgsql-8.0']; m['target']['charset']='UTF8'; m['target']['collation']='C'; (pack/'pack.json').write_text(json.dumps(m,indent=2)+'\n')
            s=json.loads((pack/'support-matrix.json').read_text());
            for cap in s['capabilities']: cap['owner']='database-team'
            (pack/'support-matrix.json').write_text(json.dumps(s,indent=2)+'\n')
            p=json.loads((pack/'target-profile'/'profile.json').read_text()); p['owner']='database-team'; p['driver_versions']=['npgsql-8.0']; p['charset']='UTF8'; p['collation']='C'; p['provision']={'commands':['true'],'image_digests':['sha256:test']}; (pack/'target-profile'/'profile.json').write_text(json.dumps(p,indent=2)+'\n')
            d=json.loads((pack/'migration'/'data-migration-plan.json').read_text()); d['owner']='data-team'; d['source']={'engine':'mysql'}; d['target']={'engine':'postgresql'}; d['rollback']={'strategy':'source-authority'}; (pack/'migration'/'data-migration-plan.json').write_text(json.dumps(d,indent=2)+'\n')
            ir=json.loads((pack/'canonical-ir'/'model.json').read_text()); ir['source_snapshot_digest']='sha256:fake'; (pack/'canonical-ir'/'model.json').write_text(json.dumps(ir,indent=2)+'\n')
            c=json.loads((pack/'certification'/'certification.json').read_text()); c['status']='certified'; (pack/'certification'/'certification.json').write_text(json.dumps(c,indent=2)+'\n')
            result=subprocess.run([sys.executable,str(SCRIPTS/'run_database_gate.py'),str(pack)])
            self.assertEqual(result.returncode,2)

if __name__=='__main__': unittest.main()
