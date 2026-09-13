/**
 * @file island-architecture-compiler.ts
 * @description Island Architecture Compiler for selective and progressive hydration.
 * Compiles static HTML shells with embedded micro-islands and runtime hydration triggers
 * (client:load, client:idle, client:visible, client:media, client:only).
 * Conforms to Batch 32 Skill 1213 (b32-rendering-ssr-csr-hydration).
 */

import {
  HydrationBoundaryIR,
  IslandArchitectureIR,
  HydrationStrategy,
} from './hydration-ir-types';

export class IslandArchitectureCompiler {
  /**
   * Compile a collection of hydration boundaries into an IslandArchitectureIR document
   */
  public compile(
    documentId: string,
    staticHtmlBody: string,
    islands: HydrationBoundaryIR[]
  ): IslandArchitectureIR {
    let htmlShell = staticHtmlBody;
    const preloadLinks: string[] = [];

    // Replace island marker placeholders or inject island container wrappers
    for (const island of islands) {
      const islandTag = this.generateIslandElement(island);
      const placeholder = `<!-- ELMOS_ISLAND:${island.id} -->`;

      if (htmlShell.includes(placeholder)) {
        htmlShell = htmlShell.replace(placeholder, islandTag);
      } else {
        htmlShell += `\n${islandTag}`;
      }

      preloadLinks.push(island.entryFilePath);
    }

    const scriptLoader = this.generateClientScriptLoader(islands);

    return {
      documentId,
      staticHtmlShell: htmlShell,
      islands,
      scriptLoaderBundle: scriptLoader,
      streamingEnabled: islands.some((i) => i.strategy === 'server:streaming'),
      preloadLinks,
    };
  }

  private generateIslandElement(island: HydrationBoundaryIR): string {
    const propsJson = JSON.stringify(island.props).replace(/"/g, '&quot;');
    const attrs = [
      `component-name="${island.componentName}"`,
      `component-url="${island.entryFilePath}"`,
      `strategy="${island.strategy}"`,
      `props="${propsJson}"`,
    ];

    if (island.mediaQueryCondition) {
      attrs.push(`media="${island.mediaQueryCondition}"`);
    }
    if (island.viewportMargin) {
      attrs.push(`root-margin="${island.viewportMargin}"`);
    }

    const fallback = island.fallbackHtml || `<div class="island-fallback">${island.componentName} (Loading...)</div>`;

    return `<elmos-island id="${island.id}" ${attrs.join(' ')}>${fallback}</elmos-island>`;
  }

  /**
   * Generate vanilla JS runtime loader that activates islands based on their strategy
   */
  public generateClientScriptLoader(islands: HydrationBoundaryIR[]): string {
    const lines: string[] = [];

    lines.push(`(function() {`);
    lines.push(`  function hydrateIsland(el) {`);
    lines.push(`    if (el.__hydrated) return;`);
    lines.push(`    el.__hydrated = true;`);
    lines.push(`    var url = el.getAttribute('component-url');`);
    lines.push(`    var rawProps = el.getAttribute('props');`);
    lines.push(`    var props = rawProps ? JSON.parse(rawProps) : {};`);
    lines.push(`    import(url).then(function(mod) {`);
    lines.push(`      var render = mod.render || mod.default;`);
    lines.push(`      if (typeof render === 'function') {`);
    lines.push(`        render(el, props);`);
    lines.push(`      }`);
    lines.push(`    }).catch(function(err) {`);
    lines.push(`      console.error('[IslandLoader] Hydration error for ' + url, err);`);
    lines.push(`    });`);
    lines.push(`  }\n`);

    lines.push(`  var islands = document.querySelectorAll('elmos-island');`);
    lines.push(`  islands.forEach(function(island) {`);
    lines.push(`    var strategy = island.getAttribute('strategy');`);
    lines.push(`    if (strategy === 'client:load') {`);
    lines.push(`      hydrateIsland(island);`);
    lines.push(`    } else if (strategy === 'client:idle') {`);
    lines.push(`      if ('requestIdleCallback' in window) {`);
    lines.push(`        window.requestIdleCallback(function() { hydrateIsland(island); });`);
    lines.push(`      } else {`);
    lines.push(`        setTimeout(function() { hydrateIsland(island); }, 200);`);
    lines.push(`      }`);
    lines.push(`    } else if (strategy === 'client:visible') {`);
    lines.push(`      if ('IntersectionObserver' in window) {`);
    lines.push(`        var observer = new IntersectionObserver(function(entries) {`);
    lines.push(`          if (entries[0].isIntersecting) {`);
    lines.push(`            observer.disconnect();`);
    lines.push(`            hydrateIsland(island);`);
    lines.push(`          }`);
    lines.push(`        }, { rootMargin: island.getAttribute('root-margin') || '100px' });`);
    lines.push(`        observer.observe(island);`);
    lines.push(`      } else {`);
    lines.push(`        hydrateIsland(island);`);
    lines.push(`      }`);
    lines.push(`    } else if (strategy === 'client:media') {`);
    lines.push(`      var mediaQuery = island.getAttribute('media');`);
    lines.push(`      if (mediaQuery && window.matchMedia) {`);
    lines.push(`        var mql = window.matchMedia(mediaQuery);`);
    lines.push(`        if (mql.matches) {`);
    lines.push(`          hydrateIsland(island);`);
    lines.push(`        } else {`);
    lines.push(`          mql.addEventListener('change', function handler(e) {`);
    lines.push(`            if (e.matches) {`);
    lines.push(`              mql.removeEventListener('change', handler);`);
    lines.push(`              hydrateIsland(island);`);
    lines.push(`            }`);
    lines.push(`          });`);
    lines.push(`        }`);
    lines.push(`      }`);
    lines.push(`    }`);
    lines.push(`  });`);
    lines.push(`})();`);

    return lines.join('\n');
  }
}
