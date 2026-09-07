---
name: visual-regression-and-rendering-validator
description: Validate component, page, journey, responsive, desktop, mobile, print, and PDF rendering against approved environment-bound visual baselines. Use after rendering evidence exists in a stable Runner.
---

# Visual Regression Validation

## Workflow

1. Bind each baseline to application/browser/OS/image/font/viewport/DPR/theme/locale/timezone/color/reduced-motion/fixture/clock/randomness metadata.
2. Capture repeatedly, evaluate stability, obtain named human review, sign, and approve before using a baseline as authority.
3. Normalize only the smallest dynamic regions through approved mask, freeze, fixture, or region policies; never ignore an entire page.
4. Compare by approved pixel, threshold, perceptual, layout, DOM-semantic, or manual method and preserve raw baseline, actual, and diff artifacts.
5. Use a separately approved target-design baseline when an intentional design-system change is in scope.

## Decisions

Return `VISUAL_MATCH`, `WITHIN_THRESHOLD`, `EXPECTED_APPROVED_CHANGE`, `REGRESSION`, `UNSTABLE_BASELINE`, or `NOT_COMPARABLE`. Environment mismatch or missing evidence is inconclusive, never pass.

## Output

Emit manifests, scenarios, images, diff categories, instability, approvals, thresholds, environment hashes, and Evidence references.
