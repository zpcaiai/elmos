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

def verify_manifests(pack,refs):
 for ref in refs:
  mp=(pack/ref).resolve()
  if pack.resolve() not in mp.parents or not mp.is_file(): fail("invalid evidence manifest path")
  m=load(mp)
  if not valid_digest(m.get("artifact_sha256")) or not valid_digest(m.get("environment_sha256")): fail("invalid evidence digest")
  for f in m.get("files",[]):
   fp=(pack/f["path"]).resolve()
   if pack.resolve() not in fp.parents or not fp.is_file(): fail("invalid evidence file")
   if sha256(fp)!=f["sha256"]: fail("evidence tamper")
def main():
 pack=Path(sys.argv[1]).resolve(); c=load(pack/"certification.json")
 for k,v in c["owners"].items():
  if not non_placeholder(v): fail("placeholder certification owner "+k)
 if not all(c["kernel"].values()): fail("unified kernel incomplete")
 if c["reference_route"].get("certified") is not True: fail("reference route not certified")
 if c["private_runner"].get("certified") is not True: fail("private runner not certified")
 if c["design_partners"].get("accepted_count",0)<2: fail("two design partners required")
 if c["handoff"].get("passed") is not True: fail("handoff required")
 if len(c.get("verified_workloads",[]))<2: fail("two verified workloads required")
 if c["delivery_model"].get("passed") is not True: fail("profitable delivery model required")
 if c["sla_proof"].get("passed") is not True: fail("sla proof required")
 if c.get("zero_tolerance_findings"): fail("zero tolerance finding")
 if len(c.get("evidence_manifests",[]))<10: fail("insufficient evidence manifests")
 verify_manifests(pack,c["evidence_manifests"])
 # Cross-file strong validation.
 import importlib.util
 def mod(n):
  sp=importlib.util.spec_from_file_location(n,Path(__file__).with_name(n+".py")); m=importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
 mod("validate_dependency_graph").validate(pack/"dependency-graph.json")
 mod("validate_workflow_definition").validate(pack/"workflow-definition.json")
 mod("validate_policy_bundle").validate(pack/"policy-bundle.json")
 mod("validate_evidence_graph").validate(pack/"evidence-graph.json")
 mod("validate_skill_registry").validate(pack/"skill-registry.json")
 mod("validate_benchmark_corpus").validate(pack/"benchmark-corpus.json")
 mod("validate_reference_route").validate(pack/"reference-route.json",True)
 mod("validate_design_partners").validate(pack/"design-partners.json")
 mod("validate_delivery_model").validate(pack/"delivery-model.json")
 mod("validate_sla_proof").validate(pack/"sla-proof.json")
 print(json.dumps({"status":"passed","evaluated_at":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()},indent=2))
if __name__=="__main__":main()
