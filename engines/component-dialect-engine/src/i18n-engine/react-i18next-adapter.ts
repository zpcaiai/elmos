/**
 * @file react-i18next-adapter.ts
 * @description Full AST parser, lowerer, and code generator for react-i18next.
 * Extracts `useTranslation()`, `withTranslation()`, and `<Trans>` JSX invocations into
 * the Universal I18n IR, and emits idiomatic react-i18next TypeScript code from the IR.
 * Supports namespace extraction, interpolation tokens, plural keys (`key_zero`, `key_one`, `key_other`),
 * and ICU MessageFormat plugins.
 */

import * as ts from 'typescript';
import {
  TranslationMessageIR,
  LocaleDictionaryIR,
  InterpolationToken,
  PluralRuleMessage,
  PluralCategory,
  SupportedLocale,
  TextDirection,
  UniversalI18nBundleIR,
  I18nTransformResult,
} from './i18n-ir-types';

export interface ReactI18nextParsedComponent {
  componentName: string;
  namespaces: string[];
  translationCalls: Array<{
    key: string;
    namespace?: string;
    variables: Record<string, string>;
    hasPlural: boolean;
    pluralVariable?: string;
    line: number;
  }>;
  transComponents: Array<{
    i18nKey: string;
    namespace?: string;
    values: Record<string, string>;
    childrenSummary: string;
  }>;
}

export class ReactI18nextAdapter {
  private defaultNamespace: string = 'common';

  constructor(defaultNamespace: string = 'common') {
    this.defaultNamespace = defaultNamespace;
  }

  /**
   * Parse a React component file containing react-i18next hooks or components.
   */
  public parseComponent(sourceCode: string, fileName: string = 'Component.tsx'): ReactI18nextParsedComponent {
    const sourceFile = ts.createSourceFile(
      fileName,
      sourceCode,
      ts.ScriptTarget.Latest,
      true,
      fileName.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS
    );

    const result: ReactI18nextParsedComponent = {
      componentName: 'AnonymousComponent',
      namespaces: [this.defaultNamespace],
      translationCalls: [],
      transComponents: [],
    };

    let tFunctionIdentifierName: string = 't';

    const visit = (node: ts.Node) => {
      // 1. Detect Component Name
      if (ts.isFunctionDeclaration(node) && node.name) {
        result.componentName = node.name.text;
      } else if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) {
        if (node.initializer && (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer))) {
          result.componentName = node.name.text;
        }
      }

      // 2. Detect const { t } = useTranslation('namespace') or const [t] = useTranslation()
      if (ts.isVariableDeclaration(node) && node.initializer && ts.isCallExpression(node.initializer)) {
        const callExp = node.initializer;
        if (ts.isIdentifier(callExp.expression) && callExp.expression.text === 'useTranslation') {
          // Check namespace argument
          if (callExp.arguments.length > 0) {
            const firstArg = callExp.arguments[0];
            if (firstArg && ts.isStringLiteral(firstArg)) {
              if (!result.namespaces.includes(firstArg.text)) {
                result.namespaces.push(firstArg.text);
              }
            } else if (firstArg && ts.isArrayLiteralExpression(firstArg)) {
              for (const elem of firstArg.elements) {
                if (elem && ts.isStringLiteral(elem) && !result.namespaces.includes(elem.text)) {
                  result.namespaces.push(elem.text);
                }
              }
            }
          }

          // Check bound identifiers
          if (ts.isObjectBindingPattern(node.name)) {
            for (const elem of node.name.elements) {
              const propName = elem.propertyName ? elem.propertyName.getText(sourceFile) : elem.name.getText(sourceFile);
              if (ts.isIdentifier(elem.name) && (propName === 't' || elem.name.text === 't')) {
                tFunctionIdentifierName = elem.name.text;
              }
            }
          } else if (ts.isArrayBindingPattern(node.name) && node.name.elements.length > 0) {
            const firstElem = node.name.elements[0];
            if (firstElem && ts.isBindingElement(firstElem) && ts.isIdentifier(firstElem.name)) {
              tFunctionIdentifierName = firstElem.name.text;
            }
          }
        }
      }

