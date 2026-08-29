#!/usr/bin/env python3
import json,sys,math
s=json.load(open(sys.argv[1])); t=json.load(open(sys.argv[2])); cfg=json.load(open(sys.argv[3])) if len(sys.argv)>3 else {}
ignore=set(cfg.get('ignoreKeys',[])); tol=cfg.get('numericTolerance',0)
def norm(x):
 if isinstance(x,dict): return {k:norm(v) for k,v in sorted(x.items()) if k not in ignore}
 if isinstance(x,list): return [norm(v) for v in x]
 return x
def eq(a,b):
 if isinstance(a,(int,float)) and isinstance(b,(int,float)) and not isinstance(a,bool) and not isinstance(b,bool): return abs(a-b)<=tol
 if type(a)!=type(b): return False
 if isinstance(a,dict): return a.keys()==b.keys() and all(eq(a[k],b[k]) for k in a)
 if isinstance(a,list): return len(a)==len(b) and all(eq(x,y) for x,y in zip(a,b))
 return a==b
ns,nt=norm(s),norm(t); ok=eq(ns,nt); print(json.dumps({'verdict':'pass' if ok else 'fail','source':ns,'target':nt},indent=2)); raise SystemExit(0 if ok else 1)
