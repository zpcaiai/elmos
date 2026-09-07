#!/usr/bin/env python3
import argparse,json,pathlib
p=argparse.ArgumentParser(); p.add_argument('--registry',default='route-certification-registry.json'); p.add_argument('--route',required=True); p.add_argument('--level',default='E5'); p.add_argument('--out',required=True); a=p.parse_args()
r=json.load(open(a.registry)); item=next((x for x in r['spec']['routes'] if x['route']==a.route),None)
if not item: raise SystemExit('unknown route')
d={'route':a.route,'targetLevel':a.level,'requiredSemanticSkills':item['requiredSemanticSkills'],'runtimeLabs':item['requiredLabs'],'obligations':[],'corpora':[],'formalMethods':[],'stressMethods':[],'status':'not-run'}
pathlib.Path(a.out).write_text(json.dumps(d,indent=2)+'\n'); print(a.out)
