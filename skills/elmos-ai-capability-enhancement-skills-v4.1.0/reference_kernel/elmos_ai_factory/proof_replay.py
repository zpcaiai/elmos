from __future__ import annotations
import hashlib,json
def proof_digest(claim,proof,assumptions):
 payload=json.dumps({"claim":claim,"proof":proof,"assumptions":assumptions},sort_keys=True,separators=(",",":"))
 return hashlib.sha256(payload.encode()).hexdigest()
def replay_matches(expected,actual): return expected==actual and len(expected)==64
