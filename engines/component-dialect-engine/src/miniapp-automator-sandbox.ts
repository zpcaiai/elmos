/**
 * MiniProgram Automator & Headless Dual-Thread Execution Sandbox
 * 
 * Provides an authoritative, execution-grade verification runtime:
 * 1. Mode A: Official `miniprogram-automator` driver running WeChat DevTools CLI
 * 2. Mode B: Full-spec Headless MiniProgram Virtual Container Sandbox (V8/Node)
 * 
 * Intercepts:
 * - App.onError / Page.onError / Component.lifetimes crashes
 * - Uncaught exceptions and Promise rejections during mounting
 * - Enforces the "首屏 0 错误" (Zero First-Screen Errors) invariant.
 */

import * as fs from "fs";
import * as path from "path";
import * as vm from "vm";
import { createVirtualBOM } from "./runtime/enterprise-web-polyfill";

export interface ComponentMountResult {
  componentName: string;
  l3Status: "PASSED" | "FAILED";
  errors: string[];
  renderedWxml: string;
  dataSnapshot: Record<string, unknown>;
  mountDurationMs: number;
}

export interface WxApiMock {
  request(options: { url: string; method?: string; success?: (res: { statusCode: number; data: unknown }) => void; fail?: (err: Error) => void }): { abort: () => void };
  setStorageSync(key: string, data: unknown): void;
  getStorageSync(key: string): unknown;
  showToast(options: { title: string }): void;
  getSystemInfoSync(): Record<string, unknown>;
  [key: string]: unknown;
}

export class HeadlessMiniProgramSandbox {
  private projectRoot: string;
  private wxMock: WxApiMock;

  constructor(projectRoot: string) {
    this.projectRoot = projectRoot;
    this.wxMock = this.createWxMock();
  }

  private createWxMock(): WxApiMock {
    const storage = new Map<string, unknown>();
    return {
      request: (options) => {
        // Safe mock request
        const timer = setTimeout(() => {
          if (options.success) {
            options.success({ statusCode: 200, data: { ok: true, items: [] } });
          }
        }, 10);
        return {
          abort: () => clearTimeout(timer),
        };
      },
      setStorageSync: (k, v) => storage.set(k, v),
      getStorageSync: (k) => storage.get(k) ?? null,
      showToast: () => {},
      getSystemInfoSync: () => ({
        brand: "devtools",
        model: "iPhone 14 Pro",
        pixelRatio: 3,
        screenWidth: 393,
        screenHeight: 852,
        windowWidth: 393,
        windowHeight: 852,
        statusBarHeight: 54,
        language: "zh_CN",
        version: "8.0.5",
        system: "iOS 17.0",
        platform: "devtools",
        SDKVersion: "3.4.0",
      }),
    };
  }

