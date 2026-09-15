import type { MiniappPlatform } from "./miniapp-types.js";

/**
 * Standard Web Storage interface supported across MiniApp runtimes.
 */
export interface MiniappStorageAdapter {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
  clear(): void;
  key(index: number): string | null;
  readonly length: number;
}

export interface StorageAdapterOptions {
  readonly isSession?: boolean;
  readonly inMemoryOnly?: boolean;
  readonly keyPrefix?: string;
  readonly onQuotaExceeded?: (key: string, value: string, error: unknown) => void;
}

/**
 * Resolves platform-specific global API object (wx, my, tt, xhs).
 */
export function getMiniappPlatformGlobal(platform: MiniappPlatform): any {
  if (typeof globalThis === "undefined") return null;
  const g = globalThis as Record<string, any>;
  switch (platform) {
    case "wechat":
      return typeof g.wx === "object" && g.wx !== null ? g.wx : null;
    case "alipay":
      return typeof g.my === "object" && g.my !== null ? g.my : null;
    case "douyin":
      return typeof g.tt === "object" && g.tt !== null ? g.tt : null;
    case "xiaohongshu":
      return typeof g.xhs === "object" && g.xhs !== null ? g.xhs : null;
    default:
      return null;
  }
}

/**
 * Creates a standard Web-compatible Storage adapter bridging to native miniapp storage.
 * Gracefully falls back to in-memory store if the platform API is unavailable or quota is exceeded.
 */
export function createUnifiedStorageAdapter(
  platform: MiniappPlatform,
  options: StorageAdapterOptions = {}
): MiniappStorageAdapter {
  const memoryStore = new Map<string, string>();
  const prefix = options.keyPrefix ?? (options.isSession ? "__elmos_sess_" : "__elmos_store_");
  const inMemoryOnly = options.inMemoryOnly ?? false;

  function toPlatformKey(key: string): string {
    return `${prefix}${key}`;
  }

  function fromPlatformKey(pKey: string): string | null {
    if (pKey.startsWith(prefix)) {
      return pKey.slice(prefix.length);
    }
    return null;
  }

  const native = inMemoryOnly ? null : getMiniappPlatformGlobal(platform);

  return {
    getItem(key: string): string | null {
      if (!key) return null;
      if (inMemoryOnly || !native) {
        return memoryStore.get(key) ?? null;
      }
      try {
        const pKey = toPlatformKey(key);
        if (platform === "alipay") {
          // Alipay support for my.getStorageSync({ key }) or my.getStorageSync(key)
          const res = typeof native.getStorageSync === "function"
            ? native.getStorageSync({ key: pKey })
            : null;
          if (res && typeof res === "object" && "data" in res) {
            return res.data !== null && res.data !== undefined ? String(res.data) : null;
          }
          if (res !== null && res !== undefined) return String(res);
        } else if (typeof native.getStorageSync === "function") {
          const res = native.getStorageSync(pKey);
          if (res !== null && res !== undefined && res !== "") {
            return typeof res === "string" ? res : JSON.stringify(res);
          }
          return res === "" ? "" : null;
        }
      } catch {
        // Fallback to memory store if native read throws
        return memoryStore.get(key) ?? null;
      }
      return memoryStore.get(key) ?? null;
    },

    setItem(key: string, value: string): void {
      if (!key) return;
      const strVal = String(value);
      memoryStore.set(key, strVal);

      if (inMemoryOnly || !native) return;

      try {
        const pKey = toPlatformKey(key);
        if (platform === "alipay") {
          if (typeof native.setStorageSync === "function") {
            native.setStorageSync({ key: pKey, data: strVal });
          }
        } else if (typeof native.setStorageSync === "function") {
          native.setStorageSync(pKey, strVal);
        }
      } catch (err) {
        // Quota exceeded or permission issue
        if (options.onQuotaExceeded) {
          options.onQuotaExceeded(key, strVal, err);
        }
      }
    },

    removeItem(key: string): void {
      if (!key) return;
      memoryStore.delete(key);

      if (inMemoryOnly || !native) return;

      try {
        const pKey = toPlatformKey(key);
        if (platform === "alipay") {
          if (typeof native.removeStorageSync === "function") {
            native.removeStorageSync({ key: pKey });
          }
        } else if (typeof native.removeStorageSync === "function") {
          native.removeStorageSync(pKey);
        }
      } catch {
        // Ignore removal error
      }
    },

    clear(): void {
      memoryStore.clear();

      if (inMemoryOnly || !native) return;

      try {
        if (typeof native.getStorageInfoSync === "function") {
          const info = native.getStorageInfoSync();
          const keys: string[] = info?.keys ?? [];
          for (const k of keys) {
            if (k.startsWith(prefix)) {
              if (platform === "alipay" && typeof native.removeStorageSync === "function") {
                native.removeStorageSync({ key: k });
              } else if (typeof native.removeStorageSync === "function") {
                native.removeStorageSync(k);
              }
            }
          }
        }
      } catch {
        // Ignore clear error
      }
    },

    key(index: number): string | null {
      if (index < 0) return null;
      if (inMemoryOnly || !native) {
        const keys = Array.from(memoryStore.keys());
        return keys[index] ?? null;
      }
      try {
        if (typeof native.getStorageInfoSync === "function") {
          const info = native.getStorageInfoSync();
          const allKeys: string[] = info?.keys ?? [];
          const matchedKeys: string[] = [];
          for (const k of allKeys) {
            const stripped = fromPlatformKey(k);
            if (stripped !== null) matchedKeys.push(stripped);
          }
          return matchedKeys[index] ?? null;
        }
      } catch {
        // Fall back to memoryStore keys
      }
      const keys = Array.from(memoryStore.keys());
      return keys[index] ?? null;
    },

    get length(): number {
      if (inMemoryOnly || !native) {
        return memoryStore.size;
      }
      try {
        if (typeof native.getStorageInfoSync === "function") {
          const info = native.getStorageInfoSync();
          const allKeys: string[] = info?.keys ?? [];
          let count = 0;
          for (const k of allKeys) {
            if (k.startsWith(prefix)) count++;
          }
          return count;
        }
      } catch {
        // Fall back
      }
      return memoryStore.size;
    },
  };
}

