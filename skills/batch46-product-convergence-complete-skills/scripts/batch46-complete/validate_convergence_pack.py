from __future__ import annotations
from pathlib import Path
import json, hashlib, re, sys
PLACEHOLDERS={"tbd","unknown","none","team","owner","placeholder","todo","n/a","na"}
def load(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def save(path,obj): Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def sha256(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for b in iter(lambda:f.read(1048576),b""): h.update(b)
 return h.hexdigest()
def valid_digest(v): return isinstance(v,str) and bool(re.fullmatch(r"[a-f0-9]{64}",v)) and len(set(v))>1
def non_placeholder(v): return isinstance(v,str) and len(v.strip())>=3 and v.strip().lower() not in PLACEHOLDERS
def fail(msg): raise AssertionError(msg)

FILES={"capability-package.json":"capability-package.schema.json","dependency-graph.json":"capability-dependency-graph.schema.json","project-lifecycle.json":"project-lifecycle.schema.json","workflow-definition.json":"workflow-definition.schema.json","policy-bundle.json":"policy-bundle.schema.json","evidence-graph.json":"evidence-graph.schema.json","capability-registry.json":"capability-registry.schema.json","skill-registry.json":"skill-registry.schema.json","test-pyramid.json":"test-pyramid.schema.json","benchmark-corpus.json":"benchmark-corpus.schema.json","maintainability-profile.json":"maintainability-profile.schema.json","product-navigation.json":"product-navigation.schema.json","design-studio-plan.json":"design-studio-plan.schema.json","handoff-acceptance.json":"handoff-acceptance.schema.json","control-plane-modules.json":"control-plane-modules.schema.json","private-runner-profile.json":"private-runner-profile.schema.json","reference-route.json":"reference-route.schema.json","eval-suite.json":"eval-suite.schema.json","recipe-promotion.json":"recipe-promotion.schema.json","edition-profile.json":"edition-profile.schema.json","delivery-packages.json":"delivery-package.schema.json","deferred-capabilities.json":"deferred-capability.schema.json","reference-architecture.json":"reference-architecture.schema.json","roadmap.json":"roadmap.schema.json","design-partners.json":"design-partners.schema.json","delivery-model.json":"delivery-model.schema.json","sla-proof.json":"sla-proof.schema.json","certification.json":"certification.schema.json"}
def validate(pack):
 from jsonschema import Draft202012Validator
 pack=Path(pack); root=Path(__file__).resolve().parents[2]; schemas=root/"schemas/batch46-complete"
 for f,s in FILES.items():
  if not (pack/f).is_file(): fail("missing "+f)
  Draft202012Validator(load(schemas/s)).validate(load(pack/f))
 cap=load(pack/"capability-package.json")
 for k,v in cap["ownership"].items():
  if not non_placeholder(v): fail("placeholder owner "+k)
 return pack
def main():validate(sys.argv[1]);print("convergence pack schema ok")
if __name__=="__main__":main()