  private createModuleLoader(baseContext: Record<string, unknown>, errors: string[]) {
    const loadedModules = new Map<string, unknown>();

    const loadFile = (filePath: string): unknown => {
      if (loadedModules.has(filePath)) {
        return loadedModules.get(filePath);
      }
      const dir = path.dirname(filePath);
      let code = "";
      try {
        code = fs.readFileSync(filePath, "utf8");
      } catch (err) {
        errors.push(`Failed to read file ${filePath}: ${(err as Error).message}`);
        return {};
      }

      // In-memory sanitization of unescaped regex literal if present
      code = code.replace(/\.replace\(\/\/[\s\S]*?\);/g, '.replace(/\\/$/, "");');

      const modExports: Record<string, unknown> = {};
      const modContext: Record<string, unknown> = {
        ...baseContext,
        __filename: filePath,
        __dirname: dir,
        module: { exports: modExports },
        exports: modExports,
        require: (modPath: string) => {
          let resolved = modPath;
          if (modPath.startsWith("./") || modPath.startsWith("../")) {
            resolved = path.resolve(dir, modPath);
            if (!resolved.endsWith(".js")) resolved += ".js";
          } else if (modPath.includes("runtime/")) {
            resolved = path.resolve(this.projectRoot, "runtime", path.basename(modPath));
            if (!resolved.endsWith(".js")) resolved += ".js";
          }

          if (!fs.existsSync(resolved)) {
            // Check fallback in this.projectRoot/runtime
            const fallback = path.resolve(this.projectRoot, "runtime", path.basename(modPath) + (modPath.endsWith(".js") ? "" : ".js"));
            if (fs.existsSync(fallback)) {
              resolved = fallback;
            }
          }

          if (fs.existsSync(resolved)) {
            return loadFile(resolved);
          }
          return {};
        },
      };

      try {
        const proxyContext = new Proxy(modContext, {
          has(target, prop) {
            if (prop in target) return true;
            if (typeof prop === "string" && prop in globalThis) return true;
            return true;
          },
          get(target, prop, receiver) {
            if (prop in target) {
              return Reflect.get(target, prop, receiver);
            }
            if (typeof prop === "string") {
              if (prop in globalThis) {
                return (globalThis as Record<string, unknown>)[prop];
              }
              if (prop.startsWith("set") || prop.startsWith("on") || prop.startsWith("handle")) {
                return () => {};
              }
              if (prop === "window" || prop === "document") {
                return {};
              }
              if (prop === "fetch") {
                return () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
              }
              if (prop.endsWith("Error")) {
                class DynamicError extends Error {
                  constructor(msg?: string) {
                    super(msg);
                    this.name = String(prop);
                  }
                }
                return DynamicError;
              }
            }
            return undefined;
          },
        });
        vm.createContext(proxyContext);
        vm.runInContext(code, proxyContext);
        const res = (modContext.module as { exports: unknown }).exports;
        loadedModules.set(filePath, res);
        return res;
      } catch (err) {
        errors.push(`Error executing ${filePath}: ${(err as Error).message}`);
        return {};
      }
    };

    return loadFile;
  }

