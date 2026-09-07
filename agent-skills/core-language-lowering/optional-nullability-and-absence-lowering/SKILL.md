---
name: optional-nullability-and-absence-lowering
description: Lower null, None, undefined, optional-empty, missing key/property, uninitialized and not-found states without collapsing meaning. Use for every absence, null guard, optional default, truthiness, or nullable API.
---
# Optional, Nullability, and Absence Lowering
Read `../references/lowering-v1.md`. Prefer native equivalence, wrapper/option, discriminated union, sentinel, `{present,value}`, compatibility helper, then manual. Record whether null remains distinguishable and how guards/defaults evaluate.

Do not merge null/None/undefined by default, turn Optional into nullable blindly, eager-evaluate a lazy default, simplify Python truthiness to non-null, merge missing key with null value, or use non-null assertions to hide uncertainty. Public absence changes block unless explicitly approved and verified.
