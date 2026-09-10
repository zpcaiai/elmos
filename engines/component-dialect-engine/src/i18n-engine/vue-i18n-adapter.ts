/**
 * @file vue-i18n-adapter.ts
 * @description Full AST parser, lowerer, and code generator for vue-i18n (Vue 2 & Vue 3 Composition API).
 * Handles `$t()`, `$tc()`, `useI18n()`, `<i18n-t>` translation components,
 * pipe-delimited plural rules, named interpolation, and JSON/TypeScript dictionary output.
 */

import * as ts from 'typescript';
import {
  TranslationMessageIR,
  LocaleDictionaryIR,
  InterpolationToken,
  PluralRuleMessage,
  SupportedLocale,
  TextDirection,
  UniversalI18nBundleIR,
} from './i18n-ir-types';

export interface VueI18nParsedTemplate {
  templateInterpolations: Array<{
    key: string;
    args: string[];
    isPlural: boolean;
    line: number;
  }>;
  i18nComponents: Array<{
    keypath: string;
    tag: string;
    scope: 'global' | 'parent';
  }>;
}

export interface VueI18nParsedScript {
  usesCompositionApi: boolean;
  importedFunctions: string[];
  scriptCalls: Array<{
    key: string;
    args: string[];
    isPlural: boolean;
  }>;
}

export class VueI18nAdapter {
  private defaultNamespace: string = 'messages';

  constructor(defaultNamespace: string = 'messages') {
    this.defaultNamespace = defaultNamespace;
  }

  /**
   * Parse Vue Single-File Component (SFC) template & script sections for vue-i18n invocations.
   */
  public parseVueSfc(sfcContent: string): { template: VueI18nParsedTemplate; script: VueI18nParsedScript } {
    const templateMatch = sfcContent.match(/<template>([\s\S]*?)<\/template>/i);
    const templateContent = templateMatch ? templateMatch[1] || '' : '';

    const scriptMatch = sfcContent.match(/<script(?:\s+[^>]*)?>([\s\S]*?)<\/script>/i);
    const scriptContent = scriptMatch ? scriptMatch[1] || '' : '';

    const templateResult = this.parseTemplate(templateContent);
    const scriptResult = this.parseScript(scriptContent);

    return {
      template: templateResult,
      script: scriptResult,
    };
  }

  /**
   * Parse template block for `$t('key')`, `$tc('key', count)`, and `<i18n-t keypath="...">`.
   */
  public parseTemplate(templateContent: string): VueI18nParsedTemplate {
    const result: VueI18nParsedTemplate = {
      templateInterpolations: [],
      i18nComponents: [],
    };

    // 1. Match {{ $t('key', ...) }} or {{ $tc('key', ...) }}
    const tRegex = /\{\{\s*\$(t|tc)\s*\(\s*(['"][^'"]+['"])([^)]*)\)\s*\}\}/g;
    let match: RegExpExecArray | null;

    while ((match = tRegex.exec(templateContent)) !== null) {
      const isPlural = match[1] === 'tc';
      const rawKey = match[2] ? match[2].slice(1, -1) : '';
      const rawArgs = match[3] ? match[3].trim() : '';
      const args = rawArgs ? rawArgs.split(',').map((s) => s.trim()).filter(Boolean) : [];

      result.templateInterpolations.push({
        key: rawKey,
        args,
        isPlural,
        line: templateContent.slice(0, match.index).split('\n').length,
      });
    }

