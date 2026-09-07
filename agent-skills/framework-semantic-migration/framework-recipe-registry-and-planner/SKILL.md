---
name: framework-recipe-registry-and-planner
description: "Register and deterministically select versioned AFSM-to-target framework recipes. Use when planning Batch 7 transformations for lifted framework entities."
---
# Framework Recipe Registry and Planner
Read `../references/afsm-v1.md` and use `contracts/framework-schema/framework-recipe.schema.json`. Select only production, tested, idempotent recipes whose source/target framework, version, entity kind and preconditions match.

Apply specificity and priority deterministically. Reject equal-ranked conflicts, unapproved dependencies, missing provenance or unverified recipes. Emit one primary plan per entity plus alternatives, transformations, dependencies, validations and blocking obligations.