// ============================================================================
// Cookie Polyfill
// ============================================================================

export interface CookieOptions {
  expires?: Date | string | number;
  maxAge?: number;
  path?: string;
  domain?: string;
  secure?: boolean;
  sameSite?: "Strict" | "Lax" | "None";
}

interface StoredCookie {
  name: string;
  value: string;
  expiresTimestamp?: number | undefined;
  path?: string | undefined;
  domain?: string | undefined;
  secure?: boolean | undefined;
  sameSite?: "Strict" | "Lax" | "None" | undefined;
}

export class UnifiedCookieStore {
  private cookies = new Map<string, StoredCookie>();
  private readonly storage: MiniappStorageAdapter | null;
  private readonly storageKey: string;

  constructor(storage: MiniappStorageAdapter | null = null, storageKey = "__elmos_cookies__") {
    this.storage = storage;
    this.storageKey = storageKey;
    if (this.storage) {
      this.hydrate();
    }
  }

  private cleanExpired(): void {
    const now = Date.now();
    for (const [key, c] of this.cookies.entries()) {
      if (c.expiresTimestamp && c.expiresTimestamp <= now) {
        this.cookies.delete(key);
      }
    }
  }

  public get(name: string): string | undefined {
    this.cleanExpired();
    return this.cookies.get(name)?.value;
  }

  public set(name: string, value: string, options: CookieOptions = {}): void {
    if (!name || typeof name !== "string") return;
    const now = Date.now();
    let expiresTimestamp: number | undefined;

    if (typeof options.maxAge === "number") {
      expiresTimestamp = now + options.maxAge * 1000;
    } else if (options.expires) {
      if (options.expires instanceof Date) {
        expiresTimestamp = options.expires.getTime();
      } else if (typeof options.expires === "number") {
        expiresTimestamp = options.expires;
      } else {
        const parsed = Date.parse(options.expires);
        if (!Number.isNaN(parsed)) {
          expiresTimestamp = parsed;
        }
      }
    }

    // If already expired, remove
    if (expiresTimestamp !== undefined && expiresTimestamp <= now) {
      this.cookies.delete(name);
      this.persist();
      return;
    }

    this.cookies.set(name, {
      name,
      value: String(value),
      expiresTimestamp,
      path: options.path,
      domain: options.domain,
      secure: options.secure,
      sameSite: options.sameSite,
    });
    this.persist();
  }

  public delete(name: string): void {
    this.cookies.delete(name);
    this.persist();
  }

  public getAll(): Record<string, string> {
    this.cleanExpired();
    const result: Record<string, string> = {};
    for (const [name, item] of this.cookies.entries()) {
      result[name] = item.value;
    }
    return result;
  }

  public toCookieString(): string {
    this.cleanExpired();
    const parts: string[] = [];
    for (const [name, item] of this.cookies.entries()) {
      parts.push(`${encodeURIComponent(name)}=${encodeURIComponent(item.value)}`);
    }
    return parts.join("; ");
  }

