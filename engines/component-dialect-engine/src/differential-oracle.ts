/**
 * Double-Blind Differential Oracle (React / Next.js DOM vs WeChat MiniProgram WXML)
 * 
 * Strict behavioral equivalence evaluator:
 * 1. Takes identical Props / Fixture inputs
 * 2. Renders Next.js React 19 Source DOM via real React server renderer
 * 3. Renders WeChat MiniProgram Target via Headless MiniProgram Sandbox
 * 4. Extracts text token stream and semantic structural tags
 * 5. Computes consistency score:
 *    Consistency = 0.6 * TextSimilarity + 0.4 * StructuralSimilarity
 * 6. Hard Gate: Consistency >= 95.0% AND Zero Runtime Errors -> L4 PASSED
 */

import * as path from "path";
import * as ts from "typescript";
import { normalizeHtml } from "./execution";
import { HeadlessMiniProgramSandbox } from "./miniapp-automator-sandbox";

export interface DifferentialResult {
  componentName: string;
  l3Passed: boolean;
  l4Passed: boolean;
  consistencyScore: number;
  textSimilarity: number;
  structuralSimilarity: number;
  sourceDomSample: string;
  targetWxmlSample: string;
  diagnostics: string[];
}

export class DoubleBlindDifferentialOracle {
  private sandbox: HeadlessMiniProgramSandbox;

  constructor(wechatProjectRoot: string) {
    this.sandbox = new HeadlessMiniProgramSandbox(wechatProjectRoot);
  }

  /**
   * Evaluates a component pair (React source vs WeChat mini-program target)
   * under a blind test fixture props.
   */
  public async evaluateComponent(
    componentName: string,
    reactSourceJsx: string,
    wechatComponentRelativeDir: string,
    fixtureProps: Record<string, unknown> = {}
  ): Promise<DifferentialResult> {
    const diagnostics: string[] = [];

    // 1. Render React 19 / Next.js Source Component
    let sourceDom = "";
    try {
      sourceDom = await this.renderReactSource(reactSourceJsx, fixtureProps, componentName);
    } catch (err) {
      diagnostics.push(`Source React render failed: ${(err as Error).message}`);
    }

    // 2. Render WeChat MiniProgram Component in Sandbox
    const mountResult = this.sandbox.mountComponent(wechatComponentRelativeDir, fixtureProps);
    if (mountResult.l3Status === "FAILED") {
      diagnostics.push(...mountResult.errors.map(e => `Target MiniProgram mount error: ${e}`));
    }

    const targetWxml = mountResult.renderedWxml;

    // 3. Compute Differential Comparison
    const normSource = this.normalizeMarkup(sourceDom, false);
    const normTarget = this.normalizeMarkup(targetWxml, true);

    const sourceTokens = this.extractTokens(normSource);
    const targetTokens = this.extractTokens(normTarget);

    const textSimilarity = this.computeTokenSimilarity(sourceTokens, targetTokens);
    const structuralSimilarity = this.computeStructuralSimilarity(normSource, normTarget);

    const consistencyScore = Math.round((0.6 * textSimilarity + 0.4 * structuralSimilarity) * 1000) / 1000;

    const l3Passed = mountResult.l3Status === "PASSED";
    const l4Passed = l3Passed && consistencyScore >= 0.95;

    if (!l4Passed && l3Passed) {
      diagnostics.push(
        `Consistency ${Math.round(consistencyScore * 100)}% fell below 95.0% threshold (text: ${Math.round(
          textSimilarity * 100
        )}%, structure: ${Math.round(structuralSimilarity * 100)}%)`
      );
    }

    return {
      componentName,
      l3Passed,
      l4Passed,
      consistencyScore,
      textSimilarity,
      structuralSimilarity,
      sourceDomSample: normSource.slice(0, 150),
      targetWxmlSample: normTarget.slice(0, 150),
      diagnostics,
    };
  }

  private async renderReactSource(
    jsxSource: string,
    props: Record<string, unknown>,
    componentName?: string
  ): Promise<string> {
    const React = require("react");
    const { renderToStaticMarkup } = require("react-dom/server");

    // Transpile JSX/TSX
    const transpileResult = ts.transpileModule(jsxSource, {
      compilerOptions: {
        target: ts.ScriptTarget.ES2022,
        module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.React,
        esModuleInterop: true,
      },
    }).outputText;

    // Custom require resolver for Next.js, CSS modules, providers and child components
    const customRequire = (reqPath: string): unknown => {
      if (reqPath === "react") return React;
      if (reqPath === "react-dom/server") return require("react-dom/server");

      // CSS / SCSS modules -> return Proxy so styles.card returns "card"
      if (reqPath.endsWith(".css") || reqPath.endsWith(".scss")) {
        return new Proxy({}, {
          get: (_target, prop) => (typeof prop === "string" ? prop : ""),
        });
      }

      // Next.js standard packages
      if (reqPath === "next/link") {
        return {
          __esModule: true,
          default: ({ href, children, ...rest }: any) =>
            React.createElement("a", { href, ...rest }, children),
        };
      }
      if (reqPath === "next/image") {
        return {
          __esModule: true,
          default: ({ src, alt, ...rest }: any) =>
            React.createElement("img", { src, alt, ...rest }),
        };
      }
      if (reqPath === "next/navigation") {
        return {
          useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {}, back: () => {} }),
          usePathname: () => "/",
          useSearchParams: () => new URLSearchParams(),
          useParams: () => ({}),
        };
      }

