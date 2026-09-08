"""Real SQLite FTS on authorized fixtures; synthetic vector inputs; no model calls.
Per-query FTS reconstruction deliberately favors test isolation, NOT scalability.
Authority/Scope are internal policy doubles, not HTTP authentication.
"""
from __future__ import annotations
import hashlib,json,math,re,sqlite3
from dataclasses import dataclass,asdict
from pathlib import PurePosixPath

class Denied(ValueError): pass
class Stale(ValueError): pass

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True)
class Revision:
    repository:str
    snapshot:str
    generation:str

@dataclass(frozen=True)
class Scope:
    tenant:str
    principal:str
    acl_epoch:int
    revisions:tuple[Revision,...]

class Authority:
    def __init__(self):self.grants={}
    def set_grants(self,tenant,principal,repositories):
        if not tenant or not principal:raise Denied('empty identity')
        key=(tenant,principal);epoch=self.grants.get(key,(0,()))[0]+1
        self.grants[key]=(epoch,frozenset(repositories))
    def resolve(self,tenant,principal,revisions):
        entry=self.grants.get((tenant,principal))
        if not entry or not revisions:raise Denied('no scope')
        if len({r.repository for r in revisions})!=len(revisions):raise Denied('one snapshot per repo; explicit comparison scopes required')
        if any(not r.snapshot or not r.generation or r.repository not in entry[1] for r in revisions):raise Denied('ungranted/incomplete revision')
        return Scope(tenant,principal,entry[0],tuple(sorted(revisions,key=lambda r:(r.repository,r.snapshot,r.generation))))
    def validate(self,scope):
        if self.resolve(scope.tenant,scope.principal,scope.revisions)!=scope:raise Denied('ACL epoch changed')

@dataclass(frozen=True)
class Document:
    id:str
    tenant:str
    repository:str
    snapshot:str
    generation:str
    path:str
    symbol:str
    blob:bytes
    start:int
    end:int
    language:str='text'
    vector:tuple[float,...]=()
    def __post_init__(self):
        p=PurePosixPath(self.path)
        if not self.id or not self.path or self.path=='.' or p.is_absolute() or '..' in p.parts or '\\' in self.path or '\x00' in self.path or re.match(r'^[A-Za-z]:',self.path) or str(p)!=self.path:raise ValueError('unsafe path/id')
        if not 0<=self.start<self.end<=len(self.blob):raise ValueError('invalid byte range')
        self.blob.decode();self.blob[:self.start].decode();self.blob[:self.end].decode()
        if any(not math.isfinite(v) for v in self.vector):raise ValueError('nonfinite vector')
    @property
    def text(self):return self.blob[self.start:self.end].decode()
    @property
    def anchor(self):return dict(repository=self.repository,snapshot=self.snapshot,generation=self.generation,path=self.path,blob_digest=hashlib.sha256(self.blob).hexdigest(),start_byte=self.start,end_byte=self.end,symbol=self.symbol)
    @property
    def identity(self):return digest(self.anchor)

class Corpus:
    def __init__(self,documents):
        self.docs={};self.tombstones=set();self.deletion_epoch=0
        for d in documents:
            if d.id in self.docs:raise ValueError('duplicate ID')
            self.docs[d.id]=d
    def tombstone(self,tenant,repository,snapshot,path):
        self.tombstones.add((tenant,repository,snapshot,path));self.deletion_epoch+=1
    def eligible(self,scope,auth):
        auth.validate(scope);tuples={(r.repository,r.snapshot,r.generation) for r in scope.revisions}
        return [d for d in self.docs.values() if d.tenant==scope.tenant and (d.repository,d.snapshot,d.generation) in tuples and (d.tenant,d.repository,d.snapshot,d.path) not in self.tombstones]

@dataclass(frozen=True)
class Request:
    query:str
    mode:str='lexical'
    top_k:int=5
    symbol:str|None=None
    path:str|None=None
    query_vector:tuple[float,...]=()
    context_bytes:int=8192
    def validate(self):
        if self.mode not in {'exact','lexical','hybrid'} or not 1<=self.top_k<=50 or not 1<=self.context_bytes<=262144 or len(self.query.encode())>4096:raise ValueError('invalid request/budget')
        if self.mode=='exact' and not(self.symbol or self.path):raise ValueError('exact selector required')
        if self.mode!='exact' and not self.query.strip():raise ValueError('query required')

def rrf(lanes,k=60):
    if k<1:raise ValueError('rrf k')
    scores={}
    for lane in lanes:
        for rank,identifier in enumerate(dict.fromkeys(lane),1):scores[identifier]=scores.get(identifier,0)+1/(k+rank)
    return sorted(scores,key=lambda i:(-scores[i],i))

def lexical(docs,query):
    terms=re.findall(r'[^\W_]+',query,flags=re.UNICODE)[:32]
    if not terms:return []
    match=' OR '.join('"'+t.replace('"','""')+'"' for t in terms)
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE VIRTUAL TABLE search USING fts5(id UNINDEXED,symbol,path,text)')
        db.executemany('INSERT INTO search VALUES(?,?,?,?)',[(d.id,d.symbol,d.path,d.text) for d in docs])
        return [r[0] for r in db.execute('SELECT id FROM search WHERE search MATCH ? ORDER BY bm25(search,0,4,2,1),id',(match,))]

