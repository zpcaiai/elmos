/**
 * @file miniapp-i18n-adapter.ts
 * @description Full compiler and runtime generator for WeChat / Alipay MiniApp Internationalization.
 * MiniApps execute UI rendering inside a Webview / Native thread isolated from JavaScript runtime.
 * This adapter compiles Universal I18n IR into:
 * 1. High-performance WXS (WeiXin Script) rendering-thread translator (`i18n.wxs`) with token interpolation & plural rules.
 * 2. Page & Component lifecycle bridges (`attached`, `onLoad`) for dynamic locale switching.
 * 3. RTL text-direction indicators for Arabic / Hebrew localization.
 */

import {
  TranslationMessageIR,
  LocaleDictionaryIR,
  SupportedLocale,
  TextDirection,
  UniversalI18nBundleIR,
  PluralRuleMessage,
} from './i18n-ir-types';

export interface MiniAppParsedWxml {
  wxsModuleDeclarations: Array<{ module: string; src: string }>;
  wxmlInterpolations: Array<{
    module: string;
    key: string;
    args: Record<string, string>;
    rawExpression: string;
  }>;
}

export class MiniAppI18nAdapter {
  private defaultNamespace: string = 'app';

  constructor(defaultNamespace: string = 'app') {
    this.defaultNamespace = defaultNamespace;
  }

  /**
   * Parse WXML content for `<wxs module="i18n" src="..."/>` and `{{ i18n.t('key', { ... }) }}`.
   */
  public parseWxml(wxmlContent: string): MiniAppParsedWxml {
    const result: MiniAppParsedWxml = {
      wxsModuleDeclarations: [],
      wxmlInterpolations: [],
    };

    // 1. Detect WXS module tag
    const wxsRegex = /<wxs\s+([^>]+)(?:\/>|><\/wxs>)/g;
    let wxsMatch: RegExpExecArray | null;

    while ((wxsMatch = wxsRegex.exec(wxmlContent)) !== null) {
      const attrsStr = wxsMatch[1] || '';
      const modMatch = attrsStr.match(/module\s*=\s*(['"][^'"]+['"])/);
      const srcMatch = attrsStr.match(/src\s*=\s*(['"][^'"]+['"])/);

      if (modMatch && srcMatch && modMatch[1] && srcMatch[1]) {
        result.wxsModuleDeclarations.push({
          module: modMatch[1].slice(1, -1),
          src: srcMatch[1].slice(1, -1),
        });
      }
    }

    // 2. Detect {{ module.t('key', { ... }) }}
    const tRegex = /\{\{\s*([a-zA-Z0-9_]+)\.t\(\s*(['"][^'"]+['"])(?:,\s*(\{[^}]+\}))?\s*\)\s*\}\}/g;
    let tMatch: RegExpExecArray | null;

    while ((tMatch = tRegex.exec(wxmlContent)) !== null) {
      const mod = tMatch[1] || 'i18n';
      const rawKey = tMatch[2] || "''";
      const key = rawKey.slice(1, -1);
      const rawParams = tMatch[3] ? tMatch[3].trim() : '';

      const args: Record<string, string> = {};
      if (rawParams) {
        const inner = rawParams.slice(1, -1);
        const pairs = inner.split(',');
        for (const pair of pairs) {
          const colonIdx = pair.indexOf(':');
          if (colonIdx !== -1) {
            const k = pair.slice(0, colonIdx).trim();
            const v = pair.slice(colonIdx + 1).trim();
            args[k] = v;
          }
        }
      }

      result.wxmlInterpolations.push({
        module: mod,
        key,
        args,
        rawExpression: tMatch[0],
      });
    }