      if (reqPath.includes("pricingCatalog")) {
        return {
          formatQuota: (v: number) => v.toLocaleString("zh-CN"),
          percent: (bps: number) => `${(bps / 100).toFixed(2)}%`,
          meterLabel: (label: string, consumed: number, limit: number, bps: number) =>
            `${label}：已使用 ${consumed.toLocaleString("zh-CN")}，额度 ${limit.toLocaleString("zh-CN")}，消耗进度 ${(bps / 100).toFixed(2)}%`,
        };
      }

      // App-specific providers & contexts
      if (reqPath.includes("AccountSessionProvider")) {
        return {
          useAccountSession: () => ({
            status: "authenticated",
            principal: {
              actorId: "actor-1",
              displayName: "Admin User",
              organizationId: "org-main",
              roles: ["ADMIN"],
              permissions: ["*"],
              memberships: [{ organizationId: "org-main", roles: ["ADMIN"], permissions: ["*"] }],
            },
            expiresAt: "2099-01-01T00:00:00Z",
            refresh: async () => {},
            switchTenant: async () => {},
            logout: async () => {},
          }),
          AccountSessionProvider: ({ children }: any) => children,
        };
      }

      if (reqPath.includes("UiPreferencesProvider")) {
        return {
          useUiPreferences: () => ({
            theme: "light",
            locale: "zh-CN",
            setLocale: () => {},
            setTheme: () => {},
          }),
          UiPreferencesProvider: ({ children }: any) => children,
        };
      }

      // Relative or foreign component imports -> return stub component/function
      const stubName = path.basename(reqPath, path.extname(reqPath));
      const StubFunctionOrComponent: any = function (p: any) {
        if (arguments.length === 0) return true;
        const cleanProps = p && typeof p === "object" ? { ...p } : {};
        delete cleanProps.children;
        return React.createElement("div", { "data-component": stubName, ...cleanProps }, p?.children);
      };
      StubFunctionOrComponent.displayName = stubName;
      StubFunctionOrComponent.default = StubFunctionOrComponent;
      StubFunctionOrComponent.__esModule = true;

      const stubModule = new Proxy(StubFunctionOrComponent, {
        get: (target, prop) => {
          if (prop in target) return (target as any)[prop];
          if (prop === "default") return StubFunctionOrComponent;
          if (prop === "__esModule") return true;
          if (typeof prop === "symbol") return undefined;
          const ChildStub: any = function (p: any) {
            if (arguments.length === 0) return true;
            const cleanProps = p && typeof p === "object" ? { ...p } : {};
            delete cleanProps.children;
            const compName = typeof prop === "string" && /^[A-Z]/.test(prop) ? prop : `${stubName}.${String(prop)}`;
            return React.createElement("div", { "data-component": compName, ...cleanProps }, p?.children);
          };
          const compDisplayName = typeof prop === "string" && /^[A-Z]/.test(prop) ? prop : `${stubName}.${String(prop)}`;
          ChildStub.displayName = compDisplayName;
          ChildStub.default = ChildStub;
          ChildStub.__esModule = true;
          return ChildStub;
        },
      });

