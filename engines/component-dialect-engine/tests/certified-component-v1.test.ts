/**
 * Real, executed tests for certified-component-v1.
 *
 * These are not shape assertions over hand-written fixtures: every test
 * drives the actual framework toolchains -- the TypeScript Compiler API,
 * @vue/compiler-sfc, @wxml/parser -- and the SSR tests really render both
 * components with react-dom/server and @vue/server-renderer and compare
 * the resulting DOM.
 */
import { parseReactComponent } from "../src/parsers/react";
import { parseVue3Component } from "../src/parsers/vue3";
import { emitReact } from "../src/emitters/react";
import { emitVue3 } from "../src/emitters/vue3";
import { emitMiniProgram } from "../src/emitters/miniprogram";
import { validateSyntax } from "../src/validator";
import { compareRendered, defaultExecutionCases, normalizeHtml } from "../src/execution";
import { DialectError } from "../src/models";

const COUNTER_TSX = `
function Counter({ label, step = 1, onDone }: { label: string; step?: number; onDone: (value: number) => void }) {
  const [count, setCount] = useState<number>(0);
  const [busy, setBusy] = useState<boolean>(false);
  return (
    <div className="counter">
      <span>{label}</span>
      <em>{count}</em>
      {step > 3 ? (<strong>big</strong>) : (<strong>small</strong>)}
      <button type="button" disabled={busy} onClick={() => { setCount(count + step); onDone(count); }}>add</button>
    </div>
  );
}
`;

