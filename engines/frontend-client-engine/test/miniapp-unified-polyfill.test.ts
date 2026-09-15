import assert from "node:assert/strict";
import test from "node:test";
import { runInNewContext } from "node:vm";

import {
  createUnifiedStorageAdapter,
  createCookieStoreAdapter,
  UnifiedCookieStore,
  createLifecycleBridge,
  MiniappLifecycleBridge,
  generateMiniappRuntimePolyfillScript,
} from "../src/miniapp-unified-polyfill.js";
import type { MiniappPlatform } from "../src/miniapp-types.js";

test("StorageAdapter operates correctly in memory fallback mode", () => {
  const platforms: MiniappPlatform[] = ["wechat", "alipay", "douyin", "xiaohongshu"];
  for (const p of platforms) {
    const storage = createUnifiedStorageAdapter(p, { inMemoryOnly: true });
    assert.equal(storage.length, 0);
    assert.equal(storage.getItem("non_existent"), null);

    storage.setItem("user_token", "abc-123");
    assert.equal(storage.getItem("user_token"), "abc-123");
    assert.equal(storage.length, 1);
    assert.equal(storage.key(0), "user_token");

    storage.setItem("theme", "dark");
    assert.equal(storage.length, 2);

    storage.removeItem("user_token");
    assert.equal(storage.getItem("user_token"), null);
    assert.equal(storage.getItem("theme"), "dark");
    assert.equal(storage.length, 1);

    storage.clear();
    assert.equal(storage.length, 0);
    assert.equal(storage.getItem("theme"), null);
  }
});

test("StorageAdapter bridges with simulated native miniapp globals", () => {
  const simulatedNative = {
    wx: {
      _store: {} as Record<string, any>,
      getStorageSync(k: string) { return this._store[k] ?? null; },
      setStorageSync(k: string, v: any) { this._store[k] = v; },
      removeStorageSync(k: string) { delete this._store[k]; },
      getStorageInfoSync() { return { keys: Object.keys(this._store) }; },
    },
    my: {
      _store: {} as Record<string, any>,
      getStorageSync(opt: { key: string }) { return { data: this._store[opt.key] ?? null }; },
      setStorageSync(opt: { key: string; data: any }) { this._store[opt.key] = opt.data; },
      removeStorageSync(opt: { key: string }) { delete this._store[opt.key]; },
      getStorageInfoSync() { return { keys: Object.keys(this._store) }; },
    },
    tt: {
      _store: {} as Record<string, any>,
      getStorageSync(k: string) { return this._store[k] ?? null; },
      setStorageSync(k: string, v: any) { this._store[k] = v; },
      removeStorageSync(k: string) { delete this._store[k]; },
      getStorageInfoSync() { return { keys: Object.keys(this._store) }; },
    },
    xhs: {
      _store: {} as Record<string, any>,
      getStorageSync(k: string) { return this._store[k] ?? null; },
      setStorageSync(k: string, v: any) { this._store[k] = v; },
      removeStorageSync(k: string) { delete this._store[k]; },
      getStorageInfoSync() { return { keys: Object.keys(this._store) }; },
    },
  };

  const g = globalThis as Record<string, any>;
  g.wx = simulatedNative.wx;
  g.my = simulatedNative.my;
  g.tt = simulatedNative.tt;
  g.xhs = simulatedNative.xhs;

  try {
    for (const p of ["wechat", "alipay", "douyin", "xiaohongshu"] as const) {
      const storage = createUnifiedStorageAdapter(p);
      storage.setItem("key1", "val1");
      assert.equal(storage.getItem("key1"), "val1");
      assert.equal(storage.length, 1);
      assert.equal(storage.key(0), "key1");

      storage.removeItem("key1");
      assert.equal(storage.getItem("key1"), null);
      assert.equal(storage.length, 0);

      storage.setItem("key2", "val2");
      storage.clear();
      assert.equal(storage.getItem("key2"), null);
      assert.equal(storage.length, 0);
    }
  } finally {
    delete g.wx;
    delete g.my;
    delete g.tt;
    delete g.xhs;
  }
});

