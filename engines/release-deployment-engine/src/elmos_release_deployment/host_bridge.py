"""Authenticated host transport. Trust keys and replay storage are operator-owned."""
from __future__ import annotations

import base64
import io
import json
import sqlite3
import time
from contextlib import contextmanager

from .contracts import Denied, Principal, Scope, digest, identifier, require


def strict_json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    def constant(_):
        raise Denied('nonfinite_json')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


class ReplayStore:
    """Atomic across processes; entries expire only after their permit is invalid."""
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS host_nonces (key TEXT PRIMARY KEY, expires INTEGER NOT NULL)')

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def claim(self, key, expires, now):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM host_nonces WHERE expires < ?', (now,))
            try:
                db.execute('INSERT INTO host_nonces VALUES (?, ?)', (key, expires))
            except sqlite3.IntegrityError as error:
                raise Denied('host_request_replayed') from error


class SignedHostAuthenticator:
    """Ed25519 signature covers exact envelope bytes, including the body hash.

    Header format: key-id.base64url(envelope).base64url(signature).
    Keys map to a public key and an exact allowlist of Scope.key values; possession
    of a signing key alone cannot expand its registered tenant/environment scope.
    A fresh nonce is required per HTTP attempt. Business idempotency is separate.
    """
    def __init__(self, keys, replay_store, audience, clock=time.time):
        self.keys = dict(keys)
        self.replays, self.audience, self.clock = replay_store, audience, clock

    def __call__(self, environ):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        try:
            token = environ.get('HTTP_X_ELMOS_HOST_AUTH', '')
            require(len(token) <= 16384, 'host_token_bounds')
            key_id, payload, signature = token.split('.')
            require(key_id in self.keys, 'host_key_unknown')
            def decode(value):
                return base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
            raw = decode(payload)
            public_key, allowed_scopes = self.keys[key_id]
            Ed25519PublicKey.from_public_bytes(public_key).verify(
                decode(signature), b'elmos-deployment-host-v1\x00' + raw)
            claim = strict_json(raw)
            require(set(claim) == {'audience','nonce','issued_at','expires_at','method','path',
                                    'body_digest','actor_id','scope','permissions'}, 'host_claim_fields')
            now = int(self.clock())
            require(type(claim['issued_at']) is int and type(claim['expires_at']) is int
                    and now - 60 <= claim['issued_at'] <= now
                    and now < claim['expires_at'] <= claim['issued_at'] + 60, 'host_token_expired')
            require(claim['audience'] == self.audience, 'host_audience')
            require(claim['method'] == environ['REQUEST_METHOD'] and claim['path'] == environ['PATH_INFO']
                    and not environ.get('QUERY_STRING'), 'host_route_binding')
            require(not environ.get('HTTP_TRANSFER_ENCODING') and not environ.get('HTTP_CONTENT_ENCODING'),
                    'host_encoding')
            length = int(environ.get('CONTENT_LENGTH') or '0')
            require(0 <= length <= 65536, 'request_too_large')
            body = environ['wsgi.input'].read(length)
            require(len(body) == length and digest(body) == claim['body_digest'], 'host_body_binding')
            scope = Scope(**claim['scope'])
            require(scope.key in allowed_scopes, 'host_scope_not_registered')
            import re
            require(type(claim['actor_id']) is str and re.fullmatch(
                r'[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}', claim['actor_id']) is not None, 'invalid_actor')
            identifier(claim['nonce'])
            permissions = claim['permissions']
            require(type(permissions) is list and len(permissions) <= 32
                    and all(type(p) is str and len(p) <= 64 for p in permissions), 'host_permissions')
            self.replays.claim(key_id + ':' + claim['nonce'], claim['expires_at'], now)
            environ['wsgi.input'] = io.BytesIO(body)
            return Principal(claim['actor_id'], scope, frozenset(permissions))
        except Denied:
            raise
        except Exception as error:
            raise Denied('host_authentication_failed') from error
