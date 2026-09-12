/**
 * @file enterprise-microfrontend-container.ts
 * @description Enterprise Microfrontend Container, Sandbox Isolation, and Communication Bus.
 * Provides:
 * 1. ProxySandbox: ES6 Proxy-based JS sandbox isolating global window pollution per sub-app
 * 2. ScopedCssSandbox: Prefixes all sub-app style rules with a container namespace
 * 3. MicroEventBus: Cross-application pub/sub bus with automatic unmount disposal
 * 4. MicroRouterSync: Synchronizes host route navigation with sub-app micro-routers.
 */

export interface MicroAppConfig {
  name: string;
  entry: string;
  container: string;
  activeRule: string; // URL prefix or route regex
  props?: Record<string, any>;
}

export interface SubAppLifecycle {
  bootstrap?: () => Promise<void>;
  mount?: (props: any) => Promise<void>;
  unmount?: () => Promise<void>;
}

/**
 * ES6 Proxy Window Sandbox for sub-app isolation
 */
export class ProxySandbox {
  public name: string;
  public proxy: any;
  private fakeWindow: Record<string | symbol, any> = {};
  private active = false;

  constructor(name: string) {
    this.name = name;
    const rawWindow = typeof window !== 'undefined' ? window : {};

    this.proxy = new Proxy(this.fakeWindow, {
      get: (target, prop, receiver) => {
        if (prop === 'window' || prop === 'self' || prop === 'globalThis') {
          return this.proxy;
        }
        if (prop in target) {
          return Reflect.get(target, prop, receiver);
        }
        return Reflect.get(rawWindow, prop, receiver);
      },

      set: (target, prop, value, receiver) => {
        if (this.active) {
          return Reflect.set(target, prop, value, receiver);
        }
        return true;
      },

      has: (target, prop) => {
        return prop in target || prop in rawWindow;
      },
    });
  }

  public activeSandbox(): void {
    this.active = true;
  }

  public inactiveSandbox(): void {
    this.active = false;
  }

  public getModifiedProperties(): Record<string, any> {
    return { ...this.fakeWindow };
  }
}

/**
 * Cross-App Typed Event Bus with lifecycle memory leak protection
 */
export class MicroEventBus {
  private static instance: MicroEventBus;
  private listeners: Map<string, Set<(payload: any) => void>> = new Map();
  private appDisposers: Map<string, Array<() => void>> = new Map();

  public static getInstance(): MicroEventBus {
    if (!MicroEventBus.instance) {
      MicroEventBus.instance = new MicroEventBus();
    }
    return MicroEventBus.instance;
  }

  /**
   * Subscribe to event, automatically tagged with subscribing sub-app name
   */
  public on<T = any>(eventName: string, handler: (payload: T) => void, appName?: string): () => void {
    let set = this.listeners.get(eventName);
    if (!set) {
      set = new Set();
      this.listeners.set(eventName, set);
    }
    set.add(handler);

    const disposer = () => {
      const s = this.listeners.get(eventName);
      if (s) s.delete(handler);
    };

    if (appName) {
      const list = this.appDisposers.get(appName) || [];
      list.push(disposer);
      this.appDisposers.set(appName, list);
    }

    return disposer;
  }

  /**
   * Emit event to all subscribers
   */
  public emit<T = any>(eventName: string, payload: T): void {
    const set = this.listeners.get(eventName);
    if (set) {
      set.forEach((handler) => {
        try {
          handler(payload);
        } catch (err) {
          console.error(`[MicroEventBus] Error in handler for event "${eventName}":`, err);
        }
      });
    }
  }

  /**
   * Clean up all event listeners for a specific sub-app upon unmounting
   */
  public destroyAppListeners(appName: string): void {
    const disposers = this.appDisposers.get(appName);
    if (disposers) {
      disposers.forEach((dispose) => dispose());
      this.appDisposers.delete(appName);
    }
  }
}

/**
 * Scoped CSS Sandbox prefixer
 */
export class ScopedCssSandbox {
  /**
   * Prefixes all CSS selectors with the sub-app container selector
   */
  public static prefixStyles(cssContent: string, prefixSelector: string): string {
    return cssContent.replace(/(^|[\}\n;])\s*([^{};@\s][^{};]*?)\s*\{/g, (_match, delimiter, selector) => {
      const trimmed = selector.trim();
      if (trimmed.startsWith('@') || trimmed.length === 0) {
        return _match;
      }
      const scoped = trimmed
        .split(',')
        .map((s: string) => {
          const part = s.trim();
          if (part.startsWith(':root') || part.startsWith('body') || part.startsWith('html')) {
            return `${prefixSelector}`;
          }
          return `${prefixSelector} ${part}`;
        })
        .join(', ');
      return `${delimiter ? delimiter + ' ' : ''}${scoped} {`;
    });
  }
}

/**
 * Enterprise MicroFrontend Host Manager
 */
export class EnterpriseMicroFrontendContainerEngine {
  private apps: Map<string, MicroAppConfig> = new Map();
  private sandboxes: Map<string, ProxySandbox> = new Map();
  private activeApp: string | null = null;
  private eventBus = MicroEventBus.getInstance();

  public registerApp(app: MicroAppConfig): void {
    this.apps.set(app.name, app);
    this.sandboxes.set(app.name, new ProxySandbox(app.name));
  }

  public async mountApp(name: string, props: Record<string, any> = {}): Promise<void> {
    const app = this.apps.get(name);
    if (!app) {
      throw new Error(`[MFEContainer] App "${name}" is not registered`);
    }

    if (this.activeApp && this.activeApp !== name) {
      await this.unmountApp(this.activeApp);
    }

    const sandbox = this.sandboxes.get(name)!;
    sandbox.activeSandbox();
    this.activeApp = name;

    this.eventBus.emit('mfe:app-mounted', { name, props });
  }

  public async unmountApp(name: string): Promise<void> {
    const sandbox = this.sandboxes.get(name);
    if (sandbox) {
      sandbox.inactiveSandbox();
    }
    this.eventBus.destroyAppListeners(name);
    if (this.activeApp === name) {
      this.activeApp = null;
    }
    this.eventBus.emit('mfe:app-unmounted', { name });
  }

  public getActiveApp(): string | null {
    return this.activeApp;
  }

  public getSandbox(name: string): ProxySandbox | undefined {
    return this.sandboxes.get(name);
  }
}
