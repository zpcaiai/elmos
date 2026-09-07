"""SQLite-backed local contract models. No real executor, signer, or LangGraph."""
from __future__ import annotations
import json,sqlite3
from dataclasses import dataclass,asdict
from .retrieval import Denied,Stale,digest

class ProjectionCatalog:
    def __init__(self,path=':memory:'):
        self.db=sqlite3.connect(path)
        self.db.executescript('CREATE TABLE IF NOT EXISTS versions(t TEXT,r TEXT,g TEXT,s TEXT,state TEXT,expected INT,actual INT,PRIMARY KEY(t,r,g)); CREATE TABLE IF NOT EXISTS heads(t TEXT,r TEXT,g TEXT,PRIMARY KEY(t,r));');self.db.commit()
    def begin(self,t,r,g,s,count):
        if not all([t,r,g,s]) or count<0:raise ValueError('manifest')
        with self.db:self.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?)',(t,r,g,s,'BUILDING',count,0))
    def validate(self,t,r,g,actual):
        with self.db:
            n=self.db.execute("UPDATE versions SET state='VALIDATED',actual=? WHERE t=? AND r=? AND g=? AND state='BUILDING' AND expected=?",(actual,t,r,g,actual)).rowcount
            if n!=1:raise Stale('incomplete/invalid manifest')
    def head(self,t,r):
        x=self.db.execute('SELECT g FROM heads WHERE t=? AND r=?',(t,r)).fetchone();return x[0] if x else None
    def publish(self,t,r,g,expected_head):
        try:
            self.db.execute('BEGIN IMMEDIATE')
            if self.head(t,r)!=expected_head:raise Stale('head CAS')
            row=self.db.execute('SELECT state FROM versions WHERE t=? AND r=? AND g=?',(t,r,g)).fetchone()
            if not row or row[0]!='VALIDATED':raise Stale('not validated')
            self.db.execute('INSERT INTO heads VALUES(?,?,?) ON CONFLICT(t,r) DO UPDATE SET g=excluded.g',(t,r,g))
            self.db.execute("UPDATE versions SET state='PUBLISHED' WHERE t=? AND r=? AND g=?",(t,r,g));self.db.commit()
        except Exception:self.db.rollback();raise
    def close(self):self.db.close()

@dataclass(frozen=True)
class HostLease:
    """Trusted test input. Production requires host-verified context, not a client DTO."""
    tenant:str
    run_id:str
    intent_digest:str
    generation:int
    expires_at:float
    permission_epoch:int

class ActionLedger:
    def __init__(self,path=':memory:'):
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY,tenant TEXT,run_id TEXT,intent TEXT,generation INT,status TEXT,receipt TEXT)');self.db.commit()
    @staticmethod
    def action_id(t,r,step,intent):return digest([t,r,step,intent])
    def propose(self,t,r,step,intent,generation):
        if generation<1:raise ValueError('generation')
        aid=self.action_id(t,r,step,intent)
        with self.db:self.db.execute('INSERT OR IGNORE INTO actions VALUES(?,?,?,?,?,?,?)',(aid,t,r,digest(intent),generation,'PROPOSED',None))
        return aid
    def row(self,aid):
        x=self.db.execute('SELECT * FROM actions WHERE id=?',(aid,)).fetchone()
        if not x:raise KeyError(aid)
        return dict(zip(['id','tenant','run_id','intent','generation','status','receipt'],x))
    def authorize_and_dispatch(self,aid,lease,now,current_generation,current_permission_epoch):
        try:
            self.db.execute('BEGIN IMMEDIATE');r=self.row(aid)
            if (lease.tenant,lease.run_id,lease.intent_digest)!=(r['tenant'],r['run_id'],r['intent']):raise Denied('intent binding')
            if now>=lease.expires_at or lease.permission_epoch!=current_permission_epoch:raise Denied('expired/revoked')
            if lease.generation!=current_generation or r['generation']!=current_generation:raise Denied('fenced')
            if r['status']!='PROPOSED':raise Stale('do not redispatch; reconcile')
            self.db.execute("UPDATE actions SET status='DISPATCHED' WHERE id=?",(aid,));self.db.commit()
        except Exception:self.db.rollback();raise
    def mark_unknown(self,aid):
        with self.db:
            n=self.db.execute("UPDATE actions SET status='UNKNOWN_RESULT' WHERE id=? AND status='DISPATCHED'",(aid,)).rowcount
            if n!=1:raise Stale('invalid transition')
    def record_result(self,aid,generation,current_generation,receipt,success):
        if generation!=current_generation or self.row(aid)['generation']!=generation:raise Denied('old worker result')
        self._finish(aid,receipt,success)
    def reconcile(self,aid,receipt,success):
        # Host-only: actual independent receipt verification is outside this reference.
        if self.row(aid)['status']!='UNKNOWN_RESULT':raise Stale('not unknown')
        self._finish(aid,receipt,success)
    def _finish(self,aid,receipt,success):
        if len(receipt)!=64 or any(c not in '0123456789abcdef' for c in receipt):raise ValueError('receipt digest')
        try:
            self.db.execute('BEGIN IMMEDIATE');r=self.row(aid);state='SUCCEEDED' if success else 'FAILED'
            if r['status']==state and r['receipt']==receipt:self.db.commit();return
            if r['status'] not in ['DISPATCHED','UNKNOWN_RESULT']:raise Stale('conflicting receipt')
            self.db.execute('UPDATE actions SET status=?,receipt=? WHERE id=?',(state,receipt,aid));self.db.commit()
        except Exception:self.db.rollback();raise
    def close(self):self.db.close()

@dataclass
class BoundedAgent:
    max_rounds:int=3
    rounds:int=0
    no_progress_limit:int=2
    unchanged:int=0
    last_evidence:str|None=None
    status:str='RUNNABLE'
    def observe(self,evidence_digest,verified_candidate=False,needs_input=False,lease_expired=False):
        if self.status not in ['RUNNABLE','NEEDS_INPUT']:raise Stale('terminal')
        if lease_expired:self.status='BLOCKED'
        elif needs_input:self.status='NEEDS_INPUT'
        elif self.rounds>=self.max_rounds:self.status='BUDGET_EXHAUSTED'
        else:
            self.rounds+=1;self.unchanged=self.unchanged+1 if evidence_digest==self.last_evidence else 0;self.last_evidence=evidence_digest
            self.status='CANDIDATE_READY' if verified_candidate else ('NO_PROGRESS' if self.unchanged>=self.no_progress_limit else 'RUNNABLE')
        return self.status
    def checkpoint(self):return json.dumps(asdict(self),sort_keys=True)
    @classmethod
    def resume(cls,raw):
        d=json.loads(raw)
        if set(d)!=set(asdict(cls())):raise Stale('schema migration required')
        a=cls(**d)
        if a.max_rounds<1 or not 0<=a.rounds<=a.max_rounds or a.no_progress_limit<1 or a.status not in ['RUNNABLE','NEEDS_INPUT','BLOCKED','BUDGET_EXHAUSTED','NO_PROGRESS','CANDIDATE_READY']:raise ValueError('checkpoint')
        return a
