#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'reference'))
from elmos_opt.evaluation import preflight_release
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('report',type=Path);p.add_argument('--artifact-root',type=Path,default=ROOT);a=p.parse_args()
    try:r=preflight_release(json.loads(a.report.read_text()),a.artifact_root)
    except Exception as e:r={'local_precheck':'blocked','production_allowed':False,'reasons':[str(e)]}
    print(json.dumps(r,indent=2));sys.exit(2 if r['local_precheck']=='blocked' else 0)