      // 3. Detect t('key', { ...options }) calls
      if (ts.isCallExpression(node)) {
        if (ts.isIdentifier(node.expression) && node.expression.text === tFunctionIdentifierName) {
          const firstArg = node.arguments[0];
          if (node.arguments.length > 0 && firstArg && ts.isStringLiteral(firstArg)) {
            const rawKey = firstArg.text;
            let key = rawKey;
            let ns = result.namespaces[0] || this.defaultNamespace;

            // Check if key contains namespace prefix: "common:greeting" or "admin:user.title"
            if (rawKey.includes(':')) {
              const parts = rawKey.split(':');
              ns = parts[0] || this.defaultNamespace;
              key = parts.slice(1).join(':');
              if (!result.namespaces.includes(ns)) {
                result.namespaces.push(ns);
              }
            }

            const variables: Record<string, string> = {};
            let hasPlural = false;
            let pluralVar: string | undefined = undefined;

            const secondArg = node.arguments[1];
            if (node.arguments.length > 1 && secondArg && ts.isObjectLiteralExpression(secondArg)) {
              for (const prop of secondArg.properties) {
                if (ts.isPropertyAssignment(prop) && ts.isIdentifier(prop.name)) {
                  const propName = prop.name.text;
                  const propValue = prop.initializer ? prop.initializer.getText(sourceFile) : '';
                  variables[propName] = propValue;

                  if (propName === 'count' || propName === 'quantity' || propName.toLowerCase().includes('count')) {
                    hasPlural = true;
                    pluralVar = propName;
                  }
                  if (propName === 'ns' && prop.initializer && ts.isStringLiteral(prop.initializer)) {
                    ns = prop.initializer.text;
                  }
                }
              }
            }

            const { line } = sourceFile.getLineAndCharacterOfPosition(node.getStart());
            result.translationCalls.push({
              key,
              namespace: ns,
              variables,
              hasPlural,
              pluralVariable: pluralVar,
              line: line + 1,
            });
          }
        }
      }

      // 4. Detect <Trans i18nKey="key" ...> JSX Elements
      if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
        const opening = ts.isJsxElement(node) ? node.openingElement : node;
        const tagName = opening.tagName.getText(sourceFile);

