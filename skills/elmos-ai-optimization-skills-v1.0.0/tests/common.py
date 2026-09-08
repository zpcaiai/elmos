from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'reference'),str(ROOT/'scripts')]
from elmos_opt.retrieval import *
def doc(id='d1',text='def cancel_order(): return True',**kw):
    blob=text.encode();d=dict(id=id,tenant='acme',repository='shop',snapshot='s1',generation='g1',path=id+'.py',symbol='cancel_order',blob=blob,start=0,end=len(blob),vector=(1.,0.,0.));d.update(kw);return Document(**d)
def system(docs=None):
    a=Authority();a.set_grants('acme','alice',['shop']);s=a.resolve('acme','alice',[Revision('shop','s1','g1')]);c=Corpus([doc()] if docs is None else docs);return a,s,c,EvidenceService(c,a)
VERSIONS={k:'1' for k in ['retrieval','embedding','reranker','tokenizer','prompt','model','redaction']}