    // 2. Match :title="$t('key')" in attributes
    const attrRegex = /:(?:[a-zA-Z0-9_-]+)\s*=\s*"\s*\$(t|tc)\s*\(\s*(['"][^'"]+['"])([^)]*)\)"/g;
    while ((match = attrRegex.exec(templateContent)) !== null) {
      const isPlural = match[1] === 'tc';
      const rawKey = match[2] ? match[2].slice(1, -1) : '';
      const rawArgs = match[3] ? match[3].trim() : '';
      const args = rawArgs ? rawArgs.split(',').map((s) => s.trim()).filter(Boolean) : [];

      result.templateInterpolations.push({
        key: rawKey,
        args,
        isPlural,
        line: templateContent.slice(0, match.index).split('\n').length,
      });
    }

    // 3. Match <i18n-t keypath="key" tag="span">
    const compRegex = /<i18n-t\s+([^>]+)>/g;
    while ((match = compRegex.exec(templateContent)) !== null) {
      const attrsStr = match[1] || '';
      const keypathMatch = attrsStr.match(/keypath\s*=\s*(['"][^'"]+['"]|"[^"]+")/);
      const tagMatch = attrsStr.match(/tag\s*=\s*(['"][^'"]+['"]|"[^"]+")/);
      const scopeMatch = attrsStr.match(/scope\s*=\s*(['"][^'"]+['"]|"[^"]+")/);

      const keypath = keypathMatch && keypathMatch[1] ? keypathMatch[1].replace(/['"]/g, '') : '';
      const tag = tagMatch && tagMatch[1] ? tagMatch[1].replace(/['"]/g, '') : 'span';
      const scope = (scopeMatch && scopeMatch[1] && scopeMatch[1].includes('parent')) ? 'parent' : 'global';

      if (keypath) {
        result.i18nComponents.push({ keypath, tag, scope });
      }
    }

    return result;
  }

  /**
   * Parse TypeScript/JavaScript script block for `useI18n()` or `this.$t()` invocations.
   */
  public parseScript(scriptContent: string): VueI18nParsedScript {
    const result: VueI18nParsedScript = {
      usesCompositionApi: false,
      importedFunctions: [],
      scriptCalls: [],
    };

    if (!scriptContent.trim()) return result;

    const sourceFile = ts.createSourceFile(
      'script.ts',
      scriptContent,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS
    );

    let tIdentName = 't';

    const visit = (node: ts.Node) => {
      // 1. Check imports: import { useI18n } from 'vue-i18n'
      if (ts.isImportDeclaration(node) && node.importClause && node.moduleSpecifier) {
        const mod = (node.moduleSpecifier as ts.StringLiteral).text;
        if (mod === 'vue-i18n' || mod === 'vue-i18n/dist/vue-i18n.esm-bundler.js') {
          if (node.importClause.namedBindings && ts.isNamedImports(node.importClause.namedBindings)) {
            for (const el of node.importClause.namedBindings.elements) {
              result.importedFunctions.push(el.name.text);
              if (el.name.text === 'useI18n') {
                result.usesCompositionApi = true;
              }
            }
          }
        }
      }

      // 2. Check const { t } = useI18n()
      if (ts.isVariableDeclaration(node) && node.initializer && ts.isCallExpression(node.initializer)) {
        if (ts.isIdentifier(node.initializer.expression) && node.initializer.expression.text === 'useI18n') {
          result.usesCompositionApi = true;
          if (ts.isObjectBindingPattern(node.name)) {
            for (const elem of node.name.elements) {
              if (ts.isIdentifier(elem.name) && (elem.propertyName?.getText(sourceFile) === 't' || elem.name.text === 't')) {
                tIdentName = elem.name.text;
              }
            }
          }
        }
      }

      // 3. Check t('key', ...) or this.$t('key', ...)
      if (ts.isCallExpression(node)) {
        let isMatch = false;
        let isPlural = false;

        if (ts.isIdentifier(node.expression) && node.expression.text === tIdentName) {
          isMatch = true;
        } else if (ts.isPropertyAccessExpression(node.expression)) {
          const prop = node.expression.name.text;
          if (prop === '$t' || prop === '$tc') {
            isMatch = true;
            isPlural = prop === '$tc';
          }
        }

        if (isMatch && node.arguments.length > 0) {
          const firstArg = node.arguments[0];
          if (firstArg && ts.isStringLiteral(firstArg)) {
            const key = firstArg.text;
            const args = node.arguments.slice(1).map((a) => (a ? a.getText(sourceFile) : ''));
            result.scriptCalls.push({ key, args, isPlural });
          }
        }
      }

      ts.forEachChild(node, visit);
    };

    visit(sourceFile);
    return result;
  }

  /**
   * Lift Vue i18n messages dictionary into Universal I18n IR.
   */
  public liftVueDictionary(
    locales: SupportedLocale[],
    rawMessages: Record<SupportedLocale, Record<string, any>>
  ): UniversalI18nBundleIR {
    const dictionaries: Record<SupportedLocale, Record<string, LocaleDictionaryIR>> = {} as any;

    for (const loc of locales) {
      dictionaries[loc] = {};
      const rawMap = rawMessages[loc] || {};
      const direction: TextDirection = (loc === 'ar-SA' || loc === 'he-IL') ? 'rtl' : 'ltr';

      const flatMessages = this.flattenObject(rawMap, '');
      const messagesIR: Record<string, TranslationMessageIR> = {};

      for (const [key, val] of Object.entries(flatMessages)) {
        const text = String(val);

        if (text.includes('|')) {
          const parts = text.split('|').map((p) => p.trim());
          const pluralRule = this.convertPipePluralToIcuRule(parts);
          const rawPattern = this.convertPipePluralToIcuPattern('count', parts);
          const tokens: InterpolationToken[] = [{ name: 'count', type: 'number' }];

          const otherTokens = this.extractVueTokens(text).filter((t) => t.name !== 'count');
          tokens.push(...otherTokens);

          messagesIR[key] = {
            key,
            rawPattern,
            tokens,
            pluralRule,
            namespace: this.defaultNamespace,
          };
        } else {
          const tokens = this.extractVueTokens(text);
          messagesIR[key] = {
            key,
            rawPattern: text,
            tokens,
            namespace: this.defaultNamespace,
          };
        }
      }

      dictionaries[loc][this.defaultNamespace] = {
        locale: loc,
        direction,
        namespace: this.defaultNamespace,
        messages: messagesIR,
      };
    }

    return {
      version: '1.0',
      defaultLocale: locales[0] || 'zh-CN',
      fallbackLocale: locales.includes('en-US') ? 'en-US' : (locales[0] || 'zh-CN'),
      namespaces: [this.defaultNamespace],
      dictionaries,
    };
  }

  /**
   * Emit Vue 3 SFC component using `<script setup lang="ts">` and `useI18n()`.
   */
  public emitVue3Sfc(
    componentName: string,
    messageKeys: string[],
    options: { scopedCss?: boolean } = {}
  ): string {
    const lines: string[] = [];

    lines.push(`<template>`);
    lines.push(`  <div class="${this.kebabCase(componentName)}-container">`);

    for (const key of messageKeys) {
      if (key.includes('count') || key.includes('item') || key.includes('total')) {
        lines.push(`    <p class="i18n-plural">{{ t('${key}', { count: itemCount }, itemCount) }}</p>`);
      } else if (key.includes('user') || key.includes('name') || key.includes('greeting')) {
        lines.push(`    <h1 class="i18n-interpolated">{{ t('${key}', { name: userName }) }}</h1>`);
      } else {
        lines.push(`    <span class="i18n-text">{{ t('${key}') }}</span>`);
      }
    }

    lines.push(`  </div>`);
    lines.push(`</template>`);
    lines.push('');

    lines.push(`<script setup lang="ts">`);
    lines.push(`import { ref } from 'vue';`);
    lines.push(`import { useI18n } from 'vue-i18n';`);
    lines.push('');
    lines.push(`const { t, locale } = useI18n();`);
    lines.push('');
    lines.push(`const itemCount = ref<number>(1);`);
    lines.push(`const userName = ref<string>('Developer');`);
    lines.push(`</script>`);

    if (options.scopedCss) {
      lines.push('');
      lines.push(`<style scoped>`);
      lines.push(`.${this.kebabCase(componentName)}-container {`);
      lines.push(`  display: flex;`);
      lines.push(`  flex-direction: column;`);
      lines.push(`  gap: 12px;`);
      lines.push(`}`);
      lines.push(`</style>`);
    }

    return lines.join('\n');
  }

  /**
   * Emit vue-i18n dictionary objects formatted as JSON or TS export.
   */
  public emitVueDictionaries(bundle: UniversalI18nBundleIR): Record<string, string> {
    const result: Record<string, string> = {};

    for (const [locale, nsMap] of Object.entries(bundle.dictionaries)) {
      const messagesObj: Record<string, any> = {};

      for (const [ns, dict] of Object.entries(nsMap)) {
        for (const [key, msg] of Object.entries(dict.messages)) {
          if (msg.pluralRule) {
            const pipeStr = this.convertPluralRuleToVuePipe(msg.pluralRule);
            this.setDeepValue(messagesObj, key, pipeStr);
          } else {
            this.setDeepValue(messagesObj, key, msg.rawPattern);
          }
        }
      }

      result[`locales/${locale}.json`] = JSON.stringify(messagesObj, null, 2);
    }

    return result;
  }

  /**
   * Generate `i18n.ts` vue-i18n instance configuration for Vue 3 createI18n().
   */
  public emitVueI18nPlugin(bundle: UniversalI18nBundleIR): string {
    const locales = Object.keys(bundle.dictionaries);

    const lines: string[] = [
      `import { createI18n } from 'vue-i18n';`,
      '',
    ];

    for (const loc of locales) {
      const locClean = loc.replace('-', '_');
      lines.push(`import ${locClean} from './locales/${loc}.json';`);
    }

    lines.push('');
    lines.push(`export const messages = {`);
    for (const loc of locales) {
      const locClean = loc.replace('-', '_');
      lines.push(`  '${loc}': ${locClean},`);
    }
    lines.push(`};`);
    lines.push('');

    lines.push(`export const i18n = createI18n({`);
    lines.push(`  legacy: false, // Composition API mode`);
    lines.push(`  locale: '${bundle.defaultLocale}',`);
    lines.push(`  fallbackLocale: '${bundle.fallbackLocale}',`);
    lines.push(`  messages,`);
    lines.push(`  globalInjection: true,`);
    lines.push(`});`);
    lines.push('');
    lines.push(`export default i18n;`);

    return lines.join('\n');
  }

  private extractVueTokens(pattern: string): InterpolationToken[] {
    const tokens: InterpolationToken[] = [];
    const seen = new Set<string>();

    const regex = /\{([a-zA-Z0-9_]+)\}/g;
    let match: RegExpExecArray | null;
    while ((match = regex.exec(pattern)) !== null) {
      const name = match[1];
      if (name && !seen.has(name)) {
        seen.add(name);
        tokens.push({
          name,
          type: name.includes('count') || name.includes('num') ? 'number' : 'string',
        });
      }
    }

    return tokens;
  }

  private convertPipePluralToIcuRule(parts: string[]): PluralRuleMessage {
    if (parts.length === 2) {
      return {
        type: 'plural',
        variableName: 'count',
        options: {
          one: parts[0] || '',
          other: parts[1] || '',
        },
      };
    } else if (parts.length >= 3) {
      return {
        type: 'plural',
        variableName: 'count',
        options: {
          zero: parts[0] || '',
          one: parts[1] || '',
          other: parts[2] || '',
        },
      };
    } else {
      return {
        type: 'plural',
        variableName: 'count',
        options: {
          other: parts[0] || '',
        },
      };
    }
  }

  private convertPipePluralToIcuPattern(variableName: string, parts: string[]): string {
    if (parts.length === 2) {
      return `{${variableName}, plural, one{${parts[0] || ''}} other{${parts[1] || ''}}}`;
    } else if (parts.length >= 3) {
      return `{${variableName}, plural, zero{${parts[0] || ''}} one{${parts[1] || ''}} other{${parts[2] || ''}}}`;
    } else {
      return `{${variableName}, plural, other{${parts[0] || ''}}}`;
    }
  }

  private convertPluralRuleToVuePipe(rule: PluralRuleMessage): string {
    const opts = rule.options;
    if (opts.zero && opts.one && opts.other) {
      return `${opts.zero} | ${opts.one} | ${opts.other}`;
    } else if (opts.one && opts.other) {
      return `${opts.one} | ${opts.other}`;
    } else {
      return opts.other || '';
    }
  }

  private flattenObject(obj: Record<string, any>, prefix: string = ''): Record<string, string> {
    const result: Record<string, string> = {};

    for (const [key, value] of Object.entries(obj)) {
      const newKey = prefix ? `${prefix}.${key}` : key;
      if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        Object.assign(result, this.flattenObject(value, newKey));
      } else {
        result[newKey] = String(value);
      }
    }

    return result;
  }

  private setDeepValue(obj: Record<string, any>, path: string, value: any): void {
    const segments = path.split('.');
    let cur = obj;
    for (let i = 0; i < segments.length - 1; i++) {
      const s = segments[i];
      if (!s) continue;
      if (!cur[s] || typeof cur[s] !== 'object') {
        cur[s] = {};
      }
      cur = cur[s];
    }
    const lastSeg = segments[segments.length - 1];
    if (lastSeg) {
      cur[lastSeg] = value;
    }
  }

  private kebabCase(str: string): string {
    return str.replace(/([a-z])([A-Z])/g, '$1-$2').toLowerCase();
  }
}