        if (tagName === 'Trans') {
          let i18nKey = '';
          let ns: string | undefined = undefined;
          const values: Record<string, string> = {};

          for (const attr of opening.attributes.properties) {
            if (ts.isJsxAttribute(attr) && attr.name) {
              const attrName = attr.name.getText(sourceFile);
              if (attrName === 'i18nKey' && attr.initializer) {
                if (ts.isStringLiteral(attr.initializer)) {
                  i18nKey = attr.initializer.text;
                } else if (ts.isJsxExpression(attr.initializer) && attr.initializer.expression && ts.isStringLiteral(attr.initializer.expression)) {
                  i18nKey = attr.initializer.expression.text;
                }
              } else if (attrName === 'ns' && attr.initializer && ts.isStringLiteral(attr.initializer)) {
                ns = attr.initializer.text;
              } else if (attrName === 'values' && attr.initializer && ts.isJsxExpression(attr.initializer)) {
                if (attr.initializer.expression && ts.isObjectLiteralExpression(attr.initializer.expression)) {
                  for (const prop of attr.initializer.expression.properties) {
                    if (ts.isPropertyAssignment(prop) && ts.isIdentifier(prop.name)) {
                      values[prop.name.text] = prop.initializer ? prop.initializer.getText(sourceFile) : '';
                    }
                  }
                }
              }
            }
          }

          let childrenSummary = '';
          if (ts.isJsxElement(node)) {
            childrenSummary = node.children.map((c) => c.getText(sourceFile)).join('').trim();
          }

          if (i18nKey) {
            result.transComponents.push({
              i18nKey,
              namespace: ns || result.namespaces[0] || this.defaultNamespace,
              values,
              childrenSummary,
            });
          }
        }
      }

      ts.forEachChild(node, visit);
    };

    visit(sourceFile);
    return result;
  }

  /**
   * Parse multiple JSON dictionary files for react-i18next and lift into Universal I18n IR.
   */
  public liftDictionaries(
    locales: SupportedLocale[],
    rawDictionaries: Record<SupportedLocale, Record<string, Record<string, any>>>
  ): UniversalI18nBundleIR {
    const namespacesSet = new Set<string>();
    const dictionaries: Record<SupportedLocale, Record<string, LocaleDictionaryIR>> = {} as any;

    for (const loc of locales) {
      dictionaries[loc] = {};
      const nsMap = rawDictionaries[loc] || {};

      for (const [ns, content] of Object.entries(nsMap)) {
        namespacesSet.add(ns);
        const direction: TextDirection = (loc === 'ar-SA' || loc === 'he-IL') ? 'rtl' : 'ltr';

        const flatMessages = this.flattenDictionary(content, '');
        const messageIRs: Record<string, TranslationMessageIR> = {};

        const pluralGroups = new Map<string, { baseKey: string; forms: Record<string, string> }>();
        const processedKeys = new Set<string>();

        for (const [key, val] of Object.entries(flatMessages)) {
          const pluralSuffixMatch = key.match(/^(.*)_(zero|one|two|few|many|other)$/);
          if (pluralSuffixMatch) {
            const baseKey = pluralSuffixMatch[1] || key;
            const form = (pluralSuffixMatch[2] || 'other') as PluralCategory;
            if (!pluralGroups.has(baseKey)) {
              pluralGroups.set(baseKey, { baseKey, forms: {} });
            }
            pluralGroups.get(baseKey)!.forms[form] = String(val);
            processedKeys.add(key);
          }
        }

        for (const [baseKey, group] of pluralGroups.entries()) {
          const rawPattern = this.buildIcuPluralPattern('count', group.forms);
          const tokens: InterpolationToken[] = [{ name: 'count', type: 'number' }];
          const pluralRule: PluralRuleMessage = {
            type: 'plural',
            variableName: 'count',
            options: group.forms as any,
          };

          messageIRs[baseKey] = {
            key: baseKey,
            rawPattern,
            tokens,
            pluralRule,
            namespace: ns,
          };
        }

        for (const [key, val] of Object.entries(flatMessages)) {
          if (processedKeys.has(key)) continue;

          const strVal = String(val);
          const tokens = this.extractTokensFromPattern(strVal);

          const icuPluralMatch = strVal.match(/\{([a-zA-Z0-9_]+),\s*plural,\s*(.+)\}/s);
          let pluralRule: PluralRuleMessage | undefined = undefined;

          if (icuPluralMatch) {
            const varName = icuPluralMatch[1] || 'count';
            const body = icuPluralMatch[2] || '';
            const forms = this.parseIcuPluralBody(body);
            if (forms.other) {
              pluralRule = {
                type: 'plural',
                variableName: varName,
                options: forms as any,
              };
            }
          }

          messageIRs[key] = {
            key,
            rawPattern: strVal,
            tokens,
            pluralRule,
            namespace: ns,
          };
        }

        dictionaries[loc][ns] = {
          locale: loc,
          direction,
          namespace: ns,
          messages: messageIRs,
        };
      }
    }

    return {
      version: '1.0',
      defaultLocale: locales[0] || 'zh-CN',
      fallbackLocale: locales.includes('en-US') ? 'en-US' : (locales[0] || 'zh-CN'),
      namespaces: Array.from(namespacesSet),
      dictionaries,
    };
  }

  /**
   * Emit react-i18next React Component code with typed useTranslation hooks.
   */
  public emitReactComponent(
    componentName: string,
    namespaces: string[],
    messageKeys: string[],
    options: { typescript?: boolean; useTransComponent?: boolean } = {}
  ): string {
    const isTs = options.typescript !== false;
    const nsParam = namespaces.length === 1 ? `'${namespaces[0]}'` : `[${namespaces.map((n) => `'${n}'`).join(', ')}]`;

    const imports = [
      `import React from 'react';`,
      `import { useTranslation${options.useTransComponent ? ', Trans' : ''} } from 'react-i18next';`,
    ];

    const lines: string[] = [...imports, ''];

    if (isTs) {
      lines.push(`export interface ${componentName}Props {`);
      lines.push(`  className?: string;`);
      lines.push(`  count?: number;`);
      lines.push(`  userName?: string;`);
      lines.push(`}`);
      lines.push('');
    }

    const propsSignature = isTs ? `props: ${componentName}Props` : `props`;
    lines.push(`export const ${componentName}: React.FC<${isTs ? `${componentName}Props` : 'any'}> = (${propsSignature}) => {`);
    lines.push(`  const { t } = useTranslation(${nsParam});`);
    lines.push(`  const count = props.count ?? 1;`);
    lines.push(`  const userName = props.userName ?? 'Guest';`);
    lines.push('');
    lines.push(`  return (`);
    lines.push(`    <div className={props.className || '${componentName.toLowerCase()}-container'}>`);

    for (const key of messageKeys) {
      if (key.includes('count') || key.includes('item') || key.includes('total')) {
        lines.push(`      <p className="i18n-plural">{t('${key}', { count })}</p>`);
      } else if (key.includes('user') || key.includes('name') || key.includes('greeting')) {
        lines.push(`      <h1 className="i18n-interpolated">{t('${key}', { name: userName })}</h1>`);
      } else {
        lines.push(`      <span className="i18n-text">{t('${key}')}</span>`);
      }
    }

    if (options.useTransComponent && messageKeys.length > 0) {
      const transKey = messageKeys[0];
      lines.push(`      <Trans i18nKey="${transKey}" values={{ name: userName, count }}>`);
      lines.push(`        Welcome <strong>{userName}</strong>, you have <em>{count}</em> updates.`);
      lines.push(`      </Trans>`);
    }

    lines.push(`    </div>`);
    lines.push(`  );`);
    lines.push(`};`);
    lines.push('');
    lines.push(`export default ${componentName};`);

    return lines.join('\n');
  }

  /**
   * Emit JSON dictionary files suitable for react-i18next.
   */
  public emitDictionaryFiles(
    bundle: UniversalI18nBundleIR,
    mode: 'flat' | 'nested' | 'plural_suffix' = 'plural_suffix'
  ): Record<string, string> {
    const result: Record<string, string> = {};

    for (const [locale, nsMap] of Object.entries(bundle.dictionaries)) {
      for (const [ns, dict] of Object.entries(nsMap)) {
        const filePath = `locales/${locale}/${ns}.json`;
        const jsonContent: Record<string, any> = {};

        for (const [key, msg] of Object.entries(dict.messages)) {
          if (msg.pluralRule && mode === 'plural_suffix') {
            for (const [form, text] of Object.entries(msg.pluralRule.options)) {
              if (text) {
                const convertedText = this.convertIcuToI18next(text);
                jsonContent[`${key}_${form}`] = convertedText;
              }
            }
          } else {
            const convertedText = this.convertIcuToI18next(msg.rawPattern);
            if (mode === 'nested' && key.includes('.')) {
              this.setNestedProperty(jsonContent, key.split('.'), convertedText);
            } else {
              jsonContent[key] = convertedText;
            }
          }
        }

        result[filePath] = JSON.stringify(jsonContent, null, 2);
      }
    }

    return result;
  }

  /**
   * Generate complete react-i18next initialization configuration (i18n.ts).
   */
  public emitI18nInitFile(bundle: UniversalI18nBundleIR): string {
    const locales = Object.keys(bundle.dictionaries);
    const namespaces = bundle.namespaces;

    const lines: string[] = [
      `import i18n from 'i18next';`,
      `import { initReactI18next } from 'react-i18next';`,
      `import LanguageDetector from 'i18next-browser-languagedetector';`,
      '',
    ];

    for (const loc of locales) {
      const locClean = loc.replace('-', '_');
      for (const ns of namespaces) {
        lines.push(`import ${locClean}_${ns} from './locales/${loc}/${ns}.json';`);
      }
    }

    lines.push('');
    lines.push(`export const resources = {`);
    for (const loc of locales) {
      const locClean = loc.replace('-', '_');
      lines.push(`  '${loc}': {`);
      for (const ns of namespaces) {
        lines.push(`    ${ns}: ${locClean}_${ns},`);
      }
      lines.push(`  },`);
    }
    lines.push(`} as const;`);
    lines.push('');

    lines.push(`i18n`);
    lines.push(`  .use(LanguageDetector)`);
    lines.push(`  .use(initReactI18next)`);
    lines.push(`  .init({`);
    lines.push(`    resources,`);
    lines.push(`    lng: '${bundle.defaultLocale}',`);
    lines.push(`    fallbackLng: '${bundle.fallbackLocale}',`);
    lines.push(`    ns: [${namespaces.map((n) => `'${n}'`).join(', ')}],`);
    lines.push(`    defaultNS: '${namespaces[0] || this.defaultNamespace}',`);
    lines.push(`    interpolation: {`);
    lines.push(`      escapeValue: false, // React already safeguards against XSS`);
    lines.push(`    },`);
    lines.push(`    react: {`);
    lines.push(`      useSuspense: false,`);
    lines.push(`    },`);
    lines.push(`  });`);
    lines.push('');
    lines.push(`export default i18n;`);

    return lines.join('\n');
  }

  public convertIcuToI18next(icuPattern: string): string {
    return icuPattern.replace(/\{([a-zA-Z0-9_]+)\}/g, '{{$1}}');
  }

  public convertI18nextToIcu(i18nextPattern: string): string {
    return i18nextPattern.replace(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g, '{$1}');
  }

  private extractTokensFromPattern(pattern: string): InterpolationToken[] {
    const tokens: InterpolationToken[] = [];
    const seen = new Set<string>();

    const i18nRegex = /\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g;
    let match: RegExpExecArray | null;
    while ((match = i18nRegex.exec(pattern)) !== null) {
      const name = match[1];
      if (name && !seen.has(name)) {
        seen.add(name);
        tokens.push({
          name,
          type: name.includes('count') || name.includes('num') ? 'number' : 'string',
        });
      }
    }

    const icuRegex = /\{([a-zA-Z0-9_]+)\}/g;
    while ((match = icuRegex.exec(pattern)) !== null) {
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

  private flattenDictionary(obj: Record<string, any>, prefix: string = ''): Record<string, string> {
    const result: Record<string, string> = {};

    for (const [key, value] of Object.entries(obj)) {
      const newKey = prefix ? `${prefix}.${key}` : key;
      if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        Object.assign(result, this.flattenDictionary(value, newKey));
      } else {
        result[newKey] = String(value);
      }
    }

    return result;
  }

  private setNestedProperty(obj: Record<string, any>, path: string[], value: any): void {
    let current = obj;
    for (let i = 0; i < path.length - 1; i++) {
      const p = path[i];
      if (!p) continue;
      if (!current[p] || typeof current[p] !== 'object') {
        current[p] = {};
      }
      current = current[p];
    }
    const last = path[path.length - 1];
    if (last) {
      current[last] = value;
    }
  }

  private buildIcuPluralPattern(variableName: string, forms: Record<string, string>): string {
    const parts = Object.entries(forms).map(([form, text]) => `${form}{${text}}`);
    return `{${variableName}, plural, ${parts.join(' ')}}`;
  }

  private parseIcuPluralBody(body: string): Record<string, string> {
    const result: Record<string, string> = {};
    const regex = /(zero|one|two|few|many|other)\s*\{([^}]+)\}/g;
    let match: RegExpExecArray | null;

    while ((match = regex.exec(body)) !== null) {
      if (match[1] && match[2]) {
        result[match[1]] = match[2];
      }
    }

    return result;
  }
}
