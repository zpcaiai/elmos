/**
 * @file seo-meta-generator.ts
 * @description Cross-Platform SEO Metadata and Structured Data Generator.
 * Generates:
 * 1. Next.js 14/15 App Router typed `Metadata` objects.
 * 2. React Helmet `<Helmet>` JSX components.
 * 3. Vue 3 / Nuxt 3 `useHead()` / `useSeoMeta()` composables.
 * 4. WeChat MiniApp Page `onShareAppMessage` and `onShareTimeline` handlers.
 * 5. W3C Schema.org JSON-LD structured data scripts.
 * Conforms to Batch 32 Skill 1221 (b32-accessibility-i18n-seo-visual-e2e).
 */

import {
  UniversalSeoMetadataIR,
  JsonLdSchemaIR,
} from './a11y-seo-ir-types';

export class SeoMetaGenerator {
  /**
   * Emit Next.js 14/15 App Router Metadata TypeScript declaration.
   */
  public emitNextJsMetadata(seo: UniversalSeoMetadataIR): string {
    const lines: string[] = [
      `import type { Metadata } from 'next';`,
      '',
      `export const metadata: Metadata = {`,
    ];

    if (seo.titleTemplate) {
      lines.push(`  title: {`);
      lines.push(`    default: '${this.escapeStr(seo.title)}',`);
      lines.push(`    template: '${this.escapeStr(seo.titleTemplate)}',`);
      lines.push(`  },`);
    } else {
      lines.push(`  title: '${this.escapeStr(seo.title)}',`);
    }

    lines.push(`  description: '${this.escapeStr(seo.description)}',`);

    if (seo.keywords && seo.keywords.length > 0) {
      lines.push(`  keywords: [${seo.keywords.map((k) => `'${this.escapeStr(k)}'`).join(', ')}],`);
    }

    if (seo.canonicalUrl || seo.alternateLanguages) {
      lines.push(`  alternates: {`);
      if (seo.canonicalUrl) {
        lines.push(`    canonical: '${this.escapeStr(seo.canonicalUrl)}',`);
      }
      if (seo.alternateLanguages && seo.alternateLanguages.length > 0) {
        lines.push(`    languages: {`);
        for (const alt of seo.alternateLanguages) {
          lines.push(`      '${alt.hrefLang}': '${this.escapeStr(alt.href)}',`);
        }
        lines.push(`    },`);
      }
      lines.push(`  },`);
    }

    if (seo.robots) {
      lines.push(`  robots: {`);
      lines.push(`    index: ${seo.robots.index},`);
      lines.push(`    follow: ${seo.robots.follow},`);
      lines.push(`  },`);
    }

    if (seo.openGraph) {
      const og = seo.openGraph;
      lines.push(`  openGraph: {`);
      lines.push(`    title: '${this.escapeStr(og.title)}',`);
      lines.push(`    description: '${this.escapeStr(og.description)}',`);
      lines.push(`    url: '${this.escapeStr(og.url)}',`);
      lines.push(`    siteName: '${this.escapeStr(og.siteName || og.title)}',`);
      lines.push(`    images: [{ url: '${this.escapeStr(og.image)}', alt: '${this.escapeStr(og.imageAlt || og.title)}' }],`);
      lines.push(`    type: '${og.type}',`);
      lines.push(`  },`);
    }

    if (seo.twitter) {
      const tw = seo.twitter;
      lines.push(`  twitter: {`);
      lines.push(`    card: '${tw.card}',`);
      lines.push(`    title: '${this.escapeStr(tw.title)}',`);
      lines.push(`    description: '${this.escapeStr(tw.description)}',`);
      if (tw.image) lines.push(`    images: ['${this.escapeStr(tw.image)}'],`);
      if (tw.site) lines.push(`    site: '${this.escapeStr(tw.site)}',`);
      lines.push(`  },`);
    }

    lines.push(`};`);
    return lines.join('\n');
  }