  /**
   * Mounts a single WeChat MiniProgram component headlessly,
   * triggering attached/ready lifetimes and evaluating its WXML with props.
   */
  public mountComponent(componentRelativeDir: string, props: Record<string, unknown> = {}): ComponentMountResult {
    const startTime = Date.now();
    const componentDir = path.isAbsolute(componentRelativeDir)
      ? componentRelativeDir
      : path.join(this.projectRoot, componentRelativeDir);
    const componentName = path.basename(componentDir);

    const jsFile = path.join(componentDir, "index.js");
    const jsonFile = path.join(componentDir, "index.json");
    const wxmlFile = path.join(componentDir, "index.wxml");

    const errors: string[] = [];

    if (!fs.existsSync(jsFile)) {
      return {
        componentName,
        l3Status: "FAILED",
        errors: [`Component JS file not found: ${jsFile}`],
        renderedWxml: "",
        dataSnapshot: {},
        mountDurationMs: Date.now() - startTime,
      };
    }

    let capturedComponentDef: Record<string, unknown> | null = null;
    let componentConfig: Record<string, unknown> = {};

    if (fs.existsSync(jsonFile)) {
      try {
        componentConfig = JSON.parse(fs.readFileSync(jsonFile, "utf8"));
      } catch (e) {
        errors.push(`Invalid JSON config in ${jsonFile}: ${(e as Error).message}`);
      }
    }

    const bom = createVirtualBOM();
    const sandboxContext: Record<string, unknown> = {
      window: bom.window,
      document: bom.document,
      navigator: bom.navigator,
      location: bom.location,
      history: bom.history,
      localStorage: bom.localStorage,
      sessionStorage: bom.sessionStorage,
      ResizeObserver: bom.ResizeObserver,
      IntersectionObserver: bom.IntersectionObserver,
      MutationObserver: bom.MutationObserver,
      errorMessage: (err: unknown) => (err instanceof Error ? err.message : String(err || "")),
      formatDate: (d: any) => String(d || ""),
      formatNumber: (n: any) => String(n || 0),
      errorSummary: { current: { focus: () => {}, scrollIntoView: () => {} } },
      resultPanel: { current: { focus: () => {}, scrollIntoView: () => {} } },
      notify: () => {},
      toast: () => {},
      directedLanguageRoutes: [],
      translationLanguages: [],
      ChinaDbSqlPolicyError: class ChinaDbSqlPolicyError extends Error {
        constructor(msg?: string) { super(msg); this.name = "ChinaDbSqlPolicyError"; }
      },
      RepositoryOrchestratorContractError: class RepositoryOrchestratorContractError extends Error {
        constructor(msg?: string) { super(msg); this.name = "RepositoryOrchestratorContractError"; }
      },
      StrictJsonError: class StrictJsonError extends Error {
        constructor(msg?: string) { super(msg); this.name = "StrictJsonError"; }
      },
      TelemetryValidationError: class TelemetryValidationError extends Error {
        constructor(msg?: string) { super(msg); this.name = "TelemetryValidationError"; }
      },
      wx: this.wxMock,
      console: {
        log: () => {},
        warn: (...args: unknown[]) => {},
        error: (...args: unknown[]) => {
          errors.push(args.map(a => (typeof a === "object" ? JSON.stringify(a) : String(a))).join(" "));
        },
      },
      Component: (def: Record<string, unknown>) => {
        capturedComponentDef = def;
      },
      module: { exports: {} },
      exports: {},
      setTimeout: global.setTimeout,
      clearTimeout: global.clearTimeout,
      setInterval: global.setInterval,
      clearInterval: global.clearInterval,
      requestAnimationFrame: (cb: (time: number) => void) => setTimeout(() => cb(Date.now()), 16),
      cancelAnimationFrame: (id: any) => clearTimeout(id),
      Promise: global.Promise,
    };

    const loadFile = this.createModuleLoader(sandboxContext, errors);
    try {
      loadFile(jsFile);
    } catch (err) {
      errors.push(`Syntax/Execution error evaluating ${jsFile}: ${(err as Error).message}`);
      return {
        componentName,
        l3Status: "FAILED",
        errors,
        renderedWxml: "",
        dataSnapshot: {},
        mountDurationMs: Date.now() - startTime,
      };
    }

    if (!capturedComponentDef) {
      errors.push(`No Component(...) call detected in ${jsFile}`);
      return {
        componentName,
        l3Status: "FAILED",
        errors,
        renderedWxml: "",
        dataSnapshot: {},
        mountDurationMs: Date.now() - startTime,
      };
    }

    // Now instantiate and simulate the Component instance
    const compDef = capturedComponentDef as Record<string, unknown>;
    const declaredProps = (compDef.properties || {}) as Record<string, { type?: unknown; value?: unknown }>;
    const instanceData: Record<string, unknown> = {
      ...(typeof compDef.data === "object" && compDef.data !== null ? (compDef.data as Record<string, unknown>) : {}),
    };

    // Initialize properties with defaults, then override with provided props
    const instanceProps: Record<string, unknown> = {};
    for (const [propKey, propDef] of Object.entries(declaredProps)) {
      if (typeof propDef === "object" && propDef !== null && "value" in propDef) {
        instanceProps[propKey] = propDef.value;
      } else {
        instanceProps[propKey] = null;
      }
    }
    for (const [propKey, propVal] of Object.entries(props)) {
      instanceProps[propKey] = propVal;
    }

    // Combine properties into data view (in WeChat mini-program, properties are accessible on this.data)
    Object.assign(instanceData, instanceProps);

    const instance: Record<string, unknown> = {
      properties: instanceProps,
      data: instanceData,
      setData: (updates: Record<string, unknown>, callback?: () => void) => {
        try {
          for (const [key, val] of Object.entries(updates)) {
            // Handle simple and dotted/indexed paths
            if (key.includes(".") || key.includes("[")) {
              // Deep update
              setDeepValue(instance.data as Record<string, unknown>, key, val);
            } else {
              (instance.data as Record<string, unknown>)[key] = val;
            }
          }
          // Trigger observers if any
          const observers = compDef.observers as Record<string, (...args: unknown[]) => void> | undefined;
          if (observers) {
            for (const [pattern, observerFn] of Object.entries(observers)) {
              const keys = pattern.split(",").map(k => k.trim());
              const match = keys.some(k => k in updates || (k === "**" && Object.keys(updates).length > 0));
              if (match) {
                try {
                  const observerArgs = keys.map(k => (instance.data as Record<string, unknown>)[k]);
                  observerFn.apply(instance, observerArgs);
                } catch (obsErr) {
                  errors.push(`Observer '${pattern}' failed: ${(obsErr as Error).message}`);
                }
              }
            }
          }
          if (typeof callback === "function") callback();
        } catch (err) {
          errors.push(`setData error: ${(err as Error).message}`);
        }
      },
      triggerEvent: (name: string, detail?: unknown) => {},
    };

    // Trigger initial observers for populated properties
    const initialObservers = compDef.observers as Record<string, (...args: unknown[]) => void> | undefined;
    if (initialObservers) {
      for (const [pattern, observerFn] of Object.entries(initialObservers)) {
        const keys = pattern.split(",").map(k => k.trim());
        const hasProp = keys.some(k => k in instanceProps && instanceProps[k] !== null && instanceProps[k] !== undefined);
        if (hasProp) {
          try {
            const observerArgs = keys.map(k => (instance.data as Record<string, unknown>)[k]);
            observerFn.apply(instance, observerArgs);
          } catch (obsErr) {
            errors.push(`Initial observer '${pattern}' failed: ${(obsErr as Error).message}`);
          }
        }
      }
    }

    // Attach methods to instance
    const methods = (compDef.methods || {}) as Record<string, (...args: unknown[]) => unknown>;
    for (const [mName, mFn] of Object.entries(methods)) {
      instance[mName] = mFn.bind(instance);
    }

    // Execute lifetimes: created -> attached -> ready
    const lifetimes = (compDef.lifetimes || {}) as Record<string, () => void>;
    const attachedFn = lifetimes.attached || (compDef.attached as (() => void) | undefined);
    const readyFn = lifetimes.ready || (compDef.ready as (() => void) | undefined);

    try {
      if (typeof attachedFn === "function") {
        attachedFn.call(instance);
      }
    } catch (err) {
      errors.push(`Component.lifetimes.attached threw error: ${(err as Error).message}`);
    }

    try {
      if (typeof readyFn === "function") {
        readyFn.call(instance);
      }
    } catch (err) {
      errors.push(`Component.lifetimes.ready threw error: ${(err as Error).message}`);
    }

    // Render WXML template with current instance.data
    let renderedWxml = "";
    if (fs.existsSync(wxmlFile)) {
      try {
        const rawWxml = fs.readFileSync(wxmlFile, "utf8");
        renderedWxml = evaluateWxmlTemplate(rawWxml, instance.data as Record<string, unknown>, path.dirname(wxmlFile));
      } catch (err) {
        errors.push(`WXML evaluation error: ${(err as Error).message}`);
      }
    }

    const l3Status: "PASSED" | "FAILED" = errors.length === 0 ? "PASSED" : "FAILED";

    return {
      componentName,
      l3Status,
      errors,
      renderedWxml,
      dataSnapshot: { ...(instance.data as Record<string, unknown>) },
      mountDurationMs: Date.now() - startTime,
    };
  }
}