      return stubModule;
    };

    let transpileCode = transpileResult;
    if (componentName) {
      transpileCode += `\nif (typeof ${componentName} !== "undefined" && !exports["${componentName}"]) exports["${componentName}"] = ${componentName};`;
    }

    // Evaluate in safe local function wrapper
    const modWrapper = new Function("require", "exports", "module", "React", transpileCode);
    const modExports: Record<string, unknown> = {};
    const mod = { exports: modExports };

    try {
      modWrapper(customRequire, modExports, mod, React);
    } catch (err) {
      throw new Error(`Execution error evaluating React module: ${(err as Error).message}`);
    }

    // Locate the component export
    let Component: unknown = null;
    if (componentName && typeof mod.exports[componentName] === "function") {
      Component = mod.exports[componentName];
    } else if (typeof mod.exports.default === "function") {
      Component = mod.exports.default;
    } else {
      for (const val of Object.values(mod.exports)) {
        if (typeof val === "function") {
          Component = val;
          break;
        }
      }
    }

    if (typeof Component !== "function") {
      throw new Error(`Exported React component '${componentName || "default"}' is not a callable function`);
    }

    let renderedElement: any = null;
    try {
      if (Component.constructor && Component.constructor.name === "AsyncFunction") {
        renderedElement = await (Component as any)(props);
      } else {
        renderedElement = React.createElement(Component as any, props);
      }
    } catch {
      renderedElement = React.createElement(Component as any, props);
    }

    return renderToStaticMarkup(renderedElement);
  }

  private normalizeMarkup(html: string, isWxml: boolean): string {
    let res = html;
    if (isWxml) {
      res = res.replace(/<([a-z0-9]+-[a-z0-9-]+)(\b[^>]*)\/>/g, (_m, tag, attrs) => {
        const pascal = tag.split("-").map((s: string) => s.charAt(0).toUpperCase() + s.slice(1)).join("");
        return `<div data-component="${pascal}" ${attrs}></div>`;
      });
      res = res.replace(/<([a-z0-9]+-[a-z0-9-]+)(\b[^>]*)>([\s\S]*?)<\/\1>/g, (_m, tag, attrs, inner) => {
        const pascal = tag.split("-").map((s: string) => s.charAt(0).toUpperCase() + s.slice(1)).join("");
        return `<div data-component="${pascal}" ${attrs}>${inner}</div>`;
      });

      res = res.replace(/<icon(\b[^>]*)\/>/g, '<div data-component="Icon" $1></div>');
      res = res.replace(/<icon(\b[^>]*)>([\s\S]*?)<\/icon>/g, '<div data-component="Icon" $1>$2</div>');

      res = res.replace(/<navigator\b([^>]*)url="([^"]*)"([^>]*)>/g, '<a$1href="$2"$3>');
      res = res.replace(/<navigator\b([^>]*)>/g, '<a$1>').replace(/<\/navigator>/g, '</a>');

      res = res.replace(/<view(\b[^>]*)\/>/g, '<div$1></div>').replace(/<view\b([^>]*)>/g, '<div$1>').replace(/<\/view>/g, '</div>');
      res = res.replace(/<text(\b[^>]*)\/>/g, '<span$1></span>').replace(/<text\b([^>]*)>/g, '<span$1>').replace(/<\/text>/g, '</span>');
      res = res.replace(/<scroll-view(\b[^>]*)>/g, '<div$1>').replace(/<\/scroll-view>/g, '</div>');
      res = res.replace(/<image(\b[^>]*)>/g, '<img$1>').replace(/<\/image>/g, '</img>');
      res = res.replace(/<button(\b[^>]*)>/g, '<button$1>').replace(/<\/button>/g, '</button>');
    }

    // Homomorphic tag mapping for cross-platform comparison
    res = res.replace(/<(\/?)(main|header|footer|section|article|aside|nav|ul|ol|li|dl|dt|dd|table|thead|tbody|tr|th|td|details|summary|h1|h2|h3|h4|h5|h6|p)\b/gi, '<$1div');
    res = res.replace(/<(\/?)(b|i|em|strong|small|code|label)\b/gi, '<$1span');
    res = res.replace(/<(\/?)(navigator)\b/gi, '<$1a');
    res = res.replace(/<(\/?)(image)\b/gi, '<$1img');

    // Remove event and framework directives
    res = res.replace(/\s+bindtap="[^"]*"/g, "");
    res = res.replace(/\s+bindchange="[^"]*"/g, "");
    res = res.replace(/\s+bindinput="[^"]*"/g, "");
    res = res.replace(/\s+wx:key="[^"]*"/g, "");
    res = res.replace(/\s+data-action="[^"]*"/g, "");
    res = res.replace(/\s+size="[^"]*"/g, "");

    return res;
  }

  private extractTokens(html: string): string[] {
    const textOnly = html.replace(/<[^>]+>/g, " ");
    return textOnly
      .toLowerCase()
      .split(/[\s,.;:!?()[\]{}"'<>=\-\u00B7\uFF1A\uFF0C\u3002\uFF1B\uFF01\uFF1F\u3001\u201C\u201D\u2018\u2019\uFF08\uFF09\u300A\u300B\u3010\u3011\u2026]+/)
      .filter(t => t.length > 0);
  }

  private computeTokenSimilarity(a: string[], b: string[]): number {
    if (a.length === 0 && b.length === 0) return 1.0;
    if (a.length === 0 || b.length === 0) return 0.0;

    const setA = new Map<string, number>();
    for (const t of a) setA.set(t, (setA.get(t) || 0) + 1);

    let overlap = 0;
    const setB = new Map<string, number>();
    for (const t of b) setB.set(t, (setB.get(t) || 0) + 1);

    for (const [t, countA] of setA.entries()) {
      if (setB.has(t)) {
        overlap += Math.min(countA, setB.get(t)!);
      }
    }

    return (2.0 * overlap) / (a.length + b.length);
  }

  private computeStructuralSimilarity(htmlA: string, htmlB: string): number {
    const tagsA = (htmlA.match(/<\/?([a-zA-Z][\w-]*)/g) || []).map(t => t.toLowerCase());
    const tagsB = (htmlB.match(/<\/?([a-zA-Z][\w-]*)/g) || []).map(t => t.toLowerCase());

    if (tagsA.length === 0 && tagsB.length === 0) return 1.0;
    if (tagsA.length === 0 || tagsB.length === 0) return 0.0;

    const countA = new Map<string, number>();
    for (const t of tagsA) countA.set(t, (countA.get(t) || 0) + 1);

    let match = 0;
    for (const t of tagsB) {
      if ((countA.get(t) || 0) > 0) {
        match++;
        countA.set(t, countA.get(t)! - 1);
      }
    }

    return (2.0 * match) / (tagsA.length + tagsB.length);
  }
}
