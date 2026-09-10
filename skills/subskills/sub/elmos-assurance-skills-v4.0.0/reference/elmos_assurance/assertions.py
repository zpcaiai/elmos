"""Finite, non-executable Assertion IR interpreter; no eval, shell, URLs or regex ops.

Standalone evaluation is not oracle approval, report authenticity or certification.
"""
from __future__ import annotations
import re
from decimal import Decimal
from typing import Any
from .core import canonical, require_schema
MISSING=object()

def pointer(document:Any,path:str)->Any:
    if not isinstance(path,str) or not re.fullmatch(r'(?:/(?:[^~/]|~[01])*)*',path):raise ValueError('INVALID_POINTER')
    current=document
    if path=='':return current
    for raw in path.split('/')[1:]:
        part=raw.replace('~1','/').replace('~0','~')
        if isinstance(current,dict):
            if part not in current:return MISSING
            current=current[part]
        elif isinstance(current,list):
            if not re.fullmatch(r'0|[1-9][0-9]*',part):return MISSING
            index=int(part)
            if index>=len(current):return MISSING
            current=current[index]
        else:return MISSING
    return current

def evaluate_assertions(program:dict,observation:dict)->dict:
    try:
        require_schema('assertion-program',program);require_schema('typed-observation',observation)
        canonical(program);canonical(observation)
        ids=[a['id']for a in program['assertions']]
        if len(ids)!=len(set(ids)):raise ValueError('DUPLICATE_ASSERTION_ID')
    except (ValueError,TypeError,KeyError,RecursionError,UnicodeError):
        return {'kind':'ASSERTION_EVALUATION_ONLY','status':'UNKNOWN','reason':'INVALID_PROGRAM_OR_OBSERVATION','results':[]}
    if observation['completion']!='COMPLETED':
        return {'kind':'ASSERTION_EVALUATION_ONLY','status':'UNKNOWN','reason':'OBSERVATION_NOT_COMPLETED','results':[]}
    results=[]
    for a in program['assertions']:
        val=pointer(observation,a['path']);op=a['op'];expected=a.get('expected');status='UNKNOWN'
        if op=='exists':status='PASS'if val is not MISSING else'FAIL'
        elif op=='not_exists':status='PASS'if val is MISSING else'FAIL'
        elif val is MISSING:pass
        elif op in {'equals','not_equals'}:
            equal=canonical(val)==canonical(expected)
            status='PASS'if equal==(op=='equals')else'FAIL'
        elif op=='count_equals':
            if isinstance(val,list):status='PASS'if len(val)==expected else'FAIL'
        elif op=='decimal_equals':
            if isinstance(val,str)and re.fullmatch(r'-?(0|[1-9][0-9]*)(\.[0-9]+)?',val):
                status='PASS'if Decimal(val)==Decimal(expected)else'FAIL'
        results.append({'id':a['id'],'status':status})
    verdict='FAIL'if any(r['status']=='FAIL'for r in results)else('UNKNOWN'if any(r['status']=='UNKNOWN'for r in results)else'PASS')
    return {'kind':'ASSERTION_EVALUATION_ONLY','status':verdict,'results':results}
