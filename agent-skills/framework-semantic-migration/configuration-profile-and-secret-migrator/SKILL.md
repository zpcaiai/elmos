---
name: configuration-profile-and-secret-migrator
description: "Migrate configuration sources, precedence, profiles, binding, validation, reload, environment keys, test overrides, and secret references. Use for framework configuration conversion."
---
# Configuration Profile and Secret Migrator
Read `../references/afsm-v1.md`. Preserve key hierarchy, source priority, profile/environment, default/required/type conversion, startup snapshot, dynamic reload and test override behavior. Make dot/colon/underscore/case/nesting environment mappings reversible.

Write only secret references and deployment bindings. Required missing configuration must fail startup. Block secret material, silent precedence/default changes or unsupported reload without an explicit strategy.

