/**
 * @file cross-platform-a11y-normalizer.ts
 * @description Cross-Platform Accessibility Normalizer and ARIA Compiler.
 * Translates universal ARIA attributes and focus management rules across
 * React JSX, Vue 3 templates, WeChat MiniApp WXML, and ArkUI HarmonyOS components.
 * Conforms to Batch 32 Skill 1221 (b32-accessibility-i18n-seo-visual-e2e).
 */

import {
  AccessibleNodeIR,
  AriaAttributesIR,
  FocusManagementIR,
} from './a11y-seo-ir-types';

export class CrossPlatformA11yNormalizer {
  /**
   * Compile accessible node properties to React JSX attribute string.
   */
  public emitReactAriaAttributes(node: AccessibleNodeIR): string {
    const attrs: string[] = [];
    const aria = node.aria;

    if (aria.role) attrs.push(`role="${aria.role}"`);
    if (aria.label) attrs.push(`aria-label="${this.escapeAttr(aria.label)}"`);
    if (aria.labelledby) attrs.push(`aria-labelledby="${aria.labelledby}"`);
    if (aria.describedby) attrs.push(`aria-describedby="${aria.describedby}"`);

    if (aria.expanded !== undefined) {
      attrs.push(typeof aria.expanded === 'boolean' ? `aria-expanded={${aria.expanded}}` : `aria-expanded={Boolean(${aria.expanded})}`);
    }
    if (aria.hidden !== undefined) {
      attrs.push(typeof aria.hidden === 'boolean' ? `aria-hidden={${aria.hidden}}` : `aria-hidden={Boolean(${aria.hidden})}`);
    }
    if (aria.selected !== undefined) {
      attrs.push(typeof aria.selected === 'boolean' ? `aria-selected={${aria.selected}}` : `aria-selected={Boolean(${aria.selected})}`);
    }
    if (aria.checked !== undefined) {
      attrs.push(typeof aria.checked === 'boolean' ? `aria-checked={${aria.checked}}` : `aria-checked={${aria.checked}}`);
    }
    if (aria.live) attrs.push(`aria-live="${aria.live}"`);
    if (aria.atomic) attrs.push(`aria-atomic={true}`);
    if (aria.controls) attrs.push(`aria-controls="${aria.controls}"`);
    if (aria.haspopup) attrs.push(`aria-haspopup="${aria.haspopup}"`);

    if (node.focus?.autoFocus) attrs.push(`autoFocus`);
    if (node.focus?.rovingTabIndex) attrs.push(`tabIndex={isFocused ? 0 : -1}`);

    return attrs.join(' ');
  }

  /**
   * Compile accessible node properties to Vue 3 template bindings.
   */
  public emitVueAriaAttributes(node: AccessibleNodeIR): string {
    const attrs: string[] = [];
    const aria = node.aria;

    if (aria.role) attrs.push(`role="${aria.role}"`);
    if (aria.label) attrs.push(`aria-label="${this.escapeAttr(aria.label)}"`);
    if (aria.labelledby) attrs.push(`aria-labelledby="${aria.labelledby}"`);
    if (aria.describedby) attrs.push(`aria-describedby="${aria.describedby}"`);

    if (aria.expanded !== undefined) {
      attrs.push(typeof aria.expanded === 'boolean' ? `:aria-expanded="${aria.expanded}"` : `:aria-expanded="Boolean(${aria.expanded})"`);
    }
    if (aria.hidden !== undefined) {
      attrs.push(typeof aria.hidden === 'boolean' ? `:aria-hidden="${aria.hidden}"` : `:aria-hidden="Boolean(${aria.hidden})"`);
    }
    if (aria.selected !== undefined) {
      attrs.push(typeof aria.selected === 'boolean' ? `:aria-selected="${aria.selected}"` : `:aria-selected="Boolean(${aria.selected})"`);
    }
    if (aria.live) attrs.push(`aria-live="${aria.live}"`);

    if (node.focus?.autoFocus) attrs.push(`autofocus`);
    if (node.focus?.rovingTabIndex) attrs.push(`:tabindex="isFocused ? 0 : -1"`);

    return attrs.join(' ');
  }