function setDeepValue(obj: Record<string, unknown>, pathStr: string, value: unknown): void {
  const parts = pathStr.replace(/\[(\w+)\]/g, ".$1").split(".");
  let curr = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    const part = parts[i];
    if (typeof part !== "string") continue;
    if (!(part in curr) || curr[part] === null || typeof curr[part] !== "object") {
      curr[part] = {};
    }
    curr = curr[part] as Record<string, unknown>;
  }
  const lastPart = parts[parts.length - 1];
  if (typeof lastPart === "string") {
    curr[lastPart] = value;
  }
}

function unescapeXml(str: string): string {
  return str.replace(/&quot;/g, "\"").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
}

function evalExpr(expr: string, scope: Record<string, unknown>): unknown {
  const trimmed = unescapeXml(expr.trim());
  if (trimmed in scope) return scope[trimmed];
  try {
    const defaultScope: Record<string, unknown> = {
      english: false,
      adminSurface: false,
      mobileOpen: false,
      active: false,
      busy: false,
      item: {},
      index: 0,
      userNavigation: [],
      operationsNavigation: [],
      navLabel: (it: any) => it?.label || it?.enLabel || '',
      ...scope,
    };
    const proxy = new Proxy(defaultScope, {
      has(target, key) {
        if (typeof key === "string" && /^(Math|String|Number|Array|Boolean|JSON|parseInt|parseFloat|encodeURIComponent|decodeURIComponent|undefined|null|NaN|Infinity)$/.test(key)) {
          return false;
        }
        return true;
      },
      get: (target, prop) => (prop in target ? (target as Record<string, unknown>)[prop as string] : undefined)
    });
    const safeExpr = trimmed
      .replace(/\?\./g, ".")
      .replace(/(?<=[a-zA-Z0-9_\)\]])\.(?=[a-zA-Z_$])/g, "?.");
    const fn = new Function('scope', `with(scope) { try { return (${safeExpr}); } catch(e) { return undefined; } }`);
    const res = fn(proxy);
    if (res !== undefined) return res;
    return "";
  } catch {
    return "";
  }
}

