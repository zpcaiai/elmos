# Batch 32 accessibility and visual policy

## Accessibility

- Use an exact, customer-approved accessibility profile. Automated tools are necessary but insufficient.
- P0 journeys require keyboard, focus, semantic tree, labels, descriptions, errors, announcements, contrast, zoom, motion, and targeted assistive-technology evidence.
- Accessibility regressions are not acceptable tradeoffs for visual similarity.

## Visual baselines

- Baselines are versioned and approved before target comparison.
- Masks and tolerances are scoped by field, component, route, viewport, theme, locale, and browser.
- Target failures must not auto-update baselines.
- Dynamic data should be controlled, tokenized, or compared structurally instead of broadly masked.
- Visual evidence must be paired with semantic and interaction checks.

## Responsive and rendering evidence

- P0 routes are validated across declared viewport, browser, device, locale, and theme matrices.
- Hydration, layout shift, focus, loading, error, empty, permission, hover, active, disabled, high-contrast, and reduced-motion states are captured where relevant.
