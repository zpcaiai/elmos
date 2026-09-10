/**
 * @file cross-platform-i18n-engine.ts
 * @description Master orchestration engine for Cross-Platform Internationalization (I18n).
 * Transforms translation schemas, dictionary files, template bindings, and plural rules
 * across React (react-i18next), Vue (vue-i18n), and WeChat MiniApp (WXS + Page data).
 * Conforms to Batch 32 Skill 1221 (b32-accessibility-i18n-seo-visual-e2e).
 */

import {
  UniversalI18nBundleIR,
  I18nFrameworkId,
  I18nTransformResult,
  SupportedLocale,
  LocaleMetadata,
  TextDirection,
} from './i18n-ir-types';
import { ReactI18nextAdapter } from './react-i18next-adapter';
import { VueI18nAdapter } from './vue-i18n-adapter';
import { MiniAppI18nAdapter } from './miniapp-i18n-adapter';

export interface I18nIntegrityReport {
  isValid: boolean;
  totalKeys: number;
  missingTranslations: Array<{ locale: SupportedLocale; namespace: string; key: string }>;
  tokenMismatches: Array<{
    key: string;
    expectedTokens: string[];
    locale: SupportedLocale;
    actualTokens: string[];
  }>;
  rtlLocalesCount: number;
}

export class CrossPlatformI18nEngine {
  private reactAdapter: ReactI18nextAdapter;
  private vueAdapter: VueI18nAdapter;
  private miniappAdapter: MiniAppI18nAdapter;

  private localeMetadataMap: Record<SupportedLocale, LocaleMetadata> = {
    'zh-CN': { locale: 'zh-CN', language: 'zh', region: 'CN', direction: 'ltr', displayName: '简体中文' },
    'zh-TW': { locale: 'zh-TW', language: 'zh', region: 'TW', direction: 'ltr', displayName: '繁體中文' },
    'en-US': { locale: 'en-US', language: 'en', region: 'US', direction: 'ltr', displayName: 'English (US)' },
    'en-GB': { locale: 'en-GB', language: 'en', region: 'GB', direction: 'ltr', displayName: 'English (UK)' },
    'ja-JP': { locale: 'ja-JP', language: 'ja', region: 'JP', direction: 'ltr', displayName: '日本語' },
    'ko-KR': { locale: 'ko-KR', language: 'ko', region: 'KR', direction: 'ltr', displayName: '한국어' },
    'fr-FR': { locale: 'fr-FR', language: 'fr', region: 'FR', direction: 'ltr', displayName: 'Français' },
    'de-DE': { locale: 'de-DE', language: 'de', region: 'DE', direction: 'ltr', displayName: 'Deutsch' },
    'es-ES': { locale: 'es-ES', language: 'es', region: 'ES', direction: 'ltr', displayName: 'Español' },
    'ar-SA': { locale: 'ar-SA', language: 'ar', region: 'SA', direction: 'rtl', displayName: 'العربية' },
    'he-IL': { locale: 'he-IL', language: 'he', region: 'IL', direction: 'rtl', displayName: 'עברית' },
  };

  constructor() {
    this.reactAdapter = new ReactI18nextAdapter();
    this.vueAdapter = new VueI18nAdapter();
    this.miniappAdapter = new MiniAppI18nAdapter();
  }

  public getReactAdapter(): ReactI18nextAdapter {
    return this.reactAdapter;
  }

  public getVueAdapter(): VueI18nAdapter {
    return this.vueAdapter;
  }

  public getMiniAppAdapter(): MiniAppI18nAdapter {
    return this.miniappAdapter;
  }

  /**
   * Get metadata for a given locale, including text direction ('ltr' or 'rtl').
   */
  public getLocaleMetadata(locale: SupportedLocale): LocaleMetadata {
    return (
      this.localeMetadataMap[locale] || {
        locale,
        language: locale.split('-')[0],
        direction: (locale === 'ar-SA' || locale === 'he-IL') ? 'rtl' : 'ltr',
        displayName: locale,
      }
    );
  }

  /**
   * Check if a locale requires RTL (Right-to-Left) layout.
   */
  public isRtlLocale(locale: SupportedLocale): boolean {
    return this.getLocaleMetadata(locale).direction === 'rtl';
  }

