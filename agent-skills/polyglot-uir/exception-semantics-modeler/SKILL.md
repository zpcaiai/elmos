---
name: exception-semantics-modeler
description: Model cross-language throw, catch, finally, cleanup, rejection, and propagation semantics. Use for callable error contracts or exception-sensitive lifting.
---
# Exception Semantics Modeler
Read `../references/uir-v1.md`. Preserve Java checked/unchecked/suppressed, Python chaining/groups/context suppression, C# filters/rethrow/disposal, and JS thrown values/promise rejection. Finally covers every abrupt exit; rejection is not synchronous throw; rethrow preserves identity; cleanup ordering and secondary errors remain explicit. Emit throw sets, propagation edges, source maps, confidence, and obligations.
