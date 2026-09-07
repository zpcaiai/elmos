from __future__ import annotations

def delegation_allowed(parent:set[str],child:set[str],audience_ok:bool,ttl_ok:bool)->bool:
    return child<=parent and audience_ok and ttl_ok

def attestation_allows(measurement:str,approved:set[str],fresh:bool)->bool:
    return measurement in approved and fresh

def tenant_access(subject_tenant:str,resource_tenant:str,break_glass:bool=False)->bool:
    return subject_tenant==resource_tenant and not break_glass

def egress_allowed(destination:str,allowlist:set[str],data_class:str)->bool:
    return destination in allowlist and data_class not in {'restricted','secret'}
