from __future__ import annotations
import hashlib,json
def digest(obj)->str:return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
def append_entry(chain:list[dict],artifact_hash:str,producer:str)->dict:
    prev=chain[-1]["entryHash"] if chain else "0"*64
    entry={"sequence":len(chain)+1,"previousHash":prev,"artifactHash":artifact_hash,"producer":producer}
    entry["entryHash"]=digest(entry);chain.append(entry);return entry
def verify_chain(chain:list[dict])->bool:
    prev="0"*64
    for i,e in enumerate(chain,1):
        if e.get("sequence")!=i or e.get("previousHash")!=prev:return False
        raw={k:v for k,v in e.items() if k!="entryHash"}
        if digest(raw)!=e.get("entryHash"):return False
        prev=e["entryHash"]
    return True
def merkle_root(hashes:list[str])->str:
    if not hashes:return digest("")
    level=list(hashes)
    while len(level)>1:
        if len(level)%2:level.append(level[-1])
        level=[hashlib.sha256((level[i]+level[i+1]).encode()).hexdigest() for i in range(0,len(level),2)]
    return level[0]
