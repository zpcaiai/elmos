from __future__ import annotations
def transition_status(inventory):
 if not inventory: return "UNKNOWN"
 if any(x.get("algorithm") in {"RSA","ECDSA","ECDH"} and not x.get("transition") for x in inventory): return "BLOCKED"
 return "READY"
def hybrid_required(long_lived_confidentiality,external_interop): return bool(long_lived_confidentiality or external_interop)
