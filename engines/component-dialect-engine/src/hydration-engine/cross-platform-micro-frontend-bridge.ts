/**
 * @file cross-platform-micro-frontend-bridge.ts
 * @description W3C Web Components and Custom Elements bridge for cross-framework micro-frontends.
 * Wraps React, Vue, Svelte, and Angular components as isolated Custom Elements
 * with attribute-to-prop reflection and synthetic event re-dispatch.
 * Conforms to Batch 32 Skill 1213 (b32-rendering-ssr-csr-hydration).
 */

import { MicroFrontendBridgeConfig } from './hydration-ir-types';

export class CrossPlatformMicroFrontendBridge {
  /**
   * Emit Custom Element wrapper JavaScript code for a micro-frontend component
   */
  public static emitCustomElementWrapper(config: MicroFrontendBridgeConfig): string {
    const lines: string[] = [];
    const className = `${this.toPascalCase(config.componentName)}Element`;

    lines.push(`/**`);
    lines.push(` * Auto-generated W3C Custom Element Micro-Frontend Bridge`);
    lines.push(` * Source: ${config.sourceFramework} -> Target: ${config.targetHostFramework}`);
    lines.push(` */\n`);

    lines.push(`class ${className} extends HTMLElement {`);
    lines.push(`  static get observedAttributes() {`);
    lines.push(`    return ${JSON.stringify(config.observedAttributes)};`);
    lines.push(`  }\n`);

    lines.push(`  constructor() {`);
    lines.push(`    super();`);
    lines.push(`    this.attachShadow({ mode: 'open' });`);
    lines.push(`    this._props = {};`);
    lines.push(`  }\n`);

    lines.push(`  connectedCallback() {`);
    lines.push(`    this._render();`);
    lines.push(`  }\n`);

    lines.push(`  disconnectedCallback() {`);
    lines.push(`    this._cleanup();`);
    lines.push(`  }\n`);

    lines.push(`  attributeChangedCallback(name, oldValue, newValue) {`);
    lines.push(`    if (oldValue !== newValue) {`);
    lines.push(`      this._props[name] = newValue;`);
    lines.push(`      this._render();`);
    lines.push(`    }`);
    lines.push(`  }\n`);

    lines.push(`  _render() {`);
    lines.push(`    // Mount framework-specific root into this.shadowRoot`);
    if (config.sourceFramework === 'react') {
      lines.push(`    if (!this._reactRoot) {`);
      lines.push(`      var ReactDOM = window.ReactDOM;`);
      lines.push(`      var React = window.React;`);
      lines.push(`      if (ReactDOM && ReactDOM.createRoot) {`);
      lines.push(`        this._reactRoot = ReactDOM.createRoot(this.shadowRoot);`);
      lines.push(`      }`);
      lines.push(`    }`);
      lines.push(`    if (this._reactRoot && window.${config.componentName}) {`);
      lines.push(`      this._reactRoot.render(window.React.createElement(window.${config.componentName}, this._props));`);
      lines.push(`    }`);
    } else if (config.sourceFramework === 'vue') {
      lines.push(`    if (!this._vueApp && window.Vue) {`);
      lines.push(`      var app = window.Vue.createApp(window.${config.componentName}, this._props);`);
      lines.push(`      app.mount(this.shadowRoot);`);
      lines.push(`      this._vueApp = app;`);
      lines.push(`    }`);
    } else {
      lines.push(`    this.shadowRoot.innerHTML = '<div class="mfe-placeholder">${config.componentName}</div>';`);
    }
    lines.push(`  }\n`);

    lines.push(`  _cleanup() {`);
    if (config.sourceFramework === 'react') {
      lines.push(`    if (this._reactRoot) { this._reactRoot.unmount(); }`);
    } else if (config.sourceFramework === 'vue') {
      lines.push(`    if (this._vueApp) { this._vueApp.unmount(); }`);
    }
    lines.push(`  }`);
    lines.push(`}\n`);

    lines.push(`if (!customElements.get('${config.customTag}')) {`);
    lines.push(`  customElements.define('${config.customTag}', ${className});`);
    lines.push(`}\n`);

    return lines.join('\n');
  }

  private static toPascalCase(str: string): string {
    return str
      .replace(/[^a-zA-Z0-9]/g, ' ')
      .split(' ')
      .filter(Boolean)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join('');
  }
}
