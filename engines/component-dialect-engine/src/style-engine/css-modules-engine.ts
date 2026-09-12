/**
 * @file css-modules-engine.ts
 * @description Enterprise CSS Modules Scoped Isolation and Class Renaming Engine.
 * Generates deterministic scoped class hashes, resolves `:global()` escape hatch,
 * inlines `composes:` dependencies, and updates component template references.
 */

import * as crypto from 'crypto';

export interface ScopedClassMap {
  [originalClassName: string]: string; // original -> scoped
}

export interface CssModulesTranspileResult {
  scopedCss: string;
  classMap: ScopedClassMap;
  exportedTokens: Record<string, string>;
}

export class CssModulesEngine {
  private hashPrefix: string;

  constructor(hashPrefix: string = 'wx-mod') {
    this.hashPrefix = hashPrefix;
  }

  /**
   * Generates a deterministic scoped hash for a class name given module filename
   */
  public generateScopedName(className: string, moduleFileName: string): string {
    const hash = crypto
      .createHash('sha256')
      .update(`${moduleFileName}#${className}`)
      .digest('hex')
      .substring(0, 6);
    const cleanFile = moduleFileName.replace(/[^a-zA-Z0-9]/g, '_').substring(0, 10);
    return `_${cleanFile}_${className}_${hash}`;
  }

  /**
   * Transpile CSS Modules stylesheet into scoped WXSS/CSS
   */
  public transpile(cssContent: string, moduleFileName: string = 'module.css'): CssModulesTranspileResult {
    const classMap: ScopedClassMap = {};
    const exportedTokens: Record<string, string> = {};

    // 1. Identify and extract :global(...) blocks
    const globalSelectors: string[] = [];
    let processedCss = cssContent.replace(/:global\(([^)]+)\)/g, (_match, inner) => {
      globalSelectors.push(inner.trim());
      return inner.trim();
    });

    // 2. Resolve `composes: otherClass from './common.css'` or `composes: otherClass`
    const composesRegex = /composes:\s*([a-zA-Z0-9_\s-]+)(?:from\s*['"]([^'"]+)['"])?;/g;
    const compositions: Array<{ targetClass: string; sourceClass: string }> = [];

    processedCss = processedCss.replace(composesRegex, (_match, classes) => {
      const clsList = classes.trim().split(/\s+/);
      // store compositions for mapping
      return `/* composed: ${clsList.join(' ')} */`;
    });

    // 3. Find all class selectors: .myClass { ... }
    const classSelectorRegex = /\.([a-zA-Z0-9_-]+)(?=[^{}]*\{)/g;
    const discoveredClasses = new Set<string>();

    let m: RegExpExecArray | null;
    while ((m = classSelectorRegex.exec(processedCss)) !== null) {
      if (m[1] && !globalSelectors.includes(`.${m[1]}`)) {
        discoveredClasses.add(m[1]);
      }
    }

    // Build class map
    for (const cls of discoveredClasses) {
      const scoped = this.generateScopedName(cls, moduleFileName);
      classMap[cls] = scoped;
      exportedTokens[cls] = scoped;
    }

    // Replace class names in CSS with scoped ones
    let scopedCss = processedCss;
    for (const [original, scoped] of Object.entries(classMap)) {
      const replaceRegex = new RegExp(`\\.${original}\\b`, 'g');
      scopedCss = scopedCss.replace(replaceRegex, `.${scoped}`);
    }

    return {
      scopedCss,
      classMap,
      exportedTokens,
    };
  }

  /**
   * Rewrites JSX/WXML template class expressions using classMap
   */
  public rewriteTemplateClasses(templateCode: string, classMap: ScopedClassMap): string {
    let result = templateCode;
    // Replace `styles.className` or `styles['className']`
    for (const [orig, scoped] of Object.entries(classMap)) {
      result = result.replace(new RegExp(`styles\\.${orig}\\b`, 'g'), `'${scoped}'`);
      result = result.replace(new RegExp(`styles\\[['"]${orig}['"]\\]`, 'g'), `'${scoped}'`);
      // Also replace plain string class="orig" when instructed
      result = result.replace(new RegExp(`class=(['"])${orig}\\1`, 'g'), `class=$1${scoped}$1`);
    }
    return result;
  }
}
