from __future__ import annotations

def bridge_allowed(identity_preserved:bool,cancel_preserved:bool,effects_preserved:bool,errors_mapped:bool)->bool:
    return all((identity_preserved,cancel_preserved,effects_preserved,errors_mapped))

def tool_hints_consistent(read_only:bool,destructive:bool,open_world:bool,actual_effect:str)->bool:
    if actual_effect=='read': return read_only and not destructive
    if actual_effect=='delete': return (not read_only) and destructive
    if actual_effect=='external-write': return (not read_only) and open_world
    return not read_only

def extension_negotiated(required:set[str],offered:set[str])->bool:
    return required<=offered
