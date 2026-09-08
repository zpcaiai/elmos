"""Query/response builders, NOT native backend execution."""
import json,math
from dataclasses import asdict
from .retrieval import Denied,digest

def elastic_queries(scope,query,vector,k=20):
    if not scope.revisions or not query.strip() or not 1<=k<=100 or not vector or any(not math.isfinite(v) for v in vector):raise ValueError('search request')
    tuples=[{'bool':{'filter':[{'term':{field:getattr(r,field)}} for field in ['repository','snapshot','generation']]}} for r in scope.revisions]
    filters=[{'term':{'tenant':scope.tenant}},{'term':{'tombstoned':False}},{'bool':{'should':tuples,'minimum_should_match':1}}]
    return {'lexical':{'size':k,'_source':False,'query':{'bool':{'filter':filters,'must':[{'multi_match':{'query':query,'fields':['symbol_parts^4','path_parts^2','text']}}]}}},'dense':{'size':k,'_source':False,'knn':{'field':'embedding','query_vector':vector,'k':k,'num_candidates':min(k*5,1000),'filter':{'bool':{'filter':filters}}}},'qualification':'not_backend_executed'}

def pgvector_query(scope,vector,k=20):
    if not scope.revisions or not 1<=k<=100 or not vector or any(not math.isfinite(v) for v in vector):raise ValueError('query')
    sql='''WITH requested AS (SELECT * FROM jsonb_to_recordset(%(bindings)s::jsonb) AS x(repository text,snapshot text,generation text))
SELECT d.chunk_id,d.embedding <=> %(vector)s::vector AS distance
FROM elmos_evidence_chunks d JOIN requested r ON (d.repository,d.snapshot,d.generation)=(r.repository,r.snapshot,r.generation)
WHERE d.tenant=%(tenant)s AND NOT d.tombstoned ORDER BY d.embedding <=> %(vector)s::vector,d.chunk_id LIMIT %(k)s'''
    return sql,{'bindings':json.dumps([asdict(r) for r in scope.revisions]),'tenant':scope.tenant,'vector':'['+','.join(map(str,vector))+']','k':k}

def dify_records(scope,result,scores,binding,threshold=0.):
    if binding.get('tenant')!=scope.tenant or binding.get('principal')!=scope.principal:raise Denied('knowledge principal binding')
    if result.get('scope_digest')!=digest(asdict(scope)) or result.get('acl_epoch')!=scope.acl_epoch:raise Denied('upstream scope mismatch')
    if not binding.get('scoring_profile') or not 0<=threshold<=1:raise ValueError('scoring profile')
    records=[]
    for i in result['items']:
        score=scores.get(i['id'])
        if score is None or not math.isfinite(score) or not 0<=score<=1:raise ValueError('normalized relevance required, not RRF confidence')
        if score>=threshold:records.append({'content':i['text'],'score':score,'title':i['anchor']['path'],'metadata':{'anchor':i['anchor'],'scoring_profile':binding['scoring_profile']}})
    return {'records':records}