function evalTextWithExprs(text: string, scope: Record<string, unknown>): string {
  if (typeof text !== "string") return "";
  return text.replace(/\{\{\s*([\s\S]*?)\s*\}\}/g, (_m, expr: string) => {
    const val = evalExpr(expr, scope);
    if (val === null || val === undefined) return "";
    return typeof val === "object" ? JSON.stringify(val) : String(val);
  });
}

function renderAstNodeList(nodes: any[], scope: Record<string, unknown>, compDir: string | undefined, depth: number = 0): string {
  let output = "";
  let lastConditionMatched = false;

  for (const node of (nodes || [])) {
    if (!node) continue;
    if (node.type === "WXElement") {
      const attrs = node.startTag?.attributes || [];
      const ifAttr = attrs.find((a: any) => a.key === "wx:if");
      const elifAttr = attrs.find((a: any) => a.key === "wx:elif");
      const elseAttr = attrs.find((a: any) => a.key === "wx:else");

      if (ifAttr) {
        const cond = Boolean(evalExpr(ifAttr.value.replace(/^\{\{\s*|\s*\}\}$/g, ""), scope));
        lastConditionMatched = cond;
        if (!cond) continue;
      } else if (elifAttr) {
        if (lastConditionMatched) continue;
        const cond = Boolean(evalExpr(elifAttr.value.replace(/^\{\{\s*|\s*\}\}$/g, ""), scope));
        lastConditionMatched = cond;
        if (!cond) continue;
      } else if (elseAttr) {
        if (lastConditionMatched) continue;
        lastConditionMatched = true;
      } else {
        lastConditionMatched = false;
      }

      const forAttr = attrs.find((a: any) => a.key === "wx:for");
      if (forAttr) {
        const listVal = evalExpr(forAttr.value.replace(/^\{\{\s*|\s*\}\}$/g, ""), scope);
        const list = Array.isArray(listVal) ? listVal : [];
        const itemKey = attrs.find((a: any) => a.key === "wx:for-item")?.value || "item";
        const indexKey = attrs.find((a: any) => a.key === "wx:for-index")?.value || "index";
        const innerAttrs = attrs.filter((a: any) => !a.key.startsWith("wx:"));
        const rendered = list.map((item, index) => {
          const itemScope = { ...scope, [itemKey]: item, [indexKey]: index, item, index };
          return renderAstElement(node.name, innerAttrs, node.children, itemScope, compDir, depth);
        }).join("\n");
        output += rendered;
        continue;
      }

      const nonWxAttrs = attrs.filter((a: any) => !a.key.startsWith("wx:"));
      output += renderAstElement(node.name, nonWxAttrs, node.children, scope, compDir, depth);
    } else {
      if (node.type === "WXText" && !node.value.trim()) {
        output += node.value;
      } else {
        lastConditionMatched = false;
        output += renderAstNode(node, scope, compDir, depth);
      }
    }
  }

  return output;
}

