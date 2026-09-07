#!/usr/bin/env python3
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'reference'))
from elmos_opt.retrieval import Document,Authority,Revision,Corpus,Request,EvidenceService
from elmos_opt.evaluation import ranked_metrics

def main():
    docs=[]
    for row in json.loads((ROOT/'fixtures/corpus.json').read_text()):
        row=dict(row);blob=row.pop('text').encode();row['vector']=tuple(row['vector']);docs.append(Document(**row,blob=blob,start=0,end=len(blob)))
    auth=Authority();auth.set_grants('acme','learner',['shop','migration']);scope=auth.resolve('acme','learner',[Revision('shop','s1','g1'),Revision('migration','s1','g1')]);service=EvidenceService(Corpus(docs),auth);results=[]
    for q in json.loads((ROOT/'fixtures/queries.json').read_text()):
        start=time.perf_counter();v=service.query(scope,Request(query=q['query'],mode=q['mode'],symbol=q.get('symbol'),query_vector=tuple(q.get('query_vector',[])),top_k=5));ms=(time.perf_counter()-start)*1000;ids=[i['id'] for i in v['items']]
        assert not set(ids)&{'old-expiry','other-tenant','private-repo'}
        results.append(dict(id=q['id'],route=q['mode'],returned_ids=ids,metrics=ranked_metrics(ids,q['qrels']),elapsed_ms=ms))
    return dict(status='pass',cases=len(results),answerable=sum(x['metrics']['answerable'] for x in results),unanswerable=sum(not x['metrics']['answerable'] for x in results),model_calls=0,embedding_calls=0,vector_origin='handcrafted fixture',scope_leaks=0,production_benchmark=False,results=results)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);a=p.parse_args();text=json.dumps(main(),ensure_ascii=False,indent=2)
    if a.output:a.output.write_text(text+'\n')
    else:print(text)
