---
name: mutability-alias-and-ownership-analyzer
description: Analyze binding/referent mutability, aliases, escape, ownership, and resource lifetime. Use before choosing target collection, immutability, or disposal structures.
---
# Mutability Alias and Ownership Analyzer
Read `../references/uir-v1.md`. Separate binding, referent, field, collection, deep, thread-safe, and observable mutation. Emit must/may/no/unknown alias only at supported confidence; incomplete analysis cannot claim no-alias. Track closure capture, return/global/thread/native escape, owned/borrowed/shared/transferred/runtime ownership, disposal, and callable summaries. Final/readonly/const never implies deep immutability.
