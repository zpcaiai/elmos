---
name: canonicalization-and-desugaring-pass-manager
description: Run reversible, provenance-rich UIR canonicalization and desugaring. Use before stable serialization or target lowering.
---
# Canonicalization and Desugaring Pass Manager
Read `../references/uir-v1.md`. Each pass declares version, dialects, reversibility, idempotence, and obligations. Preserve evaluation count/order, side effects, resource-close order, optional access count, comprehension/pattern scopes, structured flow, maps, and regeneration hints. Unproven rewrites cannot claim equivalence. Re-running enabled passes must be stable and failure must not replace valid UIR.