  public setFromCookieString(cookieString: string): void {
    if (!cookieString || typeof cookieString !== "string") return;
    const segments = cookieString.split(";").map(s => s.trim()).filter(Boolean);
    if (segments.length === 0) return;

    const first = segments[0];
    if (!first) return;
    const eqIdx = first.indexOf("=");
    if (eqIdx <= 0) return;

    const rawName = first.slice(0, eqIdx).trim();
    const rawVal = first.slice(eqIdx + 1).trim();
    const name = decodeURIComponent(rawName);
    const value = decodeURIComponent(rawVal);

    const options: CookieOptions = {};
    for (let i = 1; i < segments.length; i++) {
      const seg = segments[i];
      if (!seg) continue;
      const sEq = seg.indexOf("=");
      if (sEq === -1) {
        if (seg.toLowerCase() === "secure") options.secure = true;
      } else {
        const optKey = seg.slice(0, sEq).trim().toLowerCase();
        const optVal = seg.slice(sEq + 1).trim();
        if (optKey === "expires") {
          options.expires = optVal;
        } else if (optKey === "max-age") {
          const ma = Number.parseInt(optVal, 10);
          if (!Number.isNaN(ma)) options.maxAge = ma;
        } else if (optKey === "path") {
          options.path = optVal;
        } else if (optKey === "domain") {
          options.domain = optVal;
        } else if (optKey === "samesite") {
          const ss = optVal.toLowerCase();
          if (ss === "strict") options.sameSite = "Strict";
          else if (ss === "lax") options.sameSite = "Lax";
          else if (ss === "none") options.sameSite = "None";
        }
      }
    }

    this.set(name, value, options);
  }

  public clear(): void {
    this.cookies.clear();
    this.persist();
  }

  private persist(): void {
    if (!this.storage) return;
    try {
      this.cleanExpired();
      const arr = Array.from(this.cookies.values());
      this.storage.setItem(this.storageKey, JSON.stringify(arr));
    } catch {
      // Ignore persistence error
    }
  }

  private hydrate(): void {
    if (!this.storage) return;
    try {
      const raw = this.storage.getItem(this.storageKey);
      if (!raw) return;
      const parsed: StoredCookie[] = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        const now = Date.now();
        for (const c of parsed) {
          if (!c.expiresTimestamp || c.expiresTimestamp > now) {
            this.cookies.set(c.name, c);
          }
        }
      }
    } catch {
      // Ignore hydration error
    }
  }
}

export function createCookieStoreAdapter(
  platform: MiniappPlatform,
  storage?: MiniappStorageAdapter
): UnifiedCookieStore {
  const store = storage ?? createUnifiedStorageAdapter(platform);
  return new UnifiedCookieStore(store);
}

// ============================================================================
// Lifecycle Bridge
// ============================================================================

export type MiniappLifecycleEvent =
  | "launch"
  | "show"
  | "hide"
  | "error"
  | "load"
  | "ready"
  | "unload"
  | "pullDownRefresh"
  | "reachBottom"
  | "share";

export type LifecycleListener = (event: MiniappLifecycleEvent, payload?: unknown) => void;

export class MiniappLifecycleBridge {
  private readonly platform: MiniappPlatform;
  private readonly listeners = new Map<MiniappLifecycleEvent, Set<LifecycleListener>>();
  private state = {
    isMounted: false,
    isVisible: false,
    lastRoute: undefined as string | undefined,
    launchOptions: undefined as unknown,
  };

  constructor(platform: MiniappPlatform) {
    this.platform = platform;
  }

  public on(event: MiniappLifecycleEvent, listener: LifecycleListener): () => void {
    let set = this.listeners.get(event);
    if (!set) {
      set = new Set();
      this.listeners.set(event, set);
    }
    set.add(listener);
    return () => {
      set?.delete(listener);
    };
  }

  public emit(event: MiniappLifecycleEvent, payload?: unknown): void {
    switch (event) {
      case "launch":
        this.state.launchOptions = payload;
        break;
      case "load":
      case "ready":
        this.state.isMounted = true;
        break;
      case "show":
        this.state.isVisible = true;
        break;
      case "hide":
        this.state.isVisible = false;
        break;
      case "unload":
        this.state.isMounted = false;
        this.state.isVisible = false;
        break;
    }

    const set = this.listeners.get(event);
    if (set) {
      for (const fn of set) {
        try {
          fn(event, payload);
        } catch {
          // Prevent listener error from bubbling to host platform
        }
      }
    }
  }

  public getCurrentState(): Readonly<typeof this.state> {
    return { ...this.state };
  }

  /**
   * Generates standard Page options with lifecycle forwarders.
   */
  public createPageLifecycleHooks(pageRoute?: string): Record<string, Function> {
    const bridge = this;
    return {
      onLoad(query: unknown) {
        if (pageRoute) bridge.state.lastRoute = pageRoute;
        bridge.emit("load", query);
      },
      onShow() {
        if (pageRoute) bridge.state.lastRoute = pageRoute;
        bridge.emit("show");
      },
      onReady() {
        bridge.emit("ready");
      },
      onHide() {
        bridge.emit("hide");
      },
      onUnload() {
        bridge.emit("unload");
      },
      onPullDownRefresh() {
        bridge.emit("pullDownRefresh");
      },
      onReachBottom() {
        bridge.emit("reachBottom");
      },
      onShareAppMessage(options: unknown) {
        bridge.emit("share", options);
        return {
          title: "MiniApp",
          path: pageRoute ?? "/",
        };
      },
    };
  }

