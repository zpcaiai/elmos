/**
 * @file i18n-ir-types.ts
 * @description Universal Internationalization (I18n) Intermediate Representation types.
 * Supports ICU MessageFormat, pluralization rules, interpolation tokens,
 * locale date/number formatting, and bidirectional text / RTL direction contracts.
 * Conforms to Batch 32 Skill 1221 (b32-accessibility-i18n-seo-visual-e2e).
 */

export type SupportedLocale =
  | 'zh-CN'
  | 'zh-TW'
  | 'en-US'
  | 'en-GB'
  | 'ja-JP'
  | 'ko-KR'
  | 'fr-FR'
  | 'de-DE'
  | 'es-ES'
  | 'ar-SA'
  | 'he-IL';

export type TextDirection = 'ltr' | 'rtl';

export interface LocaleMetadata {
  locale: SupportedLocale;
  language: string;
  region?: string;
  direction: TextDirection;
  displayName: string;
  fallbackLocale?: SupportedLocale;
}

/**
 * ICU Plural Categories
 */
export type PluralCategory = 'zero' | 'one' | 'two' | 'few' | 'many' | 'other';

export interface PluralRuleMessage {
  type: 'plural';
  variableName: string;
  options: Partial<Record<PluralCategory, string>> & { other: string };
  offset?: number;
}

export interface InterpolationToken {
  name: string;
  type: 'string' | 'number' | 'date' | 'currency' | 'custom';
  formatOptions?: Record<string, string | number>;
}

export interface TranslationMessageIR {
  key: string;
  rawPattern: string; // e.g. "Hello {name}, you have {count, plural, one{# item} other{# items}}."
  description?: string;
  tokens: InterpolationToken[];
  pluralRule?: PluralRuleMessage;
  namespace?: string;
}

export interface LocaleDictionaryIR {
  locale: SupportedLocale;
  direction: TextDirection;
  namespace: string;
  messages: Record<string, TranslationMessageIR>;
}

export type I18nFrameworkId =
  | 'react-i18next'
  | 'vue-i18n'
  | 'angular-transloco'
  | 'miniapp-i18n'
  | 'arkui-i18n'
  | 'flutter-intl';

export interface UniversalI18nBundleIR {
  version: '1.0';
  defaultLocale: SupportedLocale;
  fallbackLocale: SupportedLocale;
  namespaces: string[];
  dictionaries: Partial<Record<SupportedLocale, Record<string, LocaleDictionaryIR>>>;
}

export interface I18nTransformResult {
  targetFramework: I18nFrameworkId;
  code: string;
  dictionaryFiles: Record<string, string>; // filename -> json or js content
  warnings: string[];
  metrics: {
    totalKeys: number;
    pluralRulesCount: number;
    interpolationsCount: number;
    rtlLocalesSupported: number;
  };
}
