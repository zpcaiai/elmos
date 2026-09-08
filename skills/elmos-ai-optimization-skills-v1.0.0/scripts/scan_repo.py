#!/usr/bin/env python3
"""Bounded filename-only inventory. Does NOT execute code or infer implementation status."""
import argparse,json,os
from pathlib import Path
SKIP={'.git','node_modules','.venv','venv','vendor','target','dist','build','.next','__pycache__'}
HINTS={'retrieval':['retriev','search','embed','vector'],'semantic':['semantic','symbol','index','lsp','graph'],'auth':['auth','permission','lease','capability'],'execution':['harness','workflow','executor','temporal'],'model':['llm','model','provider'],'evaluation':['eval','benchmark','certification'],'skills':['skill','agents.md']}
def scan(root,max_files=50000):
    if root.is_symlink() or not root.is_dir() or not 1<=max_files<=200000:raise ValueError('root/budget')
    out={k:[] for k in HINTS};count=0;partial=False
    for parent,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in SKIP and not(Path(parent)/d).is_symlink())
        for name in sorted(files):
            p=Path(parent)/name
            if p.is_symlink() or name.startswith('.env') or name.endswith(('.pem','.key','.p12')):continue
            count+=1
            if count>max_files:partial=True;break
            rel=p.relative_to(root).as_posix()
            for category,words in HINTS.items():
                if len(out[category])<100 and any(w in rel.lower() for w in words):out[category].append(rel)
        if partial:break
    return dict(schema_version='ao.v1',root=str(root.resolve()),files_examined=min(count,max_files),partial=partial,candidate_paths=out,status='needs_source_review',secrets_read=False,repository_commands_executed=False,note='Filename hints only; no candidates does NOT establish missing implementation.')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',required=True,type=Path);p.add_argument('--max-files',type=int,default=50000);p.add_argument('--output',type=Path);a=p.parse_args();text=json.dumps(scan(a.repo,a.max_files),ensure_ascii=False,indent=2)
    if a.output:
        with a.output.open('x') as f:f.write(text+'\n')
    else:print(text)