describe("React parsing (real TypeScript Compiler API)", () => {
  it("extracts props, defaults, callbacks, state and the render tree", () => {
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    expect(ir.name).toBe("Counter");
    expect(ir.props).toEqual([
      { kind: "data", name: "label", propType: "string", required: true, defaultValue: undefined },
      { kind: "data", name: "step", propType: "number", required: false, defaultValue: { type: "number", value: 1 } },
      { kind: "callback", name: "onDone", paramType: "number" },
    ]);
    expect(ir.state.map((s) => s.name)).toEqual(["count", "busy"]);
    expect(ir.root.kind).toBe("element");
  });

  it("inlines earlier pure local expressions without widening the target IR", () => {
    const ir = parseReactComponent(`
      function Alias({ name }: { name: string }) {
        const heading = name;
        const display = true ? heading : "unused";
        return (<p>{display}</p>);
      }
    `, "Alias.tsx");
    expect(ir.root.kind).toBe("element");
    const child = ir.root.kind === "element" ? ir.root.children[0] : undefined;
    expect(child).toEqual({
      kind: "text",
      value: {
        kind: "ternary",
        condition: { kind: "literal", literal: { type: "boolean", value: true } },
        then: { kind: "ident", name: "name" },
        else: { kind: "literal", literal: { type: "string", value: "unused" } },
      },
    });
  });

  it("preserves certified string methods and static label-map lookups", () => {
    const ir = parseReactComponent(`
      const labels = { READY: "就绪", BLOCKED: "阻断" };
      function Label({ status }: { status: string }) {
        const normalized = status.toUpperCase();
        return <span aria-hidden={true}>{labels[normalized] ?? status}</span>;
      }
    `, "Label.tsx");
    expect(ir.root).toEqual({
      kind: "element",
      tag: "span",
      attrs: [{ kind: "dynamic", name: "aria-hidden", value: { kind: "literal", literal: { type: "boolean", value: true } } }],
      events: [],
      children: [{
        kind: "text",
        value: {
          kind: "binary",
          operator: "??",
          left: {
            kind: "ternary",
            condition: { kind: "binary", operator: "==", left: { kind: "stringMethod", method: "toUpperCase", receiver: { kind: "ident", name: "status" }, args: [] }, right: { kind: "literal", literal: { type: "string", value: "READY" } } },
            then: { kind: "literal", literal: { type: "string", value: "就绪" } },
            else: {
              kind: "ternary",
              condition: { kind: "binary", operator: "==", left: { kind: "stringMethod", method: "toUpperCase", receiver: { kind: "ident", name: "status" }, args: [] }, right: { kind: "literal", literal: { type: "string", value: "BLOCKED" } } },
              then: { kind: "literal", literal: { type: "string", value: "阻断" } },
              else: { kind: "literal", literal: { type: "null" } },
            },
          },
          right: { kind: "ident", name: "status" },
        },
      }],
    });
    expect(emitReact(ir)).toContain("status.toUpperCase()");
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("vue3", emitVue3(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("retains typed nested object paths and array length reads", () => {
    const ir = parseReactComponent(`
      function Summary({ report }: { report: { totals: { count: number }; items: string[] } }) {
        return <p>{report.totals.count} / {report.items.length}</p>;
      }
    `, "Summary.tsx");
    expect(ir.root.kind).toBe("element");
    const values = ir.root.kind === "element" ? ir.root.children.filter((child) => child.kind === "text").map((child) => child.value) : [];
    expect(values).toEqual([
      { kind: "path", object: "report", fields: ["totals", "count"] },
      { kind: "literal", literal: { type: "string", value: "/" } },
      { kind: "arrayLength", operand: { kind: "member", object: "report", field: "items" } },
    ]);
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });
});

describe("cross-framework round trip", () => {
  it("React -> Vue 3 -> React produces an identical canonical model", () => {
    const first = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const vue = emitVue3(first);
    const second = parseVue3Component(vue, "Counter.vue");
    expect(second).toEqual(first);
  });

  it("re-emitted React is accepted by the real TypeScript parser", () => {
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const report = validateSyntax("react", emitReact(ir));
    expect(report).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("emitted Vue 3 is accepted by the real @vue/compiler-sfc", () => {
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const report = validateSyntax("vue3", emitVue3(ir));
    expect(report).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("emitted WeChat mini program bundle is accepted by the real @wxml/parser", () => {
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const report = validateSyntax("miniprogram", emitMiniProgram(ir));
    expect(report).toEqual({ status: "PASSED", diagnostics: [] });
  });
});

describe("real SSR execution comparison", () => {
  it("React and Vue 3 render identical DOM for the same props", async () => {
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const result = await compareRendered(
      { framework: "react", source: emitReact(ir) },
      { framework: "vue3", source: emitVue3(ir) },
      defaultExecutionCases(ir),
    );
    expect(result).toEqual({ status: "PASSED", diagnostics: [] });
  }, 30000);

  it("detects a real behavioral divergence rather than rubber-stamping it", async () => {
    // A deliberately wrong "translation": the Vue side renders a different
    // element than the React side. If the execution leg were cosmetic this
    // would pass; it must fail.
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const brokenVue = emitVue3(ir).replace("<em>", "<span>").replace("</em>", "</span>");
    const result = await compareRendered(
      { framework: "react", source: emitReact(ir) },
      { framework: "vue3", source: brokenVue },
      defaultExecutionCases(ir),
    );
    expect(result.status).toBe("FAILED");
    expect(result.diagnostics.length).toBeGreaterThan(0);
  }, 30000);
});

describe("WeChat mini program semantics", () => {
  it("maps HTML tags to mini program built-in components", () => {
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const bundle = emitMiniProgram(ir);
    expect(bundle["wxml"]).toContain("<view class=\"counter\">");
    expect(bundle["wxml"]).not.toContain("<div");
    expect(bundle["wxml"]).toContain("bindtap=");
    expect(bundle["wxml"]).toContain("wx:if=");
  });

  it("writes state only through setData, never by assignment", () => {
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const js = emitMiniProgram(ir)["js"] as string;
    expect(js).toContain("this.setData({");
    expect(js).not.toMatch(/this\.data\.\w+\s*=/);
  });

  it("preserves React closure semantics across the synchronous setData boundary", () => {
    // In React, `setCount(count + step); onDone(count)` passes the OLD count.
    // WeChat's setData updates this.data synchronously, so a naive
    // transliteration would pass the NEW count. The emitter must snapshot.
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const js = emitMiniProgram(ir)["js"] as string;
    expect(js).toContain("const count$0 = this.data.count;");
    expect(js).toContain("this.triggerEvent(\"done\", { value: count$0 });");
  });
});

describe("fail-closed behavior outside certified-component-v1", () => {
  const cases: [string, string][] = [
    ["array state", `function C() { const [x, setX] = useState<number[]>([]); return (<div>{x}</div>); }`],
    ["unsupported hook", `function C() { useEffect(() => {}, []); return (<div>hi</div>); }`],
    ["unsupported tag", `function C() { return (<video>hi</video>); }`],
    ["unsupported attribute", `function C() { return (<div data-tracking="x">hi</div>); }`],
    ["spread props", `function C(props: { a: string }) { return (<div {...props}>hi</div>); }`],
    ["unsupported method call in expression", `function C({ a }: { a: string }) { return (<div>{a.includes("x")}</div>); }`],
    ["two components in one file", `function A() { return (<div>a</div>); } function B() { return (<div>b</div>); }`],
    ["untyped props", `function C(props) { return (<div>hi</div>); }`],
    ["handler with a loop", `function C() { const [x, setX] = useState<number>(0); return (<button onClick={() => { for (;;) {} }}>go</button>); }`],
    ["non-literal useState", `function C({ a }: { a: number }) { const [x, setX] = useState<number>(a); return (<div>{x}</div>); }`],
    ["forward local read", `function C({ a }: { a: number }) { const b = a + c; const c = a + 1; return (<div>{b}</div>); }`],
    ["cyclic local read", `function C({ a }: { a: number }) { const b = c; const c = b; return (<div>{b}</div>); }`],
  ];

  it.each(cases)("blocks %s instead of guessing", (_name, source) => {
    expect(() => parseReactComponent(source, "C.tsx")).toThrow(DialectError);
  });

  it("blocks a Vue SFC that uses the Options API rather than <script setup>", () => {
    const sfc = `<script>export default { data() { return { x: 1 }; } }</script>\n<template><div>{{ x }}</div></template>`;
    expect(() => parseVue3Component(sfc, "C.vue")).toThrow(DialectError);
  });

  it("blocks a Vue template with multiple root elements", () => {
    const sfc = `<script setup lang="ts">\n</script>\n<template><div>a</div><div>b</div></template>`;
    expect(() => parseVue3Component(sfc, "C.vue")).toThrow(DialectError);
  });

  it("carries a machine-readable reason code on every block", () => {
    try {
      parseReactComponent(`function C() { return (<video>hi</video>); }`, "C.tsx");
      throw new Error("expected a DialectError");
    } catch (error) {
      expect(error).toBeInstanceOf(DialectError);
      expect((error as DialectError).code).toBe("CERTIFIED_COMPONENT_UNSUPPORTED_TAG");
    }
  });
});

describe("html normalization used by the execution leg", () => {
  it("ignores comment markers and attribute order but not content", () => {
    expect(normalizeHtml(`<!--[--><div b="2" a="1">x</div><!--]-->`)).toBe(normalizeHtml(`<div a="1" b="2">x</div>`));
    expect(normalizeHtml(`<div>x</div>`)).not.toBe(normalizeHtml(`<div>y</div>`));
    expect(normalizeHtml(`<div a="1">x</div>`)).not.toBe(normalizeHtml(`<div a="2">x</div>`));
  });
});
