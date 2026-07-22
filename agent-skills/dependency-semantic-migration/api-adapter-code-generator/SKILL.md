---
name: api-adapter-code-generator
description: Generate protected target-language adapter code from an approved adaptation plan and semantic mappings. Use only after candidate and risk gates.
---
# API Adapter Code Generator
Read `../references/dependency-migration-v1.md`. Generate only planned facades, conversions, error bridges, async/cancellation bridges, configuration and tests using an injected target AST/compiler backend. Mark generation IDs, source dependency/API IDs, mapping IDs and protected regions; reruns must be deterministic and idempotent. Never emit string-template production code, unplanned APIs, credentials, swallowed failures, placeholder success, or overwrite manual regions. Missing compiler/static validation blocks promotion.
