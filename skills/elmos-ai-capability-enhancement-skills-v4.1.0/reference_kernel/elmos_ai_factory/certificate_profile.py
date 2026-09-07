from __future__ import annotations
import hashlib,json
def certificate_digest(payload): return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def status_valid(status,not_expired): return status=="ACTIVE" and not_expired
