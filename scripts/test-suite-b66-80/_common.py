from __future__ import annotations
import hashlib, json
from pathlib import Path
ALLOWED_RESULT_STATUSES={"not-run","passed","failed","blocked","skipped","waived","flaky"}
def load(path):
    with Path(path).open(encoding="utf-8") as f: return json.load(f)
def sha256_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()
def fail(msg):
    raise SystemExit("ERROR: "+msg)
