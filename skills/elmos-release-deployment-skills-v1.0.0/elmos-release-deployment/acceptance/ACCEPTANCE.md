# P0 acceptance matrix

1. Spring Boot image deploy succeeds and actuator health passes.
2. Vue image deploy succeeds and HTTP/asset check passes.
3. Python service deploy succeeds with locked dependencies.
4. .NET service deploy succeeds and health endpoint passes.
5. Mutable tag changes after planning; deployment still uses pinned digest.
6. Release evidence digest mismatch -> rejected before mutation.
7. Expired DeploymentTicket -> rejected.
8. Ticket targets instance A but request attempts instance B -> rejected.
9. STS/lease expires before apply -> reacquire only through authorized workflow; stale lease rejected.
10. ECS not Running -> preflight failure, no mutation.
11. Cloud Assistant absent/unhealthy -> preflight blocks or approved bootstrap path runs.
12. Runtime disk insufficient -> no deployment.
13. Health fails after new container activation -> previous release restored.
14. Smoke test fails -> previous release restored.
15. Rollback health fails -> FAILED_NEEDS_HUMAN.
16. Destructive DB migration without dedicated approval -> denied.
17. Orchestrator crashes after remote command submission -> resume uses saved invocation ID, not duplicate submission.
18. Duplicate deploy request with same idempotency key -> same deployment returned.
19. Parallel deploys to same prod environment -> serialized by environment mutex.
20. Different tenants cannot address each other's target/secret/release IDs.
21. Secret values absent from command text, logs, traces and evidence.
22. Deployment evidence validates against schema and contains exact image digest/provider invocation IDs.
23. Full-stack backend+frontend bundle deploys using external DB binding.
24. Production policy denies local containerized DB by default.
25. Rollback restores previous config version as well as image.