test("UnifiedCookieStore handles set, get, delete, expiration, and string parsing", () => {
  const cookieStore = new UnifiedCookieStore();

  cookieStore.set("session_id", "xyz789", { path: "/", secure: true, sameSite: "Strict" });
  assert.equal(cookieStore.get("session_id"), "xyz789");

  // Multi-cookie export string
  cookieStore.set("lang", "zh-CN");
  const cookieStr = cookieStore.toCookieString();
  assert.ok(cookieStr.includes("session_id=xyz789"));
  assert.ok(cookieStr.includes("lang=zh-CN"));

  // Cookie expiration with maxAge <= 0
  cookieStore.set("temp", "remove-me", { maxAge: -1 });
  assert.equal(cookieStore.get("temp"), undefined);

  // Parse document.cookie string
  cookieStore.setFromCookieString("token=jwt-token-val; Path=/api; Secure; SameSite=Lax");
  assert.equal(cookieStore.get("token"), "jwt-token-val");

  // Deletion
  cookieStore.delete("token");
  assert.equal(cookieStore.get("token"), undefined);

  // Persistence to storage adapter
  const storage = createUnifiedStorageAdapter("wechat", { inMemoryOnly: true });
  const persistentStore = new UnifiedCookieStore(storage, "__test_cookies__");
  persistentStore.set("saved_cookie", "persisted_value");

  // Hydrate another store instance from same storage
  const restoredStore = new UnifiedCookieStore(storage, "__test_cookies__");
  assert.equal(restoredStore.get("saved_cookie"), "persisted_value");
});

test("MiniappLifecycleBridge dispatches lifecycle events and tracks state", () => {
  const bridge = createLifecycleBridge("xiaohongshu");
  let launched = false;
  let loaded = false;
  let shownCount = 0;
  let hiddenCount = 0;

  bridge.on("launch", (_evt, opts) => {
    launched = true;
    assert.deepEqual(opts, { scene: 1001 });
  });

  bridge.on("load", (_evt, query) => {
    loaded = true;
    assert.deepEqual(query, { id: "42" });
  });

  bridge.on("show", () => {
    shownCount++;
  });

  bridge.on("hide", () => {
    hiddenCount++;
  });

  const appHooks = bridge.createAppLifecycleHooks();
  const pageHooks = bridge.createPageLifecycleHooks("/pages/detail/index");

  // Simulate miniapp runtime calling app hooks
  appHooks.onLaunch?.({ scene: 1001 });
  assert.equal(launched, true);

  // Simulate miniapp runtime calling page hooks
  pageHooks.onLoad?.({ id: "42" });
  assert.equal(loaded, true);
  assert.equal(bridge.getCurrentState().isMounted, true);
  assert.equal(bridge.getCurrentState().lastRoute, "/pages/detail/index");

  pageHooks.onShow?.();
  assert.equal(shownCount, 1);
  assert.equal(bridge.getCurrentState().isVisible, true);

  pageHooks.onHide?.();
  assert.equal(hiddenCount, 1);
  assert.equal(bridge.getCurrentState().isVisible, false);

  pageHooks.onUnload?.();
  assert.equal(bridge.getCurrentState().isMounted, false);
});

test("generateMiniappRuntimePolyfillScript executes cleanly in a VM sandbox", () => {
  const platforms: MiniappPlatform[] = ["wechat", "alipay", "douyin", "xiaohongshu"];
  for (const p of platforms) {
    const script = generateMiniappRuntimePolyfillScript(p);
    assert.ok(script.length > 500);
    assert.ok(script.includes(p));

    const sandbox: Record<string, any> = {};
    if (p === "wechat") sandbox.wx = {};
    if (p === "alipay") sandbox.my = {};
    if (p === "douyin") sandbox.tt = {};
    if (p === "xiaohongshu") sandbox.xhs = {};

    runInNewContext(script, sandbox);

    assert.ok(sandbox.window);
    assert.ok(sandbox.localStorage);
    assert.ok(sandbox.sessionStorage);
    assert.ok(sandbox.document);

    // Test storage polyfill in sandbox
    sandbox.localStorage.setItem("test_key", "test_val");
    assert.equal(sandbox.localStorage.getItem("test_key"), "test_val");
    sandbox.localStorage.removeItem("test_key");
    assert.equal(sandbox.localStorage.getItem("test_key"), null);

    // Test cookie polyfill in sandbox
    sandbox.document.cookie = "username=john; Path=/";
    assert.ok(sandbox.document.cookie.includes("username=john"));
  }
});