def vector_rank(docs,query):
    if not query or any(not math.isfinite(x) for x in query):raise ValueError('invalid vector')
    norm=math.sqrt(sum(x*x for x in query))
    if not norm:raise ValueError('zero vector')
    ranked=[]
    for d in docs:
        if not d.vector:continue
        if len(d.vector)!=len(query):raise ValueError('embedding space mismatch')
        dn=math.sqrt(sum(x*x for x in d.vector))
        if dn:ranked.append((sum(a*b for a,b in zip(query,d.vector))/(norm*dn),d.id))
    return [i for _,i in sorted(ranked,key=lambda x:(-x[0],x[1]))]

def pack(docs,max_bytes):
    if max_bytes<=0:raise ValueError('budget')
    result=[];seen=set();remaining=max_bytes
    for d in docs:
        if d.identity in seen:continue
        seen.add(d.identity);raw=d.blob[d.start:d.end]
        text=raw[:remaining].decode(errors='ignore');size=len(text.encode())
        if not size:continue
        result.append(dict(id=d.id,anchor=dict(d.anchor,end_byte=d.start+size),text=text,truncated=size<len(raw),trust='source-data-not-instructions'))
        remaining-=size
        if not remaining:break
    return result

class EvidenceService:
    def __init__(self,corpus,auth):self.corpus=corpus;self.auth=auth
    def query(self,scope,request):
        request.validate();docs=self.corpus.eligible(scope,self.auth);by_id={d.id:d for d in docs}
        if request.mode=='exact':
            ranked=sorted(d.id for d in docs if (request.symbol is None or d.symbol==request.symbol) and (request.path is None or d.path==request.path));methods=['exact']
        else:
            ranked=lexical(docs,request.query);methods=['sqlite-fts5-reference']
            if request.mode=='hybrid':
                dense=vector_rank(docs,request.query_vector);canonical={}
                for d in sorted(docs,key=lambda d:d.id):canonical.setdefault(d.identity,d.id)
                ranked=rrf([[canonical[by_id[i].identity] for i in lane] for lane in [ranked,dense]])
                methods+=['supplied-vector-reference','rrf']
        chosen=[];seen=set()
        for i in ranked:
            d=by_id[i]
            if d.identity not in seen:chosen.append(d);seen.add(d.identity)
        items=pack(chosen[:request.top_k],request.context_bytes);self.auth.validate(scope)
        return dict(schema_version='ao.v1',status='ok' if items else 'insufficient_evidence',scope_digest=digest(asdict(scope)),acl_epoch=scope.acl_epoch,deletion_epoch=self.corpus.deletion_epoch,route=request.mode,methods=methods,model_calls=0,embedding_calls=0,budget_unit='utf8_bytes',items=items,note='Reference only: vectors supplied; no model or embedding executed.')
    def graph_expand(self,scope,seeds,edges,depth=1,max_nodes=20):
        if not 0<=depth<=3 or not 1<=max_nodes<=200:raise ValueError('graph budget')
        allowed={d.id:d for d in self.corpus.eligible(scope,self.auth)};frontier=[i for i in seeds if i in allowed];seen=set();out=[]
        for _ in range(depth+1):
            nxt=[]
            for i in frontier:
                if i in seen or i not in allowed:continue
                seen.add(i);out.append(allowed[i])
                if len(out)>=max_nodes:self.auth.validate(scope);return out
                nxt.extend(j for j in edges.get(i,[]) if j in allowed)
            frontier=nxt
        self.auth.validate(scope);return out

class ContextCache:
    def __init__(self):self.entries={}
    @staticmethod
    def key(scope,request,deletion_epoch,versions):
        required={'retrieval','embedding','reranker','tokenizer','prompt','model','redaction'}
        if set(versions)!=required or not all(versions.values()):raise ValueError('complete version tuple required')
        return digest([asdict(scope),asdict(request),deletion_epoch,versions])
    def put(self,key,value):self.entries[key]=json.loads(json.dumps(value,allow_nan=False))
    def get(self,key,scope,corpus,auth):
        allowed=corpus.eligible(scope,auth);v=self.entries.get(key)
        if v is None:return None
        if v['scope_digest']!=digest(asdict(scope)):raise Denied('cache scope')
        if v['acl_epoch']!=scope.acl_epoch or v['deletion_epoch']!=corpus.deletion_epoch:raise Stale('cache epoch')
        for item in v['items']:
            a=item['anchor'];matches=[d for d in allowed if all(d.anchor[k]==a[k] for k in ['repository','snapshot','generation','path','blob_digest','symbol']) and d.start<=a['start_byte']<a['end_byte']<=d.end]
            if not matches:raise Denied('cache anchor scope')
            if matches[0].blob[a['start_byte']:a['end_byte']].decode()!=item['text']:raise Stale('cached bytes forged')
        auth.validate(scope);return json.loads(json.dumps(v))
