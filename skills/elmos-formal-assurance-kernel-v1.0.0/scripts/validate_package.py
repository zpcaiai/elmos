#!/usr/bin/env python3
from __future__ import annotations
import compileall
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict, deque
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SKILL_FILES = {"SKILL.md","manifest.yaml","acceptance.yaml","implementation.yaml","runbook.md"}

class Validation:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checks: list[dict] = []

    def check(self, name: str, ok: bool, detail: str = ""):
        self.checks.append({"name":name,"result":"PASS" if ok else "FAIL","detail":detail})
        if not ok:
            self.errors.append(f"{name}: {detail}")

    def warn(self, message: str):
        self.warnings.append(message)

def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def check_dag(nodes: set[str], edges: dict[str,list[str]]) -> tuple[bool,str]:
    indegree={n:0 for n in nodes}
    out=defaultdict(list)
    for node,deps in edges.items():
        for dep in deps:
            if dep not in nodes:
                return False,f"{node} references unknown dependency {dep}"
            indegree[node]+=1
            out[dep].append(node)
    queue=deque(sorted(n for n,d in indegree.items() if d==0))
    seen=[]
    while queue:
        n=queue.popleft()
        seen.append(n)
        for nxt in out[n]:
            indegree[nxt]-=1
            if indegree[nxt]==0:
                queue.append(nxt)
    if len(seen)!=len(nodes):
        return False,f"cycle among {sorted(n for n,d in indegree.items() if d>0)}"
    return True,f"{len(nodes)} nodes"

