# Transformation Rule DSL Contract

A rule includes:

```yaml
id: java.spring.mvc.controller-to-aspnet.v1
source:
  technology: java
  versions: [">=17"]
  query: REPLACE-ME
target:
  technology: csharp
  versions: [">=approved"]
preconditions: []
forbiddenContexts: []
rewrite:
  sourceEdits: []
  dependencyEdits: []
  configEdits: []
semanticClaims: []
knownLosses: []
fixtures:
  positive: []
  negative: []
  conflicts: []
idempotent: true
review:
  risk: critical
  required: true
```

Rules are deterministic, source-located, versioned, idempotent, and tested. They cannot claim behavior they do not verify.
