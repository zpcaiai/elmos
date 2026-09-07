---
name: accessibility-and-inclusive-interaction-validator
description: Judge WCAG and platform accessibility across static checks, rendered automation, keyboard, focus, screen reader, zoom, contrast, touch, authentication, mobile, and manual review. Use for Batch 14 accessibility gates.
---

# Accessibility Validation

## Workflow

1. Resolve the contractual/regional/product accessibility policy; default to WCAG 2.2 AA only when policy permits.
2. Keep static lint, rendered automation, keyboard, focus, screen reader, zoom/reflow, contrast, touch/pointer, cognitive/error, platform, and manual results separate.
3. Test tab/shift-tab, activation, arrows, escape, traps, skip links, grids, drag alternatives, focus visibility/order/restore/obscuring, landmarks, names, roles, values, live regions, errors, resize, orientation, and reduced motion.
4. Use approved profiles for NVDA/JAWS/VoiceOver/TalkBack and distinguish simulator, automated, and human observations.
5. Require exception criterion, scope, reason, affected users, workaround, owner, expiry, remediation, and named approval.

## Decisions

Keep `VIOLATION`, `NEEDS_REVIEW`, `PASS_AUTOMATED`, `PASS_MANUAL`, `NOT_APPLICABLE`, and `ACCEPTED_EXCEPTION` distinct. Automated zero violations or incomplete checks cannot become full pass.

## Output

Emit policy/profile, raw automated results, keyboard/focus flows, screen-reader review, contrast/mobile evidence, exceptions, and final independent decision.
