---
name: numeric-coercion-and-operator-lowering
description: Preserve numeric width, precision, overflow, division, remainder, equality, conversion, and operator binding across languages. Use whenever Batch 5 lowers arithmetic or comparisons.
---
# Numeric Coercion and Operator Lowering
Read `../references/lowering-v1.md`. Build an explicit plan for operand types, result kind, rounding, overflow, zero division, remainder sign, equality category, conversions and user-defined dispatch. Insert range/precision checks or big-number helpers rather than relying on target implicit conversion.

Desugar JavaScript coercive equality. Preserve Decimal scale/rounding and Python arbitrary precision. Verify operator binding after compilation and create property-test obligations for NaN, ranges, division and equality edge cases.
