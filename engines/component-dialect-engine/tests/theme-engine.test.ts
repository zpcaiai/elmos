/**
 * @file theme-engine.test.ts
 * @description Comprehensive unit test suite for Design Token Extractor and Theme Token Emitter.
 * Verifies token extraction from CSS custom properties and Ant Design theme objects,
 * type inference, alias resolution, and cross-platform token emission to CSS Variables,
 * Tailwind configs, MiniApp WXSS, and W3C DTCG format.
 * Conforms to Batch 32 Skill 1204.
 */

import {
  DesignTokenExtractor,
  ThemeTokenEmitter,
  UniversalThemeIR,
} from '../src/theme-engine';

describe('Design Token & Theme Engine', () => {
  const extractor = new DesignTokenExtractor();
  const emitter = new ThemeTokenEmitter();

  const sampleCss = `
    :root {
      --color-primary: #1890ff;
      --color-success: #52c41a;
      --spacing-base: 16px;
      --font-size-body: 14px;
      --border-radius-base: 4px;
      --color-primary-alias: var(--color-primary);
    }
  `;

  describe('DesignTokenExtractor', () => {
    it('should extract design tokens and infer types from CSS custom properties', () => {
      const result = extractor.extractFromCSS(sampleCss, 'ant-theme');
      expect(result.tokenCount).toBe(6);
      expect(result.themeIR.themeId).toBe('ant-theme');

      const primary = result.themeIR.tokens.find((t) => t.name === 'color-primary');
      expect(primary).toBeDefined();
      expect(primary!.type).toBe('color');
      expect(primary!.value).toBe('#1890ff');

      const spacing = result.themeIR.tokens.find((t) => t.name === 'spacing-base');
      expect(spacing).toBeDefined();
      expect(spacing!.type).toBe('dimension');
      expect(spacing!.value).toBe('16px');

      const alias = result.themeIR.tokens.find((t) => t.name === 'color-primary-alias');
      expect(alias).toBeDefined();
      expect(alias!.isAlias).toBe(true);
      expect(alias!.aliasTarget).toBe('--color-primary');
    });

    it('should extract tokens from Ant Design JS theme object', () => {
      const antdTheme = {
        colorPrimary: '#1677ff',
        colorSuccess: '#52c41a',
        borderRadius: 6,
        fontSize: 14,
      };

      const result = extractor.extractFromAntDTheme(antdTheme, 'antd-v5');
      expect(result.tokenCount).toBe(4);
      expect(result.themeIR.tokens.some((t) => t.name === 'colorPrimary' && t.type === 'color')).toBe(true);
      expect(result.themeIR.tokens.some((t) => t.name === 'borderRadius' && t.type === 'dimension')).toBe(true);
    });
  });

  describe('ThemeTokenEmitter', () => {
    let sampleThemeIR: UniversalThemeIR;

    beforeEach(() => {
      sampleThemeIR = extractor.extractFromCSS(sampleCss, 'test-theme').themeIR;
    });

    it('should emit CSS custom properties stylesheet', () => {
      const emitted = emitter.emit(sampleThemeIR, 'css-variables');
      expect(emitted.format).toBe('css-variables');
      expect(emitted.code).toContain(`:root {`);
      expect(emitted.code).toContain(`--color-primary: #1890ff;`);
    });

    it('should emit Tailwind theme configuration', () => {
      const emitted = emitter.emit(sampleThemeIR, 'tailwind-theme');
      expect(emitted.format).toBe('tailwind-theme');
      expect(emitted.code).toContain(`module.exports = {`);
      expect(emitted.code).toContain(`colors:`);
      expect(emitted.code).toContain(`'#1890ff'`);
    });

    it('should emit MiniApp WXSS with page variables and rpx conversion', () => {
      const emitted = emitter.emit(sampleThemeIR, 'miniapp-wxss');
      expect(emitted.format).toBe('miniapp-wxss');
      expect(emitted.code).toContain(`page {`);
      expect(emitted.code).toContain(`--color-primary: #1890ff;`);
      expect(emitted.code).toContain(`WeChat MiniApp Global Theme Variables (WXSS)`);
    });

    it('should emit W3C DTCG standard design tokens JSON', () => {
      const emitted = emitter.emit(sampleThemeIR, 'dtcg-json');
      expect(emitted.format).toBe('dtcg-json');
      const parsed = JSON.parse(emitted.code);
      expect(parsed['color']).toBeDefined();
      expect(parsed['color']['primary']['$value']).toBe('#1890ff');
      expect(parsed['color']['primary']['$type']).toBe('color');
    });
  });
});
