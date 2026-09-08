#!/usr/bin/env python3
"""Local references only; no actual Elmos repo/cloud/model execution."""
import argparse,io,json,platform,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'reference'),str(ROOT/'tests'),str(ROOT/'scripts')]
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path);a=p.parse_args();log=io.StringIO();start=time.perf_counter()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*.py');r=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    data=dict(status='pass' if r.wasSuccessful() else 'failed',tests_run=r.testsRun,failures=len(r.failures),errors=len(r.errors),skipped=len(r.skipped),duration_seconds=time.perf_counter()-start,python=platform.python_version(),environment_kind='local_reference',host_integration_verified=False,native_langgraph_verified=False,production_qualified=False)
    if a.output_dir:
        a.output_dir.mkdir(parents=True,exist_ok=True);(a.output_dir/'reference-tests.log').write_text(log.getvalue());(a.output_dir/'reference-tests.json').write_text(json.dumps(data,indent=2)+'\n')
    print(log.getvalue());print(json.dumps(data,indent=2));sys.exit(0 if r.wasSuccessful() else 1)
