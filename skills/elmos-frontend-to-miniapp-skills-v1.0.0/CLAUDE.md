# CLAUDE.md — Elmos Frontend → MiniApp

Project skills are installed under `.claude/skills/`. For repository-level frontend conversion, invoke:

```text
/frontend-to-miniapp-orchestrator
```

Rules:

- Read only the selected skill first; load its `references/` or `assets/` when the workflow asks for them.
- Keep source repositories read-only and write to `runs/<run-id>/`.
- Validate JSON with the package schemas.
- Preserve source → IR → target traceability.
- Do not use WebView, full-page Canvas, screenshots, or empty stubs as silent fallbacks.
- Stop for approval before real payment, refund, permission expansion, upload, review submission, or release.
- Never expose secrets.
- A build is not a completed migration: semantic, visual, privacy, security, and evidence gates still apply.
