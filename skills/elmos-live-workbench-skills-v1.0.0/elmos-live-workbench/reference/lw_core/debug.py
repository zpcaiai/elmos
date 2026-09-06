"""Command ledger model. Durable storage/authorization belongs in the host."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass

INSPECT = {"stackTrace","scopes","variables","threads"}
CONTROL = {"next","stepIn","stepOut","continue","pause","terminate"}
MUTATE = {"evaluate","setVariable","setExpression"}

class DebugError(ValueError): pass

@dataclass(frozen=True)
class Command:
    key: str
    tenant: str
    session: str
    generation: int
    stop_epoch: int
    name: str
    arguments: dict
    controller: str

class CommandLedger:
    def __init__(self, tenant: str, session: str, generation: int=1, stop_epoch: int=1, controller: str="owner"):
        self.tenant, self.session, self.generation, self.stop_epoch, self.controller = tenant, session, generation, stop_epoch, controller
        self.records: dict[str,dict] = {}
        self.paused = True

    def claim(self, c: Command, *, authorized: bool, alive: bool, allow_mutation: bool=False, safe_inspection: bool=True) -> str:
        if not authorized or not alive:
            raise DebugError("authorization missing or lease expired")
        if (c.tenant,c.session,c.generation,c.stop_epoch) != (self.tenant,self.session,self.generation,self.stop_epoch):
            raise DebugError("binding/epoch mismatch")
        if c.name in INSPECT:
            if not safe_inspection or (c.name != "threads" and not self.paused):
                raise DebugError("inspection cannot be guaranteed or target is running")
        elif c.name in CONTROL | MUTATE:
            if c.controller != self.controller:
                raise DebugError("not the single controller")
            if c.name in MUTATE and not allow_mutation:
                raise DebugError("mutation denied")
            if c.name in {"next","stepIn","stepOut","continue"} and not self.paused:
                raise DebugError("target not stopped")
        else:
            raise DebugError("unsupported command; host-exec denied")
        fingerprint = hashlib.sha256(json.dumps([c.name,c.arguments,c.generation,c.stop_epoch,c.controller],sort_keys=True,separators=(",",":")).encode()).hexdigest()
        old = self.records.get(c.key)
        if old:
            if old["fingerprint"] != fingerprint:
                raise DebugError("idempotency parameter conflict")
            return "CACHED" if old["state"] == "COMMITTED" else "RECONCILE_NO_RETRY"
        self.records[c.key] = {"fingerprint":fingerprint,"state":"PENDING","command":c.name,"generation":c.generation}
        return "EXECUTE_ONCE"

    def commit(self,key: str, *, generation: int) -> None:
        rec = self.records[key]
        if generation != self.generation or rec["generation"] != generation:
            raise DebugError("stale worker result cannot commit")
        if rec["state"] == "UNKNOWN":
            raise DebugError("cannot silently commit unknown outcome")
        rec["state"] = "COMMITTED"

    def uncertain(self,key: str) -> None:
        self.records[key]["state"] = "UNKNOWN"

    def on_continued(self) -> None:
        self.paused = False
        self.stop_epoch += 1  # invalidate all stopped-state handles immediately

    def on_stopped(self) -> None:
        self.paused = True
        self.stop_epoch += 1

    def replace_worker(self) -> None:
        self.generation += 1
        self.stop_epoch += 1
        self.paused = False
