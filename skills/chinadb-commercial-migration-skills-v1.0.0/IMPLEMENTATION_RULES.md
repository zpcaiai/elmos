# Implementation Rules

1. AST/IR first. Regex-only SQL or PL conversion is prohibited except as a post-parse lexical cleanup.
2. Every conversion rule has: rule id, source predicate, target action, risk level, examples, negative examples, test fixture and evidence link.
3. Unknown semantics must fail closed: emit an unsupported node + remediation recommendation, never silently approximate.
4. Auto-repair is patch-producing and evidence-gated. It must not mutate production databases directly.
5. Target database version and compatibility mode are part of the route key and evidence fingerprint.
6. Behavioral tests compare values, errors, transaction outcomes and side effects; row-count checks alone are insufficient.
7. Performance tests record dataset size, concurrency, warm/cold cache conditions, plans and infrastructure metadata.
8. All credentials are references to secret managers or environment variables; never write live secrets into evidence.
9. Vendor-native tools may be orchestrated when licensed/available, but the platform must preserve a vendor-neutral evidence model.
10. A route is releasable only after E1-E5 gates or explicit waivers with owner, reason, expiry and rollback plan.