  /**
   * Validate dictionary integrity across all registered locales in the bundle.
   * Detects missing keys and variable token mismatches.
   */
  public auditIntegrity(bundle: UniversalI18nBundleIR): I18nIntegrityReport {
    const missingTranslations: Array<{ locale: SupportedLocale; namespace: string; key: string }> = [];
    const tokenMismatches: Array<{
      key: string;
      expectedTokens: string[];
      locale: SupportedLocale;
      actualTokens: string[];
    }> = [];

    const defaultDictMap = bundle.dictionaries[bundle.defaultLocale] || {};
    let totalKeys = 0;
    const keyCanonicalTokens: Record<string, string[]> = {};

    // Collect reference keys and expected tokens from default locale
    for (const [ns, dict] of Object.entries(defaultDictMap)) {
      for (const [key, msg] of Object.entries(dict.messages)) {
        totalKeys++;
        const fullKey = `${ns}:${key}`;
        keyCanonicalTokens[fullKey] = msg.tokens.map((t) => t.name).sort();
      }
    }

    let rtlCount = 0;

    // Cross-check all locales
    for (const [locStr, nsMap] of Object.entries(bundle.dictionaries)) {
      const loc = locStr as SupportedLocale;
      if (this.isRtlLocale(loc)) {
        rtlCount++;
      }

      for (const [ns, defaultDict] of Object.entries(defaultDictMap)) {
        const targetDict = nsMap[ns];
        if (!targetDict) {
          for (const key of Object.keys(defaultDict.messages)) {
            missingTranslations.push({ locale: loc, namespace: ns, key });
          }
          continue;
        }

        for (const [key, defaultMsg] of Object.entries(defaultDict.messages)) {
          const targetMsg = targetDict.messages[key];
          if (!targetMsg) {
            missingTranslations.push({ locale: loc, namespace: ns, key });
          } else {
            // Check tokens
            const expected = keyCanonicalTokens[`${ns}:${key}`] || [];
            const actual = targetMsg.tokens.map((t) => t.name).sort();

            if (JSON.stringify(expected) !== JSON.stringify(actual)) {
              tokenMismatches.push({
                key: `${ns}:${key}`,
                expectedTokens: expected,
                locale: loc,
                actualTokens: actual,
              });
            }
          }
        }
      }
    }

    return {
      isValid: missingTranslations.length === 0 && tokenMismatches.length === 0,
      totalKeys,
      missingTranslations,
      tokenMismatches,
      rtlLocalesCount: rtlCount,
    };
  }

  /**
   * Universal transform: convert Universal I18n IR to target framework implementation.
   */
  public transform(
    bundle: UniversalI18nBundleIR,
    targetFramework: I18nFrameworkId,
    componentName: string = 'LocalizedView'
  ): I18nTransformResult {
    const warnings: string[] = [];
    const integrity = this.auditIntegrity(bundle);

    if (!integrity.isValid) {
      if (integrity.missingTranslations.length > 0) {
        warnings.push(
          `Detected ${integrity.missingTranslations.length} missing translation keys across target locales.`
        );
      }
      if (integrity.tokenMismatches.length > 0) {
        warnings.push(
          `Detected ${integrity.tokenMismatches.length} interpolation token mismatches across locales.`
        );
      }
    }

    let code = '';
    let dictionaryFiles: Record<string, string> = {};

    const defaultDict = bundle.dictionaries[bundle.defaultLocale] || {};
    const sampleKeys: string[] = [];
    let pluralCount = 0;
    let interpolationCount = 0;

    for (const dict of Object.values(defaultDict)) {
      for (const [key, msg] of Object.entries(dict.messages)) {
        sampleKeys.push(key);
        if (msg.pluralRule) pluralCount++;
        if (msg.tokens.length > 0) interpolationCount += msg.tokens.length;
      }
    }

    switch (targetFramework) {
      case 'react-i18next': {
        code = this.reactAdapter.emitReactComponent(componentName, bundle.namespaces, sampleKeys);
        dictionaryFiles = this.reactAdapter.emitDictionaryFiles(bundle, 'plural_suffix');
        dictionaryFiles['i18n.ts'] = this.reactAdapter.emitI18nInitFile(bundle);
        break;
      }
      case 'vue-i18n': {
        code = this.vueAdapter.emitVue3Sfc(componentName, sampleKeys);
        dictionaryFiles = this.vueAdapter.emitVueDictionaries(bundle);
        dictionaryFiles['i18n.ts'] = this.vueAdapter.emitVueI18nPlugin(bundle);
        break;
      }
      case 'miniapp-i18n': {
        code = this.miniappAdapter.emitWxml(componentName, sampleKeys);
        dictionaryFiles['utils/i18n.wxs'] = this.miniappAdapter.emitWxsScript(bundle);
        dictionaryFiles[`pages/${componentName.toLowerCase()}/${componentName.toLowerCase()}.ts`] =
          this.miniappAdapter.emitMiniAppTs(componentName, true);
        dictionaryFiles[`pages/${componentName.toLowerCase()}/${componentName.toLowerCase()}.wxss`] =
          this.miniappAdapter.emitWxss(componentName);
        break;
      }
      default: {
        warnings.push(`Target framework ${targetFramework} fallback to react-i18next.`);
        code = this.reactAdapter.emitReactComponent(componentName, bundle.namespaces, sampleKeys);
        dictionaryFiles = this.reactAdapter.emitDictionaryFiles(bundle);
        break;
      }
    }

    return {
      targetFramework,
      code,
      dictionaryFiles,
      warnings,
      metrics: {
        totalKeys: integrity.totalKeys,
        pluralRulesCount: pluralCount,
        interpolationsCount: interpolationCount,
        rtlLocalesSupported: integrity.rtlLocalesCount,
      },
    };
  }
}
