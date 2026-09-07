---
name: evaluation-order-and-numeric-semantics-preserver
description: Preserve operand evaluation, coercion, overflow, division, equality, formatting, locale, and numeric representation. Use for operations where target defaults could drift.
---
# Evaluation Order and Numeric Semantics Preserver
Read `../references/uir-v1.md`. Record receiver/argument order, lazy/short-circuit behavior, exception stopping, signedness, width, precision/scale, rounding, overflow, divide-by-zero, NaN/infinity, identity/value/structural/strict/coercive equality, and locale/culture/timezone formatting. Never map JS `==`, Python `is`, Java `equals`, C# overloads, arbitrary integers, or decimals by spelling. Generate obligations for drift.
