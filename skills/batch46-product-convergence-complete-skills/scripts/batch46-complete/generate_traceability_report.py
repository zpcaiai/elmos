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

def main():
 root=Path(sys.argv[1] if len(sys.argv)>1 else "."); out=Path(sys.argv[2] if len(sys.argv)>2 else "TRACEABILITY.generated.md")
 rows=["# Report-to-Skill Traceability","","| Report topic | Skill |","|---|---|"]
 topics=[("统一产品元模型","1498"),("跨Batch依赖图","1499"),("Workflow Runtime","1501"),("Evidence Graph","1503"),("Policy Engine","1502"),("全局状态机","1500"),("Core与Extension边界","1506"),("Reference Route","1519"),("Skill分层","1507"),("Skill Registry/Compiler","1508"),("Skill去重","1509"),("测试金字塔","1510"),("Benchmark Corpus","1511"),("Maintainability Gate","1512"),("产品信息架构","1513"),("Migration Design Studio","1514"),("Customer Handoff","1515"),("Control Plane","1516"),("Private Runner","1517"),("确定性优先","1518"),("Edition收敛","1523"),("产品套餐","1524"),("Verified Migrated Workload","1525")]
 for t,s in topics: rows.append(f"| {t} | Skill {s} |")
 out.write_text("\n".join(rows)+"\n",encoding="utf-8");print(out)
if __name__=="__main__":main()
