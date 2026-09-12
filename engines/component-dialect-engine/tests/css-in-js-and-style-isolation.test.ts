/**
 * @file css-in-js-and-style-isolation.test.ts
 * @description Comprehensive unit & integration tests for CSS-in-JS (Emotion),
 * CSS Modules scoped isolation, and pseudo-class / responsive media query bridging.
 */

import {
  CssInJsEmotionTranspiler,
  CssModulesEngine,
  MediaQueryPseudoBridge,
} from '../src/style-engine';

describe('CSS-in-JS & Style Isolation Engine (M32)', () => {
  describe('Emotion / styled-components Transpiler', () => {
    it('should parse tagged template literals, separate static styles, and extract dynamic bindings', () => {
      const transpiler = new CssInJsEmotionTranspiler();
      const code = `
        import styled from '@emotion/styled';

        const PrimaryButton = styled.button\`
          display: inline-flex;
          padding: 8px 16px;
          border-radius: 4px;
          color: \${props => props.primary ? '#ffffff' : '#333333'};
          background-color: \${props => props.primary ? '#1677ff' : '#f0f0f0'};
          font-weight: bold;
        \`;
      `;

      const result = transpiler.transpile(code);
      expect(result.components.length).toBe(1);

      const comp = result.components[0]!;
      expect(comp.componentName).toBe('PrimaryButton');
      expect(comp.baseTag).toBe('button');
      expect(comp.dynamicBindings.length).toBe(2);
      expect(comp.dynamicBindings[0]?.property).toBe('color');
      expect(comp.dynamicBindings[0]?.expression).toContain('props.primary');
      expect(comp.dynamicBindings[1]?.property).toBe('background-color');

      // Static WXSS should contain padding and border-radius
      expect(comp.staticCss).toContain('display: inline-flex');
      expect(comp.staticCss).toContain('padding: 8px 16px');
      expect(comp.staticCss).toContain('border-radius: 4px');

      // ArkUI attribute modifiers
      expect(comp.arkUiAttributeModifiers).toContain(".fontColor(props.primary ? '#ffffff' : '#333333')");
      expect(comp.arkUiAttributeModifiers).toContain(".backgroundColor(props.primary ? '#1677ff' : '#f0f0f0')");
    });
  });

  describe('CSS Modules Scoped Isolation Engine', () => {
    it('should generate deterministic scoped class hashes and rewrite class names', () => {
      const engine = new CssModulesEngine('wx-mod');
      const css = `
        .header {
          display: flex;
          font-size: 16px;
        }
        .title {
          font-weight: bold;
        }
        :global(.global-reset) {
          margin: 0;
        }
      `;

      const result = engine.transpile(css, 'dashboard.module.css');
      expect(result.classMap['header']).toBeDefined();
      expect(result.classMap['title']).toBeDefined();
      expect(result.classMap['global-reset']).toBeUndefined(); // Ignored because of :global

      expect(result.scopedCss).toContain(`.${result.classMap['header']}`);
      expect(result.scopedCss).toContain(`.${result.classMap['title']}`);
      expect(result.scopedCss).toContain('.global-reset'); // Global preserved

      // Template rewriting
      const template = `<div class={styles.header}><span class={styles.title}>Title</span></div>`;
      const rewritten = engine.rewriteTemplateClasses(template, result.classMap);
      expect(rewritten).toContain(`'${result.classMap['header']}'`);
      expect(rewritten).toContain(`'${result.classMap['title']}'`);
    });
  });

  describe('Media Query & Pseudo-Class Bridge', () => {
    it('should map :hover, :active, and :focus to hover-class and focused classes', () => {
      const bridge = new MediaQueryPseudoBridge();
      const css = `
        .submit-btn:hover {
          background-color: #4096ff;
        }
        .submit-btn:active {
          background-color: #0958d9;
        }
        .input-field:focus {
          border-color: #1677ff;
        }
      `;

      const result = bridge.lowerPseudoClasses(css);
      expect(result.mappings.length).toBe(3);

      const hoverMapping = result.mappings.find((m) => m.pseudoKind === 'hover')!;
      expect(hoverMapping.hoverClassName).toBe('submit-btn-hover');
      expect(hoverMapping.hoverStayTimeMs).toBe(70);

      const activeMapping = result.mappings.find((m) => m.pseudoKind === 'active')!;
      expect(activeMapping.hoverClassName).toBe('submit-btn-active');

      const focusMapping = result.mappings.find((m) => m.pseudoKind === 'focus')!;
      expect(focusMapping.hoverClassName).toBe('input-field-focused');

      // Resulting WXSS
      expect(result.wxss).toContain('.submit-btn-hover');
      expect(result.wxss).toContain('.submit-btn-active');
      expect(result.wxss).toContain('.input-field-focused');
    });

    it('should generate responsive viewport observer code for MiniApp', () => {
      const bridge = new MediaQueryPseudoBridge();
      const code = bridge.generateResponsiveObserverCode();

      expect(code).toContain('MiniAppViewportObserver');
      expect(code).toContain('isSM');
      expect(code).toContain('isMD');
      expect(code).toContain('isLG');
      expect(code).toContain('wx.onWindowResize');
    });
  });
});