  /**
   * Emit React Helmet JSX Component.
   */
  public emitReactHelmet(seo: UniversalSeoMetadataIR): string {
    const lines: string[] = [
      `import React from 'react';`,
      `import { Helmet } from 'react-helmet-async';`,
      '',
      `export const PageSeo: React.FC = () => {`,
      `  return (`,
      `    <Helmet>`,
      `      <title>${this.escapeHtml(seo.title)}</title>`,
      `      <meta name="description" content="${this.escapeHtml(seo.description)}" />`,
    ];

    if (seo.keywords && seo.keywords.length > 0) {
      lines.push(`      <meta name="keywords" content="${this.escapeHtml(seo.keywords.join(', '))}" />`);
    }

    if (seo.canonicalUrl) {
      lines.push(`      <link rel="canonical" href="${this.escapeHtml(seo.canonicalUrl)}" />`);
    }

    if (seo.openGraph) {
      const og = seo.openGraph;
      lines.push(`      <meta property="og:title" content="${this.escapeHtml(og.title)}" />`);
      lines.push(`      <meta property="og:description" content="${this.escapeHtml(og.description)}" />`);
      lines.push(`      <meta property="og:type" content="${og.type}" />`);
      lines.push(`      <meta property="og:url" content="${this.escapeHtml(og.url)}" />`);
      lines.push(`      <meta property="og:image" content="${this.escapeHtml(og.image)}" />`);
    }

    if (seo.twitter) {
      const tw = seo.twitter;
      lines.push(`      <meta name="twitter:card" content="${tw.card}" />`);
      lines.push(`      <meta name="twitter:title" content="${this.escapeHtml(tw.title)}" />`);
      lines.push(`      <meta name="twitter:description" content="${this.escapeHtml(tw.description)}" />`);
      if (tw.image) lines.push(`      <meta name="twitter:image" content="${this.escapeHtml(tw.image)}" />`);
    }

    if (seo.jsonLdSchemas && seo.jsonLdSchemas.length > 0) {
      for (const schema of seo.jsonLdSchemas) {
        const jsonStr = JSON.stringify({ '@context': schema.context, '@type': schema.type, ...schema.data });
        lines.push(`      <script type="application/ld+json">{JSON.stringify(${jsonStr})}</script>`);
      }
    }

    lines.push(`    </Helmet>`);
    lines.push(`  );`);
    lines.push(`};`);

    return lines.join('\n');
  }

  /**
   * Emit Vue 3 / Nuxt 3 useSeoMeta() composable code.
   */
  public emitNuxtUseSeoMeta(seo: UniversalSeoMetadataIR): string {
    const lines: string[] = [
      `useSeoMeta({`,
      `  title: '${this.escapeStr(seo.title)}',`,
      `  description: '${this.escapeStr(seo.description)}',`,
    ];

    if (seo.openGraph) {
      const og = seo.openGraph;
      lines.push(`  ogTitle: '${this.escapeStr(og.title)}',`);
      lines.push(`  ogDescription: '${this.escapeStr(og.description)}',`);
      lines.push(`  ogImage: '${this.escapeStr(og.image)}',`);
      lines.push(`  ogUrl: '${this.escapeStr(og.url)}',`);
      lines.push(`  ogType: '${og.type}',`);
    }

    if (seo.twitter) {
      const tw = seo.twitter;
      lines.push(`  twitterCard: '${tw.card}',`);
      lines.push(`  twitterTitle: '${this.escapeStr(tw.title)}',`);
      lines.push(`  twitterDescription: '${this.escapeStr(tw.description)}',`);
      if (tw.image) lines.push(`  twitterImage: '${this.escapeStr(tw.image)}',`);
    }

    lines.push(`});`);
    return lines.join('\n');
  }

  /**
   * Emit WeChat MiniApp Page share and navigation title methods.
   */
  public emitMiniAppShareConfig(seo: UniversalSeoMetadataIR): string {
    const lines: string[] = [
      `/**`,
      ` * WeChat MiniApp Page Share & SEO configuration`,
      ` */`,
      `export const miniAppPageSeo = {`,
      `  onLoad() {`,
      `    wx.setNavigationBarTitle({`,
      `      title: '${this.escapeStr(seo.title)}',`,
      `    });`,
      `  },`,
      '',
      `  onShareAppMessage() {`,
      `    return {`,
      `      title: '${this.escapeStr(seo.openGraph?.title || seo.title)}',`,
      `      desc: '${this.escapeStr(seo.openGraph?.description || seo.description)}',`,
      `      path: '${this.escapeStr(seo.openGraph?.url || '/pages/index/index')}',`,
      `      imageUrl: '${this.escapeStr(seo.openGraph?.image || '')}',`,
      `    };`,
      `  },`,
      '',
      `  onShareTimeline() {`,
      `    return {`,
      `      title: '${this.escapeStr(seo.openGraph?.title || seo.title)}',`,
      `      query: 'from=timeline',`,
      `      imageUrl: '${this.escapeStr(seo.openGraph?.image || '')}',`,
      `    };`,
      `  },`,
      `};`,
    ];

    return lines.join('\n');
  }

  /**
   * Emit JSON-LD Schema Script.
   */
  public emitJsonLdScript(schema: JsonLdSchemaIR): string {
    const payload = {
      '@context': schema.context,
      '@type': schema.type,
      ...schema.data,
    };
    return `<script type="application/ld+json">\n${JSON.stringify(payload, null, 2)}\n</script>`;
  }

  private escapeStr(str: string): string {
    return str.replace(/'/g, "\\'").replace(/\n/g, ' ');
  }

  private escapeHtml(str: string): string {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
}
