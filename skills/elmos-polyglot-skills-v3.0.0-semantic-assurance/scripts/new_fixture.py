#!/usr/bin/env python3
import argparse,json,hashlib,pathlib
p=argparse.ArgumentParser(); p.add_argument('--route',required=True); p.add_argument('--id',required=True); p.add_argument('--source-ref',required=True); p.add_argument('--out',required=True); a=p.parse_args()
d={'fixtureId':a.id,'route':a.route,'source':{'repository':a.source_ref,'commit':'PIN-ME'},'provenance':{'origin':'unclassified','capturedAt':'PIN-ME'},'license':'REVIEW-REQUIRED','sensitivity':'unclassified','semanticTags':[],'hash':'PENDING','expectedOracles':[]}
pathlib.Path(a.out).write_text(json.dumps(d,indent=2)+'\n'); print(a.out)