  /**
   * Generates standard App options with lifecycle forwarders.
   */
  public createAppLifecycleHooks(): Record<string, Function> {
    const bridge = this;
    return {
      onLaunch(options: unknown) {
        bridge.emit("launch", options);
      },
      onShow(options: unknown) {
        bridge.emit("show", options);
      },
      onHide() {
        bridge.emit("hide");
      },
      onError(err: unknown) {
        bridge.emit("error", err);
      },
    };
  }
}

export function createLifecycleBridge(platform: MiniappPlatform): MiniappLifecycleBridge {
  return new MiniappLifecycleBridge(platform);
}

// ============================================================================
// Runtime Polyfill Script Generator
// ============================================================================

/**
 * Emits an inline JavaScript polyfill script that can be embedded into generated miniapp projects.
 * Attaches window, document, localStorage, sessionStorage, and document.cookie.
 */
export function generateMiniappRuntimePolyfillScript(platform: MiniappPlatform): string {
  return `/* Elmos MiniApp Cross-Platform Polyfill for ${platform} */
(function() {
  var globalScope = typeof globalThis !== "undefined" ? globalThis : (typeof window !== "undefined" ? window : this);
  if (!globalScope) return;

  var platform = "${platform}";
  var nativeApi = null;
  if (platform === "wechat" && typeof wx === "object") nativeApi = wx;
  else if (platform === "alipay" && typeof my === "object") nativeApi = my;
  else if (platform === "douyin" && typeof tt === "object") nativeApi = tt;
  else if (platform === "xiaohongshu" && typeof xhs === "object") nativeApi = xhs;

  // Window polyfill
  if (!globalScope.window) {
    globalScope.window = globalScope;
  }

  // Storage polyfill
  function createStorage(prefix) {
    var memory = {};
    return {
      getItem: function(key) {
        if (!key) return null;
        var pKey = prefix + key;
        try {
          if (platform === "alipay" && nativeApi && nativeApi.getStorageSync) {
            var res = nativeApi.getStorageSync({ key: pKey });
            if (res && typeof res === "object" && "data" in res) return res.data != null ? String(res.data) : null;
            return res != null ? String(res) : null;
          } else if (nativeApi && nativeApi.getStorageSync) {
            var val = nativeApi.getStorageSync(pKey);
            return val != null && val !== "" ? String(val) : (val === "" ? "" : null);
          }
        } catch(e) {}
        return Object.prototype.hasOwnProperty.call(memory, key) ? memory[key] : null;
      },
      setItem: function(key, value) {
        if (!key) return;
        var sVal = String(value);
        memory[key] = sVal;
        var pKey = prefix + key;
        try {
          if (platform === "alipay" && nativeApi && nativeApi.setStorageSync) {
            nativeApi.setStorageSync({ key: pKey, data: sVal });
          } else if (nativeApi && nativeApi.setStorageSync) {
            nativeApi.setStorageSync(pKey, sVal);
          }
        } catch(e) {}
      },
      removeItem: function(key) {
        if (!key) return;
        delete memory[key];
        var pKey = prefix + key;
        try {
          if (platform === "alipay" && nativeApi && nativeApi.removeStorageSync) {
            nativeApi.removeStorageSync({ key: pKey });
          } else if (nativeApi && nativeApi.removeStorageSync) {
            nativeApi.removeStorageSync(pKey);
          }
        } catch(e) {}
      },
      clear: function() {
        memory = {};
      }
    };
  }

  if (!globalScope.localStorage) {
    globalScope.localStorage = createStorage("__elmos_ls_");
  }
  if (!globalScope.sessionStorage) {
    globalScope.sessionStorage = createStorage("__elmos_ss_");
  }

  // Document & Cookie polyfill
  if (!globalScope.document) {
    globalScope.document = {};
  }
  var cookieStore = {};
  try {
    Object.defineProperty(globalScope.document, "cookie", {
      get: function() {
        var parts = [];
        for (var k in cookieStore) {
          if (Object.prototype.hasOwnProperty.call(cookieStore, k)) {
            parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(cookieStore[k]));
          }
        }
        return parts.join("; ");
      },
      set: function(val) {
        if (!val || typeof val !== "string") return;
        var first = val.split(";")[0];
        var eq = first.indexOf("=");
        if (eq > 0) {
          var k = decodeURIComponent(first.slice(0, eq).trim());
          var v = decodeURIComponent(first.slice(eq + 1).trim());
          cookieStore[k] = v;
        }
      },
      configurable: true
    });
  } catch(e) {}
})();
`;
}
