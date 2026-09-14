"""Bounded local durable deployment journal; host stores can implement the same port.

SQLite is a local engineering backend, not a substitute for the production
PostgreSQL tenancy/HA boundary. Locks deliberately survive process death and
unknown external outcomes: only verified terminal evidence releases them.
"""
from __future__ import annotations
from contextlib import contextmanager
import json
import sqlite3
import time
from .contracts import Scope, Denied, allowed_transition, canonical, digest, require


class Journal:
    def __init__(self, path):
        self.path = str(path)
        with self.connection() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS objects(
              scope TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL,
              body BLOB NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY(scope,kind,id));
            CREATE TABLE IF NOT EXISTS deployments(
              id TEXT PRIMARY KEY, scope TEXT NOT NULL, account TEXT NOT NULL,
              environment TEXT NOT NULL, idem TEXT NOT NULL, request_hash TEXT NOT NULL,
              plan BLOB NOT NULL, ticket TEXT NOT NULL, state TEXT NOT NULL,
              version INTEGER NOT NULL DEFAULT 0, mutated INTEGER NOT NULL DEFAULT 0,
              active INTEGER NOT NULL DEFAULT 1, evidence TEXT,
              UNIQUE(scope,idem), UNIQUE(scope,ticket));
            CREATE UNIQUE INDEX IF NOT EXISTS environment_mutex
              ON deployments(environment) WHERE active=1;
            CREATE TABLE IF NOT EXISTS target_locks(
              resource TEXT PRIMARY KEY, deployment TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS steps(
              deployment TEXT NOT NULL, operation TEXT NOT NULL, request BLOB NOT NULL,
              status TEXT NOT NULL, invocation TEXT, result BLOB, started INTEGER NOT NULL,
              finished INTEGER, PRIMARY KEY(deployment,operation));
            CREATE TABLE IF NOT EXISTS events(
              deployment TEXT NOT NULL, seq INTEGER NOT NULL, body BLOB NOT NULL,
              PRIMARY KEY(deployment,seq));
            CREATE TABLE IF NOT EXISTS evidence(
              digest TEXT PRIMARY KEY, scope TEXT NOT NULL, body BLOB NOT NULL);
            CREATE TRIGGER IF NOT EXISTS immutable_evidence_update BEFORE UPDATE ON evidence
              BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_evidence_delete BEFORE DELETE ON evidence
              BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_events_update BEFORE UPDATE ON events
              BEGIN SELECT RAISE(ABORT,'immutable events'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_events_delete BEFORE DELETE ON events
              BEGIN SELECT RAISE(ABORT,'immutable events'); END;
            ''')

    @contextmanager
    def connection(self):
        c = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA synchronous=FULL')
        try:
            yield c
        finally:
            c.close()

    @contextmanager
    def transaction(self):
        with self.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                yield c
                c.commit()
            except BaseException:
                c.rollback()
                raise

    def put(self, scope: Scope, kind, object_id, body):
        raw = canonical(body)
        with self.transaction() as c:
            old = c.execute('SELECT body FROM objects WHERE scope=? AND kind=? AND id=?',
                            (scope.key, kind, object_id)).fetchone()
            if old:
                require(old['body'] == raw, 'immutable_object_conflict')
            else:
                c.execute('INSERT INTO objects(scope,kind,id,body) VALUES(?,?,?,?)',
                          (scope.key, kind, object_id, raw))
        return object_id

    def get(self, scope, kind, object_id, *, allow_revoked=False):
        with self.connection() as c:
            row = c.execute('SELECT * FROM objects WHERE scope=? AND kind=? AND id=?',
                            (scope.key, kind, object_id)).fetchone()
        require(row is not None, 'not_found')
        require(allow_revoked or not row['revoked'], 'revoked')
        return json.loads(row['body'])

    def revoke(self, scope, kind, object_id):
        with self.transaction() as c:
            require(c.execute('UPDATE objects SET revoked=1 WHERE scope=? AND kind=? AND id=?',
                              (scope.key, kind, object_id)).rowcount == 1, 'not_found')

    def admit(self, scope, deployment_id, idem, ticket_id, plan, resources, quota, now=None):
        require(type(quota) is int and quota > 0, 'invalid_host_quota')
        request_hash = digest({'ticket': ticket_id, 'plan': plan})
        # Environment mutex covers all actors/workspaces of this tenant/project.
        environment = digest([scope.tenant_id, scope.project_id, scope.environment_id])
        with self.transaction() as c:
            old = c.execute('SELECT * FROM deployments WHERE scope=? AND idem=?', (scope.key, idem)).fetchone()
            if old:
                require(old['request_hash'] == request_hash, 'idempotency_conflict')
                return old['id']
            used = c.execute('SELECT count(*) FROM deployments WHERE account=? AND active=1', (scope.account_id,)).fetchone()[0]
            require(used < quota, 'account_quota_exceeded')
            try:
                c.execute('''INSERT INTO deployments(id,scope,account,environment,idem,request_hash,plan,ticket,state)
                             VALUES(?,?,?,?,?,?,?,?,?)''',
                          (deployment_id, scope.key, scope.account_id, environment, idem, request_hash,
                           canonical(plan), ticket_id, 'REQUESTED'))
                for resource in resources:
                    c.execute('INSERT INTO target_locks VALUES(?,?)', (resource, deployment_id))
            except sqlite3.IntegrityError:
                raise Denied('environment_resource_or_ticket_busy') from None
            self._event(c, deployment_id, {'state': 'REQUESTED', 'at':int(time.time()) if now is None else now})
        return deployment_id

    @staticmethod
    def _load(c, scope, deployment_id):
        row = c.execute('SELECT * FROM deployments WHERE scope=? AND id=?', (scope.key, deployment_id)).fetchone()
        require(row is not None, 'not_found')
        return dict(row)

    def load(self, scope, deployment_id):
        with self.connection() as c:
            row = self._load(c, scope, deployment_id)
            row['plan'] = json.loads(row['plan'])
            return row

    @staticmethod
    def _event(c, deployment_id, body):
        seq = c.execute('SELECT count(*) FROM events WHERE deployment=?', (deployment_id,)).fetchone()[0]
        c.execute('INSERT INTO events VALUES(?,?,?)', (deployment_id, seq, canonical(body)))

    def transition(self, scope, deployment_id, before, after, now, reason=None):
        require(allowed_transition(before, after), 'illegal_transition')
        with self.transaction() as c:
            row = self._load(c, scope, deployment_id)
            require(row['state'] == before, 'state_conflict')
            c.execute('UPDATE deployments SET state=?,version=version+1 WHERE id=?', (after, deployment_id))
            self._event(c, deployment_id, {'state': after, 'at': now, 'reason': reason})

    def begin_step(self, scope, deployment_id, operation, request, now, mutating):
        raw = canonical(request)
        with self.transaction() as c:
            self._load(c, scope, deployment_id)
            old = c.execute('SELECT * FROM steps WHERE deployment=? AND operation=?', (deployment_id, operation)).fetchone()
            if old:
                require(old['request'] == raw, 'operation_conflict')
                return dict(old), False
            c.execute('INSERT INTO steps(deployment,operation,request,status,started) VALUES(?,?,?,?,?)',
                      (deployment_id, operation, raw, 'DISPATCHING', now))
            if mutating:
                c.execute('UPDATE deployments SET mutated=1 WHERE id=?', (deployment_id,))
            return {'status': 'DISPATCHING', 'invocation': None}, True

    def accepted(self, scope, deployment_id, operation, invocation):
        require(isinstance(invocation, str) and 0 < len(invocation) <= 200, 'invalid_invocation')
        with self.transaction() as c:
            self._load(c, scope, deployment_id)
            row = c.execute('SELECT invocation FROM steps WHERE deployment=? AND operation=?', (deployment_id, operation)).fetchone()
            require(row is not None and row['invocation'] in {None, invocation}, 'invocation_conflict')
            c.execute('UPDATE steps SET invocation=?,status=? WHERE deployment=? AND operation=? AND status!=?',
                      (invocation, 'ACCEPTED', deployment_id, operation, 'COMPLETE'))

    def complete_step(self, scope, deployment_id, operation, result, now):
        raw = canonical(result)
        with self.transaction() as c:
            self._load(c, scope, deployment_id)
            row = c.execute('SELECT status,result,invocation FROM steps WHERE deployment=? AND operation=?',
                            (deployment_id, operation)).fetchone()
            require(row is not None and row['invocation'] is not None, 'missing_invocation')
            if row['status'] == 'COMPLETE':
                require(row['result'] == raw, 'result_conflict')
                return
            c.execute('UPDATE steps SET status=?,result=?,finished=? WHERE deployment=? AND operation=?',
                      ('COMPLETE', raw, now, deployment_id, operation))

    def steps(self, scope, deployment_id):
        with self.connection() as c:
            self._load(c, scope, deployment_id)
            rows = c.execute('SELECT * FROM steps WHERE deployment=? ORDER BY started,operation', (deployment_id,)).fetchall()
        return [{**dict(r), 'request': json.loads(r['request']),
                 'result': json.loads(r['result']) if r['result'] else None} for r in rows]

    def timeline(self, scope, deployment_id):
        with self.connection() as c:
            self._load(c, scope, deployment_id)
            return [json.loads(r[0]) for r in c.execute('SELECT body FROM events WHERE deployment=? ORDER BY seq', (deployment_id,))]

    def commit_evidence(self, scope, deployment_id, before, final_state, evidence):
        raw, key = canonical(evidence), digest(evidence)
        require(evidence['final_state'] == final_state, 'evidence_state_mismatch')
        with self.transaction() as c:
            row = self._load(c, scope, deployment_id)
            if row['evidence']:
                require(row['evidence'] == key, 'evidence_conflict')
                return key
            require(row['state'] == before, 'state_conflict')
            require(allowed_transition(before, final_state), 'illegal_transition')
            c.execute('INSERT INTO evidence VALUES(?,?,?)', (key, scope.key, raw))
            # Unsafe state keeps resource and account locks until explicit reconciliation.
            active = int(final_state == 'FAILED_NEEDS_HUMAN')
            c.execute('UPDATE deployments SET evidence=?,state=?,active=?,version=version+1 WHERE id=?',
                      (key, final_state, active, deployment_id))
            if not active:
                c.execute('DELETE FROM target_locks WHERE deployment=?', (deployment_id,))
            self._event(c, deployment_id, {'state': final_state, 'evidence_digest': key})
        return key

    def evidence(self, scope, deployment_id):
        with self.connection() as c:
            row = self._load(c, scope, deployment_id)
            require(row['evidence'] is not None, 'evidence_not_committed')
            blob = c.execute('SELECT body FROM evidence WHERE digest=? AND scope=?', (row['evidence'], scope.key)).fetchone()
            require(blob is not None and digest(blob[0]) == row['evidence'], 'evidence_integrity')
            return json.loads(blob[0])
