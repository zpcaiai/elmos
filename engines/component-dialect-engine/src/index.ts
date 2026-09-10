/**
 * @file index.ts
 * @description Master Entry Point for @elmos/component-dialect-engine.
 * Business Line 4 ("大前端组件与跨端迁移" / Batch 32) Production Compiler Engine.
 * Re-exports:
 * 1. Core IR models and compiler pipeline
 * 2. Cross-platform Component Translation Engine
 * 3. Specialized Subsystem Engines:
 *    - Layout Engine (Flexbox / Grid / Responsive / CSS-in-JS)
 *    - Theme Engine (Design Tokens / CSS Vars / Dark Mode / Semantic Color)
 *    - Router Engine (File-based / Dynamic / Deeplinks / Auth Guard)
 *    - Form Engine (Zod / Yup Schema Validation / Async Errors / Field Array)
 *    - Store Engine (Redux Toolkit / Pinia / MiniApp Global Store / Hydration)
 *    - Style Engine (Tailwind / CSS Modules / PostCSS / WXSS)
 *    - Hydration Engine (SSR / SSG / Island Architecture / Progressive Rehydration)
 *    - I18n Engine (react-i18next / vue-i18n / MiniApp Localization / Pluralization)
 *    - API Client Engine (TanStack Query / SWR / MiniApp Request Queue & Token Refresh)
 *    - A11y & SEO Engine (WCAG 2.2 AA / ARIA / OpenGraph / Schema.org JSON-LD)
 *    - Virtual Scroll Engine (Binary Search Prefix Offsets / ResizeObserver / MiniApp RecycleView)
 *    - Gesture & Animation Engine (Spring Physics / Framer Motion / MiniApp WXS 60FPS Responder)
 *    - Headless Differential Verification Suite (DOM AST / Playwright / Automator)
 * Conforms to Batch 32 Skills (1201-1222) and Execution Integrity Contract.
 */

// Core IR Models and Pipeline
export * from './models';
export * from './cross-platform-ir';
export * from './manual-component-ir';
export * from './engine';
export * from './pipeline';
export * from './evidence';
export * from './execution';
export * from './validator';
export * from './verify';
export * from './target-adapters';
export * from './differential-oracle';
export * from './l5-visual-interaction-oracle';

// Subsystem Engines
export * from './layout-engine';
export * from './theme-engine';
export * from './router-engine';
export * from './form-engine';
export * from './store-engine';
export * from './style-engine';
export * from './hydration-engine';
export * from './i18n-engine';
export * from './api-client-engine';
export * from './a11y-seo-engine';
export * from './virtual-scroll-engine';
export * from './gesture-animation-engine';
export * from './headless-differential-suite';
export * from './ui-library-engine';
