#!/usr/bin/env python3
"""Run approved real Terraform/Helm qualification against disposable local fixtures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
TOOLS={
    'terraform':{'version':'1.13.5','binary_sha256':'37095373bcf2775655502ac42bcfbcbac2927a351952a2c9c478072782a96e1c',
        'archive_sha256':'73f97943c93f268ae2c645b2a737d552175aa64d00a5c8b8f5ccc5831c033c8a',
        'source':'https://releases.hashicorp.com/terraform/1.13.5/'},
    'helm':{'version':'3.19.0','binary_sha256':'a18c49a4cd16f8b162031159eff6b4d657e04ec2df0c2be5544ad11ddf8fae79',
        'archive_sha256':'6488630c2e5d5945ed990fa02fd9e99f9c6792cdbcd79eb264b6cfb90179d2d1',
        'source':'https://get.helm.sh/helm-v3.19.0-windows-amd64.zip.sha256sum'}}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--terraform',type=Path,required=True)
    parser.add_argument('--helm',type=Path,required=True)
    args=parser.parse_args()
    if sys.platform != 'win32': raise ValueError('This qualified tool tuple is Windows amd64 only')
    engine=ROOT/'engines/release-deployment-engine'
    output=ROOT/'docs/release-deployment/qualification'
    output.mkdir(parents=True,exist_ok=True)
    def sources():
        paths=[p for p in engine.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
        paths.append(Path(__file__))
        return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    before=sources()
    environment=dict(os.environ)
    environment['PYTHONPATH']=str(engine/'src')
    for tool,pin in TOOLS.items():
        path=getattr(args,tool).resolve(strict=True)
        if hashlib.sha256(path.read_bytes()).hexdigest() != pin['binary_sha256']:
            raise ValueError(tool+' binary is not the approved digest')
        environment['ELMOS_TEST_'+tool.upper()]=str(path)
        environment['ELMOS_TEST_'+tool.upper()+'_SHA256']=pin['binary_sha256']
    commands=output/'native-commands.jsonl'
    commands.write_bytes(b'')
    environment['ELMOS_NATIVE_TEST_LOG']=str(commands)
    started=time.monotonic()
    result=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(engine/'native-tests'),'-v'],
                          env=environment,cwd=ROOT,capture_output=True,timeout=300)
    raw=result.stdout+result.stderr
    (output/'native-tests.txt').write_bytes(raw)
    after=sources()
    entries=[json.loads(line) for line in commands.read_text(encoding='utf-8').splitlines()]
    passed=result.returncode == 0 and before == after and len(entries) >= 10
    receipt={'schema':'rd.native-local-qualification.v1','status':'LOCAL_NATIVE_EXECUTED' if passed else 'FAILED',
        'platform':platform.platform(),'toolchains':TOOLS,'tests':3,'native_processes':len(entries),
        'wall_seconds':round(time.monotonic()-started,3),'source_unchanged_during_test':before == after,
        'files':after,'logs':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (commands,output/'native-tests.txt')},
        'cloud_execution':'NOT_RUN','container_isolation':'NOT_RUN','independent_verification':'NOT_RUN',
        'certification':'NOT_CERTIFIED','scope':'Synthetic terraform_data apply/refresh/destroy and dependency-free Helm rendering'}
    (output/'native-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(raw.decode(errors='replace'))
    print(json.dumps({k:v for k,v in receipt.items() if k not in {'files','logs'}},indent=2))
    return 0 if passed else 1


if __name__ == '__main__': raise SystemExit(main())
