from pathlib import Path
import json, hashlib, re, sys
HEX=set("0123456789abcdef")
def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def valid_digest(s): return isinstance(s,str) and len(s)==64 and set(s)<=HEX and len(set(s))>1
def file_sha(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for b in iter(lambda:f.read(1048576),b""): h.update(b)
 return h.hexdigest()

def main():
 d=load(sys.argv[1]); assert d['route_id']=='java-spring-to-csharp-aspnet-reference'
 r=d['repository_profile']; assert 100000<=r['loc_min']<=r['loc_max']<=500000; assert 5<=r['module_min']<=r['module_max']<=20
 req=set(d['required_capabilities']); need={'REST','authentication','authorization','database','transaction','messaging','cache','scheduler'}
 assert need<=req
 a=d['acceptance']; assert a['build_green_rate']==1.0 and a['p0_behavior_pass_rate']==1.0 and a['critical_unknowns']==0
 print('reference route plan ok')
if __name__=='__main__': main()
