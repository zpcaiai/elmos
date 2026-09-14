#!/usr/bin/env python3
"""Replay bounded local qualification; never grant production certification."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from integrate_release_deployment_skills import ROOT, PIN, run

OPA_SHA='f910bc4f4e27fe27f861ec3ea4ec58ca859ec7245007df4d3ab6d53058745991'

def sha(raw): return hashlib.sha256(raw).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--opa',type=Path)
    args=parser.parse_args()
    run(check=True)
    engine=ROOT/'engines/release-deployment-engine'
    output=ROOT/'docs/release-deployment/qualification'
    output.mkdir(parents=True,exist_ok=True)
    def source_hashes():
        sources={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in sorted(engine.rglob('*'))
                 if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc'}}
        for name in ['tooling/integrate_release_deployment_skills.py','tooling/validate_release_deployment.py',
                     'tooling/validate_release_native.py',
                     'docs/release-deployment/source-manifest.json']:
            sources[name]=sha((ROOT/name).read_bytes())
        return sources
    before=source_hashes()
    started=time.time()
    command=[sys.executable,'-m','unittest','discover','-s',str(engine/'tests'),'-v']
    test_env = dict(os.environ)
    test_env['PYTHONPATH'] = str(engine/'src')
    result=subprocess.run(command,cwd=ROOT,env=test_env,capture_output=True,timeout=600)
    raw=result.stdout+result.stderr
    (output/'python-tests.txt').write_bytes(raw)
    print(raw.decode(errors='replace'))
    opa_state='NOT_RUN'; opa_log=b''
    if args.opa:
        binary=args.opa.resolve()
        if sha(binary.read_bytes())!=OPA_SHA:
            raise ValueError('unqualified OPA binary: use the reviewed OPA 1.0.0 Windows digest')
        opa=subprocess.run([str(binary),'test',str(engine/'policies'),'-v'],capture_output=True,timeout=60)
        opa_log=opa.stdout+opa.stderr
        (output/'opa-tests.txt').write_bytes(opa_log)
        print(opa_log.decode(errors='replace'))
        opa_state='PASS' if opa.returncode==0 else 'FAIL'
    import re
    match=re.search(rb'Ran (\d+) tests',raw)
    test_count=int(match.group(1)) if match else 0
    sources=source_hashes()
    passed=result.returncode==0 and test_count>0 and opa_state!='FAIL' and sources==before
    receipt={'schema':'rd.local-qualification.v1','source_archive_sha256':PIN,
        'status':'LOCAL_ENGINEERING_VALIDATED' if passed else 'FAILED',
        'python_tests':test_count,'python_status':'PASS' if result.returncode==0 else 'FAIL',
        'opa_status':opa_state,'python_log_sha256':sha(raw),
        'source_unchanged_during_test':sources==before,
        'opa_log_sha256':sha(opa_log) if args.opa else None,
        'wall_seconds':round(time.time()-started,3),'python':platform.python_version(),
        'platform':platform.platform(),'files':sources,
        'source_acceptance':{f'RD-AC-{n:02d}':'NOT_RUN' for n in range(1,26)},
        'cloud_execution':'NOT_RUN','docker_execution':'NOT_RUN','temporal_server_execution':'NOT_RUN',
        'independent_verification':'NOT_RUN','certification':'NOT_CERTIFIED',
        'package_functionally_complete':False}
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k not in {'files','source_acceptance'}},indent=2))
    return 0 if passed else 1

if __name__=='__main__': raise SystemExit(main())