    return result;
  }

  /**
   * Emit production-ready WXS script (`i18n.wxs`) that runs directly in the WXML render thread.
   */
  public emitWxsScript(bundle: UniversalI18nBundleIR): string {
    const lines: string[] = [
      `/**`,
      ` * Auto-generated WeChat MiniApp WXS I18n Engine`,
      ` * Executes inside MiniApp rendering context (WebKit/JSCore/V8).`,
      ` */`,
      `var locales = {`,
    ];

    // Embed message tables into WXS
    for (const [locale, nsMap] of Object.entries(bundle.dictionaries)) {
      lines.push(`  '${locale}': {`);
      for (const [ns, dict] of Object.entries(nsMap)) {
        for (const [key, msg] of Object.entries(dict.messages)) {
          if (msg.pluralRule) {
            const pOpts = JSON.stringify(msg.pluralRule.options);
            lines.push(`    '${key}': { plural: true, variable: '${msg.pluralRule.variableName}', options: ${pOpts} },`);
          } else {
            const escapedPattern = msg.rawPattern.replace(/'/g, "\\'");
            lines.push(`    '${key}': '${escapedPattern}',`);
          }
        }
      }
      lines.push(`  },`);
    }

    lines.push(`};`);
    lines.push('');
    lines.push(`var defaultLocale = '${bundle.defaultLocale}';`);
    lines.push(`var fallbackLocale = '${bundle.fallbackLocale}';`);
    lines.push('');
    lines.push(`function getMessage(key, currentLocale) {`);
    lines.push(`  var loc = currentLocale || defaultLocale;`);
    lines.push(`  var dict = locales[loc] || locales[fallbackLocale] || {};`);
    lines.push(`  return dict[key] || key;`);
    lines.push(`}`);
    lines.push('');
    lines.push(`function t(key, params, currentLocale) {`);
    lines.push(`  var msg = getMessage(key, currentLocale);`);
    lines.push(`  if (!msg) return key;`);
    lines.push('');
    lines.push(`  // Check plural message`);
    lines.push(`  if (typeof msg === 'object' && msg.plural) {`);
    lines.push(`    var count = (params && params[msg.variable] !== undefined) ? params[msg.variable] : 0;`);
    lines.push(`    var form = 'other';`);
    lines.push(`    if (count === 0 && msg.options.zero) form = 'zero';`);
    lines.push(`    else if (count === 1 && msg.options.one) form = 'one';`);
    lines.push(`    msg = msg.options[form] || msg.options.other || key;`);
    lines.push(`  }`);
    lines.push('');
    lines.push(`  // Interpolate tokens {var}`);
    lines.push(`  if (params && typeof msg === 'string') {`);
    lines.push(`    for (var k in params) {`);
    lines.push(`      var placeholder = '{' + k + '}';`);
    lines.push(`      while (msg.indexOf(placeholder) !== -1) {`);
    lines.push(`        msg = msg.replace(placeholder, params[k]);`);
    lines.push(`      }`);
    lines.push(`    }`);
    lines.push(`  }`);
    lines.push(`  return msg;`);
    lines.push(`}`);
    lines.push('');
    lines.push(`module.exports = {`);
    lines.push(`  t: t,`);
    lines.push(`  locales: locales,`);
    lines.push(`  defaultLocale: defaultLocale,`);
    lines.push(`};`);

    return lines.join('\n');
  }

  /**
   * Emit WXML template markup for a component with WXS i18n tags.
   */
  public emitWxml(
    componentName: string,
    messageKeys: string[],
    wxsRelativePath: string = '../../utils/i18n.wxs'
  ): string {
    const lines: string[] = [
      `<wxs module="i18n" src="${wxsRelativePath}" />`,
      `<view class="${componentName.toLowerCase()}-container" style="{{ currentLocaleDirection === 'rtl' ? 'direction: rtl;' : '' }}">`,
    ];

    for (const key of messageKeys) {
      if (key.includes('count') || key.includes('item') || key.includes('total')) {
        lines.push(`  <view class="i18n-item">`);
        lines.push(`    <text>{{ i18n.t('${key}', { count: itemCount }, currentLocale) }}</text>`);
        lines.push(`  </view>`);
      } else if (key.includes('user') || key.includes('name') || key.includes('greeting')) {
        lines.push(`  <view class="i18n-item">`);
        lines.push(`    <text>{{ i18n.t('${key}', { name: userName }, currentLocale) }}</text>`);
        lines.push(`  </view>`);
      } else {
        lines.push(`  <view class="i18n-item">`);
        lines.push(`    <text>{{ i18n.t('${key}', {}, currentLocale) }}</text>`);
        lines.push(`  </view>`);
      }
    }

    lines.push(`</view>`);
    return lines.join('\n');
  }

  /**
   * Emit MiniApp Page or Component TS file wiring currentLocale state and listeners.
   */
  public emitMiniAppTs(componentName: string, isPage: boolean = true): string {
    const lines: string[] = [
      `/**`,
      ` * Auto-generated WeChat MiniApp ${isPage ? 'Page' : 'Component'}: ${componentName}`,
      ` */`,
    ];

    if (isPage) {
      lines.push(`Page({`);
      lines.push(`  data: {`);
      lines.push(`    currentLocale: (wx as any).getStorageSync('app_locale') || 'zh-CN',`);
      lines.push(`    currentLocaleDirection: 'ltr',`);
      lines.push(`    itemCount: 1,`);
      lines.push(`    userName: 'WeChat User',`);
      lines.push(`  },`);
      lines.push('');
      lines.push(`  onLoad() {`);
      lines.push(`    this.updateLocaleDirection();`);
      lines.push(`  },`);
      lines.push('');
      lines.push(`  switchLocale(locale: string) {`);
      lines.push(`    (wx as any).setStorageSync('app_locale', locale);`);
      lines.push(`    this.setData({ currentLocale: locale }, () => {`);
      lines.push(`      this.updateLocaleDirection();`);
      lines.push(`    });`);
      lines.push(`  },`);
      lines.push('');
      lines.push(`  updateLocaleDirection() {`);
      lines.push(`    const isRtl = this.data.currentLocale === 'ar-SA' || this.data.currentLocale === 'he-IL';`);
      lines.push(`    this.setData({ currentLocaleDirection: isRtl ? 'rtl' : 'ltr' });`);
      lines.push(`  },`);
      lines.push(`});`);
    } else {
      lines.push(`Component({`);
      lines.push(`  properties: {`);
      lines.push(`    itemCount: { type: Number, value: 1 },`);
      lines.push(`    userName: { type: String, value: 'WeChat User' },`);
      lines.push(`  },`);
      lines.push('');
      lines.push(`  data: {`);
      lines.push(`    currentLocale: 'zh-CN',`);
      lines.push(`    currentLocaleDirection: 'ltr',`);
      lines.push(`  },`);
      lines.push('');
      lines.push(`  lifetimes: {`);
      lines.push(`    attached() {`);
      lines.push(`      const loc = (wx as any).getStorageSync('app_locale') || 'zh-CN';`);
      lines.push(`      const isRtl = loc === 'ar-SA' || loc === 'he-IL';`);
      lines.push(`      this.setData({ currentLocale: loc, currentLocaleDirection: isRtl ? 'rtl' : 'ltr' });`);
      lines.push(`    },`);
      lines.push(`  },`);
      lines.push(`});`);
    }

    return lines.join('\n');
  }

  /**
   * Emit WXSS style sheet supporting RTL direction and responsive typography.
   */
  public emitWxss(componentName: string): string {
    const lines: string[] = [
      `/* ${componentName} i18n container */`,
      `.${componentName.toLowerCase()}-container {`,
      `  display: flex;`,
      `  flex-direction: column;`,
      `  padding: 24rpx;`,
      `  box-sizing: border-box;`,
      `}`,
      ``,
      `.i18n-item {`,
      `  margin-bottom: 16rpx;`,
      `  font-size: 28rpx;`,
      `  color: #333333;`,
      `}`,
      ``,
      `/* RTL direction adjustments */`,
      `[style*="direction: rtl"] .i18n-item {`,
      `  text-align: right;`,
      `}`,
    ];

    return lines.join('\n');
  }
}