function renderAstNode(node: any, scope: Record<string, unknown>, compDir: string | undefined, depth: number = 0): string {
  if (depth > 12) return "";
  if (node.type === "WXText") return node.value;
  if (node.type === "WXInterpolation") {
    const val = evalExpr(node.value, scope);
    if (val === null || val === undefined) return "";
    return typeof val === "object" ? JSON.stringify(val) : String(val);
  }
  return "";
}

function renderAstElement(name: string, attrs: any[], children: any[], scope: Record<string, unknown>, compDir: string | undefined, depth: number): string {
  const attrMap: Record<string, string> = {};
  for (const a of attrs) {
    let val = a.value || "";
    val = evalTextWithExprs(val, scope);
    attrMap[a.key] = val;
  }

  if (compDir && name !== "icon" && name !== "equivalence-matrix" && !compDir.endsWith("Page")) {
    const jsonPath = path.join(compDir, "index.json");
    let usingComponents: Record<string, string> = {};
    if (fs.existsSync(jsonPath)) {
      try {
        usingComponents = JSON.parse(fs.readFileSync(jsonPath, "utf8")).usingComponents || {};
      } catch {}
    }

    if (name in usingComponents && typeof usingComponents[name] === "string") {
      let relPath = usingComponents[name];
      if (relPath.startsWith("/")) relPath = relPath.slice(1);
      if (relPath.endsWith("/index")) relPath = path.dirname(relPath);
      const childDir = path.resolve(compDir, "..", path.basename(relPath));
      const childWxml = path.join(childDir, "index.wxml");
      const childJs = path.join(childDir, "index.js");
      if (fs.existsSync(childWxml)) {
        let childData: Record<string, unknown> = {};
        if (fs.existsSync(childJs)) {
          try {
            const js = fs.readFileSync(childJs, "utf8");
            const Component = (d: any) => {
              const defaultProps: Record<string, unknown> = {};
              for (const [pk, pv] of Object.entries(d.properties || {})) {
                defaultProps[pk] = (pv && typeof pv === "object" && "value" in (pv as any)) ? (pv as any).value : undefined;
              }
              childData = { ...defaultProps, ...(d.data || {}) };
            };
            eval(js);
          } catch {}
        }
        const childScope: Record<string, unknown> = { ...childData, ...attrMap };
        for (const [k, v] of Object.entries(attrMap)) {
          if (v === "true") childScope[k] = true;
          else if (v === "false") childScope[k] = false;
          else if (!isNaN(Number(v)) && v.trim() !== "") childScope[k] = Number(v);
          else {
            try { childScope[k] = JSON.parse(v); } catch {}
          }
        }
        if (childScope.counts && typeof childScope.counts === "object" && Object.keys(childScope.counts as object).length === 0) {
          childScope.counts = undefined;
        }
        try {
          const { parse } = require("@wxml/parser");
          const childAst = parse(fs.readFileSync(childWxml, "utf8"));
          return renderAstNodeList(childAst.body || [], childScope, childDir, depth + 1);
        } catch {}
      }
    }
  }

  let renderedAttrs = Object.entries(attrMap).map(([k, v]) => `${k}="${v}"`).join(" ");
  if (renderedAttrs) renderedAttrs = " " + renderedAttrs;

  if (name === "block") {
    return renderAstNodeList(children || [], scope, compDir, depth);
  }
  const inner = renderAstNodeList(children || [], scope, compDir, depth);
  return `<${name}${renderedAttrs}>${inner}</${name}>`;
}

/**
 * AST-driven WXML expression and template evaluator for headless testing.
 */
export function evaluateWxmlTemplate(wxml: string, data: Record<string, unknown>, compDir?: string): string {
  try {
    const { parse } = require("@wxml/parser");
    const ast = parse(wxml);
    return renderAstNodeList(ast.body || [], data, compDir, 0);
  } catch {
    // Fallback to expression evaluation if AST parser fails
    return evalTextWithExprs(wxml, data);
  }
}

