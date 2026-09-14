"""Explicit Linux tmpfs qualification using synthetic credentials only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != 'linux': raise RuntimeError('Linux tmpfs required')
    java = Path(os.environ['ELMOS_TEST_JAVA_HOME']) / 'bin'
    names = ['SecretValue', 'SecretLease', 'SecretInjectionService', 'TmpfsSecretMaterializer']
    sources = [ROOT / ('modules/secret/src/main/java/io/elmos/secret/'+name+'.java') for name in names]
    sources.append(ROOT / 'modules/secret/src/test/java/io/elmos/secret/NativeTmpfsAcceptance.java')
    def hashes():
        return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sources + [Path(__file__)]}
    before = hashes()
    records = []
    with tempfile.TemporaryDirectory(prefix='elmos-tmpfs-classes-') as directory:
        for command in [[str(java/'java'), '-version'],
                        [str(java/'javac'), '-d', directory, *map(str, sources)],
                        [str(java/'java'), '-cp', directory, 'io.elmos.secret.NativeTmpfsAcceptance']]:
            result = subprocess.run(command, capture_output=True, timeout=120)
            records.append({'argv':command,'code':result.returncode,
                            'stdout':result.stdout.decode(errors='replace'),
                            'stderr':result.stderr.decode(errors='replace')})
            if result.returncode: break
    output = ROOT / 'docs/release-deployment/qualification'
    log = output/'tmpfs-native.json'
    log.write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
    passed = len(records) == 3 and all(r['code'] == 0 for r in records) and before == hashes()
    receipt = {'status':'LOCAL_NATIVE_EXECUTED' if passed else 'FAILED','files':hashes(),
        'source_unchanged_during_test':before == hashes(),
        'logs':{log.relative_to(ROOT).as_posix():hashlib.sha256(log.read_bytes()).hexdigest()},
        'toolchains':{name:hashlib.sha256((java/name).read_bytes()).hexdigest() for name in ('java','javac')},
        'scope':'Synthetic credential creation and cleanup on actual Linux tmpfs',
        'host_service_installation':'NOT_RUN','cloud_credentials':'NOT_RUN',
        'independent_verification':'NOT_RUN','certification':'NOT_CERTIFIED'}
    (output/'tmpfs-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(records,indent=2))
    print(receipt['status'])
    return 0 if passed else 1


if __name__ == '__main__': raise SystemExit(main())
