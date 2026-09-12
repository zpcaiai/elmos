/**
 * @file i18n-engine.test.ts
 * @description Unit and Integration tests for Cross-Platform Internationalization Engine.
 * Tests react-i18next, vue-i18n, and WeChat MiniApp WXS adapters, Universal I18n IR lifting/lowering,
 * ICU pluralization, named parameter interpolation, and RTL text direction handling.
 */

import {
  CrossPlatformI18nEngine,
  ReactI18nextAdapter,
  VueI18nAdapter,
  MiniAppI18nAdapter,
  UniversalI18nBundleIR,
} from '../src/i18n-engine';

describe('Cross-Platform I18n Engine', () => {
  const engine = new CrossPlatformI18nEngine();
  const reactAdapter = engine.getReactAdapter();
  const vueAdapter = engine.getVueAdapter();
  const miniappAdapter = engine.getMiniAppAdapter();

  const sampleBundle: UniversalI18nBundleIR = {
    version: '1.0',
    defaultLocale: 'zh-CN',
    fallbackLocale: 'en-US',
    namespaces: ['common', 'auth'],
    dictionaries: {
      'zh-CN': {
        common: {
          locale: 'zh-CN',
          direction: 'ltr',
          namespace: 'common',
          messages: {
            'greeting': {
              key: 'greeting',
              rawPattern: '你好，{name}！',
              tokens: [{ name: 'name', type: 'string' }],
              namespace: 'common',
            },
            'cart.items': {
              key: 'cart.items',
              rawPattern: '{count, plural, one{您有 1 件商品} other{您有 {count} 件商品}}',
              tokens: [{ name: 'count', type: 'number' }],
              pluralRule: {
                type: 'plural',
                variableName: 'count',
                options: {
                  one: '您有 1 件商品',
                  other: '您有 {count} 件商品',
                },
              },
              namespace: 'common',
            },
          },
        },
        auth: {
          locale: 'zh-CN',
          direction: 'ltr',
          namespace: 'auth',
          messages: {
            'login.title': {
              key: 'login.title',
              rawPattern: '请登录您的账号',
              tokens: [],
              namespace: 'auth',
            },
          },
        },
      },
      'en-US': {
        common: {
          locale: 'en-US',
          direction: 'ltr',
          namespace: 'common',
          messages: {
            'greeting': {
              key: 'greeting',
              rawPattern: 'Hello, {name}!',
              tokens: [{ name: 'name', type: 'string' }],
              namespace: 'common',
            },
            'cart.items': {
              key: 'cart.items',
              rawPattern: '{count, plural, one{You have 1 item} other{You have {count} items}}',
              tokens: [{ name: 'count', type: 'number' }],
              pluralRule: {
                type: 'plural',
                variableName: 'count',
                options: {
                  one: 'You have 1 item',
                  other: 'You have {count} items',
                },
              },
              namespace: 'common',
            },
          },
        },
        auth: {
          locale: 'en-US',
          direction: 'ltr',
          namespace: 'auth',
          messages: {
            'login.title': {
              key: 'login.title',
              rawPattern: 'Please sign in to your account',
              tokens: [],
              namespace: 'auth',
            },
          },
        },
      },
      'ar-SA': {
        common: {
          locale: 'ar-SA',
          direction: 'rtl',
          namespace: 'common',
          messages: {
            'greeting': {
              key: 'greeting',
              rawPattern: 'مرحبا {name}!',
              tokens: [{ name: 'name', type: 'string' }],
              namespace: 'common',
            },
            'cart.items': {
              key: 'cart.items',
              rawPattern: '{count, plural, one{لديك عنصر واحد} other{لديك {count} عناصر}}',
              tokens: [{ name: 'count', type: 'number' }],
              pluralRule: {
                type: 'plural',
                variableName: 'count',
                options: {
                  one: 'لديك عنصر واحد',
                  other: 'لديك {count} عناصر',
                },
              },
              namespace: 'common',
            },
          },
        },
        auth: {
          locale: 'ar-SA',
          direction: 'rtl',
          namespace: 'auth',
          messages: {
            'login.title': {
              key: 'login.title',
              rawPattern: 'يرجى تسجيل الدخول',
              tokens: [],
              namespace: 'auth',
            },
          },
        },
      },
    },
  };

  describe('ReactI18nextAdapter', () => {
    it('should parse React component with useTranslation hook and Trans component', () => {
      const code = `
        import React from 'react';
        import { useTranslation, Trans } from 'react-i18next';

        export const ProfileCard = () => {
          const { t } = useTranslation('common');
          return (
            <div>
              <h1>{t('greeting', { name: 'Alice' })}</h1>
              <p>{t('cart.items', { count: 3 })}</p>
              <Trans i18nKey="terms" values={{ site: 'Elmos' }}>
                Agree to <a>terms</a>
              </Trans>
            </div>
          );
        };
      `;

      const parsed = reactAdapter.parseComponent(code, 'ProfileCard.tsx');
      expect(parsed.componentName).toBe('ProfileCard');
      expect(parsed.namespaces).toContain('common');
      expect(parsed.translationCalls.length).toBe(2);
      expect(parsed.translationCalls[0]!.key).toBe('greeting');
      expect(parsed.translationCalls[1]!.hasPlural).toBe(true);
      expect(parsed.transComponents.length).toBe(1);
      expect(parsed.transComponents[0]!.i18nKey).toBe('terms');
    });

    it('should lift raw JSON dictionaries into Universal I18n IR with plural forms', () => {
      const rawDicts = {
        'zh-CN': {
          common: {
            welcome: '欢迎',
            items_one: '1个项目',
            items_other: '{{count}}个项目',
          },
        },
        'en-US': {
          common: {
            welcome: 'Welcome',
            items_one: '1 item',
            items_other: '{{count}} items',
          },
        },
      };

      const lifted = reactAdapter.liftDictionaries(['zh-CN', 'en-US'], rawDicts as any);
      expect(lifted.version).toBe('1.0');
      expect(lifted.namespaces).toContain('common');
      const zhCommon = lifted.dictionaries['zh-CN']?.['common'];
      expect(zhCommon).toBeDefined();
      expect(zhCommon!.messages['welcome']?.rawPattern).toBe('欢迎');
      expect(zhCommon!.messages['items']?.pluralRule).toBeDefined();
      expect(zhCommon!.messages['items']?.pluralRule?.options.one).toBe('1个项目');
    });

    it('should emit idiomatic React component code with typed useTranslation', () => {
      const emitted = reactAdapter.emitReactComponent(
        'HeaderComponent',
        ['common'],
        ['greeting', 'cart.items'],
        { typescript: true, useTransComponent: true }
      );

      expect(emitted).toContain(`import { useTranslation, Trans } from 'react-i18next';`);
      expect(emitted).toContain(`export const HeaderComponent: React.FC<HeaderComponentProps> =`);
      expect(emitted).toContain(`t('greeting', { name: userName })`);
      expect(emitted).toContain(`t('cart.items', { count })`);
    });

    it('should emit dictionary files and i18n initialization config', () => {
      const files = reactAdapter.emitDictionaryFiles(sampleBundle, 'plural_suffix');
      expect(files['locales/zh-CN/common.json']).toBeDefined();
      expect(files['locales/en-US/common.json']).toBeDefined();

      const parsedZh = JSON.parse(files['locales/zh-CN/common.json']!);
      expect(parsedZh['greeting']).toBe('你好，{{name}}！');
      expect(parsedZh['cart.items_one']).toBe('您有 1 件商品');

      const initCode = reactAdapter.emitI18nInitFile(sampleBundle);
      expect(initCode).toContain(`import i18n from 'i18next';`);
      expect(initCode).toContain(`fallbackLng: 'en-US'`);
    });
  });

  describe('VueI18nAdapter', () => {
    it('should parse Vue SFC template and script for vue-i18n invocations', () => {
      const sfc = `
        <template>
          <div class="user-panel">
            <span>{{ $t('greeting', { name: 'Bob' }) }}</span>
            <p>{{ $tc('cart.items', 5) }}</p>
            <i18n-t keypath="policy" tag="p" scope="global"></i18n-t>
          </div>
        </template>
        <script setup lang="ts">
        import { useI18n } from 'vue-i18n';
        const { t } = useI18n();
        const msg = t('login.title');
        </script>
      `;

      const parsed = vueAdapter.parseVueSfc(sfc);
      expect(parsed.template.templateInterpolations.length).toBe(2);
      expect(parsed.template.templateInterpolations[0]!.key).toBe('greeting');
      expect(parsed.template.templateInterpolations[1]!.isPlural).toBe(true);
      expect(parsed.template.i18nComponents.length).toBe(1);
      expect(parsed.template.i18nComponents[0]!.keypath).toBe('policy');
      expect(parsed.script.usesCompositionApi).toBe(true);
      expect(parsed.script.scriptCalls.length).toBe(1);
      expect(parsed.script.scriptCalls[0]!.key).toBe('login.title');
    });

    it('should lift Vue pipe plural format into Universal I18n IR', () => {
      const rawVueMessages = {
        'zh-CN': {
          apple: '没有苹果 | 1个苹果 | {count}个苹果',
        },
        'en-US': {
          apple: 'no apples | one apple | {count} apples',
        },
      };

      const lifted = vueAdapter.liftVueDictionary(['zh-CN', 'en-US'], rawVueMessages as any);
      const enMsg = lifted.dictionaries['en-US']?.['messages']?.messages['apple'];
      expect(enMsg).toBeDefined();
      expect(enMsg!.pluralRule).toBeDefined();
      expect(enMsg!.pluralRule?.options.zero).toBe('no apples');
      expect(enMsg!.pluralRule?.options.one).toBe('one apple');
      expect(enMsg!.pluralRule?.options.other).toBe('{count} apples');
    });

    it('should emit Vue 3 SFC component and createI18n plugin configuration', () => {
      const sfc = vueAdapter.emitVue3Sfc('ProductSummary', ['greeting', 'cart.items'], { scopedCss: true });
      expect(sfc).toContain(`<template>`);
      expect(sfc).toContain(`useI18n()`);
      expect(sfc).toContain(`t('cart.items', { count: itemCount }, itemCount)`);
      expect(sfc).toContain(`<style scoped>`);

      const pluginCode = vueAdapter.emitVueI18nPlugin(sampleBundle);
      expect(pluginCode).toContain(`import { createI18n } from 'vue-i18n';`);
      expect(pluginCode).toContain(`legacy: false`);
    });
  });

  describe('MiniAppI18nAdapter', () => {
    it('should parse WXML content for WXS i18n tags and calls', () => {
      const wxml = `
        <wxs module="i18n" src="../../utils/i18n.wxs"></wxs>
        <view class="box">
          <text>{{ i18n.t('greeting', { name: userName }) }}</text>
          <text>{{ i18n.t('cart.items', { count: 2 }) }}</text>
        </view>
      `;

      const parsed = miniappAdapter.parseWxml(wxml);
      expect(parsed.wxsModuleDeclarations.length).toBe(1);
      expect(parsed.wxsModuleDeclarations[0]!.module).toBe('i18n');
      expect(parsed.wxmlInterpolations.length).toBe(2);
      expect(parsed.wxmlInterpolations[0]!.key).toBe('greeting');
      expect(parsed.wxmlInterpolations[0]!.args['name']).toBe('userName');
    });

    it('should emit standalone WXS script with runtime token replacement and plural support', () => {
      const wxs = miniappAdapter.emitWxsScript(sampleBundle);
      expect(wxs).toContain(`var locales = {`);
      expect(wxs).toContain(`'zh-CN': {`);
      expect(wxs).toContain(`function t(key, params, currentLocale)`);
      expect(wxs).toContain(`msg.replace(placeholder, params[k]);`);
      expect(wxs).toContain(`module.exports = {`);
    });

    it('should emit WXML, MiniApp Page TS and RTL-aware WXSS', () => {
      const wxml = miniappAdapter.emitWxml('ShopList', ['greeting', 'cart.items']);
      expect(wxml).toContain(`<wxs module="i18n"`);
      expect(wxml).toContain(`direction: rtl`);

      const pageTs = miniappAdapter.emitMiniAppTs('ShopList', true);
      expect(pageTs).toContain(`Page({`);
      expect(pageTs).toContain(`switchLocale(locale: string)`);

      const wxss = miniappAdapter.emitWxss('ShopList');
      expect(wxss).toContain(`[style*="direction: rtl"] .i18n-item`);
    });
  });

  describe('CrossPlatformI18nEngine Orchestration', () => {
    it('should audit bundle integrity and detect RTL languages', () => {
      const audit = engine.auditIntegrity(sampleBundle);
      expect(audit.isValid).toBe(true);
      expect(audit.missingTranslations.length).toBe(0);
      expect(audit.rtlLocalesCount).toBe(1); // ar-SA
      expect(engine.isRtlLocale('ar-SA')).toBe(true);
      expect(engine.isRtlLocale('zh-CN')).toBe(false);
    });

    it('should detect missing translation keys in incomplete bundle', () => {
      const incompleteBundle: UniversalI18nBundleIR = {
        ...sampleBundle,
        dictionaries: {
          ...sampleBundle.dictionaries,
          'en-US': {
            common: {
              locale: 'en-US',
              direction: 'ltr',
              namespace: 'common',
              messages: {}, // missing greeting & cart.items
            },
          },
        },
      };

      const audit = engine.auditIntegrity(incompleteBundle);
      expect(audit.isValid).toBe(false);
      expect(audit.missingTranslations.length).toBeGreaterThan(0);
    });

    it('should transform Universal I18n IR to React, Vue, and MiniApp targets', () => {
      const reactRes = engine.transform(sampleBundle, 'react-i18next', 'CartView');
      expect(reactRes.targetFramework).toBe('react-i18next');
      expect(reactRes.code).toContain('useTranslation');
      expect(reactRes.dictionaryFiles['locales/zh-CN/common.json']).toBeDefined();

      const vueRes = engine.transform(sampleBundle, 'vue-i18n', 'CartView');
      expect(vueRes.targetFramework).toBe('vue-i18n');
      expect(vueRes.code).toContain('useI18n');
      expect(vueRes.dictionaryFiles['locales/zh-CN.json']).toBeDefined();

      const miniappRes = engine.transform(sampleBundle, 'miniapp-i18n', 'CartView');
      expect(miniappRes.targetFramework).toBe('miniapp-i18n');
      expect(miniappRes.code).toContain('<wxs module="i18n"');
      expect(miniappRes.dictionaryFiles['utils/i18n.wxs']).toBeDefined();
    });
  });
});
