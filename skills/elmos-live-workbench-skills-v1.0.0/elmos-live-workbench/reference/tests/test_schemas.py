import copy,json,unittest
from pathlib import Path
from jsonschema import Draft202012Validator, ValidationError
R=Path(__file__).resolve().parents[2]
class SchemaTests(unittest.TestCase):
    def validate(self,name,data):Draft202012Validator(json.loads((R/'contracts'/f'{name}.schema.json').read_text())).validate(data)
    def example(self,name):return json.loads((R/'examples'/f'{name}.json').read_text())
    def test_all_schemas_well_formed(self):
        for p in (R/'contracts').glob('*.schema.json'):
            with self.subTest(schema=p.name):Draft202012Validator.check_schema(json.loads(p.read_text()))
    def test_all_examples_match(self):
        for p in (R/'examples').glob('*.json'):
            with self.subTest(example=p.name):self.validate(p.stem,json.loads(p.read_text()))
    def test_all_candidates_match(self):
        for p in (R/'adapters/candidates').glob('*.json'):
            with self.subTest(profile=p.name):self.validate('runtime-profile',json.loads(p.read_text()))
    def test_bad_preview_window(self):
        x=self.example('preview-session');x['window_seconds']=601
        with self.assertRaises(ValidationError):self.validate('preview-session',x)
    def test_runtime_claim_no_event(self):
        x=self.example('evidence-claim');x['runtime_event_ids']=[]
        with self.assertRaises(ValidationError):self.validate('evidence-claim',x)
    def test_traversal_path(self):
        x=self.example('source-anchor');x['path']='../secret'
        with self.assertRaises(ValidationError):self.validate('source-anchor',x)
    def test_fake_cleaned(self):
        x=self.example('cleanup-receipt');x['checks']['processes_stopped']=False
        with self.assertRaises(ValidationError):self.validate('cleanup-receipt',x)
    def test_fake_deployment_qualified(self):
        x=json.loads(next((R/'adapters/candidates').glob('*.json')).read_text());x['qualification_status']='deployment-qualified'
        with self.assertRaises(ValidationError):self.validate('runtime-profile',x)
    def test_hidden_answer_field_forbidden(self):
        x=self.example('learning-mission');x['answer']='1000'
        with self.assertRaises(ValidationError):self.validate('learning-mission',x)
