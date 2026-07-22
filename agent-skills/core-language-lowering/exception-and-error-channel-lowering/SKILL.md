---
name: exception-and-error-channel-lowering
description: Lower synchronous, checked/unchecked, promise/task, result, callback, sentinel, and process error channels. Use for throw/catch/finally, filters, chaining, cleanup, or async failures.
---
# Exception and Error Channel Lowering
Read `../references/lowering-v1.md`. Map every throw site, caught set/order/filter, rethrow form, cause chain, async fault and callable error contract. Preserve checked exception intent with types/contracts/analyzers/results/wrappers rather than deleting it.

Never swallow catch-all errors, confuse `throw ex` with rethrow, convert rejection to ordinary return, reorder finally/cleanup, lose suppressed/secondary exceptions, or claim unknown throws are absent. Coordinate result-to-exception changes with every caller and keep raw compiler diagnostics linked to UIR.
