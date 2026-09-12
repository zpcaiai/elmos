/**
 * @file a11y-seo-engine.test.ts
 * @description Comprehensive test suite for Cross-Platform Accessibility (A11y) & SEO Engine.
 * Tests WcagAuditOracle, SeoMetaGenerator, and CrossPlatformA11yNormalizer.
 * Conforms to Batch 32 Skill 1221.
 */

import {
  WcagAuditOracle,
  SeoMetaGenerator,
  CrossPlatformA11yNormalizer,
  UniversalSeoMetadataIR,
  AccessibleNodeIR,
} from '../src/a11y-seo-engine';

describe('Cross-Platform Accessibility & SEO Engine', () => {
  const oracle = new WcagAuditOracle();
  const seoGen = new SeoMetaGenerator();
  const normalizer = new CrossPlatformA11yNormalizer();

  describe('WcagAuditOracle', () => {
    it('should detect missing alt attribute on image tags', () => {
      const tsx = `
        export const Banner = () => {
          return <div><img src="/banner.jpg" /></div>;
        };
      `;

      const report = oracle.auditTsx(tsx);
      expect(report.isCompliant).toBe(false);
      expect(report.errorsCount).toBe(1);
      expect(report.violations[0]!.ruleId).toBe('img-has-alt');
    });

    it('should detect button without accessible name', () => {
      const tsx = `
        export const IconButton = () => {
          return <button><svg /></button>;
        };
      `;

      const report = oracle.auditTsx(tsx);
      expect(report.isCompliant).toBe(false);
      expect(report.violations.some((v) => v.ruleId === 'interactive-has-name')).toBe(true);
    });

    it('should detect skipped heading hierarchy', () => {
      const tsx = `
        export const Article = () => {
          return (
            <div>
              <h1>Title</h1>
              <h3>Subsection</h3>
            </div>
          );
        };
      `;

      const report = oracle.auditTsx(tsx);
      expect(report.warningsCount).toBeGreaterThanOrEqual(1);
      expect(report.violations.some((v) => v.ruleId === 'heading-order')).toBe(true);
    });

    it('should detect positive tabIndex values', () => {
      const tsx = `
        export const Navigation = () => {
          return <div tabIndex="5">Menu</div>;
        };
      `;

      const report = oracle.auditTsx(tsx);
      expect(report.violations.some((v) => v.ruleId === 'no-positive-tabindex')).toBe(true);
    });

    it('should pass compliant accessible TSX code', () => {
      const tsx = `
        export const AccessibleCard = () => {
          return (
            <div>
              <h1>Main Title</h1>
              <h2>Subtitle</h2>
              <img src="/logo.png" alt="Company Logo" />
              <button aria-label="Close dialog">X</button>
              <input type="text" aria-label="Search items" />
            </div>
          );
        };
      `;

      const report = oracle.auditTsx(tsx);
      expect(report.isCompliant).toBe(true);
      expect(report.errorsCount).toBe(0);
    });

    it('should calculate color contrast ratio correctly', () => {
      // Black on White: ~21:1
      const highContrast = oracle.calculateContrastRatio('#000000', '#ffffff');
      expect(highContrast.ratio).toBeGreaterThanOrEqual(20);
      expect(highContrast.passesAA).toBe(true);
      expect(highContrast.passesAAA).toBe(true);

      // Light gray on White: fails AA (< 4.5:1)
      const lowContrast = oracle.calculateContrastRatio('#cccccc', '#ffffff');
      expect(lowContrast.passesAA).toBe(false);
    });
  });

  describe('SeoMetaGenerator', () => {
    const sampleSeo: UniversalSeoMetadataIR = {
      title: 'Elmos Cloud Console',
      titleTemplate: '%s | Elmos Cloud',
      description: 'Enterprise Polyglot Component Dialect Migration Platform',
      keywords: ['migration', 'compiler', 'react', 'wechat', 'vue'],
      canonicalUrl: 'https://elmos.cloud/console',
      openGraph: {
        title: 'Elmos Cloud Console',
        description: 'Next-gen cross-platform component compiler',
        type: 'website',
        url: 'https://elmos.cloud/console',
        image: 'https://elmos.cloud/og.png',
        imageAlt: 'Elmos Console Banner',
        siteName: 'Elmos',
      },
      twitter: {
        card: 'summary_large_image',
        site: '@elmos_ai',
        title: 'Elmos Cloud Console',
        description: 'Next-gen cross-platform component compiler',
        image: 'https://elmos.cloud/twitter.png',
      },
      jsonLdSchemas: [
        {
          context: 'https://schema.org',
          type: 'WebSite',
          data: {
            name: 'Elmos',
            url: 'https://elmos.cloud',
          },
        },
      ],
    };

    it('should emit Next.js App Router metadata', () => {
      const code = seoGen.emitNextJsMetadata(sampleSeo);
      expect(code).toContain(`import type { Metadata } from 'next';`);
      expect(code).toContain(`export const metadata: Metadata = {`);
      expect(code).toContain(`title: {`);
      expect(code).toContain(`canonical: 'https://elmos.cloud/console'`);
      expect(code).toContain(`openGraph: {`);
    });

    it('should emit React Helmet component with JSON-LD schema', () => {
      const code = seoGen.emitReactHelmet(sampleSeo);
      expect(code).toContain(`<Helmet>`);
      expect(code).toContain(`<title>Elmos Cloud Console</title>`);
      expect(code).toContain(`property="og:title"`);
      expect(code).toContain(`type="application/ld+json"`);
    });

    it('should emit Nuxt 3 useSeoMeta composable', () => {
      const code = seoGen.emitNuxtUseSeoMeta(sampleSeo);
      expect(code).toContain(`useSeoMeta({`);
      expect(code).toContain(`ogTitle: 'Elmos Cloud Console'`);
    });

    it('should emit MiniApp page share config', () => {
      const code = seoGen.emitMiniAppShareConfig(sampleSeo);
      expect(code).toContain(`wx.setNavigationBarTitle`);
      expect(code).toContain(`onShareAppMessage()`);
      expect(code).toContain(`onShareTimeline()`);
    });
  });

  describe('CrossPlatformA11yNormalizer', () => {
    const sampleDialogNode: AccessibleNodeIR = {
      id: 'confirm_dialog',
      componentTag: 'div',
      aria: {
        role: 'dialog',
        label: 'Confirm Delete Action',
        describedby: 'desc_text',
        expanded: 'isModalOpen',
        hidden: '!isModalOpen',
      },
      focus: {
        autoFocus: true,
        trapFocus: true,
      },
    };

    it('should emit React JSX aria attributes', () => {
      const attrs = normalizer.emitReactAriaAttributes(sampleDialogNode);
      expect(attrs).toContain('role="dialog"');
      expect(attrs).toContain('aria-label="Confirm Delete Action"');
      expect(attrs).toContain('aria-expanded={Boolean(isModalOpen)}');
      expect(attrs).toContain('autoFocus');
    });

    it('should emit Vue 3 template aria attributes', () => {
      const attrs = normalizer.emitVueAriaAttributes(sampleDialogNode);
      expect(attrs).toContain('role="dialog"');
      expect(attrs).toContain(':aria-expanded="Boolean(isModalOpen)"');
      expect(attrs).toContain('autofocus');
    });

    it('should emit WeChat MiniApp WXML aria attributes', () => {
      const attrs = normalizer.emitMiniAppAriaAttributes(sampleDialogNode);
      expect(attrs).toContain('aria-role="dialog"');
      expect(attrs).toContain('aria-label="Confirm Delete Action"');
      expect(attrs).toContain('aria-expanded="{{ isModalOpen }}"');
    });

    it('should emit ArkUI Declarative accessibility modifiers', () => {
      const mods = normalizer.emitArkUIAccessibilityModifiers(sampleDialogNode);
      expect(mods).toContain('.accessibilityGroup(true)');
      expect(mods).toContain(`.accessibilityText('Confirm Delete Action')`);
    });

    it('should generate focus trap utility', () => {
      const code = normalizer.emitFocusTrapUtility();
      expect(code).toContain('createFocusTrap');
      expect(code).toContain('handleKeyDown(e: KeyboardEvent)');
      expect(code).toContain('e.key === \'Escape\'');
      expect(code).toContain('e.key !== \'Tab\'');
    });
  });
});
