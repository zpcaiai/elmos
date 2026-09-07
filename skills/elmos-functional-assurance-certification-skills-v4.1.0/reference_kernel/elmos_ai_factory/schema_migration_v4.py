from __future__ import annotations

def expand_contract_allowed(expand_done:bool,mixed_version_pass:bool,backfill_done:bool,old_readers:int)->bool:
    return expand_done and mixed_version_pass and backfill_done and old_readers==0

def rollback_ready(snapshot:bool,reverse_migration:bool,dual_write_reconciled:bool)->bool:
    return snapshot and reverse_migration and dual_write_reconciled

def online_change_safe(lock_seconds:float,max_lock:float,replica_lag:float,max_lag:float)->bool:
    return lock_seconds<=max_lock and replica_lag<=max_lag
