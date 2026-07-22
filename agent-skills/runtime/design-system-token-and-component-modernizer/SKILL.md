---
name: design-system-token-and-component-modernizer
description: Extract and govern framework-neutral design tokens, primitives, components, patterns, themes, stories, and legacy component mappings. Use during approved design-system adoption without silently redesigning UX.
---

# Design System Modernization

## Workflow

1. Separate foundation, token, primitive, component, pattern, template, and page layers.
2. Extract color, typography, spacing, size, radius, shadow, motion, z-index, breakpoint, density, and icon tokens from CSS/Sass/Less, themes, Tailwind, tool exports, libraries, inline styles, and literals.
3. Track token states as raw, candidate, approved, deprecated, alias, or removed with owners and provenance.
4. Define framework-neutral component contracts, then map React, Vue, Angular, or Web Component adapters with props, events, slots, accessibility, theme, size, visual changes, and unsupported behaviors.
5. Cover default, interactive, loading/error/empty, long text, RTL, contrast, mobile, dark, density, and reduced-motion Stories.

## Gates

Require design-owner approval for visual/brand changes. Send partial, redesign, and no-equivalent mappings to human design; remove legacy components only after usage zero and visual/accessibility gates pass.

## Output

Emit token registry, component contracts/mappings, Story matrix, adoption records, exceptions, removal decisions, and Evidence.