def run_command(command: list[str], *, env: dict | None = None) -> tuple[int,str]:
    proc=subprocess.run(command,cwd=ROOT,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    return proc.returncode,proc.stdout

def main() -> int:
    v=Validation()
    required_root=[
      "README.md","PACKAGE_MANIFEST.yaml","SKILLS_INDEX.md","LICENSE-POLICY.md","SECURITY.md",
      "CHANGELOG.md","Makefile","pyproject.toml","requirements-dev.txt"
    ]
    v.check("required-root-files",all((ROOT/x).is_file() for x in required_root),
            ", ".join(x for x in required_root if not (ROOT/x).is_file()))

    all_yaml=list(ROOT.rglob("*.yaml"))+list(ROOT.rglob("*.yml"))
    helm_templates=[p for p in all_yaml if "deploy/helm" in p.as_posix() and "/templates/" in p.as_posix()]
    yaml_files=[p for p in all_yaml if p not in helm_templates]
    yaml_errors=[]
    for path in yaml_files:
        try: load_yaml(path)
        except Exception as exc: yaml_errors.append(f"{path.relative_to(ROOT)}: {exc}")
    v.check("yaml-parse",not yaml_errors,f"{len(yaml_files)} plain YAML files; " + "; ".join(yaml_errors[:5]))
    helm_errors=[]
    for path in helm_templates:
        content=path.read_text(encoding="utf-8")
        if "apiVersion:" not in content or "kind:" not in content:
            helm_errors.append(f"{path.relative_to(ROOT)}: missing Kubernetes resource markers")
        if "{{" not in content:
            helm_errors.append(f"{path.relative_to(ROOT)}: expected Helm template expressions")
    v.check("helm-template-contracts",not helm_errors,f"{len(helm_templates)} templates; " + "; ".join(helm_errors[:5]))

    json_files=list(ROOT.rglob("*.json"))
    json_errors=[]
    for path in json_files:
        try: load_json(path)
        except Exception as exc: json_errors.append(f"{path.relative_to(ROOT)}: {exc}")
    v.check("json-parse",not json_errors,f"{len(json_files)} files; " + "; ".join(json_errors[:5]))

    skill_dirs=sorted(p for p in ROOT.glob("skills/P*/*") if p.is_dir())
    skill_names=set()
    manifests={}
    skill_errors=[]
    for d in skill_dirs:
        files={p.name for p in d.iterdir() if p.is_file()}
        if files != REQUIRED_SKILL_FILES:
            skill_errors.append(f"{d.relative_to(ROOT)} files={sorted(files)}")
            continue
        m=load_yaml(d/"manifest.yaml")
        name=m.get("metadata",{}).get("name")
        if name != d.name:
            skill_errors.append(f"{d.relative_to(ROOT)} manifest name={name}")
        if name in skill_names:
            skill_errors.append(f"duplicate skill {name}")
        skill_names.add(name)
        manifests[name]=m
        md=(d/"SKILL.md").read_text(encoding="utf-8")
        for section in ["## 1. 业务目标","## 9. 失败语义","## 10. 安全与多租户","## 12. 商业发布边界"]:
            if section not in md:
                skill_errors.append(f"{name}: missing section {section}")
        acceptance=load_yaml(d/"acceptance.yaml")
        ids=[t["id"] for t in acceptance["spec"]["tests"]]
        if len(ids)!=len(set(ids)):
            skill_errors.append(f"{name}: duplicate acceptance IDs")
        text=(d/"acceptance.yaml").read_text(encoding="utf-8")
        if "BOUNDED_NO_COUNTEREXAMPLE" not in text or "REFUTED_WITH_COUNTEREXAMPLE" not in text:
            skill_errors.append(f"{name}: missing honesty/counterexample acceptance cases")
    v.check("skill-contracts",not skill_errors,f"{len(skill_dirs)} skills, {len(skill_dirs)*5} files; " + "; ".join(skill_errors[:10]))

    edges={name:m["spec"].get("dependencies",[]) for name,m in manifests.items()}
    ok,detail=check_dag(skill_names,edges)
    v.check("skill-dependency-dag",ok,detail)

    priority_counts=Counter(m["metadata"]["priority"] for m in manifests.values())
    domain_counts=Counter(m["metadata"]["domain"] for m in manifests.values())
    v.check("skill-priority-domain",set(priority_counts)<= {"P0","P1","P2"},
            f"priority={dict(priority_counts)}, domain={dict(domain_counts)}")

    schemas={}
    registry=Registry()
    schema_errors=[]
    for path in sorted((ROOT/"contracts/schemas").glob("*.schema.json")):
        try:
            schema=load_json(path)
            Draft202012Validator.check_schema(schema)
            schemas[path.stem.replace(".schema","")]=schema
            registry=registry.with_resource(schema["$id"],Resource.from_contents(schema))
        except Exception as exc:
            schema_errors.append(f"{path.name}: {exc}")
    v.check("json-schema-meta-validation",not schema_errors,f"{len(schemas)} schemas; " + "; ".join(schema_errors[:5]))

    example_errors=[]
    for path in sorted((ROOT/"contracts/examples").glob("*.example.json")):
        name=path.name.removesuffix(".example.json")
        schema=schemas.get(name)
        if not schema:
            example_errors.append(f"{path.name}: missing schema")
            continue
        try:
            Draft202012Validator(schema,registry=registry,format_checker=FormatChecker()).validate(load_json(path))
        except Exception as exc:
            example_errors.append(f"{path.name}: {exc}")
    v.check("contract-examples",not example_errors,
            f"{len(list((ROOT/'contracts/examples').glob('*.example.json')))} examples; " + "; ".join(example_errors[:5]))

    adapter_schema=schemas.get("verifier-adapter")
    adapter_errors=[]
    adapter_paths=sorted(ROOT.glob("verifier-adapters/*/adapter.yaml"))
    if adapter_schema:
        validator=Draft202012Validator(adapter_schema,registry=registry,format_checker=FormatChecker())
        for path in adapter_paths:
            try:
                adapter=load_yaml(path)
                validator.validate(adapter)
                if adapter["metadata"]["name"]!=path.parent.name:
                    adapter_errors.append(f"{path}: folder/name mismatch")
                if adapter["spec"]["security"]["network"]!="deny" or adapter["spec"]["security"]["secrets"]!="none":
                    adapter_errors.append(f"{path}: sandbox not fail closed")
            except Exception as exc:
                adapter_errors.append(f"{path.relative_to(ROOT)}: {exc}")
    v.check("verifier-adapters",not adapter_errors,f"{len(adapter_paths)} adapters; " + "; ".join(adapter_errors[:5]))

    workflow_errors=[]
    for path in sorted((ROOT/"workflows").glob("*.yaml")):
        w=load_yaml(path)
        steps=w["spec"]["steps"]
        ids={s["id"] for s in steps}
        if len(ids)!=len(steps):
            workflow_errors.append(f"{path.name}: duplicate step ID")
        local_edges={}
        for step in steps:
            if step["skillRef"] not in skill_names:
                workflow_errors.append(f"{path.name}: unknown skill {step['skillRef']}")
            local_edges[step["id"]]=step.get("dependsOn",[])
        ok,detail=check_dag(ids,local_edges)
        if not ok: workflow_errors.append(f"{path.name}: {detail}")
    v.check("workflows",not workflow_errors,
            f"{len(list((ROOT/'workflows').glob('*.yaml')))} workflows; " + "; ".join(workflow_errors[:5]))

    profile_errors=[]
    for path in sorted((ROOT/"profiles").glob("*.yaml")):
        p=load_yaml(path)
        unknown=set(p["spec"]["skills"])-skill_names
        if unknown: profile_errors.append(f"{path.name}: {sorted(unknown)}")
    v.check("install-profiles",not profile_errors,
            f"{len(list((ROOT/'profiles').glob('*.yaml')))} profiles; " + "; ".join(profile_errors[:5]))

    route_errors=[]
    for path in sorted(ROOT.glob("golden-routes/*/route.yaml")):
        r=load_yaml(path)
        unknown=set(r["spec"]["requiredSkills"])-skill_names
        if unknown: route_errors.append(f"{path}: unknown skills {sorted(unknown)}")
        phases=[x["id"] for x in r["spec"]["phases"]]
        if phases!=["E1_STATIC","E2_MODEL","E3_DIFFERENTIAL","E4_FAILURE_INJECTION","E5_CUSTOMER_GOLDEN_ROUTE"]:
            route_errors.append(f"{path}: invalid phase sequence")
    v.check("golden-routes",not route_errors,
            f"{len(list(ROOT.glob('golden-routes/*/route.yaml')))} routes; " + "; ".join(route_errors[:5]))

    migration_paths=sorted((ROOT/"db/migration").glob("V*.sql"))
    versions=[re.match(r"V(\d+)__",p.name).group(1) for p in migration_paths if re.match(r"V(\d+)__",p.name)]
    sql_text="\n".join(p.read_text(encoding="utf-8") for p in migration_paths)
    migration_ok=(
      len(versions)==len(migration_paths)==len(set(versions))
      and "ENABLE ROW LEVEL SECURITY" in sql_text
      and "reject_artifact_mutation" in sql_text
      and "guard_proof_status" in sql_text
      and "fencing_token" in sql_text
    )
    v.check("postgres-migrations",migration_ok,f"{len(migration_paths)} ordered migrations")

    rego_modules=[p for p in (ROOT/"policies/rego").glob("*.rego") if not p.name.endswith("_test.rego")]
    rego_tests=list((ROOT/"policies/rego").glob("*_test.rego"))
    rego_text="\n".join(p.read_text(encoding="utf-8") for p in rego_modules)
    v.check("rego-policy-contracts",
            len(rego_modules)==6 and len(rego_tests)==6 and "BOUNDED_NO_COUNTEREXAMPLE" in rego_text and "unknown result cannot pass" in rego_text,
            f"{len(rego_modules)} modules, {len(rego_tests)} tests (OPA execution is external)")

    manifest=load_yaml(ROOT/"PACKAGE_MANIFEST.yaml")
    counts=manifest["spec"]["counts"]
    actual={
      "skills":len(skill_dirs),"perSkillFiles":len(skill_dirs)*5,
      "jsonSchemas":len(list((ROOT/"contracts/schemas").glob("*.schema.json"))),
      "schemaExamples":len(list((ROOT/"contracts/examples").glob("*.example.json"))),
      "postgresMigrations":len(migration_paths),
      "openApiContracts":len(list((ROOT/"contracts/openapi").glob("*.yaml"))),
      "asyncApiContracts":len(list((ROOT/"contracts/events").glob("*.yaml"))),
      "regoModules":len(rego_modules),"regoTests":len(rego_tests),
      "verifierAdapters":len(adapter_paths),
      "workflows":len(list((ROOT/"workflows").glob("*.yaml"))),
      "goldenRoutes":len(list(ROOT.glob("golden-routes/*/route.yaml"))),
      "installProfiles":len(list((ROOT/"profiles").glob("*.yaml"))),
    }
    count_mismatches={k:(counts.get(k),val) for k,val in actual.items() if counts.get(k)!=val}
    v.check("package-manifest-counts",not count_mismatches,str(count_mismatches or actual))

    registry_file=load_json(ROOT/"skills/registry.generated.json")
    index_file=load_yaml(ROOT/"skills/index.yaml")
    catalog_names={x["id"] for x in registry_file["skills"]}
    index_names={x["name"] for x in index_file["spec"]["skills"]}
    v.check("generated-catalog",catalog_names==skill_names==index_names,
            f"registry={len(catalog_names)}, index={len(index_names)}, skills={len(skill_names)}")

    md_errors=[]
    link_re=re.compile(r"\[[^\]]+\]\((?!https?://|mailto:|#)([^)]+)\)")
    for path in ROOT.rglob("*.md"):
        text=path.read_text(encoding="utf-8")
        for target in link_re.findall(text):
            clean=target.split("#",1)[0]
            if clean and not (path.parent/clean).resolve().exists():
                md_errors.append(f"{path.relative_to(ROOT)} -> {target}")
    v.check("local-markdown-links",not md_errors,f"{len(md_errors)} broken; " + "; ".join(md_errors[:5]))

    placeholder_hits=[]
    for path in list(ROOT.glob("verifier-adapters/*/adapter.yaml"))+[ROOT/"deploy/Dockerfile"]:
        if not path.exists(): continue
        text=path.read_text(encoding="utf-8")
        for token in ["REPLACE_WITH_SIGNED_DIGEST","REPLACE_WITH_RELEASE_TIME_PINNED_DIGEST"]:
            if token in text: placeholder_hits.append(f"{path.relative_to(ROOT)}:{token}")
    if placeholder_hits:
        v.warn(f"{len(placeholder_hits)} release-time digest placeholders remain by design")

    compile_ok=compileall.compile_dir(ROOT/"reference-kernel",quiet=1,force=True)
    compile_ok=compileall.compile_dir(ROOT/"scripts",quiet=1,force=True) and compile_ok
    v.check("python-compile",compile_ok,"reference kernel and scripts")

    env=dict(os.environ)
    env["PYTHONPATH"]=str(ROOT/"reference-kernel")
    code,out=run_command([sys.executable,"-m","unittest","discover","-s","reference-kernel/tests","-v"],env=env)
    match=re.search(r"Ran (\d+) tests",out)
    v.check("reference-kernel-tests",code==0,f"{match.group(1) if match else '?'} tests; " + ("" if code==0 else out[-1500:]))

    code,out=run_command([sys.executable,"scripts/run_reference_kernel_demo.py"],env=env)
    v.check("reference-kernel-demo",code==0,out.strip().replace("\n"," ")[:500])

    with tempfile.TemporaryDirectory() as td:
        target=Path(td)/"elmos"
        target.mkdir()
        code_i,out_i=run_command([sys.executable,"scripts/install.py",str(target),"--profile","core"],env=env)
        code_u,out_u=run_command([sys.executable,"scripts/uninstall.py",str(target)],env=env) if code_i==0 else (99,"")
        v.check("installer-roundtrip",code_i==0 and code_u==0,(out_i+" "+out_u).strip()[:500])

    report={
      "packageId":manifest["metadata"]["packageId"],
      "generatedAt":manifest["metadata"]["releaseDate"]+"T00:00:00Z",
      "status":"PASS" if not v.errors else "FAIL",
      "checks":v.checks,"warnings":v.warnings,"errors":v.errors,
      "actualCounts":actual,
    }
    (ROOT/"VALIDATION-REPORT.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

    print(f"Package: {report['packageId']}")
    for check in v.checks:
        print(f"[{check['result']}] {check['name']}: {check['detail']}")
    for warning in v.warnings:
        print(f"[WARN] {warning}")
    if v.errors:
        print(f"FAIL: {len(v.errors)} error(s)")
        return 1
    print(f"PASS: {len(v.checks)} checks, {len(v.warnings)} warning(s)")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
