---
name: lambda-closure-callback-and-delegate-lowering
description: Lower lambdas, closures, local functions, callbacks, delegates, method references, captures, and this-binding. Use whenever executable values or callbacks cross language boundaries.
---
# Lambda, Closure, Callback, and Delegate Lowering
Read `../references/lowering-v1.md`. Model parameter/return types, each capture mode, `this`, async/generator status and escape lifetime. Choose native lambda, method reference, local function, anonymous/delegate/closure object, mutable box or helper.

Do not guess captures. Preserve per-iteration versus shared loop bindings, mutable cells, lexical/dynamic/bound `this`, callback multiplicity, error/cancellation channel, reentrancy and execution context. Avoid method references unless receiver/effect behavior is proven, and flag closures that outlive captured resources.