  /**
   * Compile accessible node properties to WeChat MiniApp WXML attributes.
   * WeChat uses `aria-role` and `aria-label` for screen reader (VoiceOver / TalkBack) integration.
   */
  public emitMiniAppAriaAttributes(node: AccessibleNodeIR): string {
    const attrs: string[] = [];
    const aria = node.aria;

    if (aria.role) attrs.push(`aria-role="${aria.role}"`);
    if (aria.label) attrs.push(`aria-label="${this.escapeAttr(aria.label)}"`);

    if (aria.expanded !== undefined) {
      const expr = typeof aria.expanded === 'boolean' ? `${aria.expanded}` : `{{ ${aria.expanded} }}`;
      attrs.push(`aria-expanded="${expr}"`);
    }
    if (aria.hidden !== undefined) {
      const expr = typeof aria.hidden === 'boolean' ? `${aria.hidden}` : `{{ ${aria.hidden} }}`;
      attrs.push(`aria-hidden="${expr}"`);
    }
    if (aria.disabled !== undefined) {
      const expr = typeof aria.disabled === 'boolean' ? `${aria.disabled}` : `{{ ${aria.disabled} }}`;
      attrs.push(`aria-disabled="${expr}"`);
    }

    return attrs.join(' ');
  }

  /**
   * Compile accessible node properties to ArkUI Declarative modifier chaining.
   */
  public emitArkUIAccessibilityModifiers(node: AccessibleNodeIR): string {
    const lines: string[] = [];
    const aria = node.aria;

    lines.push(`.accessibilityGroup(true)`);
    if (aria.label) {
      lines.push(`.accessibilityText('${this.escapeAttr(aria.label)}')`);
    }
    if (aria.describedby || node.screenReaderText) {
      lines.push(`.accessibilityDescription('${this.escapeAttr(node.screenReaderText || aria.describedby || '')}')`);
    }
    if (aria.hidden) {
      lines.push(`.accessibilityLevel('no')`);
    }

    return lines.join('\n');
  }

  /**
   * Generate TypeScript Focus Trap utility code for accessible modal dialogs.
   */
  public emitFocusTrapUtility(): string {
    const lines: string[] = [
      `/**`,
      ` * Accessible Modal Focus Trap Utility`,
      ` * Intercepts Tab and Shift+Tab to trap keyboard focus within container.`,
      ` */`,
      `export function createFocusTrap(container: HTMLElement, onEscape?: () => void): () => void {`,
      `  const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';`,
      '',
      `  function handleKeyDown(e: KeyboardEvent) {`,
      `    if (e.key === 'Escape' && onEscape) {`,
      `      e.preventDefault();`,
      `      onEscape();`,
      `      return;`,
      `    }`,
      '',
      `    if (e.key !== 'Tab') return;`,
      '',
      `    const focusables = Array.from(container.querySelectorAll<HTMLElement>(focusableSelector)).filter(`,
      `      (el) => !el.hasAttribute('disabled') && el.offsetParent !== null`,
      `    );`,
      '',
      `    if (focusables.length === 0) {`,
      `      e.preventDefault();`,
      `      return;`,
      `    }`,
      '',
      `    const firstElement = focusables[0];`,
      `    const lastElement = focusables[focusables.length - 1];`,
      '',
      `    if (e.shiftKey) {`,
      `      if (document.activeElement === firstElement) {`,
      `        e.preventDefault();`,
      `        lastElement?.focus();`,
      `      }`,
      `    } else {`,
      `      if (document.activeElement === lastElement) {`,
      `        e.preventDefault();`,
      `        firstElement?.focus();`,
      `      }`,
      `    }`,
      `  }`,
      '',
      `  container.addEventListener('keydown', handleKeyDown);`,
      `  return () => {`,
      `    container.removeEventListener('keydown', handleKeyDown);`,
      `  };`,
      `}`,
    ];

    return lines.join('\n');
  }

  private escapeAttr(str: string): string {
    return str.replace(/"/g, '&quot;');
  }
}
