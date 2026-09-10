# Routing Model

## Why not load every skill body every time?

The router keeps every installed skill discoverable while loading only the materially relevant subset. This preserves context capacity and reduces conflicting instructions.

## Source precedence

1. Project: `<repo>/.agents/skills/`
2. Global Antigravity: `~/.gemini/config/skills/`
3. Global Antigravity CLI compatibility: `~/.gemini/antigravity-cli/skills/`
4. Generic agent skill location: `~/.agents/skills/`

If two scopes expose the same skill name, project scope wins.

## Ranking

`route_skills.py` uses skill name, frontmatter description, task tokens, and configured mandatory rules. It is a deterministic helper, not a replacement for the model's semantic routing.

The agent must use judgment to add or remove skills when task semantics require it.

## Conflict precedence

Security / Trust
→ Certification / Verification
→ Architecture
→ Business Domain
→ Testing
→ Framework / Implementation
→ Optimization
→ Documentation

## Safety and truthfulness

Routing output is planning metadata. It never proves that commands ran, tests passed, or certification succeeded.
